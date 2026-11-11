"""HTTP + WebSocket API.

    POST /api/sessions                 create a session            -> {sessionId, snapshot}
    GET  /api/sessions/{id}            current snapshot
    WS   /ws/sessions/{id}             live events (server -> client) and commands (client -> server)
    GET  /api/health
    GET  /api/admin/sessions           event-log export, needs ADMIN_TOKEN
    GET  /api/admin/sessions/{id}/events

Run with exactly one worker: sessions live in this process's memory.
    uvicorn app.main:app --host 0.0.0.0 --port 8000
"""
from __future__ import annotations

import asyncio
import json
import logging
import secrets
import time
from collections import defaultdict, deque
from contextlib import asynccontextmanager
from typing import Any, Optional

from fastapi import FastAPI, Header, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import ValidationError

from .config import Settings, get_settings
from .orchestrator import Connection, SessionRegistry
from .pipeline import Pipeline, load_pipeline
from .protocol import CLIENT_COMMANDS, PROTOCOL_VERSION, CreateSessionRequest, CreateSessionResponse, ErrorEvent
from .store import Store

log = logging.getLogger("csl")
MAX_COMMAND_BYTES = 32_000


def create_app(settings: Optional[Settings] = None, pipeline: Optional[Pipeline] = None) -> FastAPI:
    settings = settings or get_settings()
    origins = settings.cors_origin_list
    allow_all = "*" in origins

    def origin_allowed(origin: Optional[str]) -> bool:
        # Non-browser clients (CLI, tests, curl) send no Origin header.
        return allow_all or origin is None or origin.rstrip("/") in origins

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        store = Store(settings.database_path)
        await store.start()
        registry = SessionRegistry(settings, store, pipeline or load_pipeline(settings))
        registry.start()
        app.state.store, app.state.registry = store, registry
        log.info("pipeline=%s database=%s", registry.pipeline.name, settings.database_path)
        yield
        await registry.stop()
        await store.stop()

    app = FastAPI(title="CSL backend", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"] if allow_all else origins,
        allow_methods=["GET", "POST"],
        allow_headers=["*"],
    )
    recent: dict[str, deque[float]] = defaultdict(deque)

    def registry() -> SessionRegistry:
        return app.state.registry

    @app.get("/api/health")
    async def health() -> dict[str, Any]:
        return {
            "ok": True,
            "pipeline": registry().pipeline.name,
            "activeSessions": len(registry().runners),
            "protocolVersion": PROTOCOL_VERSION,
        }

    @app.post("/api/sessions")
    async def create_session(body: CreateSessionRequest, request: Request) -> dict[str, Any]:
        if settings.access_code and not secrets.compare_digest(
            (body.access_code or "").encode(), settings.access_code.encode()
        ):
            raise HTTPException(403, "Wrong access code.")
        ip = request.client.host if request.client else "?"
        window = recent[ip]
        now = time.time()
        while window and now - window[0] > 3600:
            window.popleft()
        if len(window) >= settings.sessions_per_ip_per_hour:
            raise HTTPException(429, "Too many sessions from this address. Try again later.")
        if not registry().has_capacity:
            raise HTTPException(503, "The server is busy. Try again in a few minutes.")
        if not body.topic.strip():
            raise HTTPException(422, "Topic must not be empty.")
        window.append(now)
        runner = registry().create(body.topic, body.language)
        return CreateSessionResponse(session_id=runner.session.id, snapshot=runner.session.snapshot()).wire()

    @app.get("/api/sessions/{session_id}")
    async def get_session(session_id: str) -> dict[str, Any]:
        runner = await registry().get(session_id)
        if runner is None:
            raise HTTPException(404, "No such session.")
        return runner.session.snapshot().wire()

    def require_admin(authorization: Optional[str]) -> None:
        token = settings.admin_token
        if not token:
            raise HTTPException(404)
        if not authorization or not secrets.compare_digest(authorization.encode(), f"Bearer {token}".encode()):
            raise HTTPException(401)

    @app.get("/api/admin/sessions")
    async def admin_sessions(authorization: Optional[str] = Header(default=None)) -> list[dict[str, Any]]:
        require_admin(authorization)
        return await app.state.store.list_sessions()

    @app.get("/api/admin/sessions/{session_id}/events")
    async def admin_events(session_id: str, authorization: Optional[str] = Header(default=None)) -> list[dict[str, Any]]:
        require_admin(authorization)
        return await app.state.store.list_events(session_id)

    @app.websocket("/ws/sessions/{session_id}")
    async def session_socket(websocket: WebSocket, session_id: str) -> None:
        await websocket.accept()
        if not origin_allowed(websocket.headers.get("origin")):
            await websocket.close(code=4403, reason="origin not allowed")
            return
        runner = await registry().get(session_id)
        if runner is None:
            await websocket.close(code=4404, reason="no such session")
            return
        conn = Connection()
        runner.attach(conn)

        def reject(code: str, message: str) -> None:
            conn.push({"type": "error", "seq": None, "ts": time.time(),
                       "data": ErrorEvent(code=code, message=message).wire()})

        async def sender() -> None:
            try:
                while True:
                    envelope = await conn.queue.get()
                    if envelope is None:  # the session was stopped or this client is too slow
                        await websocket.close(code=1012, reason="session closed")
                        return
                    await websocket.send_text(json.dumps(envelope, ensure_ascii=False))
            except (WebSocketDisconnect, RuntimeError):
                pass

        send_task = asyncio.create_task(sender())
        try:
            while True:
                raw = await websocket.receive_text()
                if len(raw) > MAX_COMMAND_BYTES:
                    reject("bad_command", "Command too large.")
                    continue
                try:
                    command = json.loads(raw)
                    ctype = command["type"]
                    model = CLIENT_COMMANDS[ctype].model_validate(command.get("data") or {})
                except (ValueError, KeyError, TypeError, ValidationError) as exc:
                    reject("bad_command", f"Could not read command: {type(exc).__name__}")
                    continue
                if ctype == "ping":
                    conn.push({"type": "pong", "seq": None, "ts": time.time(), "data": {}})
                else:
                    runner.submit(ctype, model)
        except (WebSocketDisconnect, RuntimeError):
            pass
        finally:
            runner.detach(conn)
            send_task.cancel()
            await asyncio.gather(send_task, return_exceptions=True)

    return app


logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
app = create_app()
