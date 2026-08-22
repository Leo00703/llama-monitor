"use strict";

/* llama-monitor — dashboard page: preset picker card, flag preview, server log */

const Dashboard = {
  presets: [],
  activeId: "",
  selectedId: "",
  pickOpen: false,

  init() {
    const pick = document.getElementById("preset-pick");
    pick.addEventListener("click", () => this.togglePick());
    pick.addEventListener("keydown", (e) => {
      if (e.key === "Enter" || e.key === " ") { e.preventDefault(); this.togglePick(); }
      else if (e.key === "Escape") this.closePick();
    });
    const pickList = document.getElementById("preset-pick-list");
    pickList.addEventListener("click", (e) => {
      if (e.target.closest("#preset-pick-manage")) {
        this.closePick();
        showPage("presets");
        return;
      }
      const card = e.target.closest(".preset-card");
      if (card) this.selectPreset(card.dataset.id);
    });
    pickList.addEventListener("keydown", (e) => {
      if (e.key !== "Enter" && e.key !== " ") return;
      const card = e.target.closest(".preset-card");
      if (card) { e.preventDefault(); this.selectPreset(card.dataset.id); }
    });
    document.addEventListener("click", (e) => {
      if (!this.pickOpen) return;
      if (e.target.closest("#preset-pick") || e.target.closest("#preset-pick-list")) return;
      this.closePick();
    });
    document.addEventListener("keydown", (e) => {
      if (e.key === "Escape" && this.pickOpen) this.closePick();
    });
    document.getElementById("btn-preview").addEventListener("click", () => this.preview());
    this.refreshPresets();
  },

  async refreshPresets() {
    let data;
    try {
      data = await API.get("/api/presets");
    } catch (e) {
      UI.toast(`failed to load presets: ${e}`, "err");
      return;
    }
    this.presets = data.presets || [];
    this.activeId = data.active_id || "";
    // keep the current pick when possible, otherwise fall back to the
    // persisted active preset, then the first one
    if (!this.presets.some((p) => p.id === this.selectedId)) {
      this.selectedId = this.presets.some((p) => p.id === this.activeId)
        ? this.activeId
        : (this.presets[0] ? this.presets[0].id : "");
    }
    this.renderPick();
  },

  /* the picker card (current selection + chevron) and the in-flow list */
  renderPick() {
    const pick = document.getElementById("preset-pick");
    const list = document.getElementById("preset-pick-list");
    const chev = `<span class="preset-pick-chev" aria-hidden="true">
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m6 9 6 6 6-6"></path></svg>
    </span>`;
    const check = `<span class="preset-pick-check" aria-hidden="true">
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M20 6 9 17l-5-5"></path></svg>
    </span>`;
    if (!this.presets.length) {
      pick.innerHTML = `<span class="preset-pick-empty">No presets yet — click to create one</span>${chev}`;
      list.innerHTML = "";
      return;
    }
    const p = this.presets.find((x) => x.id === this.selectedId) || this.presets[0];
    pick.innerHTML = Presets.cardInner(p, chev);
    list.innerHTML = this.presets.map((x) =>
      Presets.cardHtml(x, {
        trailing: x.id === this.selectedId ? check : "",
      })
    ).join("") + `\n      <button type="button" class="preset-pick-manage" id="preset-pick-manage">Manage presets →</button>`;
    // current pick: highlight + make the items keyboard reachable
    list.querySelectorAll(".preset-card").forEach((el) => {
      el.tabIndex = 0;
      el.classList.add("preset-pick-item");
      if (el.dataset.id === this.selectedId) el.classList.add("selected");
    });
  },

  togglePick() {
    if (!this.presets.length) { showPage("presets"); return; }
    if (this.pickOpen) this.closePick();
    else this.openPick();
  },

  openPick() {
    this.pickOpen = true;
    const pick = document.getElementById("preset-pick");
    pick.classList.add("open");
    pick.setAttribute("aria-expanded", "true");
    document.getElementById("preset-pick-list").classList.remove("hidden");
  },

  closePick() {
    if (!this.pickOpen) return;
    this.pickOpen = false;
    const pick = document.getElementById("preset-pick");
    pick.classList.remove("open");
    pick.setAttribute("aria-expanded", "false");
    document.getElementById("preset-pick-list").classList.add("hidden");
  },

  selectPreset(id) {
    if (id !== this.selectedId) {
      this.selectedId = id;
      this.renderPick();
      // keep a visible preview in sync with the new selection
      const pre = document.getElementById("flag-preview");
      if (!pre.classList.contains("hidden")) this.preview(true);
    }
    this.closePick();
  },

  async preview(force = false) {
    const btn = document.getElementById("btn-preview");
    const pre = document.getElementById("flag-preview");
    // toggle off: just hide (a re-show re-fetches, so the command stays fresh)
    if (!pre.classList.contains("hidden") && !force) {
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
