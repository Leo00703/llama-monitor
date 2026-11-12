"use strict";

/* Every request is timeout-bounded (default 20 s): an unbounded fetch is
   what turned a busy/slow panel into a frozen, unresponsive page (#57).
   Slow-by-design endpoints pass a longer timeout explicitly. */
const API_TIMEOUT = 20000;

/* Optional panel token (#92): stored once entered after the first 401,
   sent as X-Panel-Token on every call and as ?token= on the WebSocket
   (a browser WebSocket cannot set headers). */
const TOKEN_KEY = "lm.panel.token";

function panelToken() {
  try { return localStorage.getItem(TOKEN_KEY) || ""; } catch (_) { return ""; }
}

function authHeaders(base) {
  const headers = { ...(base || {}) };
  const t = panelToken();
  if (t) headers["X-Panel-Token"] = t;
  return headers;
}

/* (#127) Remember a dismissed token prompt for the rest of the page
   session: /api/state polls every 10 s, and without this the dismissed
   dialog re-fired forever ("close this dialog to keep browsing
   read-only" actually has to mean that). Re-armed by any non-401
   response — the panel answering without the gate means a token is
   available (or no longer needed) again. */
let tokenPromptDismissed = false;

function unauthorizedError(path) {
  const err = new Error(`401 unauthorized — panel token required (${path})`);
  err.unauthorized = true; // refreshState shows "locked" instead of "offline"
  return err;
}

/* A response is parsed as JSON when it is valid JSON (regardless of HTTP
   status — the token gate, request guard and proxy all return
   {"ok": false, "error": ...} on non-2xx and callers read that body); a
   non-JSON body (plain-text 500, reverse-proxy HTML error page, captive
   portal) becomes a clear "HTTP <code> <path>" error instead of the cryptic
   "Unexpected token '<'" SyntaxError from res.json() (#105). */
async function parseBody(res, path) {
  const text = await res.text();
  if (!text) {
    if (res.ok) return {};
    throw new Error(`HTTP ${res.status} ${res.statusText || ""} — empty response (${path})`.trim());
  }
  try {
    return JSON.parse(text);
  } catch (_) {
    const snippet = text.trim().slice(0, 120).replace(/\s+/g, " ");
    throw new Error(`HTTP ${res.status} ${res.statusText || ""} on ${path}: ${snippet}`.trim());
  }
}

function request(path, init = {}, timeout = API_TIMEOUT, retried = false) {
  const ctrl = new AbortController();
  const t = setTimeout(() => ctrl.abort(), timeout);
  return fetch(path, { ...init, headers: authHeaders(init.headers), signal: ctrl.signal })
    .then((res) => {
      if (res.status === 401) {
        // Never resolve the token gate's {"ok": false, ...} body as if it
        // were data (#127): callers rendered it (literal "undefined" status
        // badge, enabled buttons) or ran .map() on it. Throw so their
        // existing error paths take over.
        if (!retried && !tokenPromptDismissed) {
          const typed = window.prompt(
            "This panel is token-protected (#92).\n\nEnter the panel token " +
            "(Settings → Panel token) or close this dialog to keep browsing read-only:");
          if (typed !== null && typed.trim()) {
            try { localStorage.setItem(TOKEN_KEY, typed.trim()); } catch (_) { /* private mode */ }
            return request(path, init, timeout, true);
          }
          tokenPromptDismissed = true; // closed / empty — stop interrupting this session
        }
        throw unauthorizedError(path);
      }
      tokenPromptDismissed = false; // gate answered (authorized or open): re-arm the prompt
      return parseBody(res, path);
    })
    .finally(() => clearTimeout(t));
}

const API = {
  get: (path, timeout) => request(path, { headers: { Accept: "application/json" } }, timeout),

  post(path, body, timeout) {
    return request(path, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: body === undefined ? undefined : JSON.stringify(body),
    }, timeout);
  },

  put(path, body, timeout) {
    return request(path, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }, timeout);
  },

  del: (path, timeout) => request(path, { method: "DELETE" }, timeout),

  /**
   * Connect to a WebSocket with automatic reconnect.
   * @param {string} path e.g. "/ws/logs"
   * @param {(event: object) => void} onEvent
   * @returns {() => void} disconnect function
   */
  connect(path, onEvent) {
    let ws = null;
    let closed = false;
    let timer = null;
    let delay = 1500; // backoff after repeated failures (server down, device sleep)

    function open() {
      if (closed) return;
      const proto = location.protocol === "https:" ? "wss" : "ws";
      const tok = panelToken();
      ws = new WebSocket(`${proto}://${location.host}${path}${tok ? `?token=${encodeURIComponent(tok)}` : ""}`);
      ws.onopen = () => { delay = 1500; };
      ws.onmessage = (e) => {
        try { onEvent(JSON.parse(e.data)); } catch (_) { /* ignore */ }
      };
      ws.onclose = () => {
        ws = null;
        if (!closed) {
          timer = setTimeout(open, delay);
          delay = Math.min(delay * 2, 30000);
        }
      };
      ws.onerror = () => { if (ws) ws.close(); };
    }

    open();
    return () => {
      closed = true;
      if (timer) clearTimeout(timer);
      if (ws) ws.close();
    };
  },
};
