"""Web server: serves the UI and streams sensor snapshots over a WebSocket."""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import threading
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .sources import Source
from .state import SensorState

log = logging.getLogger(__name__)

STATIC_DIR = Path(__file__).parent / "static"
BROADCAST_INTERVAL_S = 0.1


def create_app(source: Source, state: SensorState) -> FastAPI:
    clients: set[WebSocket] = set()

    async def broadcast_loop() -> None:
        while True:
            await asyncio.sleep(BROADCAST_INTERVAL_S)
            phases = state.drain_phases()
            if not clients:
                continue
            message = state.snapshot()
            message["heart_wave"] = [heart for heart, _ in phases]
            payload = json.dumps(message)
            for ws in list(clients):
                try:
                    await ws.send_text(payload)
                except Exception:
                    clients.discard(ws)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        stop = threading.Event()
        reader = threading.Thread(target=_run_source, args=(source, state, stop), name="radar", daemon=True)
        reader.start()
        broadcaster = asyncio.create_task(broadcast_loop())
        try:
            yield
        finally:
            stop.set()
            broadcaster.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await broadcaster
            reader.join(timeout=2)

    app = FastAPI(title="Positional Pi Heartbeat Sensor", lifespan=lifespan)

    @app.get("/")
    async def index() -> FileResponse:
        return FileResponse(STATIC_DIR / "index.html")

    @app.get("/api/state")
    async def api_state() -> dict:
        return state.snapshot()

    @app.websocket("/ws")
    async def ws_endpoint(ws: WebSocket) -> None:
        await ws.accept()
        clients.add(ws)
        try:
            await ws.send_text(json.dumps(state.snapshot()))
            while True:
                await ws.receive_text()  # we only push; this just notices disconnects
        except WebSocketDisconnect:
            pass
        finally:
            clients.discard(ws)

    @app.middleware("http")
    async def no_stale_ui(request, call_next):
        # Browsers otherwise keep showing an old UI after the app is updated.
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-cache"
        return response

    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
    return app


def _run_source(source: Source, state: SensorState, stop: threading.Event) -> None:
    try:
        source.run(state, stop)
    except Exception:
        log.exception("Radar source %s crashed", source.name)
        state.set_status(False, f"{source.name} crashed; see server logs")
