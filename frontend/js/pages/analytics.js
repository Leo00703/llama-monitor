"use strict";

/* llama-monitor — analytics page: history summary, charts, model breakdown */

const Analytics = (() => {
  const RANGES = ["day", "week", "month", "year", "all"];
  let range = "week";
  let busy = false;

  const $ = (id) => document.getElementById(id);

  function fmtNum(v, digits = 0) {
    if (v === null || v === undefined || Number.isNaN(v)) return "—";
    const n = Number(v);
    if (n !== 0 && Math.abs(n) >= 1e6) return (n / 1e6).toFixed(1) + "M";
    if (n !== 0 && Math.abs(n) >= 1e4) return (n / 1e3).toFixed(1) + "k";
    return n.toLocaleString(undefined, { maximumFractionDigits: digits });
  }

  function shortModel(path) {
    if (!path) return "(unknown)";
    const parts = String(path).split(/[\\/]/);
    return parts[parts.length - 1] || path;
  }

  function cardHtml(label, value, sub = "", valueClass = "") {
    return `
      <div class="card metric-card">
        <div class="card-head"><h2>${label}</h2><span class="metric-value${valueClass ? " " + valueClass : ""}">${value}</span></div>
        <div class="muted small">${sub}</div>
      </div>`;
  }

  function renderSummary(s) {
    const energy = s.has_energy
      ? `${fmtNum(s.energy_wh, 2)} Wh`
      : "no GPU power data";
    const cost = s.cost_eur != null ? `€ ${s.cost_eur.toFixed(4)}` : "—";
    const cost1m = s.cost_per_1m != null ? `€ ${s.cost_per_1m.toFixed(2)} / 1M` : "";
    const failed = s.failed || 0;
    const attempts = s.requests + failed;
    const failedSub = failed
      ? `${attempts} attempts · ${((failed / attempts) * 100).toFixed(1)}% failed`
      : "none in this range";
    $("analytics-cards").innerHTML = [
      cardHtml("Requests", fmtNum(s.requests), range),
      cardHtml("Failed requests", fmtNum(failed), failedSub, failed ? "err" : ""),
      cardHtml("Tokens generated", fmtNum(s.gen_tokens), `prompt ${fmtNum(s.prompt_tokens)}`),
      cardHtml("Energy", energy, s.has_energy ? "GPU power estimate" : "nvidia-smi power not sampled"),
      cardHtml("Est. cost", cost, cost1m),
      cardHtml("Avg gen speed", s.avg_gen_tps != null ? `${s.avg_gen_tps.toFixed(1)}` : "—", "tok/s"),
      cardHtml("Peak gen speed", s.max_gen_tps != null ? `${s.max_gen_tps.toFixed(1)}` : "—", "tok/s"),
    ].join("");
  }

  function drawChart(canvas, values, labels, opts = {}) {
    if (!canvas) return;
    const dpr = window.devicePixelRatio || 1;
    const w = canvas.clientWidth || 0;
    const h = canvas.clientHeight || 0;
    if (!w || !h || !values.length) return;
    if (canvas.width !== Math.round(w * dpr) || canvas.height !== Math.round(h * dpr)) {
      canvas.width = Math.round(w * dpr);
      canvas.height = Math.round(h * dpr);
    }
    const ctx = canvas.getContext("2d");
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, w, h);

    const padL = 46, padB = 20, padT = 8, padR = 8;
    const cw = w - padL - padR;
    const ch = h - padT - padB;
    const n = values.length;
    const nums = values.filter((v) => v != null);
    if (!nums.length) return;
    const max = opts.max != null ? opts.max : Math.max(...nums) * 1.1 || 1;

    ctx.font = "11px " + getComputedStyle(document.body).fontFamily;
    ctx.textBaseline = "middle";
    ctx.fillStyle = "#a1a1a1";
    ctx.strokeStyle = "rgba(255,255,255,0.07)";
    ctx.lineWidth = 1;
    for (let g = 0; g <= 3; g++) {
      const v = (max / 3) * g;
      const y = padT + ch - (v / max) * ch;
      ctx.beginPath();
      ctx.moveTo(padL, y);
      ctx.lineTo(w - padR, y);
      ctx.stroke();
      ctx.textAlign = "right";
      ctx.fillText(fmtNum(v), padL - 6, y);
    }

    const stepX = cw / n;
    const xOf = (i) => padL + i * stepX;
    const yOf = (v) => padT + ch - (Math.max(0, Math.min(v, max)) / max) * ch;

    if (opts.mode === "bar") {
      const bw = Math.max(1, stepX * 0.62);
      ctx.fillStyle = opts.color || "#1447e6";
      values.forEach((v, i) => {
        if (v == null) return;
        const y = yOf(v);
        ctx.fillRect(xOf(i) + (stepX - bw) / 2, y, bw, padT + ch - y);
      });
    } else {
      ctx.strokeStyle = opts.color || "#1447e6";
      ctx.lineWidth = 1.5;
      ctx.beginPath();
      let started = false;
      values.forEach((v, i) => {
        if (v == null) { started = false; return; }
        const x = xOf(i) + stepX / 2;
        const y = yOf(v);
        if (!started) { ctx.moveTo(x, y); started = true; }
        else ctx.lineTo(x, y);
      });
      ctx.stroke();
    }

    const shown = Math.min(Math.max(2, Math.floor(w / 72)), n);
    ctx.fillStyle = "#a1a1a1";
    ctx.textAlign = "center";
    for (let k = 0; k < shown; k++) {
      const i = Math.round((k * (n - 1)) / Math.max(1, shown - 1));
      const label = labels[i] != null ? labels[i] : "";
      ctx.fillText(label, xOf(i) + stepX / 2, h - padB / 2);
    }
  }

  let lastTs = null;

  function drawTimeseries() {
    if (!lastTs) return;
    const buckets = lastTs.buckets || [];
    const labels = buckets.map((b) => b.label);
    drawChart(
      $("an-tokens-chart"),
      buckets.map((b) => b.gen_tokens || null),
      labels,
      { mode: "bar", color: "#1447e6" },
    );
    drawChart(
      $("an-speed-chart"),
      buckets.map((b) => b.avg_gen_tps != null ? b.avg_gen_tps : null),
      labels,
      { mode: "line", color: "#fe9a00" },
    );
  }

  function renderTimeseries(ts) {
    lastTs = ts;
    drawTimeseries();
    const buckets = ts.buckets || [];
    const total = buckets.reduce((a, b) => a + (b.gen_tokens || 0), 0);
    $("an-tokens-sub").textContent = `${fmtNum(total)} tokens · ${ts.bucket}`;
    $("an-speed-sub").textContent = "tok/s";
  }

  function renderModels(models) {
    const bars = $("an-models-bars");
    const empty = $("an-models-empty");
    const tbody = $("an-models-tbody");
    bars.innerHTML = "";
    tbody.innerHTML = "";
    if (!models.length) { empty.classList.remove("hidden"); return; }
    empty.classList.add("hidden");

    const maxGen = Math.max(...models.map((m) => m.gen_tokens || 0), 1);
    for (const m of models.slice(0, 5)) {
      const row = document.createElement("div");
      row.className = "model-bar-row";
      row.innerHTML = `
        <span class="model-bar-name" title="${UI.esc(m.model)}">${UI.esc(shortModel(m.model))}</span>
        <div class="model-bar-track">
          <div class="model-bar-fill" style="width:${Math.max(2, ((m.gen_tokens || 0) / maxGen) * 100)}%"></div>
        </div>
        <span class="model-bar-val">${fmtNum(m.gen_tokens)}</span>`;
      bars.appendChild(row);
    }
    for (const m of models) {
      const tr = document.createElement("tr");
      tr.innerHTML = `
        <td title="${UI.esc(m.model)}">${UI.esc(shortModel(m.model))}</td>
        <td>${fmtNum(m.requests)}</td>
        <td>${fmtNum(m.gen_tokens)}</td>
        <td>${m.avg_gen_tps != null ? m.avg_gen_tps.toFixed(1) : "—"}</td>
        <td>${m.max_gen_tps != null ? m.max_gen_tps.toFixed(1) : "—"}</td>
        <td>${m.cost_per_1m != null ? m.cost_per_1m.toFixed(2) : "—"}</td>`;
      tbody.appendChild(tr);
    }
  }

  function renderRecords(records) {
    const tbody = $("an-records-tbody");
    tbody.innerHTML = "";
    $("an-records-count").textContent = records.length ? `last ${records.length}` : "";
    if (!records.length) {
      const tr = document.createElement("tr");
      tr.innerHTML = `<td colspan="7" class="muted small">No requests recorded in this range yet.</td>`;
      tbody.appendChild(tr);
      return;
    }
    for (const r of records) {
      const tr = document.createElement("tr");
      const d = new Date(r.ts * 1000);
      const p2 = (n) => String(n).padStart(2, "0");
      const when = `<span class="t-full">${d.toLocaleString()}</span><span class="t-short">${p2(d.getMonth() + 1)}/${p2(d.getDate())} ${p2(d.getHours())}:${p2(d.getMinutes())}</span>`;
      const dur = r.total_ms != null ? `${(r.total_ms / 1000).toFixed(1)}s` : "—";
      const energy = r.energy_wh != null ? `${r.energy_wh.toFixed(2)} Wh` : "—";
      tr.innerHTML = `
        <td>${when}</td>
        <td title="${UI.esc(r.model)}">${UI.esc(shortModel(r.model))}</td>
        <td>${fmtNum(r.prompt_tokens)}</td>
        <td>${fmtNum(r.gen_tokens)}</td>
        <td>${r.gen_tps != null ? r.gen_tps.toFixed(1) : "—"}</td>
        <td>${dur}</td>
        <td>${energy}</td>`;
      tbody.appendChild(tr);
    }
  }

  async function refresh() {
    if (busy) return;
    busy = true;
    try {
      const [sumRes, tsRes, modelsRes, recordsRes] = await Promise.all([
        API.get(`/api/analytics/summary?range=${range}`),
        API.get(`/api/analytics/timeseries?range=${range}`),
        API.get(`/api/analytics/models?range=${range}`),
        API.get(`/api/analytics/records?range=${range}&limit=100`),
      ]);
      if (sumRes.ok) renderSummary(sumRes.summary);
      if (tsRes.ok) renderTimeseries(tsRes);
      if (modelsRes.ok) renderModels(modelsRes.models || []);
      if (recordsRes.ok) renderRecords(recordsRes.records || []);
    } catch (e) {
      UI.toast(`analytics load failed: ${e}`, "err");
    } finally {
      busy = false;
    }
  }

  /* sliding highlight for the range selector: a pill that follows the
     active button (offset-based, so it also works when the group wraps
     onto two rows on narrow screens) */
  function moveRangeSlider(animate) {
    const group = $("analytics-range");
    const btn = group.querySelector(".range-btn.active");
    const slider = group.querySelector(".range-slider");
    if (!group || !btn || !slider) return;
    const x = btn.offsetLeft - group.clientLeft;
    const y = btn.offsetTop - group.clientTop;
    if (!animate) slider.style.transition = "none";
    slider.style.width = `${btn.offsetWidth}px`;
    slider.style.height = `${btn.offsetHeight}px`;
    slider.style.transform = `translate(${x}px, ${y}px)`;
    if (!animate) {
      void slider.offsetWidth; // flush the jump, then restore the CSS transition
      slider.style.transition = "";
    }
  }

  function setRange(r) {
    if (!RANGES.includes(r) || r === range) return;
    range = r;
    document.querySelectorAll("#analytics-range .range-btn").forEach((b) => {
      b.classList.toggle("active", b.dataset.range === r);
    });
    moveRangeSlider(true);
    refresh();
  }

  let resizeTimer = null;

  function init() {
    document.querySelectorAll("#analytics-range .range-btn").forEach((b) => {
      b.addEventListener("click", () => setRange(b.dataset.range));
    });
    const group = $("analytics-range");
    moveRangeSlider(false);
    // reposition on layout changes (page shown, window resize, wrapping)
    if ("ResizeObserver" in window) {
      new ResizeObserver(() => moveRangeSlider(false)).observe(group);
    }
    window.addEventListener("resize", () => {
      clearTimeout(resizeTimer);
      resizeTimer = setTimeout(() => { drawTimeseries(); moveRangeSlider(false); }, 150);
    });
    $("btn-analytics-export").addEventListener("click", () => {
      if (!RANGES.includes(range)) return;
      window.location = `/api/analytics/export?range=${range}`;
    });
  }

  return { init, refresh, setRange };
})();
