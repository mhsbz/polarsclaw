"""Lane management — per-session serialisation primitives."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field


@dataclass
class Lane:
    """A single session lane with its own serialisation semaphore."""

    session_id: str
    semaphore: asyncio.Semaphore = field(default_factory=lambda: asyncio.Semaphore(1))
    pending: int = 0


class LaneManager:
    """Create, retrieve, and garbage-collect session lanes."""

    def __init__(self) -> None:
        self._lanes: dict[str, Lane] = {}

    def get_or_create(self, session_id: str) -> Lane:
        """Return the lane for *session_id*, creating one if needed."""
        if session_id not in self._lanes:
            self._lanes[session_id] = Lane(session_id=session_id)
        return self._lanes[session_id]

    def release(self, session_id: str) -> None:
        """Remove a lane when it has no more pending items."""
        lane = self._lanes.get(session_id)
        if lane and lane.pending <= 0:
            self._lanes.pop(session_id, None)

    @property
    def active_count(self) -> int:
        return len(self._lanes)
