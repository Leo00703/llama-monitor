"""Resource and inference metrics collection.

- CPU/RAM: psutil
- GPU: nvidia-smi (one entry per detected GPU, empty list when absent)
- Inference: llama-server /metrics (Prometheus counters -> live tok/s)
  and /slots (per-slot context usage)

All collection is async-safe: blocking calls run via asyncio.to_thread.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import re
import shutil
import subprocess
import time
from typing import Any, Optional

import httpx
import psutil

from .config import no_window_kwargs

log = logging.getLogger("llama-monitor.metrics")

NVIDIA_QUERY = (
    "index,name,utilization.gpu,memory.used,memory.total,"
    "temperature.gpu,power.draw,power.limit,"
    "clocks.current.graphics,clocks.current.memory"
)

# Prometheus metric names differ across llama.cpp versions; try in order.
_PROMETHEUS_NAMES = {
    "prompt_tokens": (
        "llamacpp:prompt_tokens_total",
        "llama_server_prompt_tokens_processed_total",
    ),
    "gen_tokens": (
        "llamacpp:tokens_predicted_total",
        "llama_server_tokens_generated_total",
    ),
}

_LINE_RE = re.compile(r"^([A-Za-z_:][A-Za-z0-9_:]*)\s+([-+]?[0-9]*\.?[0-9]+[eE]?[-+]?[0-9]*)\s*$")


def parse_prometheus(text: str) -> dict[str, Optional[float]]:
    """Extract the counters we need from a Prometheus text exposition."""
    found: dict[str, Optional[str]] = {}
    for line in text.splitlines():
        m = _LINE_RE.match(line.strip())
        if not m:
            continue
        name, value = m.group(1), m.group(2)
        for key, candidates in _PROMETHEUS_NAMES.items():
            if name == candidates[0]:
                found[key] = value
    result: dict[str, Optional[float]] = {}
    for key, candidates in _PROMETHEUS_NAMES.items():
        raw = found.get(key)
        if raw is None:
            raw = _find_any(text, candidates)
        result[key] = float(raw) if raw is not None else None
    return result


def _find_any(text: str, candidates: tuple[str, ...]) -> Optional[str]:
    for name in candidates[1:]:
        m = re.search(rf"^{re.escape(name)}\s+([-+]?[0-9.eE+-]+)\s*$", text, re.MULTILINE)
        if m:
            return m.group(1)
    return None


def _to_float(value: str) -> Optional[float]:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def run_nvidia_smi() -> Optional[list[dict]]:
    """One dict per GPU, or None when nvidia-smi is unavailable/failed."""
    if shutil.which("nvidia-smi") is None:
        return None
    try:
        out = subprocess.run(
            ["nvidia-smi", "--query-gpu", NVIDIA_QUERY, "--format=csv,noheader,nounits"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
            # polled every 1.5s: without CREATE_NO_WINDOW a windowless build
            # flashes a console window on every poll (Windows)
            **no_window_kwargs(),
        )
        if out.returncode != 0:
            log.debug("nvidia-smi failed (rc=%s)", out.returncode)
            return None
    except (OSError, subprocess.SubprocessError):
        return None

    gpus: list[dict] = []
    for line in out.stdout.splitlines():
        parts = [p.strip() for p in line.split(",")]
        if len(parts) < 9 or parts[0] in ("", "[N/A]"):
            continue
        gpus.append(
            {
                "index": _to_float(parts[0]) or 0.0,
                "name": parts[1],
                "util_percent": _to_float(parts[2]),
                "vram_used_mb": _to_float(parts[3]),
                "vram_total_mb": _to_float(parts[4]),
                "temperature_c": _to_float(parts[5]),
                "power_w": _to_float(parts[6]),
                "power_limit_w": _to_float(parts[7]),
                "clock_core_mhz": _to_float(parts[8]),
                "clock_mem_mhz": _to_float(parts[9]) if len(parts) > 9 else None,
            }
        )
    return gpus


class MetricsCollector:
    """Polls system + inference metrics and computes live tok/s deltas."""

    def __init__(self) -> None:
        psutil.cpu_percent()
        psutil.cpu_percent(percpu=True)
        self._baseline: Optional[dict[str, Any]] = None

    async def snapshot(self, port: Optional[int]) -> dict:
        """Collect one full sample. `port` = active llama-server port (or None)."""
        per_core = psutil.cpu_percent(percpu=True)
        total = psutil.cpu_percent()
        ram = psutil.virtual_memory()
        gpus = await asyncio.to_thread(run_nvidia_smi)
        inference = await self._inference(port) if port else None
        return {
            "ts": time.time(),
            "cpu": {"total": round(total, 1), "per_core": [round(v, 1) for v in per_core]},
            "ram": {
                "used_gb": round(ram.used / 1073741824, 2),
                "total_gb": round(ram.total / 1073741824, 2),
                "percent": round(ram.percent, 1),
            },
            "gpus": gpus or [],
            "inference": inference,
        }

    async def _inference(self, port: int) -> Optional[dict]:
        base = f"http://127.0.0.1:{port}"
        try:
            async with httpx.AsyncClient(timeout=2.0) as client:
                mres = await client.get(f"{base}/metrics")
                sres = await client.get(f"{base}/slots")
        except httpx.HTTPError:
            return None
        if mres.status_code != 200 and sres.status_code != 200:
            return None

        counters = parse_prometheus(mres.text if mres.status_code == 200 else "")
        prompt_tokens = counters.get("prompt_tokens")
        gen_tokens = counters.get("gen_tokens")
        prompt_tps: Optional[float] = None
        gen_tps: Optional[float] = None
        now = time.time()

        if prompt_tokens is not None and gen_tokens is not None:
            base = self._baseline
            if (
                base is not None
                and base["port"] == port
                and prompt_tokens >= base["prompt_tokens"]
                and gen_tokens >= base["gen_tokens"]
            ):
                dt = now - base["ts"]
                if dt > 0.2:
                    prompt_tps = round((prompt_tokens - base["prompt_tokens"]) / dt, 2)
                    gen_tps = round((gen_tokens - base["gen_tokens"]) / dt, 2)
            self._baseline = {
                "ts": now,
                "port": port,
                "prompt_tokens": prompt_tokens,
                "gen_tokens": gen_tokens,
            }

        slots: list[dict] = []
        ctx_total = 0
        ctx_used = 0
        if sres.status_code == 200:
            with contextlib.suppress(ValueError):
                for s in sres.json():
                    if not isinstance(s, dict):
                        continue
                    n_ctx = int(s.get("n_ctx") or 0)
                    busy = bool(s.get("is_processing"))
                    # n_prompt_tokens persists after the request finishes (the
                    # server keeps the last value), so report it even when idle.
                    used = min(int(s.get("n_prompt_tokens") or 0), n_ctx)
                    ctx_total += n_ctx
                    ctx_used += min(used, n_ctx)
                    slots.append(
                        {
                            "id": int(s.get("id") or 0),
                            "busy": busy,
                            "speculative": bool(s.get("speculative")),
                            "n_ctx": n_ctx,
                            "used": used,
                        }
                    )

        return {
            "ok": True,
            "prompt_tps": prompt_tps,
            "gen_tps": gen_tps,
            "prompt_tokens": prompt_tokens,
            "gen_tokens": gen_tokens,
            "ctx_used": ctx_used,
            "ctx_total": ctx_total,
            "slots": slots,
        }
