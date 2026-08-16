"use strict";

const API = {
  async get(path) {
    const res = await fetch(path, { headers: { Accept: "application/json" } });
    return res.json();
  },

  async post(path, body) {
    const res = await fetch(path, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: body === undefined ? undefined : JSON.stringify(body),
    });
    return res.json();
  },

  async put(path, body) {
    const res = await fetch(path, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    return res.json();
  },

  async del(path) {
    const res = await fetch(path, { method: "DELETE" });
    return res.json();
  },

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

    function open() {
      if (closed) return;
      const proto = location.protocol === "https:" ? "wss" : "ws";
      ws = new WebSocket(`${proto}://${location.host}${path}`);
      ws.onmessage = (e) => {
        try { onEvent(JSON.parse(e.data)); } catch (_) { /* ignore */ }
      };
      ws.onclose = () => {
        ws = null;
        if (!closed) timer = setTimeout(open, 1500);
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
