"""Tests for polarsclaw.gateway.server."""

from __future__ import annotations

import json

import pytest
from httpx import ASGITransport, AsyncClient

from polarsclaw.config.settings import Settings
from polarsclaw.gateway.server import create_gateway
from polarsclaw.queue.command_queue import CommandQueue


def _make_app(auth_token: str | None = None):
    settings = Settings()
    settings.gateway.auth_token = auth_token
    queue = CommandQueue()
    return create_gateway(settings, queue)


class TestHealthEndpoint:
    async def test_health_returns_200(self) -> None:
        app = _make_app()
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"


class TestPostMessage:
    async def test_post_message(self) -> None:
        app = _make_app()
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post("/message", json={"content": "hello"})
        assert resp.status_code == 202
        data = resp.json()
        assert "request_id" in data
        assert "session_id" in data


class TestWebSocket:
    async def test_ws_no_auth_hello(self) -> None:
        app = _make_app(auth_token=None)
        from starlette.testclient import TestClient

        with TestClient(app) as client:
            with client.websocket_connect("/ws") as ws:
                data = json.loads(ws.receive_text())
                assert data["type"] == "hello"
                assert "session_id" in data.get("data", {})

    async def test_ws_wrong_token_rejected(self) -> None:
        app = _make_app(auth_token="secret123")
        from starlette.testclient import TestClient

        with TestClient(app) as client:
            with pytest.raises(Exception):
                with client.websocket_connect("/ws?token=wrong") as ws:
                    ws.receive_text()
