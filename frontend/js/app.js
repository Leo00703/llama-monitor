"use strict";

/* llama-monitor — Phase 1 app: server control + live log */

const $ = (id) => document.getElementById(id);

const badge = $("status-badge");
const errorLabel = $("error-label");
const versionLabel = $("version-label");
const logEl = $("log");
const autoscrollEl = $("autoscroll");
const launchArgsEl = $("launch-args");
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

function applyState(state) {
  serverState = state.state;
  const label = STATE_LABELS[serverState] || serverState;
  badge.textContent = label;
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
  } catch (_) {
    badge.textContent = "offline";
    badge.className = "badge badge-error";
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
/* actions                                                           */
/* ---------------------------------------------------------------- */

function parseArgs() {
  const raw = launchArgsEl.value.trim();
  if (!raw) return [];
  const args = [];
  const re = /(?:[^\s"']+|"[^"]*"|'[^']*')+/g;
  let m;
  while ((m = re.exec(raw)) !== null) {
    let token = m[0];
    if ((token.startsWith('"') && token.endsWith('"')) ||
        (token.startsWith("'") && token.endsWith("'"))) {
      token = token.slice(1, -1);
    }
    args.push(token);
  }
  return args;
}

async function doStart() {
  setBusy(true);
  try {
    const res = await API.post("/api/server/start", { args: parseArgs() });
    if (!res.ok) {
      appendLogLine(`[panel] start failed: ${res.error}`);
      applyState({ state: "error", error: res.error, version: versionLabel.textContent });
    }
  } catch (e) {
    appendLogLine(`[panel] start failed: ${e}`);
  } finally {
    setBusy(false);
    refreshState();
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
  setBusy(true);
  try {
    const res = await API.post("/api/server/restart", { args: parseArgs() });
    if (!res.ok) appendLogLine(`[panel] restart failed: ${res.error}`);
  } catch (e) {
    appendLogLine(`[panel] restart failed: ${e}`);
  } finally {
    setBusy(false);
    refreshState();
  }
}

/* ---------------------------------------------------------------- */
/* websocket                                                         */
/* ---------------------------------------------------------------- */

API.connect("/ws/logs", (event) => {
  if (event.type === "init") {
    renderLog(event.lines || []);
    applyState(event.state || {});
  } else if (event.type === "log") {
    appendLogLine(event.line);
  } else if (event.type === "state") {
    applyState(event);
  }
});

/* ---------------------------------------------------------------- */
/* wiring                                                            */
/* ---------------------------------------------------------------- */

btnStart.addEventListener("click", doStart);
btnStop.addEventListener("click", doStop);
btnRestart.addEventListener("click", doRestart);

refreshState();
setInterval(refreshState, 10000);
