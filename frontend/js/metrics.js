"use strict";

/* llama-monitor — resource + inference metrics: history, sparklines, cards */

const Metrics = (() => {
  const HISTORY = 120;
  const hist = { cpu: [], ram: [] };
  const gpuHist = {};
  const gpuEls = {};
  let lastGpuCount = -1;
  let lastSeq = 0;

  const $ = (id) => document.getElementById(id);

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

    const nums = runs.flat().map((p) => p[1]);
    const max = opts.max != null ? opts.max : Math.max(...nums, 0.001);
    const span = max || 1;
    const stepX = w / (HISTORY - 1);
    const x0 = w - (values.length - 1) * stepX;
    // topPad: px reserved at the top of the canvas where data does not reach
    // (full-bleed cards: the name/value head row overlays that space)
    const topPad = opts.topPad || 0;
    const areaH = Math.max(h - topPad - 3, 1);
    const yOf = (v) => topPad + 1 + (1 - Math.min(Math.max(v, 0), max) / span) * areaH;

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

  /* ------------------------------ GPU cards ------------------------------ */

  // head-row height (+ gap) of a full-bleed card: the graph data stops
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
      card.className = "card metric-card metric-card--graph";
      card.innerHTML = `
        <canvas class="spark spark-bleed"></canvas>
        <div class="card-head">
          <div class="gpu-id">
            <h2>GPU ${i}</h2>
            <span class="muted small gpu-name"></span>
          </div>
          <span class="metric-value gpu-util">—</span>
        </div>
        <div class="metric-foot gpu-foot"></div>`;
      wrap.appendChild(card);
      gpuHist[i] = { util: [] };
      gpuEls[i] = {
        card: card,
        name: card.querySelector(".gpu-name"),
        util: card.querySelector(".gpu-util"),
        spark: card.querySelector("canvas"),
        foot: card.querySelector(".gpu-foot"),
      };
    }
  }

  function updateGpus(gpus) {
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
      drawSpark(els.spark, h.util, { max: 100, topPad: bleedTopPad(els.card) });
      if (g.name) els.name.textContent = g.name;
      els.util.textContent = `${(g.util_percent ?? 0).toFixed(0)}%`;

      let vram = "";
      if (g.vram_total_mb) {
        const used = (g.vram_used_mb ?? 0) / 1024;
        const tot = g.vram_total_mb / 1024;
        const pct = Math.round((g.vram_used_mb / g.vram_total_mb) * 100);
        vram =
          `<span class="gpu-stat"><span class="gpu-lbl">VRAM</span>` +
          `<span class="gpu-val">${used.toFixed(1)} / ${tot.toFixed(1)} GB</span>` +
          `<span class="gpu-pct${pct >= 90 ? " hot" : ""}">${pct}%</span></span>`;
      }
      let temp = "";
      if (g.temperature_c != null) {
        temp =
          `<span class="gpu-stat"><span class="gpu-lbl">Temp</span>` +
          `<span class="gpu-val">${g.temperature_c.toFixed(0)} °C</span></span>`;
      }
      let power = "";
      if (g.power_w != null) {
        power =
          `<span class="gpu-stat"><span class="gpu-lbl">Power</span>` +
          `<span class="gpu-val">${g.power_w.toFixed(0)}${g.power_limit_w ? ` / ${g.power_limit_w.toFixed(0)}` : ""} W</span></span>`;
      }
      const row1 = vram ? `<div class="gpu-row">${vram}</div>` : "";
      const row2 = temp || power ? `<div class="gpu-row">${temp}${power}</div>` : "";
      els.foot.innerHTML = row1 + row2;
    }
  }

  /* ------------------------------ inference ------------------------------ */

  // context bar color: green → yellow → orange → red as the % rises
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
      return;
    }
    const pct = inf.ctx_total ? (inf.ctx_used / inf.ctx_total) * 100 : 0;
    fill.style.width = `${pct.toFixed(1)}%`;
    fill.style.background = ctxColor(pct);
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
    const cpu = data.cpu || {};
    const ram = data.ram || {};

    push(hist.cpu, cpu.total);
    push(hist.ram, ram.percent);
    drawSpark($("cpu-spark"), hist.cpu, { max: 100, topPad: bleedTopPad($("cpu-card")) });
    drawSpark($("ram-spark"), hist.ram, { max: 100, topPad: bleedTopPad($("ram-card")) });

    const cpuTotal = $("cpu-total");
    const ramValue = $("ram-value");
    const ramDetail = $("ram-detail");
    if (cpuTotal) cpuTotal.textContent = `${(cpu.total ?? 0).toFixed(0)}%`;
    if (ramValue) ramValue.textContent = `${(ram.percent ?? 0).toFixed(0)}%`;
    if (ramDetail) ramDetail.textContent = ram.total_gb ? `${ram.used_gb} / ${ram.total_gb} GB` : "";

    updateGpus(data.gpus || []);

    const inf = data.inference && data.inference.ok ? data.inference : null;
    const promptEl = $("prompt-tps");
    const genEl = $("gen-tps");
    const stateEl = $("infer-state");
    const draftCell = $("draft-cell");
    if (inf) {
      promptEl.textContent = inf.prompt_tps == null ? "—" : inf.prompt_tps.toFixed(1);
      genEl.textContent = inf.gen_tps == null ? "—" : inf.gen_tps.toFixed(1);
      stateEl.textContent = "live";
      stateEl.classList.remove("muted");
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
      if (draftCell) draftCell.hidden = true;
    }
    updateInference(inf);
  }

  function redrawAll() {
    drawSpark($("cpu-spark"), hist.cpu, { max: 100, topPad: bleedTopPad($("cpu-card")) });
    drawSpark($("ram-spark"), hist.ram, { max: 100, topPad: bleedTopPad($("ram-card")) });
    for (const key of Object.keys(gpuEls)) {
      drawSpark(gpuEls[key].spark, gpuHist[key].util, { max: 100, topPad: bleedTopPad(gpuEls[key].card) });
    }
  }

  let resizeTimer = null;

  function init() {
    updateGpus([]);
    window.addEventListener("resize", () => {
      clearTimeout(resizeTimer);
      resizeTimer = setTimeout(redrawAll, 150);
    });
  }

  return { init, update };
})();
