"use strict";

/* llama-monitor — shared UI helpers */

const UI = {
  esc(s) {
    return String(s ?? "").replace(/[&<>"']/g, (ch) => ({
      "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
    }[ch]));
  },

  /** Show a banner inside a container element. type: "warn" | "err" */
  banner(container, type, lines) {
    container.innerHTML = "";
    if (!lines || !lines.length) return;
    const div = document.createElement("div");
    div.className = `banner banner-${type}`;
    div.innerHTML = lines.map((l) => `<div>${UI.esc(l)}</div>`).join("");
    container.appendChild(div);
  },

  clearBanner(container) {
    container.innerHTML = "";
  },

  toast(msg, kind = "ok") {
    const el = document.getElementById("toast");
    el.textContent = msg;
    el.className = `toast toast-${kind}`;
    clearTimeout(UI._toastTimer);
    UI._toastTimer = setTimeout(() => el.classList.add("hidden"), 2800);
  },

  timeAgo(ts) {
    if (!ts) return "";
    const s = Math.max(0, Math.floor(Date.now() / 1000 - ts));
    if (s < 10) return "just now";
    if (s < 60) return `${s}s ago`;
    if (s < 3600) return `${Math.floor(s / 60)}m ago`;
    if (s < 86400) return `${Math.floor(s / 3600)}h ago`;
    return `${Math.floor(s / 86400)}d ago`;
  },

  /** Shell-style quoting for display: quote tokens containing spaces. */
  quoteForDisplay(token) {
    if (token && /[\s"]/.test(token)) {
      return `"${token.replace(/"/g, '\\"')}"`;
    }
    return token;
  },

  /** Copy text to the clipboard. navigator.clipboard when available,
      execCommand fallback for plain-HTTP LAN installs. */
  async copyText(text) {
    if (navigator.clipboard && window.isSecureContext) {
      try {
        await navigator.clipboard.writeText(text);
        return true;
      } catch (_) {
        /* clipboard API blocked (permissions/permissions prompt) — try the legacy path */
      }
    }
    const ta = document.createElement("textarea");
    ta.value = text;
    ta.style.position = "fixed";
    ta.style.opacity = "0";
    document.body.appendChild(ta);
    ta.select();
    let ok = false;
    try { ok = document.execCommand("copy"); } catch (_) { ok = false; }
    ta.remove();
    return ok;
  },

  /** "8,16" -> [8,16] (tolerant) */
  parseIntList(raw) {
    if (!raw || !raw.trim()) return [];
    return raw.split(",").map((x) => x.trim()).filter(Boolean).map(Number).filter((n) => !Number.isNaN(n));
  },

  intOrEmpty(v) {
    return v && v > 0 ? v : "";
  },
};
