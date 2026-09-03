"use strict";

/* llama-monitor — dashboard page: preset picker card, flag preview, server log */

const Dashboard = {
  presets: [],
  activeId: "",
  selectedId: "",
  // first successful /api/presets fetch (false until then: the card shows a
  // skeleton row, not the empty state — #58)
  loaded: false,
  pickOpen: false,
  // the preset the server is ACTUALLY running (from the server state);
  // source of truth for the card while the server is up (#56)
  runningId: "",
  // set when the user explicitly picks in the session — suppresses the
  // auto-snap to the running preset until the next refresh/reconnect
  userPicked: false,

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
    document.getElementById("btn-copy-cmd").addEventListener("click", () => this.copyCommand());
    this.refreshPresets();
  },

  async refreshPresets() {
    let data;
    try {
      data = await API.get("/api/presets");
    } catch (e) {
      this.loaded = true; // fall back to the empty state; toast explains
      UI.toast(`failed to load presets: ${e}`, "err");
      return;
    }
    this.loaded = true;
    this.presets = data.presets || [];
    this.activeId = data.active_id || "";
    this.userPicked = false;
    // while the server is up, the card shows the preset it's actually
    // running — not the persisted/last pick (#56); otherwise keep the
    // current pick when possible, then the active preset, then the first
    if (this.runningId && this.presets.some((p) => p.id === this.runningId)) {
      this.selectedId = this.runningId;
    } else if (!this.presets.some((p) => p.id === this.selectedId)) {
      this.selectedId = this.presets.some((p) => p.id === this.activeId)
        ? this.activeId
        : (this.presets[0] ? this.presets[0].id : "");
    }
    this.renderPick();
    this.renderRunningHint();
  },

  /** Called from applyState (REST + WS) with the latest server state. */
  syncRunning(state) {
    const up = state && (state.state === "running" || state.state === "external");
    const newId = up ? (state.preset_id || "") : "";
    const changed = newId !== this.runningId;
    this.runningId = newId;
    if (changed && this.presets.length) {
      // snap the card to the running preset (covers the first state arriving
      // after the presets rendered) unless the user already picked
      if (this.runningId && !this.userPicked
          && this.presets.some((p) => p.id === this.runningId)
          && this.selectedId !== this.runningId) {
        this.selectedId = this.runningId;
      }
      this.renderPick(); // refreshes the "running" chip on/off
    }
    this.renderRunningHint();
  },

  /* explicit "next" vs "running" distinction: when the pick differs from
     what the server is running, say so under the card (#56) */
  renderRunningHint() {
    const el = document.getElementById("running-hint");
    if (!el) return;
    if (this.runningId && this.selectedId && this.selectedId !== this.runningId) {
      const run = this.presets.find((p) => p.id === this.runningId);
      el.textContent = `server is running “${run ? run.name : this.runningId}” — your pick applies on next start / restart`;
      el.classList.remove("hidden");
    } else {
      el.classList.add("hidden");
    }
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
    if (!this.loaded) {
      pick.innerHTML = '<div class="sk sk-row"></div>';
      list.innerHTML = "";
      return;
    }
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
      this.userPicked = true;
      this.renderPick();
      this.renderRunningHint();
      // keep a visible preview in sync with the new selection
      const pre = document.getElementById("flag-preview");
      if (!pre.classList.contains("hidden")) this.preview(true);
    }
    this.closePick();
  },

  // Line-continuation character per target shell (verified empirically):
  // cmd.exe uses ^, PowerShell a backtick, bash/zsh a backslash. No single
  // character works across all three, so the copy button offers a selector.
  SHELL_CONT: { cmd: "^", powershell: "`", bash: "\\" },

  /** Rebuild the paste-ready command from the last preview.
      One flag per line (a flag+value pair stays together), the selected
      shell's continuation character on every line except the last, so a
      paste leaves ONE pending command and a single Enter starts the server.
      Tokens use shell quoting (double quotes around tokens with spaces)
      — NOT the display-only quoteForDisplay, since this text is meant to run. */
  copyCommand() {
    const p = this.lastPreview;
    if (!p || !p.exe) {
      UI.toast("llama-server executable not configured — nothing to copy", "err");
      return;
    }
    const shell = document.getElementById("cmd-shell").value || "cmd";
    const cont = this.SHELL_CONT[shell] || "\\";
    // Double-quote only tokens containing whitespace (the realistic case:
    // paths with spaces). No \" escaping — that is bash-specific and
    // wrong for cmd/PowerShell, and these tokens never hold a literal quote.
    const quote = (t) => (t === "" ? '""' : /\s/.test(t) ? `"${t}"` : t);
    // a flag = 1-2 dashes + a letter; a value like `-1` (dash + digit)
    // is NOT a flag, so `-np -1` stays on one line
    const isFlag = (t) => /^-{1,2}[A-Za-z]/.test(t);
    const lines = [quote(p.exe)];
    const args = p.args;
    for (let i = 0; i < args.length; i++) {
      let line = quote(args[i]);
      if (isFlag(args[i]) && i + 1 < args.length && !isFlag(args[i + 1])) {
        line += " " + quote(args[i + 1]);
        i++;
      }
      lines.push(line);
    }
    const text = lines.map((l, i) => (i < lines.length - 1 ? `${l} ${cont}` : l)).join("\r\n");
    UI.copyText(text).then((ok) => UI.toast(
      ok ? `copied launch command (one flag per line, ${shell})` : "clipboard copy failed",
      ok ? "ok" : "err"));
  },

  async preview(force = false) {
    const btn = document.getElementById("btn-preview");
    const pre = document.getElementById("flag-preview");
    const toolbar = document.getElementById("preview-toolbar");
    // toggle off: just hide (a re-show re-fetches, so the command stays fresh)
    if (!pre.classList.contains("hidden") && !force) {
      pre.classList.add("hidden");
      toolbar.classList.add("hidden");
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
      toolbar.classList.toggle("hidden", !res.exe);
      this.lastPreview = { exe: res.exe, args: res.args };
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

  lastPreview: null,
};
