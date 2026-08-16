"""FastAPI application: REST API, WebSockets, static frontend serving."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ValidationError

from .config import AppConfig, load_config, save_config
from .process import LlamaServerManager

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-7s %(name)s: %(message)s")
log = logging.getLogger("llama-monitor")

FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"


class StartRequest(BaseModel):
    args: list[str] = []


def create_app() -> FastAPI:
    config: AppConfig = load_config()
    manager = LlamaServerManager(lambda: config)

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        log.info("llama-monitor panel starting")
        await manager.on_startup()
        log.info("panel ready (state=%s)", manager.snapshot()["state"])
        yield
        await manager.shutdown()

    app = FastAPI(title="llama-monitor", version="0.1.0", lifespan=lifespan)

    # ------------------------------------------------------------------
    # REST
    # ------------------------------------------------------------------

    @app.get("/api/health")
    async def health() -> dict:
        return {"ok": True}

    @app.get("/api/state")
    async def state() -> dict:
        return manager.snapshot()

    @app.post("/api/server/start")
    async def server_start(body: StartRequest) -> dict:
        return await manager.start(body.args)

    @app.post("/api/server/stop")
    async def server_stop() -> dict:
        return await manager.stop()

    @app.post("/api/server/restart")
    async def server_restart(body: StartRequest | None = None) -> dict:
        args = body.args if body and body.args else None
        return await manager.restart(args)

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
