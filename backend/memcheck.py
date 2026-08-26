"""Memory pre-check: estimate the VRAM/RAM a preset will occupy.

Calibration-based (no weight/KV math — the real allocator decides
placement): every successful panel launch records a per-model baseline
(per-GPU memory.used right before spawn + system RAM). The estimate for a
preset is the baseline's measured footprint, with the KV part rescaled by
the context ratio (with unified KV the pool scales with -c, not with slot
count; the per-slot compute-buffer cost is small in comparison).

Baselines live in <data-dir>/memory-baselines.json, keyed by model file
name (one entry per model, newest launch wins).
"""

from __future__ import annotations

import json
import logging
import threading
import time
from typing import Any, Optional

from .config import DATA_DIR

log = logging.getLogger("llama-monitor.memcheck")

_BASELINE_PATH = DATA_DIR / "memory-baselines.json"
_lock = threading.Lock()

# projected free VRAM below this fraction of the GPU total (or this many
# MiB, whichever is larger) is considered too tight
_FREE_FRACTION = 0.05
_FREE_MIN_MB = 100.0


def _model_key(model: str) -> str:
    return model.replace("\\", "/").strip().rsplit("/", 1)[-1].lower()


def _load() -> dict:
    try:
        with open(_BASELINE_PATH, encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict) and isinstance(data.get("models"), dict):
            return data
    except (OSError, ValueError):
        pass
    return {"models": {}}


def _save(data: dict) -> None:
    try:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        with open(_BASELINE_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=1)
    except OSError as exc:
        log.warning("cannot write %s: %s", _BASELINE_PATH, exc)


def record(facts: dict, gpus: Optional[list[dict]], ram_used: int) -> None:
    """Record the baseline of a successful launch.

    `facts` — model / -c / slots / kv flags / spec / tensor-split parsed
    from the launch args; `gpus` — nvidia-smi snapshot taken right before
    spawn (used/total per GPU); `ram_used` — system RAM in bytes.
    """
    key = _model_key(facts.get("model", ""))
    if not key:
        return
    gpu_rows = []
    for g in gpus or []:
        gpu_rows.append({
            "id": int(g.get("index") or 0),
            "name": g.get("name") or "",
            "used_mb": round(float(g.get("vram_used_mb") or 0), 1),
            "total_mb": round(float(g.get("vram_total_mb") or 0), 1),
        })
    entry = {
        "ts": time.time(),
        "model": facts.get("model", ""),
        "ctx": int(facts.get("ctx") or 0),
        "slots": facts.get("slots"),
        "kv_unified": facts.get("kv_unified"),
        "cache_type_k": facts.get("cache_type_k"),
        "cache_type_v": facts.get("cache_type_v"),
        "spec_type": facts.get("spec_type") or "none",
        "tensor_split": facts.get("tensor_split") or [],
        "n_gpu_layers": facts.get("n_gpu_layers"),
        "gpus": gpu_rows,
        "ram_used_mb": round((ram_used or 0) / 1048576, 1),
    }
    with _lock:
        data = _load()
        data["models"][key] = entry
        _save(data)


def estimate(launch: dict, now_gpus: Optional[list[dict]]) -> dict:
    """Estimate the footprint of `launch` (a preset launch dict).

    `now_gpus` — current nvidia-smi snapshot (same shape as metrics.py).
    Returns a display-ready dict; never raises for missing calibration.
    """
    model = (launch.get("model") or "").strip()
    key = _model_key(model)
    with _lock:
        base = _load()["models"].get(key)
    if not base:
        return {"ok": True, "baseline": False, "model": model}

    ctx_base = int(base.get("ctx") or 0)
    ctx_want = int(launch.get("context_size") or 0)
    if ctx_want <= 0:
        return {"ok": True, "baseline": False, "model": model,
                "note": "context size is not set"}

    ratio = (ctx_want / ctx_base) if ctx_base > 0 else 1.0

    # what does llama-server currently occupy on each GPU / in RAM?
    base_by_id = {g["id"]: g for g in base.get("gpus") or []}
    layout_changed = False
    gpu_rows = []
    warn = False
    for g in now_gpus or []:
        gid = int(g.get("index") or 0)
        total = float(g.get("vram_total_mb") or 0)
        free = float(g.get("vram_total_mb") or 0) - float(g.get("vram_used_mb") or 0)
        if gid not in base_by_id:
            layout_changed = True
            gpu_rows.append({
                "id": gid, "name": g.get("name") or f"GPU {gid}",
                "total_mb": round(total), "free_mb": round(free),
                "used_mb": None, "kv_delta_mb": None, "projected_free_mb": None,
                "status": "na",
            })
            continue
        used_now = max(0.0,
                       float(g.get("vram_used_mb") or 0) - base_by_id[gid].get("used_mb", 0.0))
        delta = used_now * (ratio - 1.0)
        projected = free - delta
        status = "ok"
        if projected < max(total * _FREE_FRACTION, _FREE_MIN_MB):
            status = "warn"
            warn = True
        gpu_rows.append({
            "id": gid, "name": g.get("name") or f"GPU {gid}",
            "total_mb": round(total), "free_mb": round(free),
            "used_mb": round(used_now), "kv_delta_mb": round(delta),
            "projected_free_mb": round(projected),
            "status": status,
        })
    if base.get("gpus") and not gpu_rows:
        layout_changed = True

    # system RAM (no per-device split — one number)
    ram_row = None
    if base.get("ram_used_mb") is not None:
        try:
            import psutil
            vmem = psutil.virtual_memory()
            ram_now_used = vmem.used / 1048576
            ram_now_free = vmem.available / 1048576
            used_now = max(0.0, ram_now_used - float(base["ram_used_mb"]))
            delta = used_now * (ratio - 1.0)
            projected = ram_now_free - delta
            status = "ok" if projected > 0 else "warn"
            if status == "warn":
                warn = True
            ram_row = {
                "used_mb": round(used_now), "free_mb": round(ram_now_free),
                "kv_delta_mb": round(delta), "projected_free_mb": round(projected),
                "status": status,
            }
        except Exception:  # psutil must never break the estimate
            log.exception("memcheck: RAM estimate failed")

    notes = []
    if ctx_want > ctx_base:
        notes.append(f"context is larger than the calibrated launch ({ctx_base}) — estimate is extrapolated")
    if layout_changed:
        notes.append("GPU layout differs from the calibrated launch — per-GPU numbers are approximate")
    if (launch.get("cache_type_k") or "f16") != (base.get("cache_type_k") or "f16") or \
       (launch.get("cache_type_v") or "f16") != (base.get("cache_type_v") or "f16"):
        notes.append("KV cache types differ from the calibrated launch")
    if (launch.get("spec") or {}).get("spec_type", "none") != (base.get("spec_type") or "none"):
        notes.append("speculative decoding setting differs from the calibrated launch")

    return {
        "ok": True, "baseline": True, "model": model,
        "calibrated_ts": base.get("ts"),
        "ctx_baseline": ctx_base, "ctx_want": ctx_want,
        "layout_changed": layout_changed,
        "gpus": gpu_rows, "ram": ram_row,
        "notes": notes,
        "verdict": "warn" if warn else "ok",
    }
