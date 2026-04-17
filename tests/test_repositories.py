"""Tests for polarsclaw.storage.repositories."""

from __future__ import annotations

import pytest

from polarsclaw.errors import RecordNotFoundError
from polarsclaw.storage.repositories import CronRepo, MemoryRepo, MessageRepo, SessionRepo


class TestMemoryRepo:
    async def test_save_and_get(self, memory_repo: MemoryRepo) -> None:
        await memory_repo.save("k1", "v1")
        m = await memory_repo.get("k1")
        assert m.key == "k1"
        assert m.value == "v1"
        assert m.type == "general"

    async def test_upsert_same_key(self, memory_repo: MemoryRepo) -> None:
        await memory_repo.save("k1", "v1")
        await memory_repo.save("k1", "v2")
        m = await memory_repo.get("k1")
        assert m.value == "v2"

    async def test_search_fts5(self, memory_repo: MemoryRepo) -> None:
        await memory_repo.save("greeting", "hello world")
        await memory_repo.save("farewell", "goodbye world")
        results = await memory_repo.search("hello")
        assert len(results) >= 1
        assert results[0].key == "greeting"

    async def test_list_with_type_filter(self, memory_repo: MemoryRepo) -> None:
        await memory_repo.save("a", "1", type="fact")
        await memory_repo.save("b", "2", type="preference")
        facts = await memory_repo.list(type="fact")
        assert len(facts) == 1
        assert facts[0].key == "a"

    async def test_delete(self, memory_repo: MemoryRepo) -> None:
        await memory_repo.save("tmp", "data")
        await memory_repo.delete("tmp")
        with pytest.raises(RecordNotFoundError):
            await memory_repo.get("tmp")

    async def test_get_missing_raises(self, memory_repo: MemoryRepo) -> None:
        with pytest.raises(RecordNotFoundError):
            await memory_repo.get("nonexistent")


class TestSessionRepo:
    async def test_create_and_get(self, session_repo: SessionRepo) -> None:
        sid = await session_repo.create(title="Test Session")
        row = await session_repo.get(sid)
        assert row["title"] == "Test Session"
        assert row["scope"] == "main"

    async def test_list(self, session_repo: SessionRepo) -> None:
        await session_repo.create(title="S1", scope="a")
        await session_repo.create(title="S2", scope="b")
        all_sessions = await session_repo.list()
        assert len(all_sessions) == 2
        scoped = await session_repo.list(scope="a")
        assert len(scoped) == 1

    async def test_delete(self, session_repo: SessionRepo) -> None:
        sid = await session_repo.create(title="Del")
        await session_repo.delete(sid)
        with pytest.raises(RecordNotFoundError):
            await session_repo.get(sid)

    async def test_get_missing_raises(self, session_repo: SessionRepo) -> None:
        with pytest.raises(RecordNotFoundError):
            await session_repo.get("nonexistent")


class TestMessageRepo:
    async def test_add_and_list(self, session_repo: SessionRepo, message_repo: MessageRepo) -> None:
        sid = await session_repo.create(title="Chat")
        msg_id = await message_repo.add(sid, "user", "hello")
        assert isinstance(msg_id, int)
        msgs = await message_repo.list(sid)
        assert len(msgs) == 1
        assert msgs[0].role == "user"
        assert msgs[0].content == "hello"

    async def test_list_chronological_order(self, session_repo: SessionRepo, message_repo: MessageRepo) -> None:
        sid = await session_repo.create(title="Chat")
        await message_repo.add(sid, "user", "first")
        await message_repo.add(sid, "assistant", "second")
        msgs = await message_repo.list(sid)
        assert msgs[0].content == "first"
        assert msgs[1].content == "second"


class TestCronRepo:
    async def test_create_and_get(self, cron_repo: CronRepo) -> None:
        jid = await cron_repo.create("daily-check", "0 9 * * *", payload={"task": "check"})
        job = await cron_repo.get(jid)
        assert job["name"] == "daily-check"
        assert job["schedule"] == "0 9 * * *"

    async def test_list_enabled_only(self, cron_repo: CronRepo) -> None:
        j1 = await cron_repo.create("j1", "* * * * *", enabled=True)
        j2 = await cron_repo.create("j2", "* * * * *", enabled=False)
        all_jobs = await cron_repo.list()
        assert len(all_jobs) == 2
        enabled = await cron_repo.list(enabled_only=True)
        assert len(enabled) == 1

    async def test_delete(self, cron_repo: CronRepo) -> None:
        jid = await cron_repo.create("tmp", "* * * * *")
        await cron_repo.delete(jid)
        with pytest.raises(RecordNotFoundError):
            await cron_repo.get(jid)

    async def test_record_and_list_results(self, cron_repo: CronRepo) -> None:
        jid = await cron_repo.create("j1", "* * * * *")
        rid = await cron_repo.record_result(jid, "success", output="ok")
        results = await cron_repo.list_results(jid)
        assert len(results) == 1
        assert results[0]["status"] == "success"
        assert results[0]["output"] == "ok"

    async def test_get_by_name(self, cron_repo: CronRepo) -> None:
        await cron_repo.create("unique-name", "0 0 * * *")
        job = await cron_repo.get_by_name("unique-name")
        assert job["name"] == "unique-name"
