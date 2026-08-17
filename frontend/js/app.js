"use strict";

/* llama-monitor — app shell: routing, topbar state, WebSocket log stream */

const $ = (id) => document.getElementById(id);

const badge = $("status-badge");
const statusText = $("status-text");
const hostBadge = $("host-badge");
const errorLabel = $("error-label");
const versionLabel = $("version-label");
const logEl = $("log");
const autoscrollEl = $("autoscroll");
const btnStart = $("btn-start");
const btnStop = $("btn-stop");
const btnRestart = $("btn-restart");

const MAX_DOM_LINES = 2000;

let serverState = "stopped";
let busy = false;

const STATE_LABELS = {
  stopped: "stopped",
  starting: "starting",
  running: "running",
  restarting: "restarting",
  error: "error",
  external: "external",
};

/* ---------------------------------------------------------------- */
/* routing                                                           */
/* ---------------------------------------------------------------- */

const PAGES = ["dashboard", "generation", "presets", "models", "settings"];

function showPage(name) {
  for (const p of PAGES) {
    $(`page-${p}`).classList.toggle("hidden", p !== name);
  }
  document.querySelectorAll(".nav-item").forEach((el) => {
    el.classList.toggle("active", el.dataset.page === name);
  });
  if (name === "generation") Generation.refresh();
  if (name === "models") Models.refresh();
}

document.querySelectorAll(".nav-item").forEach((el) => {
  el.addEventListener("click", () => showPage(el.dataset.page));
});

/* ---------------------------------------------------------------- */
/* sidebar (collapsible)                                             */
/* ---------------------------------------------------------------- */

const sidebar = $("sidebar");
const btnSidebar = $("btn-sidebar");

function setSidebarCollapsed(collapsed) {
  sidebar.classList.toggle("collapsed", collapsed);
  btnSidebar.setAttribute("aria-expanded", String(!collapsed));
  try { localStorage.setItem("lm.sidebar.collapsed", collapsed ? "1" : "0"); } catch (_) {}
}

btnSidebar.addEventListener("click", () => setSidebarCollapsed(!sidebar.classList.contains("collapsed")));
try { if (localStorage.getItem("lm.sidebar.collapsed") === "1") setSidebarCollapsed(true); } catch (_) {}

/* ---------------------------------------------------------------- */
/* log rendering                                                     */
/* ---------------------------------------------------------------- */

function appendLogLine(line) {
  const div = document.createElement("div");
  if (line.startsWith("[panel]")) div.className = "panel-line";
  div.textContent = line;
  logEl.appendChild(div);
  while (logEl.children.length > MAX_DOM_LINES) logEl.removeChild(logEl.firstChild);
  if (autoscrollEl.checked) logEl.scrollTop = logEl.scrollHeight;
}

function renderLog(lines) {
  logEl.textContent = "";
  for (const line of lines) appendLogLine(line);
  logEl.scrollTop = logEl.scrollHeight;
}

/* ---------------------------------------------------------------- */
/* state / UI updates                                                */
/* ---------------------------------------------------------------- */

function setHost(online) {
  hostBadge.classList.toggle("offline", !online);
  hostBadge.title = online ? "host online" : "host unreachable";
}

function applyState(state) {
  serverState = state.state;
  const label = STATE_LABELS[serverState] || serverState;
  statusText.textContent = label;
  badge.className = `badge badge-${serverState}`;
  errorLabel.textContent = state.error || "";
  versionLabel.textContent = state.version ? `llama-server ${state.version}` : "";

  const running = serverState === "running" || serverState === "external";
  const starting = serverState === "starting" || serverState === "restarting";
  btnStart.disabled = busy || running || starting;
  btnStop.disabled = busy || serverState === "stopped" || starting;
  btnRestart.disabled = busy || starting || serverState === "stopped";
}

async function refreshState() {
  try {
    const state = await API.get("/api/state");
    applyState(state);
    setHost(true);
  } catch (_) {
    statusText.textContent = "offline";
    badge.className = "badge badge-error";
    setHost(false);
  }
}

function setBusy(b) {
  busy = b;
  btnStart.disabled = b || btnStart.disabled;
  btnStop.disabled = b || btnStop.disabled;
  btnRestart.disabled = b || btnRestart.disabled;
  if (!b) applyState({ state: serverState, error: errorLabel.textContent, version: "" });
}

/* ---------------------------------------------------------------- */
/* actions (preset-driven)                                           */
/* ---------------------------------------------------------------- */

function selectedPresetId() {
  return Dashboard.selectedId;
}

function requirePreset() {
  if (!selectedPresetId()) {
    UI.toast("create a preset first (Presets page)", "err");
    showPage("presets");
    return false;
  }
  return true;
}

async function doStart() {
  if (!requirePreset()) return;
  setBusy(true);
  try {
    const res = await API.post("/api/server/start", { preset_id: selectedPresetId() });
    if (res.warnings && res.warnings.length) {
      showPage("dashboard");
      Dashboard.showLaunchResult(res);
    }
    if (!res.ok) {
      appendLogLine(`[panel] start failed: ${res.errors ? res.errors.join("; ") : res.error}`);
      applyState({ state: "error", error: res.error || (res.errors || []).join("; "), version: versionLabel.textContent });
    }
  } catch (e) {
    appendLogLine(`[panel] start failed: ${e}`);
  } finally {
    setBusy(false);
    refreshState();
    Dashboard.refreshPresets();
  }
}

async function doStop() {
  setBusy(true);
  try {
    await API.post("/api/server/stop");
  } catch (e) {
    appendLogLine(`[panel] stop failed: ${e}`);
  } finally {
    setBusy(false);
    refreshState();
  }
}

async function doRestart() {
  if (!requirePreset()) return;
  setBusy(true);
  try {
    const res = await API.post("/api/server/restart", { preset_id: selectedPresetId() });
    if (res.warnings && res.warnings.length) {
      showPage("dashboard");
      Dashboard.showLaunchResult(res);
    }
    if (!res.ok) appendLogLine(`[panel] restart failed: ${res.error || (res.errors || []).join("; ")}`);
  } catch (e) {
    appendLogLine(`[panel] restart failed: ${e}`);
  } finally {
    setBusy(false);
    refreshState();
    Dashboard.refreshPresets();
  }
}

/* ---------------------------------------------------------------- */
/* websocket                                                         */
/* ---------------------------------------------------------------- */

API.connect("/ws/logs", (event) => {
  if (event.type === "init") {
    renderLog(event.lines || []);
    applyState(event.state || {});
    setHost(true);
  } else if (event.type === "log") {
    appendLogLine(event.line);
  } else if (event.type === "state") {
    applyState(event);
    if (!$("page-generation").classList.contains("hidden")) Generation.refresh();
  } else if (event.type === "metrics") {
    Metrics.update(event.data);
  }
});

/* ---------------------------------------------------------------- */
/* wiring                                                            */
/* ---------------------------------------------------------------- */

btnStart.addEventListener("click", doStart);
btnStop.addEventListener("click", doStop);
btnRestart.addEventListener("click", doRestart);

$("btn-toggle-log").addEventListener("click", () => {
  const card = $("btn-toggle-log").closest(".log-card");
  const collapsed = card.classList.toggle("collapsed");
  $("btn-toggle-log").textContent = collapsed ? "Show" : "Hide";
});

async function copyText(text) {
  if (navigator.clipboard && window.isSecureContext) {
    await navigator.clipboard.writeText(text);
    return true;
  }
  // plain-HTTP fallback (panel served over http://<lan-ip>:8000)
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
}

$("btn-copy-log").addEventListener("click", async () => {
  const lines = logEl.children.length;
  if (!lines) { UI.toast("log is empty", "err"); return; }
  const ok = await copyText(logEl.innerText);
  UI.toast(ok ? `copied ${lines} log lines` : "clipboard copy failed", ok ? "ok" : "err");
});

Dashboard.init();
Models.init();
Generation.init();
Presets.init();
Settings.init();
Metrics.init();

refreshState();
setInterval(refreshState, 10000);
