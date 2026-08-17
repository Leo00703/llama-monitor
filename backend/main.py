"""FastAPI application: REST API, WebSockets, static frontend serving."""

from __future__ import annotations

import asyncio
import json
import logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, AsyncIterator, Optional

from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, ValidationError

from .config import PRESETS_DIR, AppConfig, load_config, save_config
from .flags import build_args, parse_supported_flags, validate_settings
from .metrics import MetricsCollector
from .models import list_models
from .process import LlamaServerManager
from .presets import PresetStore
from .proxy import ProxyOffline, ServerProxy
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
        task = asyncio.create_task(_metrics_loop(collector, manager))
        yield
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
                    return JSONResponse({"error": "invalid JSON body"}, status_code=400)
        headers = dict(request.headers.items())
        query = request.url.query

        if proxy.base_url() is None:
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
            return Response(content=content, status_code=status, headers=out_headers)
        except ProxyOffline as exc:
            return JSONResponse({"error": f"llama-server offline: {exc}"}, status_code=503)

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
