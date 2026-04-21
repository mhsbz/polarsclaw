"""Shared gateway bridge for routing queue events back to WebSocket clients."""

from __future__ import annotations

import asyncio
from collections import defaultdict

from fastapi import WebSocket

from polarsclaw.gateway.protocol import DONE, ERROR, STREAM, encode, make


class GatewayBridge:
    """Tracks active WebSocket connections keyed by request id."""

    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._by_request: dict[str, WebSocket] = {}
        self._by_session: dict[str, set[WebSocket]] = defaultdict(set)

    async def register(
        self,
        request_id: str,
        websocket: WebSocket,
        session_id: str,
    ) -> None:
        async with self._lock:
            self._by_request[request_id] = websocket
            self._by_session[session_id].add(websocket)

    async def unregister_websocket(self, websocket: WebSocket) -> None:
        async with self._lock:
            for request_id, ws in list(self._by_request.items()):
                if ws is websocket:
                    self._by_request.pop(request_id, None)

            for session_id, sockets in list(self._by_session.items()):
                sockets.discard(websocket)
                if not sockets:
                    self._by_session.pop(session_id, None)

    async def stream(self, request_id: str, chunk: str) -> None:
        websocket = await self._get(request_id)
        if websocket is None:
            return
        frame = make(STREAM, data={"chunk": chunk}, request_id=request_id)
        await websocket.send_text(encode(frame))

    async def done(self, request_id: str, result: str) -> None:
        websocket = await self._pop_request(request_id)
        if websocket is None:
            return
        frame = make(DONE, data={"result": result}, request_id=request_id)
        await websocket.send_text(encode(frame))

    async def error(self, request_id: str, detail: str) -> None:
        websocket = await self._pop_request(request_id)
        if websocket is None:
            return
        frame = make(ERROR, data={"detail": detail}, request_id=request_id)
        await websocket.send_text(encode(frame))

    async def _get(self, request_id: str) -> WebSocket | None:
        async with self._lock:
            return self._by_request.get(request_id)

    async def _pop_request(self, request_id: str) -> WebSocket | None:
        async with self._lock:
            return self._by_request.pop(request_id, None)
