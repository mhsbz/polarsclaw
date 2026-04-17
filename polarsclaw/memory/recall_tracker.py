"""Tracks how often and how well chunks are recalled."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from polarsclaw.memory.db import MemoryDB

logger = logging.getLogger(__name__)


class RecallTracker:
    """Records and queries recall statistics for memory chunks."""

    def __init__(self, db: MemoryDB) -> None:
        self._db = db

    async def record(
        self,
        results: list,  # list[SearchResult] — avoids circular import
        query: str,
        session_id: str | None,
    ) -> None:
        """Record a recall event for each search result."""
        for r in results:
            await self._db.record_recall(
                chunk_id=r.chunk_id,
                query=query,
                score=r.score,
                session_id=session_id or "",
            )

    async def frequency(self, chunk_id: int, days: int = 30) -> int:
        """How many times *chunk_id* was recalled in the last *days* days."""
        conn = self._db._db.get_connection()
        async with conn.execute(
            "SELECT COUNT(*) FROM mem_recalls "
            "WHERE chunk_id = ? AND recalled_at >= datetime('now', ?)",
            (chunk_id, f"-{days} days"),
        ) as cur:
            row = await cur.fetchone()
            return row[0] if row else 0  # type: ignore[index]

    async def avg_relevance(self, chunk_id: int) -> float:
        """Average recall score for *chunk_id* across all time."""
        stats = await self._db.get_recall_stats(chunk_id)
        return stats["avg_score"]

    async def unique_queries(self, chunk_id: int) -> int:
        """Number of distinct queries that recalled *chunk_id*."""
        conn = self._db._db.get_connection()
        async with conn.execute(
            "SELECT COUNT(DISTINCT query) FROM mem_recalls WHERE chunk_id = ?",
            (chunk_id,),
        ) as cur:
            row = await cur.fetchone()
            return row[0] if row else 0  # type: ignore[index]

    async def last_recalled(self, chunk_id: int) -> datetime | None:
        """Timestamp of the most recent recall for *chunk_id*."""
        conn = self._db._db.get_connection()
        async with conn.execute(
            "SELECT MAX(recalled_at) FROM mem_recalls WHERE chunk_id = ?",
            (chunk_id,),
        ) as cur:
            row = await cur.fetchone()
            if not row or row[0] is None:  # type: ignore[index]
                return None
            return datetime.fromisoformat(row[0])  # type: ignore[index]
