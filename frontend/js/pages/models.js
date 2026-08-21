"use strict";

/* llama-monitor — models page: GGUF list menu + mmproj apply (plan 4.6) */

/* provider monogram: first letter of the first two parts ("meta-llama" -> "ML") */
function monogram(s) {
  const parts = String(s).replace(/[_\-./\\]+/g, " ").split(/\s+/).filter(Boolean);
  if (!parts.length) return "?";
  if (parts.length === 1) return parts[0].slice(0, 1).toUpperCase();
  return (parts[0][0] + parts[1][0]).toUpperCase();
}

/* rebuild a <select> ("all" + entries of [value, label]), keeping the
   current selection when it still exists */
function fillSelect(sel, allLabel, entries) {
  const prev = sel.value;
  sel.innerHTML = "";
  const opt = (v, label) => {
    const o = document.createElement("option");
    o.value = v;
    o.textContent = label;
    sel.appendChild(o);
  };
  opt("all", allLabel);
  for (const [v, label] of entries) opt(v, label);
  if ([...sel.options].some((o) => o.value === prev)) sel.value = prev;
}

/* human file size from megabytes */
function fmtSize(mb) {
  return mb >= 1024 ? `${(mb / 1024).toFixed(2)} GB` : `${Math.round(mb).toLocaleString()} MB`;
}

const Models = {
  models: [],
  root: "",
  selected: "",

  find(path) {
    return this.models.find((m) => m.path === path);
  },

  init() {
    document.getElementById("models-search").addEventListener("input", () => this.render());
    document.getElementById("models-filter-provider").addEventListener("change", () => this.render());
    document.getElementById("models-filter-quant").addEventListener("change", () => this.render());
    document.getElementById("models-refresh").addEventListener("click", () => this.refresh());
    document.getElementById("models-list").addEventListener("click", (e) => {
      const row = e.target.closest(".model-row");
      if (!row) return;
      this.selected = row.dataset.path;
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
    this.renderFilters();
    this.render();
    this.renderDetail();
    if (typeof Presets !== "undefined") Presets.refreshDatalists();
  },

  /* provider = first folder under the models root ("unsloth/..." -> "unsloth") */
  providerOf(m) {
    const i = m.path.indexOf("/");
    return i > 0 ? m.path.slice(0, i) : "";
  },

  /* quantization tag parsed from the file name (Q4_K_M, IQ2_XXS, F16, ...) */
  quantOf(name) {
    const q = /\b(Q\d+(?:_[A-Za-z0-9]+)*|IQ\d+_[A-Za-z0-9]+|F16|BF16|FP16)\b/.exec(name);
    return q ? q[1].toUpperCase() : "";
  },

  /* provider monogram badge: known brand colors, hashed hue otherwise.
     Simple self-authored monograms (no external logo assets/CDN). */
  logoFor(provider) {
    const p = (provider || "").toLowerCase();
    const known = {
      qwen: ["#5b5bd6", "#fff"], "google": ["#4285f4", "#fff"],
      "google-gemma": ["#4285f4", "#fff"], "microsoft": ["#00a4ef", "#fff"],
      "meta": ["#3b82f6", "#fff"], "meta-llama": ["#3b82f6", "#fff"],
      "mistral": ["#fc7662", "#fff"], "deepseek": ["#4d6bfe", "#fff"],
      "openai": ["#10a37f", "#fff"], "nvidia": ["#76b900", "#111"],
      "huggingface": ["#ffd317", "#1a1a1a"], "unsloth": ["#f97316", "#fff"],
      "bartowski": ["#22c55e", "#fff"], "z-lab": ["#ec4899", "#fff"],
      "the-drummer": ["#eab308", "#1a1a1a"], "nomic": ["#0ea5e9", "#fff"],
      "turboderp": ["#a855f7", "#fff"], "lmstudio-community": ["#8b5cf6", "#fff"],
    };
    let label, bg, fg;
    if (known[p]) {
      [bg, fg] = known[p];
      label = monogram(p);
    } else if (provider) {
      let h = 0;
      for (let i = 0; i < p.length; i++) h = (h * 31 + p.charCodeAt(i)) >>> 0;
      bg = `hsl(${h % 360}, 48%, 40%)`;
      fg = "#fff";
      label = monogram(provider);
    } else {
      label = "?"; bg = "#444"; fg = "#fff";
    }
    return { label, bg, fg };
  },

  tags(m) {
    const out = [];
    const p = /[-_](\d+(?:\.\d+)?[BM])(?=[._\-]|$)/i.exec(m.name);
    if (p) out.push(`<span class="chip chip-params">${UI.esc(p[1].toUpperCase())}</span>`);
    const q = this.quantOf(m.name);
    if (q) out.push(`<span class="chip chip-quant">${UI.esc(q)}</span>`);
    if (m.mmproj.length) out.push(`<span class="chip chip-vision">vision</span>`);
    return out;
  },

  renderFilters() {
    const provSel = document.getElementById("models-filter-provider");
    const quantSel = document.getElementById("models-filter-quant");
    const providers = new Map();
    const quants = new Set();
    for (const m of this.models) {
      const p = this.providerOf(m);
      if (p) providers.set(p, (providers.get(p) || 0) + 1);
      const q = this.quantOf(m.name);
      if (q) quants.add(q);
    }
    const pList = [...providers.entries()].sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]));
    fillSelect(provSel, "all providers", pList.map(([p]) => [p.toLowerCase(), p]));
    fillSelect(quantSel, "all quants", [...quants].sort().map((q) => [q, q]));
  },

  render() {
    const q = (document.getElementById("models-search").value || "").toLowerCase();
    const provF = document.getElementById("models-filter-provider").value;
    const quantF = document.getElementById("models-filter-quant").value;
    const list = document.getElementById("models-list");
    const rows = this.models.filter((m) => {
      if (q && !m.name.toLowerCase().includes(q) && !m.path.toLowerCase().includes(q)) return false;
      if (provF !== "all" && this.providerOf(m).toLowerCase() !== provF) return false;
      if (quantF !== "all" && this.quantOf(m.name) !== quantF) return false;
      return true;
    });
    list.innerHTML = rows.map((m) => {
      const provider = this.providerOf(m);
      const logo = this.logoFor(provider);
      const subParts = [];
      if (provider) subParts.push(provider);
      if (m.path.includes("/")) subParts.push(m.path.slice(m.path.indexOf("/") + 1).replace(/\/[^/]+$/, ""));
      subParts.push(`${fmtSize(m.size_mb)} · ${UI.timeAgo(m.mtime)}`);
      const sub = subParts.join(" · ");
      const tags = this.tags(m);
      return `
      <div class="model-row ${m.path === this.selected ? "selected" : ""}" data-path="${UI.esc(m.path)}">
        <span class="model-logo" style="background:${logo.bg};color:${logo.fg}" title="${UI.esc(provider || "no provider folder")}">${UI.esc(logo.label)}</span>
        <div class="model-row-main">
          <div class="model-row-line1">
            <h3 class="model-name" title="${UI.esc(m.path)}">${UI.esc(m.name)}</h3>
            ${tags.length ? `<span class="model-row-chips">${tags.join("")}</span>` : ""}
          </div>
          <div class="model-row-sub" title="${UI.esc(m.path)}">${UI.esc(sub)}</div>
        </div>
      </div>`;
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
