"use strict";

/* llama-monitor — settings page: executable, models root, panel ports */

const Settings = {
  init() {
    document.getElementById("btn-save-settings").addEventListener("click", () => this.save());
    document.getElementById("btn-check-updates").addEventListener("click", async () => {
      const b = document.getElementById("btn-check-updates");
      const label = b.textContent;
      b.disabled = true;
      b.textContent = "Checking…";
      let d = null;
      try {
        d = await Update.check(true); // fetches + shows the update toast if behind
        await this.refreshUpdateStatus(true, d);
        if (!d) UI.toast("update check failed", "err");
        else if (d.behind > 0) UI.toast(`${d.behind} new commit${d.behind > 1 ? "s" : ""} available`, "ok");
        else if (d.error) UI.toast(`update check failed: ${d.error}`, "err");
        else if (!d.git) UI.toast("git is not installed — auto-updates unavailable", "err");
        else if (!d.repo) UI.toast("not running from a git checkout — auto-updates unavailable", "err");
        else UI.toast("✓ You're up to date", "ok");
      } finally {
        b.disabled = false;
        b.textContent = label;
      }
    });
    document.getElementById("btn-apply-update").addEventListener("click", async () => {
      await Update.apply();
      this.refreshUpdateStatus(true);
    });
    this.load();
  },

  async load() {
    try {
      const cfg = await API.get("/api/config");
      document.getElementById("set-exe").value = cfg.llama_server_exe || "";
      document.getElementById("set-root").value = cfg.models_root || "";
      document.getElementById("set-port").value = cfg.default_server_port || 8080;
      const panel = cfg.panel || {};
      document.getElementById("set-phost").value = panel.host || "0.0.0.0";
      document.getElementById("set-pport").value = panel.port || 8000;
      document.getElementById("set-energy-price").value = cfg.energy_price_eur_kwh ?? 0.2;
      document.getElementById("set-energy-overhead").value = cfg.energy_overhead_w ?? 0;
      document.getElementById("set-datadir").textContent = cfg.data_dir
        ? `Data (config, presets, analytics history) is stored in: ${cfg.data_dir}`
        : "";
      document.getElementById("set-update-interval").value = String(cfg.update_check_minutes ?? 5);
    } catch (e) {
      UI.toast(`failed to load settings: ${e}`, "err");
    }
    this.refreshUpdateStatus();
  },

  async refreshUpdateStatus(force = false, data = null) {
    const ver = document.getElementById("set-app-version");
    const status = document.getElementById("set-update-status");
    const applyBtn = document.getElementById("btn-apply-update");
    try {
      const d = data || await API.get(`/api/update/check${force ? "?force=true" : ""}`);
      const dirtyList = (paths, n = 3) => (paths || []).slice(0, n).join(", ") + ((paths || []).length > n ? "…" : "");
      const cur = d.current || {};
      const when = cur.date ? " · " + cur.date.replace("T", " ").slice(0, 16) : "";
      ver.textContent = cur.sha
        ? `${cur.sha} (${cur.source === "build" ? "build" : "dev"}${when})`
        : "unknown";
      if (!d.git) {
        status.textContent = "git is not installed — auto-updates are unavailable.";
        applyBtn.disabled = true;
      } else if (!d.repo) {
        status.textContent = "Not running from a git checkout — auto-updates are unavailable (the bundled exe must live in the repository).";
        applyBtn.disabled = true;
      } else if (d.error) {
        status.textContent = `Update check failed: ${d.error}`;
        applyBtn.disabled = true;
      } else if (d.behind > 0) {
        const issues = [];
        if (d.dirty) issues.push(`local changes: ${dirtyList(d.dirty_paths)}`);
        if (d.ahead > 0) issues.push(`${d.ahead} local commit(s) to push`);
        status.textContent = `${d.behind} commit${d.behind > 1 ? "s" : ""} behind origin${issues.length ? " — " + issues.join(", ") : ""}`;
        applyBtn.disabled = issues.length > 0;
      } else {
        const notes = [];
        if (d.ahead > 0) notes.push(`${d.ahead} local commit(s) to push`);
        if (d.dirty) notes.push(`local changes: ${dirtyList(d.dirty_paths)}`);
        const base = d.origin
          ? `Up to date (${(d.latest || {}).sha || "HEAD"})`
          : "Up to date";
        status.textContent = notes.length
          ? `${base} — ${notes.join(", ")}`
          : d.origin ? `${base} · ${d.origin}` : base;
        applyBtn.disabled = true;
      }
    } catch (_) {
      status.textContent = "Update check unavailable.";
      applyBtn.disabled = true;
    }
  },

  async save() {
    const body = {
      update_check_minutes: parseInt(document.getElementById("set-update-interval").value, 10) || 0,
      llama_server_exe: document.getElementById("set-exe").value.trim(),
      models_root: document.getElementById("set-root").value.trim(),
      default_server_port: parseInt(document.getElementById("set-port").value, 10) || 8080,
      panel: {
        host: document.getElementById("set-phost").value.trim() || "0.0.0.0",
        port: parseInt(document.getElementById("set-pport").value, 10) || 8000,
      },
      energy_price_eur_kwh: parseFloat(document.getElementById("set-energy-price").value) || 0,
      energy_overhead_w: parseFloat(document.getElementById("set-energy-overhead").value) || 0,
    };
    try {
      const res = await API.post("/api/config", body);
      if (!res.ok) { UI.toast(res.error || "save failed", "err"); return; }
      UI.toast("settings saved");
    } catch (e) {
      UI.toast(`save failed: ${e}`, "err");
    }
  },
};
