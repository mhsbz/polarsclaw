"""Tests for polarsclaw.sessions."""

from __future__ import annotations

import pytest

from polarsclaw.sessions.isolation import resolve_session_key
from polarsclaw.sessions.manager import SessionManager
from polarsclaw.storage.database import Database
from polarsclaw.types import DMScope


class TestResolveSessionKey:
    def test_main_scope(self) -> None:
        key = resolve_session_key("agent1", "peer1", "chan1", DMScope.MAIN)
        assert key == "session:agent1"

    def test_per_peer_scope(self) -> None:
        key = resolve_session_key("agent1", "peer1", "chan1", DMScope.PER_PEER)
        assert key == "session:agent1:peer1"

    def test_per_peer_no_peer(self) -> None:
        key = resolve_session_key("agent1", None, None, DMScope.PER_PEER)
        assert key == "session:agent1:_"

    def test_per_channel_peer(self) -> None:
        key = resolve_session_key("agent1", "peer1", "chan1", DMScope.PER_CHANNEL_PEER)
        assert key == "session:agent1:chan1:peer1"

    def test_per_channel_peer_no_values(self) -> None:
        key = resolve_session_key("agent1", None, None, DMScope.PER_CHANNEL_PEER)
        assert key == "session:agent1:_:_"


class TestSessionManager:
    async def test_create(self, tmp_db: Database) -> None:
        mgr = SessionManager(tmp_db)
        session = await mgr.create("agent1", title="Test")
        assert session.id
        assert session.scope == "session:agent1"

    async def test_resume(self, tmp_db: Database) -> None:
        mgr = SessionManager(tmp_db)
        s = await mgr.create("agent1")
        resumed = await mgr.resume(s.id)
        assert resumed.id == s.id

    async def test_resolve_creates_then_reuses(self, tmp_db: Database) -> None:
        mgr = SessionManager(tmp_db)
        s1 = await mgr.resolve("agent1")
        s2 = await mgr.resolve("agent1")
        assert s1.id == s2.id

    async def test_resolve_per_peer_different_peers(self, tmp_db: Database) -> None:
        mgr = SessionManager(tmp_db, dm_scope=DMScope.PER_PEER)
        s1 = await mgr.resolve("agent1", peer_id="alice")
        s2 = await mgr.resolve("agent1", peer_id="bob")
        assert s1.id != s2.id

    async def test_daily_reset(self, tmp_db: Database) -> None:
        mgr = SessionManager(tmp_db)
        # Create a session with old timestamp
        from polarsclaw.storage.repositories import SessionRepo
        repo = SessionRepo(tmp_db)
        sid = await repo.create(title="Old", scope="main")
        await tmp_db.execute_write(
            "UPDATE sessions SET updated_at = '2020-01-01 00:00:00' WHERE id = ?",
            (sid,),
        )
        count = await mgr.daily_reset()
        assert count >= 1
