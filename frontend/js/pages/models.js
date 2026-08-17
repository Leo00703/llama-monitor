"use strict";

/* llama-monitor — models page: GGUF browser + mmproj apply (plan 4.6) */

const Models = {
  models: [],
  root: "",
  selected: "",

  find(path) {
    return this.models.find((m) => m.path === path);
  },

  init() {
    document.getElementById("models-search").addEventListener("input", () => this.render());
    document.getElementById("models-refresh").addEventListener("click", () => this.refresh());
    document.getElementById("models-tbody").addEventListener("click", (e) => {
      const tr = e.target.closest("tr[data-path]");
      if (!tr) return;
      this.selected = tr.dataset.path;
      this.render();
      this.renderDetail();
    });
    document.getElementById("models-apply-model").addEventListener("click", () => this.apply("model"));
    document.getElementById("models-apply-mmproj").addEventListener("click", () => this.apply("mmproj"));
    this.refresh();
  },

  async refresh() {
    try {
      const data = await API.get("/api/models");
      this.models = data.models || [];
      this.root = data.root || "";
    } catch (e) {
      UI.toast(`failed to load models: ${e}`, "err");
    }
    if (!this.find(this.selected)) {
      this.selected = this.models.length ? this.models[0].path : "";
    }
    this.render();
    this.renderDetail();
    if (typeof Presets !== "undefined") Presets.refreshDatalists();
  },

  render() {
    const q = (document.getElementById("models-search").value || "").toLowerCase();
    const tbody = document.getElementById("models-tbody");
    const rows = this.models.filter(
      (m) => !q || m.name.toLowerCase().includes(q) || m.path.toLowerCase().includes(q));
    tbody.innerHTML = rows.map((m) => `
      <tr data-path="${UI.esc(m.path)}" class="${m.path === this.selected ? "selected" : ""}">
        <td>${UI.esc(m.name)}${m.mmproj.length ? ' <span class="chip chip-vision">vision</span>' : ""}</td>
        <td class="muted mono" title="${UI.esc(m.path)}">${UI.esc(m.path)}</td>
        <td>${m.size_mb} MB</td>
        <td class="muted">${UI.timeAgo(m.mtime)}</td>
      </tr>`).join("");
    document.getElementById("models-count").textContent = `${rows.length} / ${this.models.length} files`;
    document.getElementById("models-empty").classList.toggle("hidden", this.models.length > 0);
    document.getElementById("models-root").textContent = this.root ? this.root : "";
  },

  renderDetail() {
    const detail = document.getElementById("models-detail");
    const m = this.find(this.selected);
    if (!m) {
      detail.classList.add("hidden");
      return;
    }
    detail.classList.remove("hidden");
    document.getElementById("md-name").textContent = m.name;
    document.getElementById("md-path").textContent = m.path;
    document.getElementById("md-size").textContent = `${m.size_mb} MB`;
    document.getElementById("md-mtime").textContent = UI.timeAgo(m.mtime);
    document.getElementById("md-mmproj").innerHTML = m.mmproj.length
      ? m.mmproj.map((p) => `<span class="chip chip-vision">${UI.esc(p)}</span>`).join(" ")
      : '<span class="muted small">no mmproj in this folder</span>';
    this.refreshDetailPresetList();
  },

  async refreshDetailPresetList() {
    const sel = document.getElementById("models-preset-select");
    try {
      const data = await API.get("/api/presets");
      const keep = sel.value;
      sel.innerHTML = (data.presets || [])
        .map((p) => `<option value="${p.id}">${UI.esc(p.name)}</option>`).join("");
      if (keep && data.presets.some((p) => p.id === keep)) sel.value = keep;
      else if (data.active_id) sel.value = data.active_id;
    } catch (_) { /* keep current options */ }
  },

  async apply(kind) {
    const m = this.find(this.selected);
    const sel = document.getElementById("models-preset-select");
    if (!m) { UI.toast("select a model first", "err"); return; }
    if (!sel.value) { UI.toast("select a preset to apply to", "err"); return; }
    try {
      const res = await API.get(`/api/presets/${sel.value}`);
      if (!res.ok) { UI.toast(res.error || "not found", "err"); return; }
      const launch = res.preset.launch;
      if (kind === "model") launch.model = m.path;
      else launch.mmproj = m.mmproj.length ? m.mmproj[0] : "";
      const body = { name: res.preset.name, launch, generation: launch.generation };
      const saved = await API.put(`/api/presets/${sel.value}`, body);
      if (!saved.ok) { UI.toast(saved.error || "save failed", "err"); return; }
      UI.toast(kind === "model"
        ? `model → ${m.path}`
        : (launch.mmproj ? `mmproj → ${launch.mmproj}` : "mmproj cleared"));
      Dashboard.refreshPresets();
    } catch (e) { UI.toast(`save failed: ${e}`, "err"); }
  },
};
