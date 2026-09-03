"use strict";

/* llama-monitor — resource + inference metrics: history, sparklines, cards.

   Two dashboard display modes (config dashboard.usage_style, pushed live in
   every metrics WS tick): "graph" = full-bleed sparklines with gridlines and
   overlaid values; "bar" = one big traffic-light bar per card. The DOM is
   shared — the mode lives on the #metrics-grid class (mode-graph/mode-bar). */

const Metrics = (() => {
  const HISTORY = 120;
  const hist = { cpu: [], ram: [] };
  const gpuHist = {};
  const gpuEls = {};
  let lastGpuCount = -1;
  let lastSeq = 0;
  let mode = "graph";
  let lastGpus = [];

  const $ = (id) => document.getElementById(id);

  const ICONS = {
    temp: '<svg class="micon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M14 14.76V4a2 2 0 0 0-4 0v10.76a4 4 0 1 0 4 0z"/></svg>',
    power: '<svg class="micon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M13 2 3 14h9l-1 8 10-12h-9l1-8z"/></svg>',
  };

  // usage traffic light: < 80% ok, < 95% warn, >= 95% hot (both modes)
  function usageClass(pct) {
    if (pct == null || Number.isNaN(pct)) return "";
    if (pct >= 95) return "v-hot";
    if (pct >= 80) return "v-warn";
    return "v-ok";
  }

  function setUsage(el, pct) {
    if (!el) return;
    const cls = usageClass(pct);
    el.classList.remove("v-ok", "v-warn", "v-hot");
    if (cls) el.classList.add(cls);
  }

  function setBar(fill, pct) {
    if (!fill) return;
    fill.style.width = `${Math.min(100, Math.max(0, pct || 0)).toFixed(1)}%`;
    fill.classList.remove("v-warn", "v-hot");
    if (pct >= 95) fill.classList.add("v-hot");
    else if (pct >= 80) fill.classList.add("v-warn");
  }

  function footItem(html, muted = false) {
    return `<span class="metric-foot-item${muted ? " muted" : ""}">${html}</span>`;
  }

  function push(arr, v) {
    if (v === undefined || Number.isNaN(v)) v = null;
    if (v === null) {
      // hold the last value flat until a new one is parsed: the graph stays
      // uniform with no data gaps (leading nulls stay null — nothing yet)
      for (let i = arr.length - 1; i >= 0; i--) {
        if (arr[i] != null) { v = arr[i]; break; }
      }
    }
    arr.push(v);
    if (arr.length > HISTORY) arr.shift();
  }

  /* ------------------------------ sparkline ------------------------------ */

  function drawSpark(canvas, values, opts = {}) {
    if (!canvas) return;
    const dpr = window.devicePixelRatio || 1;
    const w = canvas.clientWidth || 0;
    const h = canvas.clientHeight || 0;
    if (!w || !h) return;
    if (canvas.width !== Math.round(w * dpr) || canvas.height !== Math.round(h * dpr)) {
      canvas.width = Math.round(w * dpr);
      canvas.height = Math.round(h * dpr);
    }
    const ctx = canvas.getContext("2d");
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, w, h);
    if (values.length < 2) return;

    const nums = [];
    values.forEach((v) => { if (v != null) nums.push(v); });
    if (nums.length < 2) return;
    const max = opts.max != null ? opts.max : Math.max(...nums, 0.001);
    const span = max || 1;
    const stepX = w / (HISTORY - 1);
    const x0 = w - (values.length - 1) * stepX;
    // topPad: px reserved at the top of the canvas where data does not reach
    // (graphs mode: the name/value head row overlays that space)
    const topPad = opts.topPad || 0;
    const areaH = Math.max(h - topPad - 3, 1);
    const yOf = (v) => topPad + 1 + (1 - Math.min(Math.max(v, 0), max) / span) * areaH;

    // faint reference grid: 0% at the card bottom, one line every 10%
    if (opts.grid) {
      ctx.beginPath();
      for (let p = 0; p <= 100; p += 10) {
        const y = Math.round(yOf(p * max / 100)) + 0.5;
        ctx.moveTo(0, y);
        ctx.lineTo(w, y);
      }
      ctx.strokeStyle = "rgba(255, 255, 255, 0.07)";
      ctx.lineWidth = 1;
      ctx.stroke();
    }

    // nulls are gaps: draw each contiguous run of values as its own segment
    const runs = [];
    let run = [];
    values.forEach((v, i) => {
      if (v == null) {
        if (run.length) runs.push(run);
        run = [];
      } else {
        run.push([i, v]);
      }
    });
    if (run.length) runs.push(run);
    if (!runs.length) return;

    for (const r of runs) {
      ctx.beginPath();
      r.forEach(([i, v], k) => {
        const x = x0 + i * stepX;
        if (k === 0) ctx.moveTo(x, yOf(v));
        else ctx.lineTo(x, yOf(v));
      });
      ctx.lineTo(x0 + r[r.length - 1][0] * stepX, h);
      ctx.lineTo(x0 + r[0][0] * stepX, h);
      ctx.closePath();
      ctx.fillStyle = opts.fill || "rgba(246, 94, 0, 0.14)";
      ctx.fill();

      ctx.beginPath();
      r.forEach(([i, v], k) => {
        const x = x0 + i * stepX;
        if (k === 0) ctx.moveTo(x, yOf(v));
        else ctx.lineTo(x, yOf(v));
      });
      ctx.strokeStyle = opts.color || "#f65e00";
      ctx.lineWidth = 1.5;
      ctx.stroke();
    }
  }

  /* ------------------------------ display mode --------------------------- */

  function applyMode(style) {
    if (style === mode) return;
    mode = style;
    const grid = $("metrics-grid");
    if (grid) {
      grid.classList.toggle("mode-bar", mode === "bar");
      grid.classList.toggle("mode-graph", mode === "graph");
    }
    for (const key of Object.keys(gpuEls)) {
      const g = lastGpus.find((x) => Math.round(x.index) === Number(key));
      if (g) renderGpuFoot(g);
    }
    redrawAll();
  }

  /* ------------------------------ GPU cards ------------------------------ */

  // head-row height (+ gap) of a graphs-mode card: the graph data stops
  // just below the name/value row
  function bleedTopPad(card) {
    const head = card.querySelector(":scope > .card-head");
    return (head ? head.clientHeight : 30) + 8;
  }

  function buildGpuCards(gpus) {
    const wrap = $("gpu-cards");
    if (!wrap) return;
    wrap.innerHTML = "";
    for (const key of Object.keys(gpuHist)) delete gpuHist[key];
    for (const key of Object.keys(gpuEls)) delete gpuEls[key];

    for (const g of gpus) {
      const i = Math.round(g.index);
      const card = document.createElement("div");
      card.className = "card metric-card metric-card--spark";
      card.innerHTML = `
        <canvas class="spark spark-bleed"></canvas>
        <div class="card-head">
          <div class="gpu-id">
            <h2>GPU ${i}</h2>
            <span class="gpu-id-sub"><span class="gpu-name"></span><span class="gpu-util-inline" hidden></span></span>
          </div>
          <span class="metric-value gpu-util" hidden>—</span>
        </div>
        <div class="metric-bar">
          <div class="metric-bar-nums">
            <span class="metric-bar-main"></span>
            <span class="metric-bar-pct"></span>
          </div>
          <div class="metric-bar-track"><div class="metric-bar-fill"></div></div>
        </div>
        <div class="metric-foot"></div>`;
      wrap.appendChild(card);
      gpuHist[i] = { util: [] };
      gpuEls[i] = {
        card: card,
        name: card.querySelector(".gpu-name"),
        utilInline: card.querySelector(".gpu-util-inline"),
        util: card.querySelector(".gpu-util"),
        nums: card.querySelector(".metric-bar-nums"),
        barMain: card.querySelector(".metric-bar-main"),
        barPct: card.querySelector(".metric-bar-pct"),
        barFill: card.querySelector(".metric-bar-fill"),
        spark: card.querySelector("canvas"),
        foot: card.querySelector(":scope > .metric-foot"),
      };
    }
  }

  function renderGpuFoot(g) {
    const els = gpuEls[Math.round(g.index)];
    if (!els) return;
    const temp = g.temperature_c != null
      ? footItem(`${ICONS.temp}${g.temperature_c.toFixed(0)} °C`)
      : footItem(`${ICONS.temp}—`, true);
    const power = g.power_w != null
      ? footItem(`${ICONS.power}${g.power_w.toFixed(0)}${g.power_limit_w ? ` / ${g.power_limit_w.toFixed(0)}` : ""} W`)
      : footItem(`${ICONS.power}—`, true);
    let vram = "";
    if (mode === "graph") {
      // A3: graphs-mode foot = temp (left) + VRAM (center) + power (right)
      vram = g.vram_total_mb
        ? footItem(`${(g.vram_used_mb / 1024).toFixed(1)} / ${(g.vram_total_mb / 1024).toFixed(1)} GB`)
        : footItem("—", true);
    }
    els.foot.innerHTML = `${temp}${vram}${power}`;
  }

  function updateGpus(gpus) {
    lastGpus = gpus;
    if (gpus.length !== lastGpuCount) {
      lastGpuCount = gpus.length;
      buildGpuCards(gpus);
    }
    for (const g of gpus) {
      const i = Math.round(g.index);
      const els = gpuEls[i];
      const h = gpuHist[i];
      if (!els || !h) continue;
      push(h.util, g.util_percent);
      if (mode === "graph") {
        drawSpark(els.spark, h.util, { max: 100, topPad: bleedTopPad(els.card), grid: true });
      }
      if (g.name) els.name.textContent = g.name;
      const util = g.util_percent == null ? null : g.util_percent.toFixed(0);

      if (mode === "bar") {
        // util % is a small secondary value next to the model name
        els.util.hidden = true;
        els.utilInline.hidden = !util;
        els.utilInline.textContent = util != null ? `${util}%` : "";
        // the VRAM bar is the centerpiece: values + % above it
        if (g.vram_total_mb) {
          const used = (g.vram_used_mb ?? 0) / 1024;
          const tot = g.vram_total_mb / 1024;
          // (#78) always a bounded whole number: used can momentarily
          // exceed total (driver accounting) and bad data must never turn
          // into 1e308% — render "—" instead
          const ratio = (g.vram_used_mb ?? 0) / g.vram_total_mb;
          const pct = Number.isFinite(ratio)
            ? Math.min(100, Math.max(0, Math.round(ratio * 100)))
            : null;
          els.nums.style.display = "";
          els.barMain.textContent = `${used.toFixed(1)} / ${tot.toFixed(1)} GB`;
          els.barPct.textContent = pct == null ? "—" : `${pct}%`;
          setUsage(els.barPct, pct);
          setBar(els.barFill, pct);
        } else {
          els.nums.style.display = "none";
          setBar(els.barFill, 0);
        }
      } else {
        els.utilInline.hidden = true;
        els.util.hidden = !util;
        els.util.textContent = util != null ? `${util}%` : "—";
        setUsage(els.util, g.util_percent);
        els.nums.style.display = "none";
      }
      renderGpuFoot(g);
    }
  }

  /* ------------------------------ inference ------------------------------ */

  // per-slot context color: green → yellow → orange → red as the % rises
  function ctxColor(pct) {
    const p = Math.min(100, Math.max(0, pct));
    return `hsl(${Math.round(120 - 1.2 * p)}, 80%, 52%)`;
  }

  function updateInference(inf) {
    const list = $("slot-list");
    const nums = $("ctx-detail");
    const fill = $("ctx-fill");
    if (!list || !nums || !fill) return;
    if (!inf || !inf.ok) {
      list.innerHTML = "";
      nums.textContent = "—";
      fill.style.width = "0%";
      fill.classList.remove("v-warn");
      return;
    }
    const pct = inf.ctx_total ? (inf.ctx_used / inf.ctx_total) * 100 : 0;
    fill.style.width = `${pct.toFixed(1)}%`;
    // context is capacity, not health: neutral, warn at >= 95%
    fill.classList.toggle("v-warn", pct >= 95);
    nums.textContent = inf.ctx_total
      ? `${inf.ctx_used.toLocaleString()} / ${inf.ctx_total.toLocaleString()} · ${pct.toFixed(0)}%`
      : "—";
    list.innerHTML = "";
    for (const s of inf.slots) {
      const spct = s.n_ctx ? Math.min(100, (s.used / s.n_ctx) * 100) : 0;
      const row = document.createElement("div");
      row.className = "slot-item";
      row.innerHTML = `
        <span class="slot-id">slot ${s.id}${s.speculative ? " ·spec" : ""}</span>
        <div class="slot-track"><div class="slot-fill${s.busy ? "" : " idle"}"></div></div>
        <span class="slot-nums">${s.busy ? `${s.used.toLocaleString()} / ${s.n_ctx.toLocaleString()}` : "idle"}</span>`;
      const slotFill = row.querySelector(".slot-fill");
      slotFill.style.width = `${spct.toFixed(1)}%`;
      if (s.busy) slotFill.style.background = ctxColor(spct);
      list.appendChild(row);
    }
  }

  /* ------------------------------ update ---------------------------------- */

  function update(data) {
    if (!data) return;
    // first live sample: replace the skeleton placeholders in place (#58)
    const grid = $("metrics-grid");
    if (grid) grid.classList.remove("sk");
    applyMode(data.usage_style || "graph");

    const cpu = data.cpu || {};
    const ram = data.ram || {};

    push(hist.cpu, cpu.total);
    push(hist.ram, ram.percent);
    if (mode === "graph") {
      drawSpark($("cpu-spark"), hist.cpu, { max: 100, topPad: bleedTopPad($("cpu-card")), grid: true });
      drawSpark($("ram-spark"), hist.ram, { max: 100, topPad: bleedTopPad($("ram-card")), grid: true });
    }

    const cpuTotal = $("cpu-total");
    if (cpuTotal) cpuTotal.textContent = `${(cpu.total ?? 0).toFixed(0)}%`;
    setUsage(cpuTotal, cpu.total);
    setBar($("cpu-bar-fill"), cpu.total);
    const cores = cpu.per_core ? cpu.per_core.length : null;
    $("cpu-cores").textContent = cores ? `${cores} cores` : "—";
    const ghzEl = $("cpu-ghz");
    const ghzItem = $("cpu-ghz-item");
    if (cpu.freq_ghz != null) {
      ghzItem.style.display = "";
      ghzItem.classList.remove("muted");
      ghzEl.textContent = `${cpu.freq_ghz.toFixed(2)} GHz`;
    } else {
      ghzItem.style.display = "none";
    }
    // CPU temp/power: only shown where the OS exposes a sensor (Linux
    // sysfs). Windows has none without admin — hidden, not faked (#61).
    const sensors = data.cpu_sensors || {};
    const tempItem = $("cpu-temp-item");
    if (tempItem) {
      if (sensors.temp_c != null) {
        tempItem.style.display = "";
        $("cpu-temp").textContent = `${sensors.temp_c.toFixed(0)} °C`;
      } else tempItem.style.display = "none";
    }
    const powerItem = $("cpu-power-item");
    if (powerItem) {
      if (sensors.power_w != null) {
        powerItem.style.display = "";
        $("cpu-power").textContent = `${sensors.power_w.toFixed(0)} W`;
      } else powerItem.style.display = "none";
    }

    const ramValue = $("ram-value");
    const ramDetail = $("ram-detail");
    if (ramValue) ramValue.textContent = `${(ram.percent ?? 0).toFixed(0)}%`;
    setUsage(ramValue, ram.percent);
    setBar($("ram-bar-fill"), ram.percent);
    if (ramDetail) {
      ramDetail.textContent = ram.total_gb ? `${ram.used_gb} / ${ram.total_gb} GB` : "";
      ramDetail.classList.toggle("muted", !ram.total_gb);
    }

    updateGpus(data.gpus || []);

    const inf = data.inference && data.inference.ok ? data.inference : null;
    const promptEl = $("prompt-tps");
    const genEl = $("gen-tps");
    const stateEl = $("infer-state");
    const draftCell = $("draft-cell");
    if (inf) {
      promptEl.textContent = inf.prompt_tps == null ? "—" : inf.prompt_tps.toFixed(1);
      genEl.textContent = inf.gen_tps == null ? "—" : inf.gen_tps.toFixed(1);
      const slots = inf.slots || [];
      const busy = slots.some((s) => s.busy);
      if (data.preset_slots != null && inf.n_slots && inf.n_slots !== data.preset_slots) {
        // The preset's slot setting is not what the running server has —
        // it was started with other settings and needs a restart to apply.
        stateEl.textContent = `server has ${inf.n_slots} slot${inf.n_slots > 1 ? "s" : ""} · preset wants ${data.preset_slots} — restart to apply`;
        stateEl.classList.remove("muted");
        stateEl.classList.add("slots-mismatch");
      } else {
        stateEl.textContent = `${busy ? "generating" : "idle"} · ${inf.n_slots ?? "?"} slot${(inf.n_slots ?? 0) > 1 ? "s" : ""}`;
        stateEl.classList.remove("muted", "slots-mismatch");
      }
      if (inf.last_seq != null && inf.last_seq !== lastSeq) {
        lastSeq = inf.last_seq;
        if ((inf.draft_proposed || 0) > 0) {
          const rate = (inf.draft_accepted / inf.draft_proposed) * 100;
          if (draftCell) {
            draftCell.hidden = false;
            $("draft-rate").textContent = `${rate.toFixed(1)}%`;
          }
        } else if (draftCell) {
          draftCell.hidden = true;
        }
      }
    } else {
      promptEl.textContent = "—";
      genEl.textContent = "—";
      stateEl.textContent = "no server";
      stateEl.classList.add("muted");
      stateEl.classList.remove("slots-mismatch");
      if (draftCell) draftCell.hidden = true;
    }
    updateInference(inf);
  }

  function redrawAll() {
    if (mode !== "graph") return;
    drawSpark($("cpu-spark"), hist.cpu, { max: 100, topPad: bleedTopPad($("cpu-card")), grid: true });
    drawSpark($("ram-spark"), hist.ram, { max: 100, topPad: bleedTopPad($("ram-card")), grid: true });
    for (const key of Object.keys(gpuEls)) {
      drawSpark(gpuEls[key].spark, gpuHist[key].util, { max: 100, topPad: bleedTopPad(gpuEls[key].card), grid: true });
    }
  }

  let resizeTimer = null;

  function init() {
    updateGpus([]);
    applyMode("graph");
    window.addEventListener("resize", () => {
      clearTimeout(resizeTimer);
      resizeTimer = setTimeout(redrawAll, 150);
    });
  }

  return { init, update };
})();
