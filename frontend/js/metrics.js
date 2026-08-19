"use strict";

/* llama-monitor — resource + inference metrics: history, sparklines, cards */

const Metrics = (() => {
  const HISTORY = 120;
  const hist = { cpu: [], ram: [], prompt: [], gen: [], draft: [] };
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
    const yOf = (v) => h - 1 - (Math.min(Math.max(v, 0), max) / span) * (h - 3);

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
      ctx.fillStyle = opts.fill || "rgba(125, 162, 255, 0.14)";
      ctx.fill();

      ctx.beginPath();
      r.forEach(([i, v], k) => {
        const x = x0 + i * stepX;
        if (k === 0) ctx.moveTo(x, yOf(v));
        else ctx.lineTo(x, yOf(v));
      });
      ctx.strokeStyle = opts.color || "#7da2ff";
      ctx.lineWidth = 1.5;
      ctx.stroke();
    }
  }

  /* ------------------------------ GPU cards ------------------------------ */

  function buildGpuCards(gpus) {
    const wrap = $("gpu-cards");
    if (!wrap) return;
    wrap.innerHTML = "";
    for (const key of Object.keys(gpuHist)) delete gpuHist[key];
    for (const key of Object.keys(gpuEls)) delete gpuEls[key];

    for (const g of gpus) {
      const i = Math.round(g.index);
      const card = document.createElement("div");
      card.className = "card metric-card";
      card.innerHTML = `
        <div class="card-head">
          <h2>GPU ${i}</h2>
          <span class="muted small gpu-name"></span>
        </div>
        <div class="metric-big">
          <span class="metric-value">—</span>
          <span class="muted small">util %</span>
        </div>
        <canvas class="spark"></canvas>
        <div class="metric-detail muted small"></div>`;
      wrap.appendChild(card);
      gpuHist[i] = { util: [] };
      gpuEls[i] = {
        name: card.querySelector(".gpu-name"),
        util: card.querySelector(".metric-value"),
        spark: card.querySelector("canvas"),
        detail: card.querySelector(".metric-detail"),
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
      drawSpark(els.spark, h.util, { max: 100 });
      if (g.name) els.name.textContent = g.name;
      els.util.textContent = `${(g.util_percent ?? 0).toFixed(0)}%`;

      const bits = [];
      if (g.vram_total_mb) {
        const pct = Math.round(((g.vram_used_mb ?? 0) / g.vram_total_mb) * 100);
        bits.push(`VRAM ${(g.vram_used_mb / 1024).toFixed(1)}/${(g.vram_total_mb / 1024).toFixed(1)} GB (${pct}%)`);
      }
      if (g.temperature_c != null) bits.push(`${g.temperature_c.toFixed(0)} °C`);
      if (g.power_w != null) {
        bits.push(`${g.power_w.toFixed(0)} W${g.power_limit_w ? ` / ${g.power_limit_w.toFixed(0)}` : ""}`);
      }
      els.detail.textContent = bits.join(" · ");
    }
  }

  /* ------------------------------ per-core bars --------------------------- */

  function updateCores(cores) {
    const wrap = $("cpu-cores");
    if (!wrap) return;
    if (wrap.childElementCount !== cores.length) {
      wrap.innerHTML = "";
      for (let i = 0; i < cores.length; i++) {
        const bar = document.createElement("div");
        bar.className = "core-bar";
        bar.title = `core ${i}`;
        wrap.appendChild(bar);
      }
    }
    cores.forEach((v, i) => {
      const bar = wrap.children[i];
      if (bar) bar.style.height = `${Math.max(4, Math.min(100, v))}%`;
    });
  }

  /* ------------------------------ slots ----------------------------------- */

  function updateSlots(inf) {
    const list = $("slot-list");
    const ctxDetail = $("ctx-detail");
    if (!list || !ctxDetail) return;
    if (!inf || !inf.ok) {
      list.innerHTML = "";
      ctxDetail.textContent = "";
      return;
    }
    ctxDetail.textContent = inf.ctx_total
      ? `context: ${inf.ctx_used.toLocaleString()} / ${inf.ctx_total.toLocaleString()} tokens`
      : "";
    list.innerHTML = "";
    for (const s of inf.slots) {
      const pct = s.n_ctx ? Math.min(100, Math.round((s.used / s.n_ctx) * 100)) : 0;
      const row = document.createElement("div");
      row.className = "slot-item";
      row.innerHTML = `
        <span class="slot-id">slot ${s.id}${s.speculative ? " ·spec" : ""}</span>
        <div class="slot-track"><div class="slot-fill${s.busy ? "" : " idle"}" style="width:${pct}%"></div></div>
        <span class="slot-nums">${s.busy ? `${s.used.toLocaleString()} / ${s.n_ctx.toLocaleString()}` : "idle"}</span>`;
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
    drawSpark($("cpu-spark"), hist.cpu, { max: 100 });
    drawSpark($("ram-spark"), hist.ram, { max: 100 });
    updateCores(cpu.per_core || []);

    const cpuTotal = $("cpu-total");
    const ramValue = $("ram-value");
    const ramDetail = $("ram-detail");
    if (cpuTotal) cpuTotal.textContent = `${(cpu.total ?? 0).toFixed(0)}%`;
    if (ramValue) ramValue.textContent = `${(ram.percent ?? 0).toFixed(0)}%`;
    if (ramDetail) ramDetail.textContent = ram.total_gb ? `${ram.used_gb} / ${ram.total_gb} GB` : "";

    updateGpus(data.gpus || []);

    const inf = data.inference && data.inference.ok ? data.inference : null;
    push(hist.prompt, inf ? inf.prompt_tps : null);
    push(hist.gen, inf ? inf.gen_tps : null);
    drawSpark(
      $("prompt-spark"), hist.prompt,
      { max: Math.max(...hist.prompt.filter((v) => v != null), 1), color: "#6ee7b7", fill: "rgba(110, 231, 183, 0.12)" },
    );
    drawSpark(
      $("gen-spark"), hist.gen,
      { max: Math.max(...hist.gen.filter((v) => v != null), 1), color: "#f5a524", fill: "rgba(245, 165, 36, 0.12)" },
    );
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
          push(hist.draft, rate);
          if (draftCell) {
            draftCell.hidden = false;
            $("draft-rate").textContent = `${rate.toFixed(1)}%`;
            drawSpark(
              $("draft-spark"), hist.draft,
              { max: 100, color: "#c084fc", fill: "rgba(192, 132, 252, 0.12)" },
            );
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
    updateSlots(inf);
  }

  function redrawAll() {
    drawSpark($("cpu-spark"), hist.cpu, { max: 100 });
    drawSpark($("ram-spark"), hist.ram, { max: 100 });
    for (const key of Object.keys(gpuEls)) {
      drawSpark(gpuEls[key].spark, gpuHist[key].util, { max: 100 });
    }
    drawSpark(
      $("prompt-spark"), hist.prompt,
      { max: Math.max(...hist.prompt.filter((v) => v != null), 1), color: "#6ee7b7", fill: "rgba(110, 231, 183, 0.12)" },
    );
    drawSpark(
      $("gen-spark"), hist.gen,
      { max: Math.max(...hist.gen.filter((v) => v != null), 1), color: "#f5a524", fill: "rgba(245, 165, 36, 0.12)" },
    );
    drawSpark(
      $("draft-spark"), hist.draft,
      { max: 100, color: "#c084fc", fill: "rgba(192, 132, 252, 0.12)" },
    );
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
