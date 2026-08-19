"""FastAPI application: REST API, WebSockets, static frontend serving."""

from __future__ import annotations

import asyncio
import json
import logging
import threading
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, AsyncIterator, Callable, Optional

from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, ValidationError

from .analytics import (
    AnalyticsStore,
    LiveLogStats,
    PowerSampler,
    PrintTimingTracker,
    RANGES,
)
from .config import DATA_DIR, PRESETS_DIR, AppConfig, load_config, save_config
from .flags import build_args, parse_supported_flags, validate_settings
from .metrics import MetricsCollector
from .models import list_models
from .process import LlamaServerManager
from .presets import PresetStore
from .proxy import INJECT_PATHS, ProxyOffline, ServerProxy
from .schema import LaunchSettings, Preset
from . import update as app_update

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-7s %(name)s: %(message)s")
log = logging.getLogger("llama-monitor")

FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"
METRICS_INTERVAL = 1.5

# Set by the tray launcher (set_restart_hook) to relaunch the app after an
# update is pulled. None in dev/uvicorn mode: the pull still works, the
# restart is reported as manual.
RESTART_HOOK: Optional[Callable[[], None]] = None


def set_restart_hook(hook: Optional[Callable[[], None]]) -> None:
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
                        live_log: LiveLogStats) -> None:
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
        manager.broadcast({"type": "metrics", "data": data})


# A log rate older than this is stale, not live (progress lines come about
# once a second / every 3s; allow slack for a slow server).
_LIVE_LOG_STALE = 10.0


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
        if live_log.prompt_tps is not None and now - live_log.prompt_ts < _LIVE_LOG_STALE:
            inf["prompt_tps"] = round(live_log.prompt_tps, 2)
        if live_log.gen_tps is not None and now - live_log.gen_ts < _LIVE_LOG_STALE:
            inf["gen_tps"] = round(live_log.gen_tps, 2)


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
    power = PowerSampler()

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
        task = asyncio.create_task(_metrics_loop(collector, manager, power, tracker, live_log))
        updater = threading.Thread(
            target=_update_loop, args=(manager, loop, config),
            daemon=True, name="update-checker")
        updater.start()
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
        supported = await parse_supported_flags(exe) if exe else None
        if exe is None:
            warnings.append("llama-server executable not configured — flag version check skipped")

        args, flag_warnings = build_args(
            preset.launch,
            models_root=models_root,
            supported=supported,
        )
        warnings.extend(flag_warnings)
        return {"ok": True, "args": args, "warnings": warnings, "errors": []}

    @app.post("/api/presets/{preset_id}/preview")
    async def preset_preview(preset_id: str) -> dict:
        return await prepare_launch(preset_id)

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
        # The hook spawns the relaunched launcher and shuts this process
        # down; the response can be lost in that race, so the frontend
        # recovers by polling /api/health and reloading.
        try:
            RESTART_HOOK()
        except Exception:
            log.exception("restart hook failed")
            return {"ok": False, "error": "restart failed — try again"}
        return {**res, "restarting": True}

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
