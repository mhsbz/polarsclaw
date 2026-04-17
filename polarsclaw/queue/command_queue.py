"""CommandQueue — lane-aware async FIFO with mode support."""

from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

from polarsclaw.queue.lanes import LaneManager
from polarsclaw.queue.modes import collect_messages, should_coalesce
from polarsclaw.types import QueueMode


@dataclass
class _QueueItem:
    request_id: str
    session_id: str
    message: str
    mode: QueueMode
    created: float = field(default_factory=lambda: asyncio.get_event_loop().time())


# Handler signature: (session_id, request_id, message) -> result string
HandlerFn = Callable[[str, str, str], Awaitable[str]]


class CommandQueue:
    """Async command queue with per-session lanes and global concurrency cap.

    Parameters
    ----------
    max_concurrency:
        Maximum number of items processed in parallel across all sessions.
    max_pending:
        Hard cap on total pending items (across all lanes).
    collect_window_ms:
        Debounce window in milliseconds for COLLECT mode.
    """

    def __init__(
        self,
        max_concurrency: int = 4,
        max_pending: int = 100,
        collect_window_ms: int = 2000,
    ) -> None:
        self._global_sem = asyncio.Semaphore(max_concurrency)
        self._max_pending = max_pending
        self._collect_window_ms = collect_window_ms
        self._lanes = LaneManager()
        self._queue: asyncio.Queue[_QueueItem] = asyncio.Queue()
        self._running = False
        self._tasks: set[asyncio.Task[Any]] = set()
        self._cancel_events: dict[str, asyncio.Event] = {}  # session_id -> cancel event

        # COLLECT buffers: session_id -> list of (request_id, message)
        self._collect_buffers: dict[str, list[tuple[str, str]]] = {}
        self._collect_timers: dict[str, asyncio.Task[Any]] = {}

    # ── Public API ───────────────────────────────────────────────────────

    @property
    def pending_count(self) -> int:
        return self._queue.qsize()

    async def enqueue(
        self,
        session_id: str,
        message: str,
        mode: QueueMode = QueueMode.COLLECT,
        *,
        request_id: str | None = None,
    ) -> str:
        """Add a message to the queue. Returns the request_id."""
        rid = request_id or str(uuid.uuid4())

        if mode is QueueMode.INTERRUPT:
            await self._handle_interrupt(session_id, rid, message)
            return rid

        if should_coalesce(mode):
            await self._handle_collect(session_id, rid, message)
            return rid

        # FOLLOWUP / STEER — straight enqueue
        lane = self._lanes.get_or_create(session_id)
        lane.pending += 1
        await self._queue.put(_QueueItem(
            request_id=rid,
            session_id=session_id,
            message=message,
            mode=mode,
        ))
        return rid

    async def process(self, handler: HandlerFn) -> None:
        """Main processing loop — call once, runs until :meth:`stop`."""
        self._running = True
        try:
            while self._running:
                try:
                    item = await asyncio.wait_for(self._queue.get(), timeout=0.5)
                except asyncio.TimeoutError:
                    continue

                task = asyncio.create_task(self._process_item(item, handler))
                self._tasks.add(task)
                task.add_done_callback(self._tasks.discard)
        except asyncio.CancelledError:
            pass

    async def stop(self) -> None:
        """Gracefully shut down: finish in-flight work, then exit."""
        self._running = False
        # Cancel all collect timers
        for timer in self._collect_timers.values():
            timer.cancel()
        self._collect_timers.clear()
        # Wait for in-flight tasks
        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)

    # ── Internal ─────────────────────────────────────────────────────────

    async def _process_item(self, item: _QueueItem, handler: HandlerFn) -> None:
        lane = self._lanes.get_or_create(item.session_id)
        cancel_event = self._cancel_events.get(item.session_id)

        # Check if cancelled before acquiring
        if cancel_event and cancel_event.is_set():
            self._cancel_events.pop(item.session_id, None)
            lane.pending -= 1
            self._lanes.release(item.session_id)
            return

        async with self._global_sem:
            async with lane.semaphore:
                try:
                    await handler(item.session_id, item.request_id, item.message)
                except Exception:
                    pass  # Handler is responsible for error reporting
                finally:
                    lane.pending -= 1
                    self._lanes.release(item.session_id)

    async def _handle_interrupt(self, session_id: str, request_id: str, message: str) -> None:
        """Cancel pending work for *session_id* and enqueue the new message."""
        # Signal cancellation to any in-flight item for this session
        evt = asyncio.Event()
        evt.set()
        self._cancel_events[session_id] = evt

        # Flush collect buffer if present
        self._collect_buffers.pop(session_id, None)
        timer = self._collect_timers.pop(session_id, None)
        if timer:
            timer.cancel()

        # Enqueue as immediate
        lane = self._lanes.get_or_create(session_id)
        lane.pending += 1
        await self._queue.put(_QueueItem(
            request_id=request_id,
            session_id=session_id,
            message=message,
            mode=QueueMode.INTERRUPT,
        ))

    async def _handle_collect(self, session_id: str, request_id: str, message: str) -> None:
        """Buffer messages and flush after the debounce window."""
        buf = self._collect_buffers.setdefault(session_id, [])
        buf.append((request_id, message))

        # Reset the debounce timer
        old_timer = self._collect_timers.pop(session_id, None)
        if old_timer:
            old_timer.cancel()

        self._collect_timers[session_id] = asyncio.create_task(
            self._flush_collect_after(session_id)
        )

    async def _flush_collect_after(self, session_id: str) -> None:
        """Wait for the debounce window then flush the collect buffer."""
        await asyncio.sleep(self._collect_window_ms / 1000.0)
        await self._flush_collect(session_id)

    async def _flush_collect(self, session_id: str) -> None:
        buf = self._collect_buffers.pop(session_id, [])
        self._collect_timers.pop(session_id, None)
        if not buf:
            return

        # Use the last request_id as the representative
        last_rid = buf[-1][0]
        combined = collect_messages([m for _, m in buf], self._collect_window_ms)

        lane = self._lanes.get_or_create(session_id)
        lane.pending += 1
        await self._queue.put(_QueueItem(
            request_id=last_rid,
            session_id=session_id,
            message=combined,
            mode=QueueMode.COLLECT,
        ))
