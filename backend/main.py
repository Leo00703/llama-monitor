"""FastAPI application: REST API, WebSockets, static frontend serving."""

from __future__ import annotations

import asyncio
import json
import logging
import shutil
import threading
import time
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, AsyncIterator, Callable, Optional

from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, ValidationError

import httpx

from .analytics import (
    AnalyticsStore,
    LiveLogStats,
    PowerSampler,
    PrintTimingTracker,
    RANGES,
)
from .config import (
    DATA_DIR,
    PRESETS_DIR,
    AppConfig,
    LlamaBackendPending,
    LlamaBackendSettings,
    load_config,
    save_config,
)
from . import backend_update
from .flags import build_args, parse_help, validate_settings
from .metrics import MetricsCollector
from .models import list_models
from .process import LlamaServerManager
from .presets import PresetStore
from .proxy import INJECT_PATHS, ProxyOffline, ServerProxy
from .schema import LaunchSettings, Preset, SPEC_TYPES
from . import update as app_update

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-7s %(name)s: %(message)s")
log = logging.getLogger("llama-monitor")

FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"
METRICS_INTERVAL = 1.5

# Set by the tray launcher (set_restart_hook) to relaunch the app after an
# update is pulled. None in dev/uvicorn mode: the pull still works, the
# restart is reported as manual. Called with deferred=True when the
# bootstrap bat (not the hook) performs the relaunch — the hook must then
# only shut the process down.
RESTART_HOOK: Optional[Callable[..., None]] = None


def set_restart_hook(hook: Optional[Callable[..., None]]) -> None:
    global RESTART_HOOK
    RESTART_HOOK = hook


_updater_stop = threading.Event()


def _update_loop(manager: LlamaServerManager, loop: asyncio.AbstractEventLoop,
                 config: AppConfig) -> None:
    """Periodically fetch the git origin and toast about new commits.

    The interval is read from the live config on every pass (settings can
    change it at runtime); 0 disables the background checks.
    """
    last_notified: Optional[str] = None
    time.sleep(15.0)  # don't slow down startup with a possibly slow fetch
    while not _updater_stop.wait(1.0):
        try:
            minutes = int(config.update_check_minutes)
        except (TypeError, ValueError):
            minutes = 0
        if minutes <= 0:
            continue
        try:
            res = app_update.check(force=True)
        except Exception:
            log.exception("background update check failed")
            res = None
        if res and res.get("repo") and res.get("behind", 0) > 0:
            latest = (res.get("latest") or {}).get("sha") or ""
            if latest and latest != last_notified:
                last_notified = latest
                loop.call_soon_threadsafe(
                    manager.broadcast, {"type": "update.available", "data": res})
        _updater_stop.wait(max(minutes, 1) * 60.0)


async def _metrics_loop(collector: MetricsCollector, manager: LlamaServerManager,
                        power: PowerSampler, tracker: PrintTimingTracker,
                        live_log: LiveLogStats, config: AppConfig) -> None:
    """Poll system + inference metrics and push them to WebSocket listeners."""
    while True:
        await asyncio.sleep(METRICS_INTERVAL)
        try:
            data = await collector.snapshot(manager.current_port())
        except Exception:  # metrics must never take the panel down
            log.exception("metrics collection failed")
            continue
        total_w = sum(g["power_w"] for g in data.get("gpus", []) if g.get("power_w") is not None)
        power.add(float(data.get("ts") or time.time()), total_w if total_w > 0 else None)
        _enrich_inference(data, tracker, live_log)
        tracker.tick()
        data["usage_style"] = config.dashboard.usage_style  # live mode switch
        manager.broadcast({"type": "metrics", "data": data})


# A log rate older than this is stale, not live (progress lines come about
# once a second / every 3s; allow slack for a slow server).
_LIVE_LOG_STALE = 10.0

# Last live measurement shown while a request is running; kept across ticks
# until a newer one arrives so the card never clears to "—" mid-generation.
_last_live: dict = {"rc": 0, "prompt": None, "gen": None}


def _enrich_inference(data: dict, tracker: PrintTimingTracker,
                      live_log: Optional[LiveLogStats] = None) -> None:
    """Show real per-request speeds when idle; live speeds when busy.

    While a slot is busy the live gauge prefers the server's own progress
    lines from the log (newer builds print them, see LiveLogStats) — they
    are immune to /slots and /metrics shape changes — and falls back to
    /slots token progress (n_decoded / n_prompt_tokens deltas, see
    MetricsCollector), then to /metrics counter deltas for older builds.
    Recent llama.cpp updates its /metrics token counters only when a request
    completes, so the deltas are only a last resort. Once idle we show the
    exact tok/s parsed from the print_timing block of the last completed
    request (``tracker.latest``). External servers emit no log lines, so
    ``latest`` stays None and the delta values are kept. A delta of exactly 0
    (no tokens moved in the window) is not a speed measurement — it is
    nulled so the UI renders "—" instead of a misleading 0.0.
    """
    inf = data.get("inference")
    if not isinstance(inf, dict) or not inf.get("ok"):
        return
    for key in ("prompt_tps", "gen_tps"):
        if inf.get(key) == 0:
            inf[key] = None
    latest = tracker.latest
    busy = any(s.get("busy") for s in inf.get("slots") or [])
    if not busy and latest is not None:
        if latest.get("prompt_tps") is not None:
            inf["prompt_tps"] = round(latest["prompt_tps"], 2)
        if latest.get("gen_tps") is not None:
            inf["gen_tps"] = round(latest["gen_tps"], 2)
    inf["last_seq"] = latest.get("seq") if latest else None
    inf["last_prompt_tps"] = round(latest["prompt_tps"], 2) if latest and latest.get("prompt_tps") is not None else None
    inf["last_gen_tps"] = round(latest["gen_tps"], 2) if latest and latest.get("gen_tps") is not None else None
    inf["draft_proposed"] = latest.get("draft_proposed") if latest else None
    inf["draft_accepted"] = latest.get("draft_accepted") if latest else None
    if busy and live_log is not None:
        # The server's own live measurements override the /slots and
        # /metrics deltas while they are fresh.
        now = time.monotonic()
        if live_log.reset_count != _last_live["rc"]:
            # Request boundary ("stop processing" or stop/restart):
            # never carry values across requests.
            _last_live["rc"] = live_log.reset_count
            _last_live["prompt"] = None
            _last_live["gen"] = None
        if live_log.prompt_tps is not None and now - live_log.prompt_ts < _LIVE_LOG_STALE:
            _last_live["prompt"] = round(live_log.prompt_tps, 2)
            inf["prompt_tps"] = _last_live["prompt"]
        if live_log.gen_tps is not None and now - live_log.gen_ts < _LIVE_LOG_STALE:
            _last_live["gen"] = round(live_log.gen_tps, 2)
            inf["gen_tps"] = _last_live["gen"]
        # Sticky: while busy, keep the last shown value instead of
        # clearing to "—" when this tick has no fresh measurement.
        if inf.get("prompt_tps") is None and _last_live["prompt"] is not None:
            inf["prompt_tps"] = _last_live["prompt"]
        if inf.get("gen_tps") is None and _last_live["gen"] is not None:
            inf["gen_tps"] = _last_live["gen"]


class StartRequest(BaseModel):
    args: list[str] = Field(default_factory=list)
    preset_id: str = ""


class PresetRequest(BaseModel):
    name: str = "New preset"
    launch: Optional[LaunchSettings] = None
    generation: Optional[dict[str, Any]] = None


def _model_from_args(args: list[str]) -> str:
    """Model path from raw launch args (-m/--model), for preset-less starts."""
    for i, a in enumerate(args):
        if a in ("-m", "--model") and i + 1 < len(args):
            return args[i + 1]
        if a.startswith("--model="):
            return a.split("=", 1)[1]
    return ""


def create_app() -> FastAPI:
    config: AppConfig = load_config()
    manager = LlamaServerManager(lambda: config)
    store = PresetStore(PRESETS_DIR)
    collector = MetricsCollector()
    analytics = AnalyticsStore(DATA_DIR / "analytics.db")
    # the per-request energy window is clamped to 1 day (see _complete_request)
    # — the ring must hold at least that many samples or long requests lose
    # their head (the high-power prompt phase) and the estimate under-counts
    power = PowerSampler(max_samples=int(86400 / METRICS_INTERVAL) + 60)

    def _model_for_request() -> str:
        """Best-effort model name for the currently launched server."""
        pid = manager.preset_id
        preset = store.get(pid) if pid else None
        model = preset.launch.model if preset and preset.launch.model else (preset.name if preset else "")
        if not model:
            model = _model_from_args(manager.launch_args)
        return model

    def _complete_request(rec: dict) -> None:
        """Persist one completed request (from a parsed print_timing block)."""
        try:
            now = time.time()
            total_ms = rec.get("total_ms") or 0.0
            start = max(now - total_ms / 1000.0, now - 86400.0)
            gpu_wh = power.energy_wh(start, now)
            energy_wh = gpu_wh
            if config.energy_overhead_w > 0:
                energy_wh = (gpu_wh or 0.0) + config.energy_overhead_w * (total_ms / 1000.0) / 3600.0
            pid = manager.preset_id
            preset = store.get(pid) if pid else None
            analytics.record(
                ts=now,
                preset_id=pid or "",
                preset_name=preset.name if preset else "",
                model=_model_for_request(),
                rec=rec,
                energy_wh=energy_wh,
            )
        except Exception:
            log.exception("failed to record generation request")

    def _record_failure(status: int, path: str) -> None:
        """Count a failed generation attempt (offline server / upstream error)."""
        try:
            analytics.record_failure(
                ts=time.time(), model=_model_for_request(), status=status, path=path)
        except Exception:
            log.exception("failed to record failed request")

    tracker = PrintTimingTracker(_complete_request)
    live_log = LiveLogStats()
    manager.add_log_hook(tracker.feed)
    manager.add_log_hook(live_log.feed)
    # Seed the sticky last-request speeds from the analytics DB so the
    # inference card doesn't read "no data" until the next request completes.
    _last = analytics.latest_record()
    if _last is not None:
        # seq=-1 (not 0): the frontend only refreshes the draft row when
        # last_seq changes from its initial 0, so a 0 seed would hide the
        # seeded draft rate. Live requests start at seq=1, so -1 never
        # collides with a real one.
        tracker.latest = {
            "seq": -1,
            "prompt_tps": _last.get("prompt_tps"),
            "gen_tps": _last.get("gen_tps"),
            "draft_proposed": _last.get("draft_proposed"),
            "draft_accepted": _last.get("draft_accepted"),
        }

    def _launch_for(preset_id: Optional[str]) -> Optional[dict[str, Any]]:
        if not preset_id:
            return None
        preset = store.get(preset_id)
        return preset.launch.model_dump() if preset else None

    proxy = ServerProxy(
        get_port=manager.current_port,
        get_launch=lambda: _launch_for(manager.preset_id or config.active_preset_id),
    )

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        log.info("llama-monitor panel starting")
        await manager.on_startup()
        log.info("panel ready (state=%s)", manager.snapshot()["state"])
        loop = asyncio.get_running_loop()
        task = asyncio.create_task(
            _metrics_loop(collector, manager, power, tracker, live_log, config))
        updater = threading.Thread(
            target=_update_loop, args=(manager, loop, config),
            daemon=True, name="update-checker")
        updater.start()
        backend_thread = threading.Thread(
            target=be_loop, args=(loop,),
            daemon=True, name="backend-checker")
        backend_thread.start()
        # leftover of an interrupted download (A9: re-download, no resume)
        try:
            backend_update.cleanup_partials(be_storage())
        except OSError:
            pass
        yield
        _updater_stop.set()
        task.cancel()
        await manager.shutdown()

    app = FastAPI(title="llama-monitor", version="0.4.0", lifespan=lifespan)

    # ------------------------------------------------------------------
    # launch preparation (presets -> validated, version-checked flags)
    # ------------------------------------------------------------------

    async def prepare_launch(preset_id: str) -> dict:
        """Resolve a preset into launch args. Returns {ok, args, warnings, errors}."""
        preset = store.get(preset_id)
        if preset is None:
            return {"ok": False, "args": [], "warnings": [], "errors": [f"preset '{preset_id}' not found"]}

        models_root = config.model_root()
        warnings, errors = validate_settings(preset.launch, gpu_count=0, models_root=models_root)
        if errors:
            return {"ok": False, "args": [], "warnings": warnings, "errors": errors}

        exe = config.resolved_exe()
        supported: set[str] = set()
        spec_types: set[str] = set()
        if exe is None:
            warnings.append("llama-server executable not configured — flag version check skipped")
        else:
            supported, spec_types = await parse_help(exe)

        # spec types the installed build doesn't document would make
        # llama-server abort at startup — block with a clear message
        st = preset.launch.spec.spec_type
        if spec_types and st not in spec_types:
            return {
                "ok": False,
                "args": [],
                "warnings": warnings,
                "errors": [
                    f"spec type '{st}' is not documented by this llama-server build — "
                    "update llama-server first"
                ],
            }

        args, flag_warnings = build_args(
            preset.launch,
            models_root=models_root,
            supported=supported or None,
        )
        warnings.extend(flag_warnings)
        return {"ok": True, "args": args, "warnings": warnings, "errors": []}

    @app.post("/api/presets/{preset_id}/preview")
    async def preset_preview(preset_id: str) -> dict:
        return await prepare_launch(preset_id)

    # ------------------------------------------------------------------
    # llama.cpp backend updates (check / download / apply — see
    # backend_update.py). Unlike the app self-update this is pure file
    # work: stop → extract → verify --version → flip config → start.
    # ------------------------------------------------------------------

    be_downloading = False  # single-flight download guard

    def be_storage() -> Path:
        return backend_update.resolve_storage(config)

    async def be_current() -> dict:
        return await backend_update.provenance(config.resolved_exe() or "")

    def be_target_tag(rel: dict) -> Optional[str]:
        return (rel.get("pinned_nightly") if config.llama_backend.channel
                == "stable" else rel.get("latest_nightly"))

    async def be_run_check(manual: bool = False) -> dict:
        """One update check: compare the channel's latest build with the
        current one, set `pending`, and (if enabled) start the download.

        Automation (notify + auto-download) only for official prebuilts —
        manual actions from the card stay available for custom builds.
        """
        nonlocal be_downloading
        try:
            rel = await backend_update.fetch_releases(force=manual)
        except (httpx.HTTPError, OSError, ValueError) as exc:
            return {"ok": False, "error": f"release check failed: {exc}"}
        lb = config.llama_backend
        lb.last_check = datetime.now().isoformat(timespec="seconds")
        current = await be_current()
        save_config(config)
        target = be_target_tag(rel)
        res: dict[str, Any] = {
            "ok": True, "remote": rel, "current": current, "target": target,
            "automation": current["official"],
        }
        if not target:
            res["error"] = "could not determine the latest build — try again later"
            return res
        if not current["official"]:
            return res
        if target == current["tag"]:
            if lb.pending is not None:
                lb.pending = None
                save_config(config)
            res["pending"] = None
            return res
        pending = lb.pending or LlamaBackendPending()
        changed = pending.tag != target or pending.state != "available"
        pending.tag, pending.variant, pending.state = target, lb.variant, "available"
        lb.pending = pending
        save_config(config)
        res["pending"] = pending
        if changed:
            manager.broadcast({
                "type": "llama.update.available",
                "data": {
                    "tag": target, "channel": lb.channel,
                    "current": current["tag"],
                    "stable_tag": rel.get("stable_tag"),
                },
            })
        if lb.auto_download and not be_downloading:
            asyncio.create_task(be_download(target, lb.variant))
        return res

    async def be_download(tag: str, variant: str) -> dict:
        """Download + extract + verify a build into the storage folder."""
        nonlocal be_downloading
        if be_downloading:
            return {"ok": False, "error": "a download is already in progress"}
        be_downloading = True
        t0 = time.time()
        try:
            storage = be_storage()
            storage.mkdir(parents=True, exist_ok=True)
            headers = {"User-Agent": backend_update.USER_AGENT}
            async with httpx.AsyncClient(timeout=30, headers=headers,
                                         follow_redirects=True) as client:
                asset = await backend_update.find_asset(client, tag, variant)
            if asset is None:
                return {"ok": False,
                        "error": f"no {variant} build for {tag} on this platform"}
            # A6: free space for the zip + the extracted copy
            free = backend_update.free_bytes(storage)
            needed = (asset.get("size") or 0) * 2
            if free is not None and free < needed:
                return {"ok": False, "error": (
                    f"not enough free space in {storage}: need ~"
                    f"{needed / 1048576:.0f} MB, have {free / 1048576:.0f} MB")}
            zip_path = storage / asset["name"]

            def progress(done: int, total: int) -> None:
                manager.broadcast({"type": "llama.update.progress", "data": {
                    "tag": tag, "done": done, "total": total,
                    "percent": round(done * 100 / total) if total else 0,
                }})

            await backend_update.download_file(asset, zip_path, progress)
            build_dir = storage / f"llama-{tag}-{variant}"
            if build_dir.exists():
                shutil.rmtree(build_dir, ignore_errors=True)
            backend_update.extract_archive(zip_path, build_dir)
            ver = await backend_update.verify_build(build_dir, tag)
            if not ver["ok"]:
                shutil.rmtree(build_dir, ignore_errors=True)
                return {"ok": False, "error": ver["error"]}
            backend_update.write_manifest(
                build_dir, tag, variant, asset["browser_download_url"],
                asset.get("size") or 0)
            config.llama_backend.pending = LlamaBackendPending(
                tag=tag, variant=variant, state="downloaded")
            save_config(config)
            manager.broadcast({"type": "llama.update.downloaded",
                               "data": {"tag": tag, "dir": str(build_dir)}})
            return {"ok": True, "dir": str(build_dir),
                    "seconds": round(time.time() - t0, 1)}
        except (httpx.HTTPError, OSError, ValueError,
                backend_update.UpdateError) as exc:
            log.exception("backend download failed")
            return {"ok": False, "error": str(exc)}
        finally:
            be_downloading = False

    async def be_apply(body: dict) -> dict:
        """Flip the configured executable to a downloaded build: stop the
        panel-managed server (if running), flip the config, restart with
        the same preset. External servers keep running on the old build
        until restarted manually."""
        d = (body or {}).get("dir") or ""
        if not d:
            return {"ok": False, "error": "missing build dir"}
        try:
            target_dir = Path(d).expanduser().resolve()
        except (OSError, RuntimeError):
            return {"ok": False, "error": "invalid build dir"}
        storage = be_storage().resolve()
        try:
            target_dir.relative_to(storage)
        except ValueError:
            return {"ok": False,
                    "error": f"build dir is not inside the storage folder ({storage})"}
        exe_name = backend_update.server_exe_name()
        if not (target_dir / exe_name).exists():
            return {"ok": False, "error": f"no {exe_name} in that build folder"}

        state = manager.snapshot()["state"]
        external = state == "external"
        preset_id = manager.preset_id  # stop() clears it — capture first
        if state in ("running", "starting", "restarting") and not external:
            stop = await manager.stop()
            if not stop.get("ok"):
                return {"ok": False,
                        "error": f"could not stop the server: {stop.get('error') or 'stop failed'}"}

        config.llama_server_exe = str(target_dir / exe_name)
        # a freshly installed build is no longer "pending"
        pend = config.llama_backend.pending
        mp = target_dir / backend_update.MANIFEST_NAME
        if pend and pend.tag and mp.exists():
            try:
                if json.loads(mp.read_text(encoding="utf-8")).get("tag") == pend.tag:
                    config.llama_backend.pending = None
            except (json.JSONDecodeError, OSError):
                pass
        save_config(config)
        await manager.redetect_version()  # topbar must show the new build
        res: dict[str, Any] = {"ok": True, "exe": config.llama_server_exe,
                               "external": external}
        if external:
            res["note"] = ("the running external server keeps the old build "
                           "until it is restarted manually")
        elif preset_id:
            prepared = await prepare_launch(preset_id)
            if prepared["ok"]:
                start = await manager.start(prepared["args"])
                if start.get("ok"):
                    manager.set_preset_id(preset_id)
                    proxy.invalidate_props_cache()
                    res["restarted"] = True
                else:
                    res["restarted"] = False
                    res["error"] = (f"config flipped, but restart failed: "
                                    f"{start.get('error') or 'start failed'}")
            else:
                res["restarted"] = False
                res["error"] = ("config flipped, but restart failed: "
                                + "; ".join(prepared["errors"]))
        else:
            res["restarted"] = False
            res["note"] = "config flipped — start the server when ready"

        # retention: keep the new current build + the most recently
        # installed managed build (the previous one — the rollback target),
        # whatever folder the old current lived in
        keep = {target_dir.name}
        for b in await asyncio.to_thread(backend_update.local_builds, storage):
            if b["name"] != target_dir.name:
                keep.add(b["name"])
                break
        deleted = await asyncio.to_thread(backend_update.prune, storage, keep)
        if deleted:
            res["pruned"] = deleted
        return res

    def be_loop(loop: asyncio.AbstractEventLoop) -> None:
        """Twice-daily (00:00 / 12:00 local) build check + startup catch-up."""
        time.sleep(25.0)  # don't slow down startup with a network call
        while not _updater_stop.wait(60.0):
            try:
                if backend_update.check_due(config.llama_backend):
                    fut = asyncio.run_coroutine_threadsafe(
                        be_run_check(manual=False), loop)
                    try:
                        fut.result(timeout=180)
                    except Exception:
                        log.exception("scheduled backend check failed")
            except Exception:
                log.exception("backend check loop error")

    @app.get("/api/backend/suggest")
    async def backend_suggest() -> dict:
        return {"ok": True, **backend_update.suggest_variant()}

    @app.get("/api/backend/versions")
    async def backend_versions() -> dict:
        current = await be_current()
        try:
            remote = await backend_update.fetch_releases()
            remote_error: Optional[str] = None
        except (httpx.HTTPError, OSError, ValueError) as exc:
            remote, remote_error = None, str(exc)
        storage = be_storage()
        return {
            "ok": True,
            "current": current,
            "remote": remote,
            "remote_error": remote_error,
            "storage": str(storage),
            "local": backend_update.local_builds(storage),
            "settings": config.llama_backend.model_dump(),
            "downloading": be_downloading,
        }

    @app.post("/api/backend/check")
    async def backend_check() -> dict:
        return await be_run_check(manual=True)

    @app.post("/api/backend/download")
    async def backend_download(body: dict[str, Any] | None = None) -> dict:
        body = body or {}
        tag = (body.get("tag") or "").strip()
        variant = (body.get("variant") or config.llama_backend.variant).strip()
        if not tag:
            # no explicit tag: use the channel's latest (fresh check)
            res = await be_run_check(manual=True)
            if not res.get("ok"):
                return res
            tag = res.get("target") or ""
            if not tag:
                return {"ok": False, "error": "no target build found"}
        if be_downloading:
            return {"ok": False, "error": "a download is already in progress"}
        asyncio.create_task(be_download(tag, variant))
        return {"ok": True, "started": True, "tag": tag, "variant": variant}

    @app.post("/api/backend/apply")
    async def backend_apply(body: dict[str, Any] | None = None) -> dict:
        return await be_apply(body or {})

    @app.post("/api/backend/config")
    async def backend_set_config(body: dict[str, Any]) -> dict:
        fields = LlamaBackendSettings.model_fields
        merged = {k: v for k, v in (body or {}).items() if k in fields}
        try:
            new = LlamaBackendSettings.model_validate(
                {**config.llama_backend.model_dump(), **merged})
        except ValidationError as exc:
            return {"ok": False, "error": str(exc)}
        if new.channel not in ("stable", "nightly"):
            return {"ok": False, "error": "channel must be 'stable' or 'nightly'"}
        if new.variant not in backend_update.VARIANTS:
            return {"ok": False, "error": f"unknown variant '{new.variant}'"}
        config.llama_backend = new
        save_config(config)
        return {"ok": True, "settings": config.llama_backend.model_dump()}

    # ------------------------------------------------------------------
    # REST: process control
    # ------------------------------------------------------------------

    @app.get("/api/health")
    async def health() -> dict:
        return {"ok": True}

    @app.get("/api/state")
    async def state() -> dict:
        return manager.snapshot()

    @app.post("/api/server/start")
    async def server_start(body: StartRequest) -> dict:
        if body.preset_id:
            prepared = await prepare_launch(body.preset_id)
            if not prepared["ok"]:
                return prepared
            args = prepared["args"]
            response_extra = {"warnings": prepared["warnings"]}
        else:
            args = body.args
            response_extra = {}
        result = await manager.start(args)
        if result.get("ok"):
            manager.set_preset_id(body.preset_id or None)
            proxy.invalidate_props_cache()
        result.update(response_extra)
        return result

    @app.post("/api/server/stop")
    async def server_stop() -> dict:
        result = await manager.stop()
        tracker.reset()
        live_log.reset()
        return result

    @app.post("/api/server/restart")
    async def server_restart(body: StartRequest | None = None) -> dict:
        if body and body.preset_id:
            prepared = await prepare_launch(body.preset_id)
            if not prepared["ok"]:
                return prepared
            args = prepared["args"]
            response_extra = {"warnings": prepared["warnings"]}
        else:
            args = (body.args if body and body.args else None)
            response_extra = {}
        result = await manager.restart(args)
        tracker.reset()
        live_log.reset()
        if result.get("ok"):
            manager.set_preset_id((body.preset_id if body and body.preset_id else None))
            proxy.invalidate_props_cache()
        result.update(response_extra)
        return result

    # ------------------------------------------------------------------
    # REST: config
    # ------------------------------------------------------------------

    @app.get("/api/config")
    async def get_config() -> dict:
        return {**config.model_dump(), "data_dir": str(DATA_DIR)}

    @app.post("/api/config")
    async def post_config(body: dict[str, Any]) -> dict:
        try:
            new_config = AppConfig.model_validate(body)
        except ValidationError as exc:
            return {"ok": False, "error": str(exc)}
        # Merge only the keys present in the body: partial clients (e.g. the
        # settings page, which never sends active_preset_id) must not reset
        # fields they didn't submit — a full-replace wiped the active preset.
        for name in new_config.model_fields:
            if name not in body:
                continue
            setattr(config, name, getattr(new_config, name))
        save_config(config)
        return {"ok": True, "config": config.model_dump()}

    # ------------------------------------------------------------------
    # REST: presets
    # ------------------------------------------------------------------

    @app.get("/api/presets")
    async def presets_list() -> dict:
        return {"presets": store.list(), "active_id": config.active_preset_id}

    @app.get("/api/presets/{preset_id}")
    async def presets_get(preset_id: str) -> dict:
        preset = store.get(preset_id)
        if preset is None:
            return {"ok": False, "error": "not found"}
        return {"ok": True, "preset": preset.model_dump()}

    @app.post("/api/presets")
    async def presets_create(body: PresetRequest) -> dict:
        launch = body.launch or LaunchSettings()
        preset = store.create(body.name, launch)
        if body.generation is not None:
            preset.launch.generation = body.generation
            store.update(preset.id, generation=body.generation)
        if not config.active_preset_id:
            config.active_preset_id = preset.id
            save_config(config)
        return {"ok": True, "preset": preset.model_dump()}

    @app.put("/api/presets/{preset_id}")
    async def presets_update(preset_id: str, body: PresetRequest) -> dict:
        preset = store.update(
            preset_id,
            name=body.name,
            launch=body.launch,
            generation=body.generation,
        )
        if preset is None:
            return {"ok": False, "error": "not found"}
        return {"ok": True, "preset": preset.model_dump()}

    @app.post("/api/presets/{preset_id}/duplicate")
    async def presets_duplicate(preset_id: str, name: str = "") -> dict:
        preset = store.duplicate(preset_id, name or None)
        if preset is None:
            return {"ok": False, "error": "not found"}
        return {"ok": True, "preset": preset.model_dump()}

    @app.delete("/api/presets/{preset_id}")
    async def presets_delete(preset_id: str) -> dict:
        deleted = store.delete(preset_id)
        if config.active_preset_id == preset_id:
            config.active_preset_id = ""
            save_config(config)
        return {"ok": deleted}

    @app.post("/api/presets/{preset_id}/activate")
    async def presets_activate(preset_id: str) -> dict:
        if store.get(preset_id) is None:
            return {"ok": False, "error": "not found"}
        config.active_preset_id = preset_id
        save_config(config)
        return {"ok": True, "active_id": config.active_preset_id}

    # ------------------------------------------------------------------
    # REST: models browser
    # ------------------------------------------------------------------

    @app.get("/api/models")
    async def models_list() -> dict:
        root = config.model_root()
        if root is None:
            return {"models": [], "root": ""}
        models = await asyncio.to_thread(list_models, root)
        return {"models": models, "root": str(root)}

    # ------------------------------------------------------------------
    # REST: generation defaults
    # ------------------------------------------------------------------

    @app.get("/api/spec/types")
    async def spec_types() -> dict:
        """All selectable spec types plus the subset the installed build
        documents (from `llama-server --help`). Empty `supported` means
        unknown — the UI treats that as no gating."""
        exe = config.resolved_exe()
        supported: set[str] = set()
        if exe is not None:
            _, supported = await parse_help(exe)
        return {"ok": True, "all": SPEC_TYPES, "supported": sorted(supported)}

    @app.get("/api/generation/defaults")
    async def generation_defaults(preset_id: str = "") -> dict:
        pid = preset_id or (manager.preset_id or config.active_preset_id)
        preset = store.get(pid) if pid else None
        saved = dict(preset.launch.generation) if preset and preset.launch.generation else {}
        params = await proxy.server_params()
        return {
            "ok": True,
            "server_online": proxy.base_url() is not None,
            "server_defaults": params,
            "saved": saved,
            "preset_id": preset.id if preset else (pid or ""),
            "preset_name": preset.name if preset else "",
        }

    @app.put("/api/presets/{preset_id}/generation")
    async def presets_update_generation(preset_id: str, body: dict[str, Any]) -> dict:
        generation = body.get("generation")
        if generation is None:
            generation = {}
        if not isinstance(generation, dict):
            return {"ok": False, "error": "generation must be an object"}
        preset = store.update(preset_id, generation=generation)
        if preset is None:
            return {"ok": False, "error": "not found"}
        return {"ok": True, "generation": preset.launch.generation}

    # ------------------------------------------------------------------
    # REST: analytics (per-request history + energy cost)
    # ------------------------------------------------------------------

    def _price() -> float:
        try:
            return max(float(config.energy_price_eur_kwh), 0.0)
        except (TypeError, ValueError):
            return 0.0

    @app.get("/api/analytics/summary")
    async def analytics_summary(range: str = "week") -> dict:
        if range not in RANGES:
            return {"ok": False, "error": f"range must be one of {', '.join(RANGES)}"}
        return {"ok": True, "summary": analytics.summary(range, _price())}

    @app.get("/api/analytics/timeseries")
    async def analytics_timeseries(range: str = "week", bucket: str = "") -> dict:
        if range not in RANGES:
            return {"ok": False, "error": f"range must be one of {', '.join(RANGES)}"}
        return {"ok": True, **analytics.timeseries(range, _price(), bucket or None)}

    @app.get("/api/analytics/models")
    async def analytics_models(range: str = "week") -> dict:
        if range not in RANGES:
            return {"ok": False, "error": f"range must be one of {', '.join(RANGES)}"}
        return {"ok": True, "models": analytics.models(range, _price())}

    @app.get("/api/analytics/records")
    async def analytics_records(range: str = "week", limit: int = 100) -> dict:
        if range not in RANGES:
            return {"ok": False, "error": f"range must be one of {', '.join(RANGES)}"}
        limit = max(1, min(int(limit), 500))
        return {"ok": True, "records": analytics.records(range, limit)}

    @app.get("/api/analytics/export")
    async def analytics_export(range: str = "week") -> Response:
        if range not in RANGES:
            return JSONResponse({"error": f"range must be one of {', '.join(RANGES)}"}, status_code=400)
        return Response(
            content=analytics.export_csv(range),
            media_type="text/csv",
            headers={"Content-Disposition": f"attachment; filename=llama-monitor-analytics-{range}.csv"},
        )

    # ------------------------------------------------------------------
    # proxy to the running llama-server
    # ------------------------------------------------------------------

    @app.api_route("/proxy/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE"])
    async def llama_proxy(path: str, request: Request) -> Response:
        body: Optional[dict[str, Any]] = None
        if request.method in ("POST", "PUT", "PATCH", "DELETE"):
            raw = await request.body()
            if raw:
                try:
                    body = json.loads(raw)
                except json.JSONDecodeError:
                    if path.lstrip("/") in INJECT_PATHS:
                        _record_failure(400, path)
                    return JSONResponse({"error": "invalid JSON body"}, status_code=400)
        headers = dict(request.headers.items())
        query = request.url.query
        is_generation = path.lstrip("/") in INJECT_PATHS

        if proxy.base_url() is None:
            if is_generation:
                _record_failure(503, path)
            return JSONResponse({"error": "llama-server is not running"}, status_code=503)

        try:
            if isinstance(body, dict) and body.get("stream") is True:
                async def gen() -> AsyncIterator[bytes]:
                    async for chunk in proxy.stream(request.method, path, body, headers, query):
                        yield chunk

                return StreamingResponse(
                    gen(),
                    media_type="text/event-stream",
                    headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
                )
            status, out_headers, content = await proxy.request(
                request.method, path, body, headers, query)
            if is_generation and status >= 400:
                _record_failure(status, path)
            return Response(content=content, status_code=status, headers=out_headers)
        except ProxyOffline as exc:
            if is_generation:
                _record_failure(503, path)
            return JSONResponse({"error": f"llama-server offline: {exc}"}, status_code=503)

    # ------------------------------------------------------------------
    # REST: app self-update (git pull + tray relaunch, see update.py)
    # ------------------------------------------------------------------

    @app.get("/api/update/check")
    async def update_check(force: bool = False) -> dict:
        return await asyncio.to_thread(app_update.check, force)

    @app.post("/api/update/apply")
    async def update_apply() -> dict:
        res = await asyncio.to_thread(app_update.apply_update)
        if not res.get("ok"):
            return res
        if RESTART_HOOK is None:
            return {
                **res, "restarting": False,
                "note": "update pulled — restart the dev server manually",
            }
        # The hook spawns the relaunched launcher (direct update) or only
        # shuts this process down (deferred: the bootstrap helper merges
        # after exit and relaunches the app itself). Either way the response
        # can be lost in the shutdown race, so the frontend recovers by
        # polling /api/health and reloading.
        try:
            if res.get("deferred"):
                RESTART_HOOK(deferred=True)
            else:
                RESTART_HOOK()
        except Exception:
            log.exception("restart hook failed")
            return {"ok": False, "error": "restart failed — try again"}
        return {**res, "restarting": True}

    @app.get("/api/update/result")
    async def update_result() -> dict:
        # One-shot outcome of a deferred update from the previous launch
        # (None when there is nothing to report).
        return {"result": await asyncio.to_thread(app_update.consume_update_result)}

    # ------------------------------------------------------------------
    # WebSockets
    # ------------------------------------------------------------------

    @app.websocket("/ws/logs")
    async def ws_logs(ws: WebSocket) -> None:
        await ws.accept()
        queue = manager.subscribe()
        try:
            await ws.send_json({"type": "init", "lines": manager.log_history(), "state": manager.snapshot()})
            while True:
                event = await queue.get()
                await ws.send_json(event)
        except (WebSocketDisconnect, RuntimeError):
            pass
        finally:
            manager.unsubscribe(queue)

    # ------------------------------------------------------------------
    # static frontend
    # ------------------------------------------------------------------

    app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")
    return app


app = create_app()
