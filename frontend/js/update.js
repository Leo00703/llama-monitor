"use strict";

/* llama-monitor — update toast (bottom-right): one-click update + restart */

const Update = (() => {
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
  let currentSha = "";
  let dismissedSha = "";
  let busy = false;

  // Restart chain on the panel host (old process exit → bootstrap merge →
  // relaunch, where the onefile exe re-extracts its bundle, antivirus
  // included) can take a few minutes — budget accordingly.
  const RESTART_TIMEOUT_MS = 300000;
  const SLOW_HINT_AFTER_S = 45;

  const toast = () => document.getElementById("update-toast");
  const btn = () => document.getElementById("update-toast-apply");
  const overlay = () => document.getElementById("update-overlay");
  const statusEl = () => document.getElementById("update-modal-status");

  function openModal({ title, status, spinner = true, error = false, closable = false }) {
    document.getElementById("update-modal-title").textContent = title;
    const st = document.getElementById("update-modal-status");
    st.textContent = status;
    if (error) st.setAttribute("data-error", ""); else st.removeAttribute("data-error");
    document.getElementById("update-modal-spinner").hidden = !spinner;
    document.getElementById("update-modal-close").hidden = !closable;
    overlay().hidden = false;
  }

  function closeModal() {
    overlay().hidden = true;
    // an update is still pending → let the user retry from the toast
    if (currentSha) toast().classList.remove("hidden");
  }

  async function healthUp() {
    // Bounded probe: a hung TCP connection (e.g. a firewall dropping
    // packets to the dead port) must not eat the restart wait budget.
    const ctrl = new AbortController();
    const timer = setTimeout(() => ctrl.abort(), 4000);
    try {
      await fetch("/api/health", {
        signal: ctrl.signal,
        headers: { Accept: "application/json" },
      });
      return true;
    } catch (_) {
      return false;
    } finally {
      clearTimeout(timer);
    }
  }

  function fill(data) {
    const box = document.getElementById("update-toast-commits");
    box.textContent = "";
    const head = document.createElement("div");
    head.className = "update-toast-count";
    head.textContent = data.behind > 1 ? `${data.behind} new commits` : "1 new commit";
    box.appendChild(head);
    for (const c of (data.commits || []).slice(0, 3)) {
      const div = document.createElement("div");
      div.className = "update-toast-commit";
      div.textContent = `${c.sha} ${c.subject}`;
      box.appendChild(div);
    }
  }

  function maybeShow(data) {
    if (!data || data.behind <= 0) return;
    const sha = (data.latest || {}).sha || "";
    if (sha && sha === dismissedSha) return; // dismissed until a newer commit
    currentSha = sha;
    fill(data);
    toast().classList.remove("hidden");
  }

  async function check(force = false) {
    try {
      const data = await API.get(`/api/update/check${force ? "?force=true" : ""}`);
      maybeShow(data);
      return data;
    } catch (_) {
      return null;
    }
  }

  async function waitPanelBack(timeoutMs = RESTART_TIMEOUT_MS, onTick = null) {
    // The old panel dies (port closes) before the new one binds: wait for
    // the up → down → up transition.
    const t0 = Date.now();
    let up = await healthUp();
    while (Date.now() - t0 < timeoutMs) {
      await sleep(1000);
      const now = await healthUp();
      if (onTick) onTick(Math.floor((Date.now() - t0) / 1000));
      if (up && now) continue; // still the old panel
      if (!up && !now) continue; // gap: new panel not up yet
      up = now;
      if (now) { await sleep(1500); return true; }
    }
    return false;
  }

  async function apply() {
    if (busy) return;
    busy = true;
    toast().classList.add("hidden");
    openModal({ title: "Updating llama-monitor…", status: "Applying update (git fast-forward)" });
    let resp = null;
    try {
      resp = await API.post("/api/update/apply");
    } catch (_) {
      // expected: the server shuts down and may drop the response
    }
    if (resp && resp.ok === false) {
      busy = false;
      openModal({ title: "Update failed", status: resp.error || "update failed", spinner: false, error: true, closable: true });
      return;
    }
    if (resp && resp.restarting === false) {
      // dev mode: pulled, but no auto-restart hook
      busy = false;
      openModal({ title: "Update pulled", status: resp.note || "restart the panel to finish the update", spinner: false, closable: true });
      return;
    }
    openModal({
      title: "Updating llama-monitor…",
      status: "Restarting the panel — it reopens automatically",
      closable: true, // first launch after an update can be slow — allow bail-out
    });
    const ok = await waitPanelBack(RESTART_TIMEOUT_MS, (s) => {
      const base = `Restarting the panel — it reopens automatically · ${s}s`;
      statusEl().textContent = s > SLOW_HINT_AFTER_S
        ? `${base} — first launch after an update is slow (the panel re-extracts its bundle); keep waiting`
        : base;
    });
    if (ok) location.reload();
    else {
      busy = false;
      openModal({
        title: "Update finished",
        status: "the panel did not come back in time — if it runs on another machine, check that machine: the update helper's outcome is in update-result.txt in the data folder (e.g. %APPDATA%\\llama-monitor), and a 'Failed to remove temporary directory' dialog on that machine may still need dismissing; reload once the panel is back",
        spinner: false,
        error: true,
        closable: true,
      });
    }
  }

  function init() {
    document.getElementById("update-toast-close").addEventListener("click", () => {
      dismissedSha = currentSha;
      toast().classList.add("hidden");
    });
    btn().addEventListener("click", apply);
    document.getElementById("update-modal-close").addEventListener("click", closeModal);
    check(false); // initial check on load
    // Surface the outcome of a deferred update from the previous launch:
    // the bootstrap bat merged the repo after the old panel exited and
    // relaunched this instance, and left its result in update-result.txt.
    API.get("/api/update/result")
      .then((r) => {
        const res = r && r.result;
        if (!res) return;
        if (res.ok) UI.toast(`panel updated to ${res.sha || "the latest version"} — you're running the new build`, "ok");
        else UI.toast(`update failed: ${res.error}`, "err");
      })
      .catch(() => {});
  }

  return { init, check, apply, maybeShow };
})();
