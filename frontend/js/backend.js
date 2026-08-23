"use strict";

/* llama-monitor — llama.cpp backend (build) updates: check / download /
   apply. The version picker is a card list in the same pattern as the
   dashboard preset picker; installing a build is always a manual choice. */

const Backend = {
  data: null,       // last GET /api/backend/versions
  pickOpen: false,
  downloading: false,
  applying: false,
  modalOpen: false,
  modalKind: "",    // confirm | progress
  modalOnDone: null,

  init() {
    const pick = document.getElementById("be-pick");
    pick.addEventListener("click", () => this.togglePick());
    pick.addEventListener("keydown", (e) => {
      if (e.key === "Enter" || e.key === " ") { e.preventDefault(); this.togglePick(); }
      else if (e.key === "Escape") this.closePick();
    });
    const list = document.getElementById("be-pick-list");
    list.addEventListener("click", (e) => {
      const item = e.target.closest(".be-version");
      if (item) this.onPickItem(item);
    });
    list.addEventListener("keydown", (e) => {
      if (e.key !== "Enter" && e.key !== " ") return;
      const item = e.target.closest(".be-version");
      if (item) { e.preventDefault(); this.onPickItem(item); }
    });
    document.addEventListener("click", (e) => {
      if (!this.pickOpen) return;
      if (e.target.closest("#be-pick") || e.target.closest("#be-pick-list")) return;
      this.closePick();
    });
    document.addEventListener("keydown", (e) => {
      if (e.key === "Escape" && this.pickOpen) this.closePick();
    });
    document.getElementById("be-check").addEventListener("click", () => this.check());
    document.getElementById("be-download").addEventListener("click", () => this.download());
    document.getElementById("be-update").addEventListener("click", () => {
      this.refresh().then(() => this.openPick());
    });
    document.getElementById("be-detect").addEventListener("click", () => this.detect());
    // modal buttons
    document.getElementById("be-modal-ok").addEventListener("click", () => this.modalOk());
    document.getElementById("be-modal-cancel").addEventListener("click", () => this.modalCancel());
    this.refresh();
  },

  /* ------------------------------------------------------------ data */

  async refresh(force = false) {
    try {
      this.data = await API.get("/api/backend/versions");
    } catch (e) {
      if (force) UI.toast(`backend update check failed: ${e}`, "err");
      return this.data;
    }
    this.render();
    return this.data;
  },

  target() {
    // the channel's latest build: stable = pinned nightly, nightly = latest
    const d = this.data || {};
    const remote = d.remote || {};
    return (d.settings || {}).channel === "nightly"
      ? (remote.latest_nightly || null)
      : (remote.pinned_nightly || null);
  },

  /* ----------------------------------------------------------- render */

  render() {
    const d = this.data;
    if (!d) return;
    const cur = d.current || {};
    const curEl = document.getElementById("be-current");
    let curHtml;
    if (cur.official) {
      curHtml = `<span class="chip chip-ok">official</span> `
        + `<b>${UI.esc(cur.tag)}</b> <span class="muted">· ${UI.esc(cur.version)}</span>`;
    } else if (cur.error) {
      curHtml = `<span class="chip chip-params">unknown</span> `
        + `<span class="muted">${UI.esc(cur.error)}</span>`;
    } else {
      curHtml = `<span class="chip chip-warn">custom build</span> `
        + `<b>${UI.esc(cur.version || "unknown")}</b> `
        + `<span class="muted">— updates stay manual, nothing is automated</span>`;
    }
    curEl.innerHTML = `<span class="be-current-label">Current</span>${curHtml}`;
    curEl.title = cur.folder || "";

    const status = document.getElementById("be-status");
    const lb = d.settings || {};
    const target = this.target();
    const parts = [];
    if (lb.last_check) parts.push(`last check ${this.when(lb.last_check)}`);
    if (d.downloading) parts.push("downloading…");
    if (d.remote_error) parts.push(`release check failed: ${d.remote_error}`);
    if (d.remote && target) {
      const pend = lb.pending;
      if (cur.official && pend && pend.state === "downloaded" && pend.tag === target) {
        parts.push(`${UI.esc(target)} downloaded — install it from “Update llama.cpp”`);
      } else if (cur.official && target === cur.tag) {
        parts.push(`up to date (${UI.esc(target)})`);
      } else if (cur.official) {
        parts.push(`${UI.esc(target)} available on the ${lb.channel} channel`);
      } else {
        parts.push(`${UI.esc(target)} available — install it from the picker`);
      }
    } else if (!d.remote_error) {
      parts.push("release info unavailable");
    }
    status.textContent = parts.length ? parts.join(" · ") : "Check for updates to get started.";
    // nothing to fetch when the channel target is the build already running
    // (or already downloaded — install it via the picker instead)
    const dl = document.getElementById("be-download");
    const pend2 = lb.pending;
    if (cur.official && target && target === cur.tag) {
      dl.disabled = true;
      dl.title = `up to date (${target})`;
    } else if (cur.official && target && pend2 && pend2.state === "downloaded" && pend2.tag === target) {
      dl.disabled = true;
      dl.title = `${target} is already downloaded — use “Update llama.cpp” to install it`;
    } else {
      dl.disabled = false;
      dl.title = "";
    }
    this.renderPick();
  },

  when(iso) {
    try {
      return UI.timeAgo(new Date(iso).getTime() / 1000);
    } catch (_) {
      return iso;
    }
  },

  renderPick() {
    const d = this.data;
    if (!d) return;
    const pick = document.getElementById("be-pick");
    const list = document.getElementById("be-pick-list");
    const chev = `<span class="preset-pick-chev" aria-hidden="true">
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m6 9 6 6 6-6"></path></svg>
    </span>`;
    const check = `<span class="preset-pick-check" aria-hidden="true">
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M20 6 9 17l-5-5"></path></svg>
    </span>`;
    const cur = d.current || {};
    const target = this.target();
    const downloadedTags = new Set((d.local || []).map((b) => b.tag));
    pick.innerHTML = `<span class="be-pick-main">
        <span class="be-pick-title">Version</span>
        <span class="muted small">${cur.official ? UI.esc(cur.tag || "unknown") : (cur.version || "unknown")}</span>
      </span>${chev}`;
    // picker items: the channel target (when different from current) first,
    // then every downloaded build (newest first — also the rollback path)
    const items = [];
    if (target && (!cur.official || target !== cur.tag)) {
      const done = downloadedTags.has(target);
      items.push({
        dir: done ? (d.local || []).find((b) => b.tag === target).dir : "",
        tag: target,
        title: `${target} — ${d.settings && d.settings.channel === "nightly" ? "latest nightly" : "stable (pinned nightly)"}`,
        sub: done ? "downloaded · ready to install" : "not downloaded yet — this will download it first",
        current: false,
      });
    }
    // a local copy of the target is already the first item — don't list it twice
    const targetOffered = items.length === 1 && items[0].tag === target;
    for (const b of d.local || []) {
      if (targetOffered && b.tag === target) continue;
      items.push({
        dir: b.dir, tag: b.tag,
        title: `${b.tag} — downloaded${b.variant ? ` · ${b.variant}` : ""}`,
        sub: b.installed_at ? `installed ${this.when(b.installed_at)}` : "",
        // version-based: the running build may live outside the storage
        // folder (same build, different path)
        current: cur.official && b.tag === cur.tag,
      });
    }
    if (!items.length) {
      list.innerHTML = `<div class="be-pick-empty muted small">
        Nothing to pick yet — run "Check for updates", then "Download".</div>`;
    } else {
      list.innerHTML = items.map((it) => `
        <div class="be-version" role="option" tabindex="0"
             data-dir="${UI.esc(it.dir)}" data-tag="${UI.esc(it.tag)}">
          <div class="preset-main">
            <div class="preset-line1">
              <h3 class="preset-name">${UI.esc(it.title)}</h3>
            </div>
            <div class="preset-sub">${UI.esc(it.sub)}</div>
          </div>
          ${it.current ? check : ""}
        </div>`).join("");
      list.querySelectorAll(".be-version").forEach((el) => {
        if (cur.official && el.dataset.tag === cur.tag) el.classList.add("selected");
      });
    }
  },

  openPick() {
    this.pickOpen = true;
    const pick = document.getElementById("be-pick");
    pick.classList.add("open");
    pick.setAttribute("aria-expanded", "true");
    document.getElementById("be-pick-list").classList.remove("hidden");
  },

  closePick() {
    if (!this.pickOpen) return;
    this.pickOpen = false;
    const pick = document.getElementById("be-pick");
    pick.classList.remove("open");
    pick.setAttribute("aria-expanded", "false");
    document.getElementById("be-pick-list").classList.add("hidden");
  },

  togglePick() {
    if (this.pickOpen) this.closePick();
    else this.openPick();
  },

  onPickItem(el) {
    this.closePick();
    const dir = el.dataset.dir || "";
    const tag = el.dataset.tag || "";
    const d = this.data || {};
    const cur = d.current || {};
    if (cur.official && tag === cur.tag) {
      UI.toast("that is the version you are already running");
      return;
    }
    if (!dir) {
      // the channel target is not downloaded yet → download, then the user
      // picks it again to install (installing stays a manual choice)
      this.confirmDownload(tag);
      return;
    }
    this.confirmApply(dir, tag);
  },

  /* ---------------------------------------------------------- actions */

  async check() {
    const b = document.getElementById("be-check");
    const label = b.textContent;
    b.disabled = true;
    b.textContent = "Checking…";
    try {
      const res = await API.post("/api/backend/check");
      if (res.ok) {
        await this.refresh();
        const t = this.target();
        if (res.error) UI.toast(`check: ${res.error}`, "err");
        else if (!res.current || !res.current.official)
          UI.toast("custom build detected — automation is off, check works manually", "ok");
        else if (t && t === res.current.tag) UI.toast(`✓ up to date (${t})`, "ok");
        else UI.toast(`${t || "a new build"} available`, "ok");
      } else {
        UI.toast(res.error || "check failed", "err");
      }
    } catch (e) {
      UI.toast(`check failed: ${e}`, "err");
    } finally {
      b.disabled = false;
      b.textContent = label;
    }
  },

  async download(tag = null) {
    const t = tag || this.target();
    if (!t) {
      UI.toast('no target build — run "Check for updates" first', "err");
      return;
    }
    this.confirmDownload(t, true);
  },

  confirmDownload(tag, fromButton = false) {
    const d = this.data || {};
    const variant = (d.settings || {}).variant || "cpu";
    this.openModal({
      kind: "confirm",
      title: `Download ${tag}?`,
      status: `Downloads the ${variant} build for ${tag} into the storage folder. It is NOT installed automatically — you choose when to install it from "Update llama.cpp".`,
      okLabel: "Download",
      onDone: () => this.startDownload(tag, fromButton),
    });
  },

  async startDownload(tag, fromButton) {
    this.closeModal();
    this.openModal({ kind: "progress", title: `Downloading ${tag}…`, status: "contacting the release server", okLabel: "" });
    this.downloading = true;
    try {
      const res = await API.post("/api/backend/download", { tag });
      if (!res.ok) {
        this.modalFail(res.error || "download could not start");
        return;
      }
      // progress + completion arrive over the websocket
    } catch (e) {
      this.modalFail(`download could not start: ${e}`);
    }
  },

  confirmApply(dir, tag) {
    const d = this.data || {};
    // serverState: global from app.js (classic script, same scope)
    const state = (typeof serverState !== "undefined" ? serverState : "stopped");
    const running = ["running", "starting", "restarting"].includes(state);
    this.openModal({
      kind: "confirm",
      title: `Update to ${tag}?`,
      status: running
        ? "The model server is running — it will be stopped, the new build installed, and the server restarted with the same preset."
        : "The new build will be installed and the configured path updated. Start the server whenever you're ready.",
      okLabel: "Update",
      onDone: () => this.startApply(dir, tag),
    });
  },

  async startApply(dir, tag) {
    this.closeModal();
    this.openModal({ kind: "progress", title: `Updating to ${tag}…`, status: "stopping the server, installing the build", okLabel: "" });
    this.applying = true;
    try {
      const res = await API.post("/api/backend/apply", { dir });
      if (!res.ok) {
        this.modalFail(res.error || "update failed");
        return;
      }
      let extra = "";
      if (res.external) extra = " The running external server keeps the old build until you restart it manually.";
      else if (res.restarted) extra = " The server was restarted with the same preset.";
      else if (res.error) { this.modalFail(res.error); return; }
      else extra = " " + (res.note || "The configured path was updated.");
      this.openModal({
        kind: "progress",
        title: `Updated to ${tag}`,
        status: `llama-server is now ${tag}.${extra}${res.pruned ? ` Removed: ${res.pruned.join(", ")}.` : ""}`,
        spinner: false,
        okLabel: "Close",
        onDone: () => { this.closeModal(); this.refresh(); },
      });
      this.refresh();
    } catch (e) {
      this.modalFail(`update failed: ${e}`);
    } finally {
      this.applying = false;
    }
  },

  async detect() {
    try {
      const res = await API.get("/api/backend/suggest");
      if (res.ok) {
        const sel = document.getElementById("be-variant");
        if ([...sel.options].some((o) => o.value === res.variant)) {
          sel.value = res.variant;
          UI.toast(`suggested: ${res.variant} — ${res.reason}`, "ok");
        }
      }
    } catch (e) {
      UI.toast(`detect failed: ${e}`, "err");
    }
  },

  /* ---------------------------------------------------------- websock */

  onWs(msg) {
    if (msg.type === "llama.update.available") {
      UI.toast(`llama.cpp ${msg.data.tag} available`, "ok");
      if (document.getElementById("page-settings").classList.contains("hidden") === false)
        this.refresh();
    } else if (msg.type === "llama.update.progress") {
      const p = msg.data || {};
      if (this.modalKind !== "progress") return;
      const el = document.getElementById("be-modal-status");
      const pct = p.percent != null ? ` · ${p.percent}%` : "";
      const mb = p.total ? `${(p.done / 1048576).toFixed(0)} / ${(p.total / 1048576).toFixed(0)} MB` : "";
      el.textContent = `downloading ${p.tag || ""} ${mb}${pct}`;
    } else if (msg.type === "llama.update.downloaded") {
      const tag = (msg.data || {}).tag || "";
      if (this.modalKind === "progress") {
        this.openModal({
          kind: "progress",
          title: `${tag} downloaded`,
          status: "Downloaded — it is NOT installed yet. Open 'Update llama.cpp' and pick it to install.",
          spinner: false,
          okLabel: "Close",
          onDone: () => { this.closeModal(); this.refresh(); },
        });
      }
      this.refresh();
    }
  },

  /* ------------------------------------------------------------ modal */

  openModal({ kind, title, status, okLabel = "OK", onDone = null }) {
    this.modalOpen = true;
    this.modalKind = kind;
    this.modalOnDone = onDone;
    const ov = document.getElementById("be-modal-overlay");
    document.getElementById("be-modal-title").textContent = title;
    const st = document.getElementById("be-modal-status");
    st.textContent = status;
    st.classList.toggle("be-modal-err", kind === "fail");
    document.getElementById("be-modal-spinner").hidden = kind !== "progress" || st.classList.contains("be-modal-err");
    const ok = document.getElementById("be-modal-ok");
    ok.textContent = okLabel;
    ok.hidden = !okLabel;
    const cancel = document.getElementById("be-modal-cancel");
    cancel.hidden = kind !== "confirm";
    ov.classList.add("neutral");
    ov.hidden = false;
    if (okLabel) ok.focus();
  },

  modalFail(msg) {
    this.openModal({ kind: "fail", title: "Backend update failed", status: msg, okLabel: "Close", onDone: () => this.refresh() });
  },

  modalOk() {
    const fn = this.modalOnDone;
    this.modalOnDone = null;
    if (fn) fn();
  },

  modalCancel() {
    this.modalOnDone = null;
    this.closeModal();
  },

  closeModal() {
    this.modalOpen = false;
    this.modalKind = "";
    this.downloading = false;
    this.applying = false;
    const ov = document.getElementById("be-modal-overlay");
    ov.hidden = true;
    ov.classList.remove("neutral");
  },
};
