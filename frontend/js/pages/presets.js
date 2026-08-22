"use strict";

/* llama-monitor — presets page: list + grouped form (plan 4.3 / 4.8) */

const Presets = {
  editingId: "",

  /* element id -> launch path, type */
  FIELDS: [
    ["pf-model", "model", "str"],
    ["pf-alias", "alias", "str"],
    ["pf-mmproj", "mmproj", "str"],
    ["pf-ctx", "context_size", "int"],
    ["pf-ngl", "n_gpu_layers", "int"],
    ["pf-ncmoe", "n_cpu_moe", "int0"],
    ["pf-override", "override_tensors", "strlist"],
    ["pf-fa", "flash_attn", "str"],
    ["pf-ctk", "cache_type_k", "str"],
    ["pf-ctv", "cache_type_v", "str"],
    ["pf-load", "load_mode", "str"],
    ["pf-ts", "tensor_split", "intlist"],
    ["pf-mg", "main_gpu", "int"],
    ["pf-sm", "split_mode", "str"],
    ["pf-threads", "threads", "int0"],
    ["pf-tb", "threads_batch", "int0"],
    ["pf-b", "batch_size", "int"],
    ["pf-ub", "micro_batch", "int"],
    ["pf-reuse", "cache_reuse", "int0"],
    ["pf-spectype", "spec.spec_type", "str"],
    ["pf-draft", "spec.draft_model", "str"],
    ["pf-dnmax", "spec.draft_n_max", "int0"],
    ["pf-dnmin", "spec.draft_n_min", "int0"],
    ["pf-slots", "slots", "int"],
    ["pf-host", "host", "str"],
    ["pf-port", "port", "int"],
    ["pf-apikey", "api_key", "str"],
    ["pf-jinja", "jinja", "bool"],
    ["pf-reasoning", "reasoning_preserve", "bool"],
    ["pf-mergeqkv", "merge_qkv", "bool"],
    ["pf-fit", "fit", "bool"],
    ["pf-gr", "graph_reuse", "int0"],
    ["pf-extra", "extra_flags", "str"],
  ],

  DEFAULTS: {
    model: "", alias: "", mmproj: "",
    context_size: 4096, n_gpu_layers: 99, n_cpu_moe: 0,
    override_tensors: [], flash_attn: "auto", cache_type_k: "f16", cache_type_v: "f16",
    load_mode: "mmap", tensor_split: [], main_gpu: 0, split_mode: "layer",
    threads: 0, threads_batch: 0, batch_size: 2048, micro_batch: 512, cache_reuse: 0,
    spec: { spec_type: "none", draft_model: "", draft_n_max: 3, draft_n_min: 0 },
    slots: 1, host: "0.0.0.0", port: 8080, api_key: "",
    jinja: true, reasoning_preserve: false, merge_qkv: false, graph_reuse: 0,
    fit: false, extra_flags: "",
  },

  init() {
    document.getElementById("btn-new-preset").addEventListener("click", () => this.openForm(null));
    document.getElementById("btn-preset-back").addEventListener("click", () => this.showList());
    document.getElementById("preset-form").addEventListener("submit", (e) => {
      e.preventDefault();
      this.save();
    });
    document.getElementById("presets-list").addEventListener("click", (e) => {
      const btn = e.target.closest("button[data-act]");
      if (btn) {
        const act = btn.dataset.act;
        const id = btn.dataset.id;
        if (act === "edit") this.openForm(id);
        else if (act === "dup") this.duplicate(id);
        else if (act === "del") this.remove(id);
        return;
      }
      const card = e.target.closest(".preset-card");
      if (card) this.openForm(card.dataset.id);
    });
    document.getElementById("pf-spectype").addEventListener("change", (e) => {
      const needsDrafter = ["draft-simple", "draft-eagle3", "draft-dflash", "draft-dspark"].includes(e.target.value);
      document.getElementById("pf-draftwrap").classList.toggle("hidden", !needsDrafter);
      this.updateMtpWarning();
    });
    document.getElementById("pf-model").addEventListener("change", () => this.suggestMmproj());
    document.getElementById("pf-mmproj").addEventListener("input", () => this.updateMtpWarning());
    this.showList();
  },

  /* ---------------- model browser integration ---------------- */

  refreshDatalists() {
    const models = (typeof Models !== "undefined" && Models.models) || [];
    const modelsList = document.getElementById("models-datalist");
    const mmprojList = document.getElementById("mmproj-datalist");
    if (modelsList) {
      modelsList.innerHTML = models.map((m) => `<option value="${UI.esc(m.path)}">`).join("");
    }
    const mm = new Set();
    for (const m of models) for (const p of m.mmproj) mm.add(p);
    if (mmprojList) {
      mmprojList.innerHTML = [...mm].map((p) => `<option value="${UI.esc(p)}">`).join("");
    }
  },

  suggestMmproj() {
    const model = document.getElementById("pf-model").value.trim();
    const mmprojEl = document.getElementById("pf-mmproj");
    if (!model || mmprojEl.value.trim()) return;
    const m = typeof Models !== "undefined" && Models.find(model);
    if (m && m.mmproj.length) mmprojEl.value = m.mmproj[0];
  },

  updateMtpWarning() {
    const el = document.getElementById("pf-mtp-warning");
    const isMtp = document.getElementById("pf-spectype").value === "draft-mtp";
    const hasMmproj = !!document.getElementById("pf-mmproj").value.trim();
    el.classList.toggle("hidden", !(isMtp && hasMmproj));
  },

  /* ---------------- list ---------------- */

  /* logo chip: the preset's model (brand icon / provider monogram, same
     rules as the models page); a monogram of the preset name when it has
     no model yet */
  logoForPreset(p) {
    const model = p.model || "";
    if (model && typeof Models !== "undefined") {
      const m = { name: model.split("/").pop() || model, path: model, mmproj: [] };
      const { icon, label } = Models.iconForModel(m);
      if (icon) {
        return `<span class="model-logo preset-logo" title="${UI.esc(label || model)}">` +
               `<img class="model-icon" src="${icon}" alt="" loading="lazy"></span>`;
      }
      const provider = Models.providerOf(m);
      const l = Models.logoFor(provider);
      return `<span class="model-logo preset-logo" style="background:${l.bg};color:${l.fg}" title="${UI.esc(provider || "no provider folder")}">${UI.esc(l.label)}</span>`;
    }
    const l = typeof Models !== "undefined" && typeof monogram === "function"
      ? Models.logoFor(p.name)
      : { label: p.name.slice(0, 2).toUpperCase(), bg: "#444", fg: "#fff" };
    return `<span class="model-logo preset-logo" style="background:${l.bg};color:${l.fg}" title="${UI.esc(p.name)}">${UI.esc(l.label)}</span>`;
  },

  async showList() {
    this.editingId = "";
    document.getElementById("presets-list-view").classList.remove("hidden");
    document.getElementById("presets-form-view").classList.add("hidden");
    await this.load();
  },

  /* info chips for a preset card (shared with the dashboard picker) */
  chipsFor(p) {
    const chips = [];
    if (p.id === this.activeId) chips.push('<span class="chip chip-ok">active</span>');
    if (p.alias) chips.push(`<span class="chip">${UI.esc(p.alias)}</span>`);
    if (p.context_size) chips.push(`<span class="chip chip-params">${Number(p.context_size).toLocaleString()} ctx</span>`);
    if (p.n_gpu_layers != null && p.n_gpu_layers !== "") chips.push(`<span class="chip chip-quant">${p.n_gpu_layers} ngl</span>`);
    if (p.spec_type && p.spec_type !== "none") chips.push(`<span class="chip chip-vision">${UI.esc(p.spec_type)}</span>`);
    if (p.port) chips.push(`<span class="chip">port ${p.port}</span>`);
    return chips;
  },

  /* the card body (logo / name + chips / sub + trailing cell) — shared with
     the dashboard picker, which passes its own chevron/check as trailing */
  cardInner(p, trailingHtml) {
    const chips = this.chipsFor(p);
    const sub = `${UI.esc(p.model || "no model set")} · updated ${UI.timeAgo(p.updated_at)}`;
    return `
        ${this.logoForPreset(p)}
        <div class="preset-main">
          <div class="preset-line1">
            <h3 class="preset-name" title="${UI.esc(p.name)}">${UI.esc(p.name)}</h3>
            ${chips.length ? `<span class="preset-chips">${chips.join("")}</span>` : ""}
          </div>
          <div class="preset-sub" title="${UI.esc(p.model)}">${sub}</div>
        </div>
        ${trailingHtml}`;
  },

  /* one preset card; the trailing cell defaults to the action buttons */
  cardHtml(p, { trailing = null } = {}) {
    const t = trailing === null ? `
        <div class="preset-actions">
          <button type="button" class="btn" data-act="edit" data-id="${p.id}">Edit</button>
          <button type="button" class="btn" data-act="dup" data-id="${p.id}">Duplicate</button>
          <button type="button" class="btn btn-danger" data-act="del" data-id="${p.id}">Delete</button>
        </div>` : trailing;
    return `<div class="preset-card" data-id="${p.id}">` + this.cardInner(p, t) + `</div>`;
  },

  async load() {
    let data;
    try {
      data = await API.get("/api/presets");
    } catch (e) {
      UI.toast(`failed to load presets: ${e}`, "err");
      return;
    }
    const rows = data.presets || [];
    this.activeId = data.active_id || "";
    const list = document.getElementById("presets-list");
    list.innerHTML = rows.map((p) => this.cardHtml(p)).join("");
    document.getElementById("presets-count").textContent =
      rows.length ? `${rows.length} preset${rows.length > 1 ? "s" : ""}` : "";
    document.getElementById("presets-empty").classList.toggle("hidden", rows.length > 0);
    this.refreshDatalists();
  },

  async duplicate(id) {
    try {
      const res = await API.post(`/api/presets/${id}/duplicate`, {});
      if (!res.ok) { UI.toast(res.error || "duplicate failed", "err"); return; }
      UI.toast(`created "${res.preset.name}"`);
      await this.load();
      Dashboard.refreshPresets();
    } catch (e) { UI.toast(`duplicate failed: ${e}`, "err"); }
  },

  async remove(id) {
    if (!confirm("Delete this preset?")) return;
    try {
      const res = await API.del(`/api/presets/${id}`);
      if (!res.ok) { UI.toast("delete failed", "err"); return; }
      UI.toast("preset deleted");
      await this.load();
      Dashboard.refreshPresets();
    } catch (e) {
      UI.toast(`delete failed: ${e}`, "err");
    }
  },

  /* ---------------- form ---------------- */

  getPath(obj, path) {
    return path.split(".").reduce((o, k) => (o == null ? undefined : o[k]), obj);
  },

  setPath(obj, path, value) {
    const keys = path.split(".");
    const last = keys.pop();
    const target = keys.reduce((o, k) => (o[k] = o[k] || {}), obj);
    target[last] = value;
  },

  readFields() {
    const launch = {};
    for (const [id, path, type] of this.FIELDS) {
      const el = document.getElementById(id);
      let v;
      if (type === "bool") v = el.checked;
      else if (type === "intlist") v = UI.parseIntList(el.value);
      else if (type === "strlist") v = el.value.split(",").map((s) => s.trim()).filter(Boolean);
      else if (type === "int" || type === "int0") {
        const n = parseInt(el.value, 10);
        v = Number.isNaN(n) ? 0 : n;
      } else v = el.value;
      this.setPath(launch, path, v);
    }
    return launch;
  },

  fillFields(launch) {
    for (const [id, path, type] of this.FIELDS) {
      const el = document.getElementById(id);
      const v = this.getPath(launch, path);
      if (type === "bool") el.checked = !!v;
      else if (type === "strlist" || type === "intlist") el.value = (v || []).join(",");
      else el.value = v == null ? "" : v;
    }
  },

  applyDefaults(launch) {
    for (const key of Object.keys(this.DEFAULTS)) {
      const d = this.DEFAULTS[key];
      if (Array.isArray(d)) {
        if (!Array.isArray(launch[key])) launch[key] = [...d];
      } else if (key === "spec") {
        launch.spec = Object.assign({ ...d }, launch.spec || {});
      } else if (launch[key] === undefined || launch[key] === "" || launch[key] === null) {
        launch[key] = d;
      }
    }
    return launch;
  },

  async openForm(id) {
    document.getElementById("presets-list-view").classList.add("hidden");
    document.getElementById("presets-form-view").classList.remove("hidden");
    if (id) {
      try {
        const res = await API.get(`/api/presets/${id}`);
        if (!res.ok) { UI.toast(res.error || "not found", "err"); this.showList(); return; }
        this.editingId = id;
        document.getElementById("preset-form-title").textContent = res.preset.name;
        document.getElementById("pf-name").value = res.preset.name;
        this.fillFields(res.preset.launch);
      } catch (e) {
        UI.toast(`failed to load preset: ${e}`, "err");
        this.showList();
        return;
      }
    } else {
      this.editingId = "";
      document.getElementById("preset-form-title").textContent = "New preset";
      document.getElementById("pf-name").value = "New preset";
      this.fillFields(this.DEFAULTS);
    }
    const specType = document.getElementById("pf-spectype").value;
    const needsDrafter = ["draft-simple", "draft-eagle3", "draft-dflash", "draft-dspark"].includes(specType);
    document.getElementById("pf-draftwrap").classList.toggle("hidden", !needsDrafter);
    this.updateMtpWarning();
  },

  async save() {
    const name = document.getElementById("pf-name").value.trim() || "Untitled preset";
    const launch = this.readFields();
    this.applyDefaults(launch);
    const body = { name, launch };
    try {
      let res;
      if (this.editingId) {
        res = await API.put(`/api/presets/${this.editingId}`, body);
      } else {
        res = await API.post("/api/presets", body);
      }
      if (!res.ok) { UI.toast(res.error || "save failed", "err"); return; }
      UI.toast(`saved "${name}"`);
      this.showList();
      Dashboard.refreshPresets();
    } catch (e) {
      UI.toast(`save failed: ${e}`, "err");
    }
  },
};
