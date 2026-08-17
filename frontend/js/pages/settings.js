"use strict";

/* llama-monitor — settings page: executable, models root, panel ports */

const Settings = {
  init() {
    document.getElementById("btn-save-settings").addEventListener("click", () => this.save());
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
    } catch (e) {
      UI.toast(`failed to load settings: ${e}`, "err");
    }
  },

  async save() {
    const body = {
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
