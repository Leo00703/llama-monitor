"use strict";

/* llama-monitor — dashboard page: preset picker, flag preview, server log */

const Dashboard = {
  presets: [],
  activeId: "",
  selectedId: "",

  init() {
    document.getElementById("preset-select").addEventListener("change", (e) => {
      this.selectedId = e.target.value;
      this.updateSummary();
    });
    document.getElementById("btn-preview").addEventListener("click", () => this.preview());
    this.refreshPresets();
  },

  async refreshPresets() {
    try {
      const data = await API.get("/api/presets");
      this.presets = data.presets || [];
      this.activeId = data.active_id || "";
      this.populateSelect();
      this.updateSummary();
    } catch (e) {
      UI.toast(`failed to load presets: ${e}`, "err");
    }
  },

  populateSelect() {
    const sel = document.getElementById("preset-select");
    const keep = sel.value || this.selectedId;
    sel.innerHTML = "";
    if (!this.presets.length) {
      const opt = document.createElement("option");
      opt.value = "";
      opt.textContent = "(no presets — create one)";
      sel.appendChild(opt);
      sel.disabled = true;
      this.selectedId = "";
      return;
    }
    sel.disabled = false;
    for (const p of this.presets) {
      const opt = document.createElement("option");
      opt.value = p.id;
      opt.textContent = p.name;
      sel.appendChild(opt);
    }
    const preferred = this.presets.some((p) => p.id === keep) ? keep
      : this.presets.some((p) => p.id === this.activeId) ? this.activeId
      : this.presets[0].id;
    sel.value = preferred;
    this.selectedId = preferred;
  },

  updateSummary() {
    const el = document.getElementById("preset-summary");
    const p = this.presets.find((x) => x.id === this.selectedId);
    if (!p) {
      el.textContent = "";
      return;
    }
    const bits = [];
    if (p.model) bits.push(p.model);
    if (p.alias) bits.push(`alias: ${p.alias}`);
    bits.push(`ctx: ${p.context_size}`);
    bits.push(`ngl: ${p.n_gpu_layers}`);
    if (p.spec_type && p.spec_type !== "none") bits.push(`spec: ${p.spec_type}`);
    bits.push(`port: ${p.port}`);
    bits.push(`updated: ${UI.timeAgo(p.updated_at)}`);
    el.innerHTML = bits.map(UI.esc).join(" &nbsp;·&nbsp; ");
  },

  async preview() {
    const btn = document.getElementById("btn-preview");
    const pre = document.getElementById("flag-preview");
    // toggle off: just hide (a re-show re-fetches, so the command stays fresh)
    if (!pre.classList.contains("hidden")) {
      pre.classList.add("hidden");
      btn.textContent = "Preview launch command";
      return;
    }
    if (!this.selectedId) {
      UI.toast("select a preset first", "err");
      return;
    }
    try {
      const res = await API.post(`/api/presets/${this.selectedId}/preview`);
      pre.textContent = res.args.map(UI.quoteForDisplay).join(" ") || "(no flags)";
      pre.classList.remove("hidden");
      btn.textContent = "Hide launch command";
      if (res.errors && res.errors.length) {
        UI.banner(document.getElementById("launch-banner"), "err", res.errors);
      } else if (res.warnings && res.warnings.length) {
        UI.banner(document.getElementById("launch-banner"), "warn", res.warnings);
      } else {
        UI.clearBanner(document.getElementById("launch-banner"));
      }
    } catch (e) {
      UI.toast(`preview failed: ${e}`, "err");
    }
  },

  /** Show warnings returned by start/restart on the dashboard banner. */
  showLaunchResult(res) {
    if (res.warnings && res.warnings.length) {
      UI.banner(document.getElementById("launch-banner"), "warn", res.warnings);
    } else {
      UI.clearBanner(document.getElementById("launch-banner"));
    }
  },

  clearLaunchResult() {
    UI.clearBanner(document.getElementById("launch-banner"));
  },
};
