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
    document.getElementById("models-cards").addEventListener("click", (e) => {
      const card = e.target.closest(".model-card");
      if (!card) return;
      this.selected = card.dataset.path;
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

  tags(m) {
    const out = [];
    const p = /[-_](\d+(?:\.\d+)?[BM])(?=[._\-]|$)/i.exec(m.name);
    if (p) out.push(`<span class="chip chip-params">${UI.esc(p[1].toUpperCase())}</span>`);
    const q = /\b(Q\d+(?:_[A-Za-z0-9]+)*|F16|BF16|FP16)\b/.exec(m.name);
    if (q) out.push(`<span class="chip chip-quant">${UI.esc(q[1])}</span>`);
    if (m.mmproj.length) out.push(`<span class="chip chip-vision">vision</span>`);
    return out;
  },

  render() {
    const q = (document.getElementById("models-search").value || "").toLowerCase();
    const cards = document.getElementById("models-cards");
    const rows = this.models.filter(
      (m) => !q || m.name.toLowerCase().includes(q) || m.path.toLowerCase().includes(q));
    cards.innerHTML = rows.map((m) => {
      const tags = this.tags(m);
      return `
      <article class="model-card ${m.path === this.selected ? "selected" : ""}" data-path="${UI.esc(m.path)}" title="${UI.esc(m.path)}">
        <h3 class="model-card-name">${UI.esc(m.name)}</h3>
        ${tags.length ? `<div class="model-card-chips">${tags.join("")}</div>` : ""}
        <div class="model-card-meta">
          <div><span class="muted small">size</span><div>${m.size_mb} MB</div></div>
          <div><span class="muted small">modified</span><div class="muted">${UI.timeAgo(m.mtime)}</div></div>
        </div>
      </article>`;
    }).join("");
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
