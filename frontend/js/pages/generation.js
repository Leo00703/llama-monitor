"use strict";

/* llama-monitor — generation page: per-preset generation defaults (plan 4.9) */

const Generation = {
  presetId: "",
  presetName: "",
  serverOnline: false,
  serverDefaults: {},
  saved: {},

  EXTRA_ALWAYS: ["stop", "grammar", "json_schema", "logit_bias"],

  // Servers report defaults as float32, so e.g. 0.95 comes back as
  // 0.949999988079071 — display (and compare) a cleaned 4-significant-digit
  // form. Integers pass through untouched.
  cleanNum(v) {
    const n = Number(v);
    if (!Number.isFinite(n) || Number.isInteger(n)) return v;
    return parseFloat(n.toPrecision(4));
  },

  FIELDS: {
    temperature:        { label: "Temperature", type: "num", tab: "sampling" },
    dynatemp_range:     { label: "Dynamic temp range", type: "num", tab: "sampling" },
    dynatemp_exponent:  { label: "Dynamic temp exponent", type: "num", tab: "sampling" },
    top_k:              { label: "Top-k", type: "int", tab: "sampling" },
    top_p:              { label: "Top-p", type: "num", tab: "sampling" },
    min_p:              { label: "Min-p", type: "num", tab: "sampling" },
    top_n_sigma:        { label: "Top-n-sigma", type: "num", tab: "sampling" },
    xtc_probability:    { label: "XTC probability", type: "num", tab: "sampling" },
    xtc_threshold:      { label: "XTC threshold", type: "num", tab: "sampling" },
    typical_p:          { label: "Typical-p", type: "num", tab: "sampling" },
    mirostat:           { label: "Mirostat (0 off / 1 / 2)", type: "sel:0,1,2", tab: "sampling" },
    mirostat_tau:       { label: "Mirostat tau", type: "num", tab: "sampling" },
    mirostat_eta:       { label: "Mirostat eta", type: "num", tab: "sampling" },
    adaptive_target:    { label: "Adaptive target", type: "num", tab: "sampling" },
    adaptive_decay:     { label: "Adaptive decay", type: "num", tab: "sampling" },
    n_probs:            { label: "Return top-n probs (n-probs)", type: "int", tab: "sampling" },
    min_keep:           { label: "Min keep", type: "int", tab: "sampling" },
    samplers:           { label: "Samplers (comma separated, in order)", type: "strlist", tab: "sampling" },
    repeat_last_n:      { label: "Repeat window (repeat-last-n)", type: "int", tab: "penalties" },
    repeat_penalty:     { label: "Repeat penalty", type: "num", tab: "penalties" },
    presence_penalty:   { label: "Presence penalty", type: "num", tab: "penalties" },
    frequency_penalty:  { label: "Frequency penalty", type: "num", tab: "penalties" },
    dry_multiplier:     { label: "DRY multiplier", type: "num", tab: "penalties" },
    dry_base:           { label: "DRY base", type: "num", tab: "penalties" },
    dry_allowed_length: { label: "DRY allowed length", type: "int", tab: "penalties" },
    dry_penalty_last_n: { label: "DRY penalty last-n", type: "int", tab: "penalties" },
    dry_sequence_breakers: { label: "DRY sequence breakers (comma separated)", type: "strlist", tab: "penalties" },
    logit_bias:         { label: "Logit bias (JSON: {token_id: bias})", type: "json", tab: "penalties" },
    seed:               { label: "Seed", type: "int", tab: "other" },
    max_tokens:         { label: "Max tokens (max-tokens / n-predict)", type: "int", tab: "other" },
    n_keep:             { label: "Keep n tokens (n-keep)", type: "int", tab: "other" },
    n_discard:          { label: "Discard n tokens (n-discard)", type: "int", tab: "other" },
    ignore_eos:         { label: "Ignore EOS", type: "bool", tab: "other" },
    chat_format:        { label: "Chat format", type: "str", tab: "other" },
    reasoning_format:   { label: "Reasoning format", type: "str", tab: "other" },
    reasoning_in_content: { label: "Reasoning in content", type: "bool", tab: "other" },
    generation_prompt:  { label: "Generation prompt", type: "str", tab: "other" },
    stop:               { label: "Stop sequences (one per line)", type: "lines", tab: "other" },
    grammar:            { label: "Grammar (GBNF)", type: "area", tab: "other" },
    json_schema:        { label: "JSON schema (JSON object)", type: "json", tab: "other" },
  },

  TABS: [
    ["sampling", "Sampling"],
    ["penalties", "Penalties"],
    ["other", "Other"],
  ],

  init() {
    document.getElementById("gen-save").addEventListener("click", () => this.save());
    document.getElementById("gen-reset").addEventListener("click", () => this.reset());
    document.querySelectorAll(".gen-tab").forEach((btn) => {
      btn.addEventListener("click", () => {
        const tab = btn.dataset.tab;
        document.querySelectorAll(".gen-tab").forEach(
          (b) => b.classList.toggle("active", b.dataset.tab === tab));
        for (const [t] of this.TABS) {
          document.getElementById(`gen-panel-${t}`).classList.toggle("hidden", t !== tab);
        }
      });
    });
    this.load();
  },

  refresh() {
    this.load();
  },

  async load() {
    let data;
    try {
      data = await API.get("/api/generation/defaults");
    } catch (e) {
      UI.toast(`failed to load generation defaults: ${e}`, "err");
      return;
    }
    this.serverOnline = !!data.server_online;
    this.serverDefaults = data.server_defaults || {};
    this.saved = data.saved || {};
    this.presetId = data.preset_id || "";
    this.presetName = data.preset_name || "";

    document.getElementById("gen-head").innerHTML = this.presetId
      ? `Preset: <b>${UI.esc(this.presetName)}</b>`
      : '<span class="muted">no preset selected — pick a preset first</span>';
    document.getElementById("gen-status").innerHTML = this.serverOnline
      ? '<span class="chip chip-ok">server online</span>'
      : '<span class="chip chip-warn">server offline — saved values only</span>';
    document.getElementById("gen-save").disabled = !this.presetId;
    document.getElementById("gen-reset").disabled = !this.presetId;
    this.buildForm();
  },

  visibleKeys() {
    return Object.keys(this.FIELDS).filter(
      (k) => k in this.serverDefaults || k in this.saved || this.EXTRA_ALWAYS.includes(k));
  },

  shownValue(key) {
    if (key in this.saved) return this.saved[key];
    if (key in this.serverDefaults) return this.serverDefaults[key];
    return "";
  },

  buildForm() {
    for (const [tab] of this.TABS) {
      const panel = document.getElementById(`gen-panel-${tab}`);
      panel.innerHTML = "";
      for (const key of this.visibleKeys()) {
        const spec = this.FIELDS[key];
        if (spec.tab !== tab) continue;
        panel.appendChild(this.makeField(key, spec));
      }
      panel.classList.toggle("empty", !panel.children.length);
    }
  },

  makeField(key, spec) {
    const wrap = document.createElement("div");
    wrap.className = "gen-field";

    const label = document.createElement("label");
    label.className = "field-label";
    label.textContent = spec.label;
    wrap.appendChild(label);

    const shown = this.shownValue(key);
    let el;
    if (spec.type === "num" || spec.type === "int") {
      el = document.createElement("input");
      el.type = "number";
      if (spec.type === "int") el.step = "1";
      el.value = shown === "" ? "" : this.cleanNum(shown);
    } else if (spec.type.startsWith("sel:")) {
      el = document.createElement("select");
      for (const opt of spec.type.slice(4).split(",")) {
        const o = document.createElement("option");
        o.value = opt;
        o.textContent = opt;
        el.appendChild(o);
      }
      el.value = String(shown);
    } else if (spec.type === "bool") {
      el = document.createElement("input");
      el.type = "checkbox";
      el.checked = !!shown;
    } else if (spec.type === "strlist") {
      el = document.createElement("input");
      el.type = "text";
      el.value = Array.isArray(shown) ? shown.join(", ") : (shown || "");
    } else if (spec.type === "lines") {
      el = document.createElement("textarea");
      el.rows = 3;
      el.value = Array.isArray(shown) ? shown.join("\n") : (shown || "");
    } else if (spec.type === "json") {
      el = document.createElement("textarea");
      el.rows = 3;
      el.spellcheck = false;
      el.value = shown === "" ? "" : (typeof shown === "string" ? shown : JSON.stringify(shown, null, 2));
    } else if (spec.type === "area") {
      el = document.createElement("textarea");
      el.rows = 4;
      el.spellcheck = false;
      el.value = shown || "";
    } else {
      el = document.createElement("input");
      el.type = "text";
      el.value = shown || "";
    }
    el.dataset.key = key;
    el.dataset.type = spec.type;
    wrap.appendChild(el);

    const isSaved = key in this.saved &&
      JSON.stringify(this.saved[key]) !== JSON.stringify(this.serverDefaults[key]);
    if (isSaved) {
      const chip = document.createElement("span");
      chip.className = "gen-saved";
      chip.textContent = "saved";
      wrap.appendChild(chip);
    }
    return wrap;
  },

  readForm() {
    const out = {};
    for (const el of document.querySelectorAll(".gen-field [data-key]")) {
      const key = el.dataset.key;
      const type = el.dataset.type;
      let v;
      if (type === "num" || type === "int") {
        if (el.value === "") continue;
        const n = Number(el.value);
        if (Number.isNaN(n)) continue;
        v = type === "int" ? Math.trunc(n) : n;
      } else if (type.startsWith("sel:")) {
        v = el.value;
      } else if (type === "bool") {
        if (!el.checked && !this.shownValue(key)) continue;
        v = el.checked;
      } else if (type === "strlist") {
        const arr = el.value.split(",").map((s) => s.trim()).filter(Boolean);
        if (!arr.length) continue;
        v = arr;
      } else if (type === "lines") {
        const arr = el.value.split("\n").filter((s) => s !== "");
        if (!arr.length) continue;
        v = arr;
      } else if (type === "json") {
        const raw = el.value.trim();
        if (!raw) continue;
        try {
          v = JSON.parse(raw);
        } catch (_) {
          UI.toast(`invalid JSON in ${key}`, "err");
          return null;
        }
      } else if (type === "area" || type === "str") {
        if (!el.value) continue;
        v = el.value;
      }
      out[key] = v;
    }
    return out;
  },

  async save() {
    if (!this.presetId) { UI.toast("no preset to save to", "err"); return; }
    const values = this.readForm();
    if (values === null) return;

    const generation = {};
    for (const [key, value] of Object.entries(values)) {
      const sd = this.serverDefaults[key];
      if (key in this.serverDefaults) {
        if (typeof value === "number" && typeof sd === "number" &&
            this.cleanNum(value) === this.cleanNum(sd)) {
          continue; // same as server default once float32 noise is ignored
        }
        if (JSON.stringify(sd) === JSON.stringify(value)) continue;
      }
      generation[key] = value;
    }
    if (generation.max_tokens !== undefined) {
      generation.n_predict = generation.max_tokens; // dual-write: /completion reads n_predict
    }

    try {
      const res = await API.put(`/api/presets/${this.presetId}/generation`, { generation });
      if (!res.ok) { UI.toast(res.error || "save failed", "err"); return; }
      UI.toast("generation defaults saved");
      this.load();
    } catch (e) { UI.toast(`save failed: ${e}`, "err"); }
  },

  async reset() {
    if (!this.presetId) { UI.toast("no preset to reset", "err"); return; }
    if (!confirm("Clear all saved generation defaults for this preset?")) return;
    try {
      const res = await API.put(`/api/presets/${this.presetId}/generation`, { generation: {} });
      if (!res.ok) { UI.toast(res.error || "reset failed", "err"); return; }
      UI.toast("generation defaults cleared");
      this.load();
    } catch (e) { UI.toast(`reset failed: ${e}`, "err"); }
  },
};
