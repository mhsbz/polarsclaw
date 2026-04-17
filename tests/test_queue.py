"""Tests for polarsclaw.queue."""

from __future__ import annotations

import asyncio

import pytest

from polarsclaw.queue.command_queue import CommandQueue
from polarsclaw.queue.lanes import Lane, LaneManager
from polarsclaw.queue.modes import collect_messages, should_coalesce
from polarsclaw.types import QueueMode


class TestLaneManager:
    def test_get_or_create(self) -> None:
        lm = LaneManager()
        lane = lm.get_or_create("s1")
        assert isinstance(lane, Lane)
        assert lane.session_id == "s1"
        assert lm.get_or_create("s1") is lane

    def test_release(self) -> None:
        lm = LaneManager()
        lane = lm.get_or_create("s1")
        lane.pending = 0
        lm.release("s1")
        assert lm.active_count == 0

    def test_release_with_pending(self) -> None:
        lm = LaneManager()
        lane = lm.get_or_create("s1")
        lane.pending = 1
        lm.release("s1")
        assert lm.active_count == 1


class TestModes:
    def test_collect_messages(self) -> None:
        result = collect_messages(["hello", "world"])
        assert result == "hello\nworld"

    def test_collect_messages_filters_empty(self) -> None:
        result = collect_messages(["hello", "", "world"])
        assert result == "hello\nworld"

    def test_should_coalesce_collect(self) -> None:
        assert should_coalesce(QueueMode.COLLECT) is True

    def test_should_coalesce_followup(self) -> None:
        assert should_coalesce(QueueMode.FOLLOWUP) is False


class TestCommandQueue:
    async def test_enqueue_returns_request_id(self) -> None:
        q = CommandQueue()
        rid = await q.enqueue("s1", "hello", QueueMode.FOLLOWUP)
        assert isinstance(rid, str)
        assert q.pending_count == 1

    async def test_process_handles_message(self) -> None:
        q = CommandQueue()
        results: list[str] = []

        async def handler(sid: str, rid: str, msg: str) -> str:
            results.append(msg)
            return "ok"

        await q.enqueue("s1", "hi", QueueMode.FOLLOWUP)

        process_task = asyncio.create_task(q.process(handler))
        await asyncio.sleep(0.3)
        await q.stop()
        process_task.cancel()
        try:
            await process_task
        except asyncio.CancelledError:
            pass

        assert results == ["hi"]

    async def test_collect_mode_coalesces(self) -> None:
        q = CommandQueue(collect_window_ms=100)
        results: list[str] = []

        async def handler(sid: str, rid: str, msg: str) -> str:
            results.append(msg)
            return "ok"

        await q.enqueue("s1", "msg1", QueueMode.COLLECT)
        await q.enqueue("s1", "msg2", QueueMode.COLLECT)

        process_task = asyncio.create_task(q.process(handler))
        await asyncio.sleep(0.5)
        await q.stop()
        process_task.cancel()
        try:
            await process_task
        except asyncio.CancelledError:
            pass

        # Should be coalesced into one message
        assert len(results) == 1
        assert "msg1" in results[0]
        assert "msg2" in results[0]

    async def test_stop_graceful(self) -> None:
        q = CommandQueue()
        process_task = asyncio.create_task(q.process(AsyncMockHandler()))
        await asyncio.sleep(0.1)
        await q.stop()
        process_task.cancel()
        try:
            await process_task
        except asyncio.CancelledError:
            pass


class AsyncMockHandler:
    async def __call__(self, sid: str, rid: str, msg: str) -> str:
        return "ok"
