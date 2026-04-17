"""Repository classes for sessions, memories, and cron jobs."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any, Sequence

import aiosqlite

from polarsclaw.errors import RecordNotFoundError
from polarsclaw.storage.database import Database
from polarsclaw.types import Memory, Message


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


# ── Sessions ─────────────────────────────────────────────────────────────────


class SessionRepo:
    """CRUD operations on the ``sessions`` table."""

    def __init__(self, db: Database) -> None:
        self._db = db

    async def create(
        self,
        *,
        title: str | None = None,
        scope: str = "main",
        peer_id: str | None = None,
        channel_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        """Create a new session and return its id."""
        session_id = uuid.uuid4().hex
        now = _now()
        await self._db.execute_write(
            """
            INSERT INTO sessions (id, title, scope, peer_id, channel_id, metadata, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                session_id,
                title,
                scope,
                peer_id,
                channel_id,
                json.dumps(metadata or {}),
                now,
                now,
            ),
        )
        return session_id

    async def get(self, session_id: str) -> dict[str, Any]:
        """Return a single session dict or raise :class:`RecordNotFoundError`."""
        db = self._db.get_connection()
        async with db.execute(
            "SELECT * FROM sessions WHERE id = ?", (session_id,)
        ) as cursor:
            row = await cursor.fetchone()
        if row is None:
            raise RecordNotFoundError(f"Session {session_id!r} not found")
        return dict(row)

    async def list(
        self, *, scope: str | None = None, limit: int = 50, offset: int = 0
    ) -> list[dict[str, Any]]:
        """Return sessions ordered by most recent first."""
        if scope:
            sql = "SELECT * FROM sessions WHERE scope = ? ORDER BY updated_at DESC LIMIT ? OFFSET ?"
            params: Sequence[Any] = (scope, limit, offset)
        else:
            sql = "SELECT * FROM sessions ORDER BY updated_at DESC LIMIT ? OFFSET ?"
            params = (limit, offset)
        db = self._db.get_connection()
        async with db.execute(sql, params) as cursor:
            return [dict(r) for r in await cursor.fetchall()]

    async def delete(self, session_id: str) -> None:
        """Delete a session (cascades to messages)."""
        await self._db.execute_write(
            "DELETE FROM sessions WHERE id = ?", (session_id,)
        )

    async def update_title(self, session_id: str, title: str) -> None:
        """Update the title and bump ``updated_at``."""
        await self._db.execute_write(
            "UPDATE sessions SET title = ?, updated_at = ? WHERE id = ?",
            (title, _now(), session_id),
        )


# ── Messages (append-only within a session) ─────────────────────────────────


class MessageRepo:
    """Read/write chat messages."""

    def __init__(self, db: Database) -> None:
        self._db = db

    async def add(
        self,
        session_id: str,
        role: str,
        content: str,
        metadata: dict[str, Any] | None = None,
    ) -> int:
        """Append a message and return its ``id``."""
        cursor = await self._db.execute_write(
            """
            INSERT INTO messages (session_id, role, content, metadata, timestamp)
            VALUES (?, ?, ?, ?, ?)
            """,
            (session_id, role, content, json.dumps(metadata or {}), _now()),
        )
        # Bump session updated_at
        await self._db.execute_write(
            "UPDATE sessions SET updated_at = ? WHERE id = ?",
            (_now(), session_id),
        )
        return cursor.lastrowid  # type: ignore[return-value]

    async def list(
        self,
        session_id: str,
        *,
        limit: int = 100,
        before_id: int | None = None,
    ) -> list[Message]:
        """Return messages in chronological order."""
        db = self._db.get_connection()
        if before_id is not None:
            sql = (
                "SELECT * FROM messages WHERE session_id = ? AND id < ? "
                "ORDER BY id DESC LIMIT ?"
            )
            params: Sequence[Any] = (session_id, before_id, limit)
        else:
            sql = (
                "SELECT * FROM messages WHERE session_id = ? "
                "ORDER BY id DESC LIMIT ?"
            )
            params = (session_id, limit)
        async with db.execute(sql, params) as cursor:
            rows = await cursor.fetchall()
        # Return in chronological order.
        return [
            Message(
                id=r["id"],
                session_id=r["session_id"],
                role=r["role"],
                content=r["content"],
                timestamp=datetime.fromisoformat(r["timestamp"]),
            )
            for r in reversed(rows)
        ]


# ── Memories ─────────────────────────────────────────────────────────────────


class MemoryRepo:
    """Key-value memory store with FTS5 search."""

    def __init__(self, db: Database) -> None:
        self._db = db

    async def save(
        self,
        key: str,
        value: str,
        *,
        type: str = "general",
        session_id: str | None = None,
    ) -> int:
        """Upsert a memory (INSERT OR REPLACE on UNIQUE key)."""
        now = _now()
        cursor = await self._db.execute_write(
            """
            INSERT OR REPLACE INTO memories (key, value, type, session_id, created_at, updated_at)
            VALUES (
                ?,
                ?,
                ?,
                ?,
                COALESCE(
                    (SELECT created_at FROM memories WHERE key = ?),
                    ?
                ),
                ?
            )
            """,
            (key, value, type, session_id, key, now, now),
        )
        return cursor.lastrowid  # type: ignore[return-value]

    async def get(self, key: str) -> Memory:
        """Fetch a single memory by key."""
        db = self._db.get_connection()
        async with db.execute(
            "SELECT * FROM memories WHERE key = ?", (key,)
        ) as cursor:
            row = await cursor.fetchone()
        if row is None:
            raise RecordNotFoundError(f"Memory {key!r} not found")
        return self._row_to_memory(row)

    async def delete(self, key: str) -> None:
        """Delete a memory by key."""
        await self._db.execute_write("DELETE FROM memories WHERE key = ?", (key,))

    async def list(
        self,
        *,
        type: str | None = None,
        session_id: str | None = None,
        limit: int = 100,
    ) -> list[Memory]:
        """List memories with optional filters."""
        clauses: list[str] = []
        params: list[Any] = []
        if type is not None:
            clauses.append("type = ?")
            params.append(type)
        if session_id is not None:
            clauses.append("session_id = ?")
            params.append(session_id)
        where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
        sql = f"SELECT * FROM memories{where} ORDER BY updated_at DESC LIMIT ?"
        params.append(limit)

        db = self._db.get_connection()
        async with db.execute(sql, params) as cursor:
            return [self._row_to_memory(r) for r in await cursor.fetchall()]

    async def search(self, query: str, *, limit: int = 10) -> list[Memory]:
        """Full-text search using FTS5 MATCH with BM25 ranking.

        Returns memories ordered by relevance (best match first).
        """
        db = self._db.get_connection()
        sql = """
            SELECT m.*
            FROM memories_fts fts
            JOIN memories m ON m.id = fts.rowid
            WHERE memories_fts MATCH ?
            ORDER BY bm25(memories_fts) ASC
            LIMIT ?
        """
        async with db.execute(sql, (query, limit)) as cursor:
            return [self._row_to_memory(r) for r in await cursor.fetchall()]

    @staticmethod
    def _row_to_memory(row: aiosqlite.Row) -> Memory:
        return Memory(
            id=row["id"],
            key=row["key"],
            value=row["value"],
            type=row["type"],
            session_id=row["session_id"],
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
        )


# ── Cron ─────────────────────────────────────────────────────────────────────


class CronRepo:
    """CRUD for scheduled jobs and their execution results."""

    def __init__(self, db: Database) -> None:
        self._db = db

    async def create(
        self,
        name: str,
        schedule: str,
        *,
        type: str = "cron",
        payload: dict[str, Any] | None = None,
        enabled: bool = True,
    ) -> int:
        """Create a cron job and return its id."""
        now = _now()
        cursor = await self._db.execute_write(
            """
            INSERT INTO cron_jobs (name, schedule, type, payload, enabled, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (name, schedule, type, json.dumps(payload or {}), int(enabled), now, now),
        )
        return cursor.lastrowid  # type: ignore[return-value]

    async def get(self, job_id: int) -> dict[str, Any]:
        """Get a job by id."""
        db = self._db.get_connection()
        async with db.execute(
            "SELECT * FROM cron_jobs WHERE id = ?", (job_id,)
        ) as cursor:
            row = await cursor.fetchone()
        if row is None:
            raise RecordNotFoundError(f"Cron job {job_id} not found")
        return dict(row)

    async def get_by_name(self, name: str) -> dict[str, Any]:
        """Get a job by unique name."""
        db = self._db.get_connection()
        async with db.execute(
            "SELECT * FROM cron_jobs WHERE name = ?", (name,)
        ) as cursor:
            row = await cursor.fetchone()
        if row is None:
            raise RecordNotFoundError(f"Cron job {name!r} not found")
        return dict(row)

    async def list(self, *, enabled_only: bool = False) -> list[dict[str, Any]]:
        """List all cron jobs."""
        db = self._db.get_connection()
        if enabled_only:
            sql = "SELECT * FROM cron_jobs WHERE enabled = 1 ORDER BY name"
        else:
            sql = "SELECT * FROM cron_jobs ORDER BY name"
        async with db.execute(sql) as cursor:
            return [dict(r) for r in await cursor.fetchall()]

    async def update(
        self,
        job_id: int,
        *,
        schedule: str | None = None,
        payload: dict[str, Any] | None = None,
        enabled: bool | None = None,
    ) -> None:
        """Partial update of a cron job."""
        sets: list[str] = ["updated_at = ?"]
        params: list[Any] = [_now()]
        if schedule is not None:
            sets.append("schedule = ?")
            params.append(schedule)
        if payload is not None:
            sets.append("payload = ?")
            params.append(json.dumps(payload))
        if enabled is not None:
            sets.append("enabled = ?")
            params.append(int(enabled))
        params.append(job_id)
        await self._db.execute_write(
            f"UPDATE cron_jobs SET {', '.join(sets)} WHERE id = ?", params
        )

    async def delete(self, job_id: int) -> None:
        """Delete a job and its results (cascade)."""
        await self._db.execute_write("DELETE FROM cron_jobs WHERE id = ?", (job_id,))

    # ── results ──────────────────────────────────────────────────────────

    async def record_result(
        self,
        job_id: int,
        status: str,
        *,
        output: str | None = None,
        error: str | None = None,
        started_at: str | None = None,
        finished_at: str | None = None,
    ) -> int:
        """Record an execution result."""
        cursor = await self._db.execute_write(
            """
            INSERT INTO cron_results (job_id, status, output, error, started_at, finished_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                job_id,
                status,
                output,
                error,
                started_at or _now(),
                finished_at,
            ),
        )
        return cursor.lastrowid  # type: ignore[return-value]

    async def list_results(
        self, job_id: int, *, limit: int = 20
    ) -> list[dict[str, Any]]:
        """Return recent results for a job."""
        db = self._db.get_connection()
        async with db.execute(
            "SELECT * FROM cron_results WHERE job_id = ? ORDER BY started_at DESC LIMIT ?",
            (job_id, limit),
        ) as cursor:
            return [dict(r) for r in await cursor.fetchall()]
