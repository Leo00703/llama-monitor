"""FastAPI application: REST API, WebSockets, static frontend serving."""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, ValidationError

from .config import PRESETS_DIR, AppConfig, load_config, save_config
from .flags import build_args, parse_supported_flags, validate_settings
from .metrics import MetricsCollector
from .process import LlamaServerManager
from .presets import PresetStore
from .schema import LaunchSettings, Preset

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-7s %(name)s: %(message)s")
log = logging.getLogger("llama-monitor")

FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"
METRICS_INTERVAL = 1.5


async def _metrics_loop(collector: MetricsCollector, manager: LlamaServerManager) -> None:
    """Poll system + inference metrics and push them to WebSocket listeners."""
    while True:
        await asyncio.sleep(METRICS_INTERVAL)
        try:
            data = await collector.snapshot(manager.current_port())
        except Exception:  # metrics must never take the panel down
            log.exception("metrics collection failed")
            continue
        manager.broadcast({"type": "metrics", "data": data})


class StartRequest(BaseModel):
    args: list[str] = Field(default_factory=list)
    preset_id: str = ""


class PresetRequest(BaseModel):
    name: str = "New preset"
    launch: Optional[LaunchSettings] = None
    generation: Optional[dict[str, Any]] = None


def create_app() -> FastAPI:
    config: AppConfig = load_config()
    manager = LlamaServerManager(lambda: config)
    store = PresetStore(PRESETS_DIR)
    collector = MetricsCollector()

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        log.info("llama-monitor panel starting")
        await manager.on_startup()
        log.info("panel ready (state=%s)", manager.snapshot()["state"])
        task = asyncio.create_task(_metrics_loop(collector, manager))
        yield
        task.cancel()
        await manager.shutdown()

    app = FastAPI(title="llama-monitor", version="0.3.0", lifespan=lifespan)

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
        result.update(response_extra)
        return result

    @app.post("/api/server/stop")
    async def server_stop() -> dict:
        return await manager.stop()

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
        result.update(response_extra)
        return result

    # ------------------------------------------------------------------
    # REST: config
    # ------------------------------------------------------------------

    @app.get("/api/config")
    async def get_config() -> dict:
        return config.model_dump()

    @app.post("/api/config")
    async def post_config(body: dict[str, Any]) -> dict:
        try:
            new_config = AppConfig.model_validate(body)
        except ValidationError as exc:
            return {"ok": False, "error": str(exc)}
        # mutate the live object in place: the manager holds a reference to it
        for name in new_config.model_fields:
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
