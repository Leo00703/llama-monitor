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
// last non-empty server version: re-applies (setBusy) carry it through so
// the top-bar label doesn't blink empty between an action and the next
// state event
let lastVersion = "";

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

const PAGES = ["dashboard", "generation", "presets", "models", "analytics", "settings"];

function showPage(name) {
  for (const p of PAGES) {
    $(`page-${p}`).classList.toggle("hidden", p !== name);
  }
  document.querySelectorAll(".nav-item").forEach((el) => {
    el.classList.toggle("active", el.dataset.page === name);
  });
  if (name === "generation") Generation.refresh();
  if (name === "models") Models.refresh();
  if (name === "analytics") Analytics.refresh();
}

document.querySelectorAll(".nav-item").forEach((el) => {
  el.addEventListener("click", () => { showPage(el.dataset.page); closeDrawer(); });
});

/* ---------------------------------------------------------------- */
/* sidebar (collapsible on desktop, off-canvas drawer on mobile)     */
/* ---------------------------------------------------------------- */

const sidebar = $("sidebar");
const btnSidebar = $("btn-sidebar");
const btnCollapse = $("btn-collapse");
const navOverlay = $("nav-overlay");
const mobileQuery = window.matchMedia("(max-width: 900px)");

function setSidebarCollapsed(collapsed) {
  sidebar.classList.toggle("collapsed", collapsed);
  btnCollapse.setAttribute("aria-expanded", String(!collapsed));
  btnCollapse.setAttribute("aria-label", collapsed ? "Expand sidebar" : "Collapse sidebar");
  btnCollapse.setAttribute("title", collapsed ? "Expand sidebar" : "Collapse sidebar");
  try { localStorage.setItem("lm.sidebar.collapsed", collapsed ? "1" : "0"); } catch (_) {}
}

function openDrawer() {
  sidebar.classList.add("open");
  navOverlay.classList.remove("hidden");
  document.body.classList.add("nav-locked");
  btnSidebar.setAttribute("aria-expanded", "true");
}

function closeDrawer() {
  if (!sidebar.classList.contains("open")) return;
  sidebar.classList.remove("open");
  navOverlay.classList.add("hidden");
  document.body.classList.remove("nav-locked");
  btnSidebar.setAttribute("aria-expanded", "false");
}

btnSidebar.addEventListener("click", () => {
  if (sidebar.classList.contains("open")) closeDrawer();
  else openDrawer();
});

btnCollapse.addEventListener("click", () => {
  setSidebarCollapsed(!sidebar.classList.contains("collapsed"));
});

navOverlay.addEventListener("click", closeDrawer);
$("btn-sidebar-close").addEventListener("click", closeDrawer);
window.addEventListener("keydown", (e) => { if (e.key === "Escape") closeDrawer(); });
mobileQuery.addEventListener("change", (e) => { if (!e.matches) closeDrawer(); });

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
  if (state.version) lastVersion = state.version;
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
  if (!b) {
    // only carry the version while a server is actually up — after a stop
    // the label must stay empty (there is no running version to show)
    const alive = serverState === "running" || serverState === "external" ||
      serverState === "starting" || serverState === "restarting";
    applyState({ state: serverState, error: errorLabel.textContent, version: alive ? lastVersion : "" });
  }
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
      applyState({ state: "error", error: res.error || (res.errors || []).join("; "), version: lastVersion });
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
  } else if (event.type === "update.available") {
    Update.maybeShow(event.data);
  } else if (event.type === "llama.update.available" ||
             event.type === "llama.update.progress" ||
             event.type === "llama.update.downloaded") {
    Backend.onWs(event);
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
Backend.init();
Analytics.init();
Metrics.init();
Update.init();

refreshState();
setInterval(refreshState, 10000);
