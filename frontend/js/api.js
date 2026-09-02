"use strict";

/* Every request is timeout-bounded (default 20 s): an unbounded fetch is
   what turned a busy/slow panel into a frozen, unresponsive page (#57).
   Slow-by-design endpoints pass a longer timeout explicitly. */
const API_TIMEOUT = 20000;

function request(path, init = {}, timeout = API_TIMEOUT) {
  const ctrl = new AbortController();
  const t = setTimeout(() => ctrl.abort(), timeout);
  return fetch(path, { ...init, signal: ctrl.signal })
    .then((res) => res.json())
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
      ws = new WebSocket(`${proto}://${location.host}${path}`);
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
