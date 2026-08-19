"use strict";

/* llama-monitor — update toast (bottom-right): one-click update + restart */

const Update = (() => {
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
  let currentSha = "";
  let dismissedSha = "";
  let busy = false;

  const toast = () => document.getElementById("update-toast");
  const btn = () => document.getElementById("update-toast-apply");

  async function healthUp() {
    try { await API.get("/api/health"); return true; } catch (_) { return false; }
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

  async function waitPanelBack(timeoutMs = 120000) {
    // The old panel dies (port closes) before the new one binds: wait for
    // the up → down → up transition.
    const t0 = Date.now();
    let up = await healthUp();
    while (Date.now() - t0 < timeoutMs) {
      await sleep(1000);
      const now = await healthUp();
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
    const b = btn();
    b.disabled = true;
    b.textContent = "Updating…";
    let resp = null;
    try {
      resp = await API.post("/api/update/apply");
    } catch (_) {
      // expected: the server shuts down and may drop the response
    }
    if (resp && resp.ok === false) {
      UI.toast(resp.error || "update failed", "err");
      b.textContent = "Update now";
      b.disabled = false;
      busy = false;
      return;
    }
    if (resp && resp.restarting === false) {
      // dev mode: pulled, but no auto-restart hook
      b.textContent = "Update now";
      b.disabled = false;
      busy = false;
      UI.toast(resp.note || "update pulled — restart the panel", "ok");
      return;
    }
    b.textContent = "Restarting…";
    const ok = await waitPanelBack();
    if (ok) location.reload();
    else {
      b.textContent = "Update now";
      b.disabled = false;
      busy = false;
      UI.toast("the panel did not come back in time — reload manually", "err");
    }
  }

  function init() {
    document.getElementById("update-toast-close").addEventListener("click", () => {
      dismissedSha = currentSha;
      toast().classList.add("hidden");
    });
    btn().addEventListener("click", apply);
    check(false); // initial check on load
  }

  return { init, check, apply, maybeShow };
})();
