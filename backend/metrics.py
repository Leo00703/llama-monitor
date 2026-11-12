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
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Callable, Optional

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


# Negative-result cache for the 1.5 s metrics loop (#106 O4): when
# nvidia-smi is absent or fails, re-probing every tick is pure waste —
# a PATH walk every tick, and a REAL process spawn per tick when a broken
# nvidia-smi sits on PATH (rc != 0). A machine WITH a working GPU needs a
# fresh spawn every tick (live utilisation), so only the negative result is
# cached. Callers that must see the truth now (launch validation, the
# Settings GPU card) keep calling run_nvidia_smi directly.
GPU_NEGATIVE_TTL = 60.0
_gpu_negative_until = 0.0


def nvidia_smi_cached() -> Optional[list[dict]]:
    """run_nvidia_smi with the negative result held for GPU_NEGATIVE_TTL."""
    global _gpu_negative_until
    now = time.monotonic()
    if now < _gpu_negative_until:
        return None
    gpus = run_nvidia_smi()
    if not gpus:  # None or [] -> negative: retry only after the TTL
        _gpu_negative_until = now + GPU_NEGATIVE_TTL
    return gpus


class CpuSensors:
    """CPU package temperature + power from sysfs (Linux only).

    Windows exposes neither cleanly without elevation: WMI thermal zones
    (MSAcpi_ThermalZoneTemperature) require admin, and RAPL needs MSR
    access — both stay None there and the UI hides the fields. RAM has no
    sensor on either OS. All reads are plain sysfs file opens (no process
    spawns), called from the metrics loop thread.
    """

    # thermal zone types that mean "CPU package", best match first
    _TEMP_ZONE_PRIORITY = ("x86_pkg_temp", "cpu_thermal", "intel_thermal")

    def __init__(self, sysroot: str = "/sys") -> None:
        self._zones: list[tuple[int, Path]] = []
        self._rapl_energy: Optional[Path] = None
        self._hwmon_power: Optional[Path] = None
        self._last_sample: Optional[tuple[float, float]] = None  # (ts, energy_uj)
        if sys.platform.startswith("linux"):
            self._discover(sysroot)

    def _discover(self, sysroot: str) -> None:
        cap = Path(sysroot) / "class" / "powercap"
        with contextlib.suppress(OSError):
            for entry in sorted(os.listdir(cap)):
                if not entry.startswith("intel-rapl"):
                    continue
                base = cap / entry
                try:
                    name = (base / "name").read_text().strip()
                except OSError:
                    continue
                # use the "Package" domain (not DRAM/core sub-domains)
                if name == "Package" and (base / "energy_uj").is_file():
                    self._rapl_energy = base / "energy_uj"
                    break
        # AMD fallback: zenpower hwmon exposes package power in microwatts
        # (Intel RAPL above is preferred when present)
        hwmon = Path(sysroot) / "class" / "hwmon"
        with contextlib.suppress(OSError):
            for entry in sorted(os.listdir(hwmon)):
                base = hwmon / entry
                try:
                    name = (base / "name").read_text().strip()
                except OSError:
                    continue
                if name == "zenpower" and not self._rapl_energy:
                    for f in ("power1_average", "power1_input"):
                        p = base / f
                        if p.is_file():
                            self._hwmon_power = p
                            break
                if self._hwmon_power:
                    break
        thermal = Path(sysroot) / "class" / "thermal"
        with contextlib.suppress(OSError):
            for entry in sorted(os.listdir(thermal)):
                if not entry.startswith("thermal_zone"):
                    continue
                base = thermal / entry
                try:
                    ztype = (base / "type").read_text().strip()
                except OSError:
                    continue
                if ztype in self._TEMP_ZONE_PRIORITY and (base / "temp").is_file():
                    self._zones.append((self._TEMP_ZONE_PRIORITY.index(ztype), base))
        self._zones.sort(key=lambda t: t[0])

    def temp_c(self) -> Optional[float]:
        """Hottest CPU package zone in °C, or None when no zone is exposed."""
        best: Optional[float] = None
        for _, base in self._zones:
            try:
                v = int(base.joinpath("temp").read_text().strip())
            except (OSError, ValueError):
                continue
            t = v / 1000.0
            if best is None or t > best:
                best = t
        return round(best, 1) if best is not None else None

    def power_w(self) -> Optional[float]:
        """Package power in watts (RAPL energy delta, or AMD hwmon average)."""
        if self._rapl_energy is not None:
            try:
                energy = int(self._rapl_energy.read_text().strip())
            except (OSError, ValueError):
                return None
            now = time.time()
            prev = self._last_sample
            self._last_sample = (now, energy)
            if prev is None or now - prev[0] < 0.5:
                return None
            de = energy - prev[1]
            if de < 0:  # counter wrap / driver reset — resync next tick
                return None
            return round(de / 1e6 / (now - prev[0]), 2)
        if self._hwmon_power is not None:
            try:
                v = int(self._hwmon_power.read_text().strip())
            except (OSError, ValueError):
                return None
            return round(v / 1e6, 2)
        return None


class MetricsCollector:
    """Polls system + inference metrics and computes live tok/s deltas."""

    def __init__(self,
                 get_auth: Optional[Callable[[], dict[str, str]]] = None,
                 get_base_url: Optional[Callable[[], Optional[str]]] = None,
                 ) -> None:
        """`get_auth` returns headers (Authorization) for the llama-server
        polls — the panel's internal /metrics + /slots GETs must carry the
        preset's API key or every poll 401s under --api-key (#99).
        `get_base_url` returns the http://host:port to dial — the bound host,
        not loopback, for a NIC-bound server (#112); None falls back to
        loopback + the snapshot port."""
        self._get_auth = get_auth or (lambda: {})
        self._get_base_url = get_base_url or (lambda: None)
        psutil.cpu_percent()
        psutil.cpu_percent(percpu=True)
        self._cpu_sensors = CpuSensors()
        self._baseline: Optional[dict[str, Any]] = None
        # long-lived inference client — see _inference (#106 O3)
        self._client: Optional[httpx.AsyncClient] = None

    async def snapshot(self, port: Optional[int]) -> dict:
        """Collect one full sample. `port` = active llama-server port (or None)."""
        per_core = psutil.cpu_percent(percpu=True)
        total = psutil.cpu_percent()
        ram = psutil.virtual_memory()
        # skip even the thread hop while the negative nvidia-smi result
        # (#106 O4) is fresh — no-GPU machines get zero per-tick cost
        if time.monotonic() >= _gpu_negative_until:
            gpus = await asyncio.to_thread(nvidia_smi_cached)
        else:
            gpus = None
        cpu_sensors = await asyncio.to_thread(self._cpu_sensors_sample)
        inference = await self._inference(port) if port else None
        freq = psutil.cpu_freq()  # None on platforms without a freq source
        return {
            "ts": time.time(),
            "cpu": {
                "total": round(total, 1),
                "per_core": [round(v, 1) for v in per_core],
                "freq_ghz": round(freq.current / 1000, 2) if freq and freq.current else None,
            },
            "cpu_sensors": cpu_sensors,
            "ram": {
                "used_gb": round(ram.used / 1073741824, 2),
                "total_gb": round(ram.total / 1073741824, 2),
                # Percent derived from the same used/total the card prints:
                # psutil's own percent is (total - available)/total, and on
                # macOS `available` counts reclaimable inactive pages, so it
                # disagrees with used/total (e.g. 88% vs 10.9/16 GB) and made
                # the headline and the detail look contradictory.
                "percent": round(ram.used / ram.total * 100, 1) if ram.total else 0.0,
            },
            "gpus": gpus or [],
            "inference": inference,
        }

    def _cpu_sensors_sample(self) -> dict[str, Optional[float]]:
        return {
            "temp_c": self._cpu_sensors.temp_c(),
            "power_w": self._cpu_sensors.power_w(),
        }

    async def _inference(self, port: int) -> Optional[dict]:
        base = self._get_base_url() or f"http://127.0.0.1:{port}"
        headers = self._get_auth() or {}
        # One long-lived client, two concurrent GETs (#106 O3): the old code
        # rebuilt the AsyncClient every 1.5 s tick (fresh TCP handshake,
        # zero keep-alive) and fetched /slots only after /metrics returned.
        # Auth headers go per-request, so a preset API-key change (#99)
        # needs no client rebuild.
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(timeout=2.0)
        mres, sres = await asyncio.gather(
            self._client.get(f"{base}/metrics", headers=headers),
            self._client.get(f"{base}/slots", headers=headers),
            return_exceptions=True,
        )
        _CONN_FAIL = (httpx.ConnectError, httpx.ConnectTimeout)
        if (isinstance(mres, _CONN_FAIL) and isinstance(sres, _CONN_FAIL)
                and "127.0.0.1" not in base):
            # #112: the launch host (preset) may not be where an ADOPTED
            # external server actually listens — one loopback retry. A
            # firewalled/dropped NIC address raises ConnectTimeout, which
            # is NOT a ConnectError subclass in httpx (0.28).
            base = f"http://127.0.0.1:{port}"
            mres, sres = await asyncio.gather(
                self._client.get(f"{base}/metrics", headers=headers),
                self._client.get(f"{base}/slots", headers=headers),
                return_exceptions=True,
            )
        if isinstance(mres, asyncio.CancelledError):
            raise mres
        if isinstance(sres, asyncio.CancelledError):
            raise sres
        if isinstance(mres, Exception) or isinstance(sres, Exception):
            # either endpoint unreachable (server down / slow) => no sample,
            # same outcome as the old serial httpx.HTTPError path
            return None
        if mres.status_code == 401 and sres.status_code == 401:
            # The server demands an API key the panel did not send (or sent
            # the wrong one) — surface it instead of silently rendering
            # blank cards (#99).
            return {"ok": False, "auth_error": True}
        if mres.status_code != 200 and sres.status_code != 200:
            return None

        counters = parse_prometheus(mres.text if mres.status_code == 200 else "")
        prompt_tokens = counters.get("prompt_tokens")
        gen_tokens = counters.get("gen_tokens")
        prompt_tps: Optional[float] = None
        gen_tps: Optional[float] = None
        now = time.time()

        slots: list[dict] = []
        ctx_total = 0
        ctx_used = 0
        n_decoded_sum = 0
        n_prompt_sum = 0
        have_decoded = False
        if sres.status_code == 200:
            with contextlib.suppress(ValueError):
                for s in sres.json():
                    if not isinstance(s, dict):
                        continue
                    n_ctx = int(s.get("n_ctx") or 0)
                    busy = bool(s.get("is_processing"))
                    n_prompt = int(s.get("n_prompt_tokens") or 0)
                    nt = s.get("next_token")
                    n_decoded = int(nt.get("n_decoded") or 0) if isinstance(nt, dict) else None
                    # n_prompt_tokens persists after the request finishes (the
                    # server keeps the last value), so report it even when idle.
                    used = min(n_prompt, n_ctx)
                    if n_decoded is not None:
                        have_decoded = True
                        n_decoded_sum += n_decoded
                    n_prompt_sum += n_prompt
                    ctx_total += n_ctx
                    ctx_used += used
                    slots.append(
                        {
                            "id": int(s.get("id") or 0),
                            "busy": busy,
                            "speculative": bool(s.get("speculative")),
                            "n_ctx": n_ctx,
                            "used": used,
                        }
                    )

        prev = self._baseline
        dt = now - prev["ts"] if prev is not None and prev.get("port") == port else 0.0
        if dt > 0.2 and have_decoded and prev.get("n_decoded") is not None:
            # Live slot-based rates. Recent llama.cpp only updates the
            # /metrics token counters when a request completes, so they read
            # 0 while generating. /slots exposes per-slot progress instead:
            # n_decoded counts every accepted token (spec-decode aware) and
            # n_prompt_tokens grows while the prompt is being processed.
            if any(s["busy"] for s in slots):
                dgen = (n_decoded_sum - prev["n_decoded"]) / dt
                if dgen > 0:
                    gen_tps = round(dgen, 2)
                elif (n_prompt_sum - prev["n_prompt"]) / dt > 0:
                    prompt_tps = round((n_prompt_sum - prev["n_prompt"]) / dt, 2)
        elif (
            dt > 0.2
            and prompt_tokens is not None
            and gen_tokens is not None
            and prev is not None
            and prev.get("prompt_tokens") is not None
            and prompt_tokens >= prev["prompt_tokens"]
            and gen_tokens >= prev["gen_tokens"]
        ):
            # Older builds without slot token progress: counter deltas.
            prompt_tps = round((prompt_tokens - prev["prompt_tokens"]) / dt, 2)
            gen_tps = round((gen_tokens - prev["gen_tokens"]) / dt, 2)

        self._baseline = {
            "ts": now,
            "port": port,
            "prompt_tokens": prompt_tokens,
            "gen_tokens": gen_tokens,
            "n_decoded": n_decoded_sum if have_decoded else None,
            "n_prompt": n_prompt_sum if have_decoded else None,
        }

        return {
            "ok": True,
            "prompt_tps": prompt_tps,
            "gen_tps": gen_tps,
            "prompt_tokens": prompt_tokens,
            "gen_tokens": gen_tokens,
            "ctx_used": ctx_used,
            "ctx_total": ctx_total,
            "slots": slots,
            # live slot count of the RUNNING server — the UI uses it to
            # flag a preset whose slot setting hasn't been applied yet
            "n_slots": len(slots),
        }
