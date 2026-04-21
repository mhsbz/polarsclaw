"""FastAPI gateway — WebSocket + REST endpoints for PolarsClaw."""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Any

from fastapi import FastAPI, Query, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from polarsclaw.gateway.auth import verify_token
from polarsclaw.gateway.bridge import GatewayBridge
from polarsclaw.gateway.protocol import ACK, DONE, ERROR, HELLO, MESSAGE, STREAM, decode, encode, make
from polarsclaw.types import QueueMode, WSMessageType

if TYPE_CHECKING:
    from polarsclaw.config.settings import Settings
    from polarsclaw.queue.command_queue import CommandQueue
    from polarsclaw.routing import Router  # noqa: F401
    from polarsclaw.sessions.manager import SessionManager


def create_gateway(
    settings: "Settings",
    command_queue: "CommandQueue",
    router: Any = None,
    session_mgr: "SessionManager | None" = None,
    bridge: GatewayBridge | None = None,
) -> FastAPI:
    """Build and return a fully-configured :class:`FastAPI` application."""

    app = FastAPI(title="PolarsClaw Gateway", version="2.0.0")

    # CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.gateway.cors_origins,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    bridge = bridge or GatewayBridge()

    # ── WebSocket ────────────────────────────────────────────────────────

    @app.websocket("/ws")
    async def ws_endpoint(
        websocket: WebSocket,
        token: str | None = Query(default=None),
        session_id: str | None = Query(default=None),
    ) -> None:
        # Auth
        if not verify_token(token, settings):
            await websocket.close(code=4001, reason="Unauthorized")
            return

        await websocket.accept()

        # Resolve session
        sid = session_id or str(uuid.uuid4())

        # Send hello
        hello = make(HELLO, data={"session_id": sid}, session_id=sid)
        await websocket.send_text(encode(hello))

        try:
            while True:
                raw = await websocket.receive_text()
                try:
                    msg = decode(raw)
                except (ValueError, KeyError):
                    err = make(ERROR, data={"detail": "Invalid message format"}, session_id=sid)
                    await websocket.send_text(encode(err))
                    continue

                request_id = msg.request_id or str(uuid.uuid4())
                mode_str = msg.data.get("mode", settings.queue.default_mode)
                mode = QueueMode(mode_str)
                content = msg.data.get("content", "")

                # Register connection for streaming
                await bridge.register(request_id, websocket, sid)

                # Enqueue
                rid = await command_queue.enqueue(sid, content, mode, request_id=request_id)

                # ACK
                ack = make(ACK, data={"request_id": rid}, session_id=sid, request_id=rid)
                await websocket.send_text(encode(ack))

        except WebSocketDisconnect:
            pass
        finally:
            await bridge.unregister_websocket(websocket)

    app.state.gateway_bridge = bridge  # type: ignore[attr-defined]

    # ── REST endpoints ───────────────────────────────────────────────────

    @app.get("/health")
    async def health() -> JSONResponse:
        return JSONResponse({"status": "ok", "queue_size": command_queue.pending_count})

    @app.get("/sessions")
    async def list_sessions() -> JSONResponse:
        if session_mgr is None:
            return JSONResponse({"sessions": []})
        sessions = await session_mgr.list_all()
        return JSONResponse({"sessions": [s.model_dump(mode="json") for s in sessions]})

    @app.post("/message")
    async def post_message(body: dict[str, Any]) -> JSONResponse:
        sid = body.get("session_id", str(uuid.uuid4()))
        content = body.get("content", "")
        mode_str = body.get("mode", settings.queue.default_mode)
        mode = QueueMode(mode_str)

        request_id = await command_queue.enqueue(sid, content, mode)
        return JSONResponse({"request_id": request_id, "session_id": sid}, status_code=202)

    return app
