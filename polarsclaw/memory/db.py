"""Memory database access layer built on top of the shared Database wrapper."""

from __future__ import annotations

import logging
from typing import Any

from polarsclaw.storage.database import Database

logger = logging.getLogger(__name__)


class MemoryDB:
    """High-level async helpers for the memory tables.

    Wraps a :class:`Database` instance that has already been initialised with
    the memory migration applied.
    """

    def __init__(self, db: Database) -> None:
        self._db = db

    # ── mem_files ────────────────────────────────────────────────────────

    async def upsert_file(
        self,
        path: str,
        file_type: str,
        file_hash: str,
        size: int,
    ) -> int:
        """Insert or update a tracked file. Returns the file row id."""
        cursor = await self._db.execute_write(
            """
            INSERT INTO mem_files (path, type, hash, size)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(path) DO UPDATE SET
                type=excluded.type,
                hash=excluded.hash,
                size=excluded.size,
                updated_at=strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
            """,
            (path, file_type, file_hash, size),
        )
        return cursor.lastrowid  # type: ignore[return-value]

    async def get_file(self, path: str) -> dict[str, Any] | None:
        conn = self._db.get_connection()
        async with conn.execute(
            "SELECT * FROM mem_files WHERE path = ?", (path,)
        ) as cur:
            row = await cur.fetchone()
            return dict(row) if row else None

    async def delete_file(self, file_id: int) -> None:
        await self._db.execute_write("DELETE FROM mem_files WHERE id = ?", (file_id,))

    async def list_files(self) -> list[dict[str, Any]]:
        conn = self._db.get_connection()
        async with conn.execute("SELECT * FROM mem_files ORDER BY path") as cur:
            return [dict(r) for r in await cur.fetchall()]

    async def get_file_by_id(self, file_id: int) -> dict[str, Any] | None:
        """Look up a mem_files row by its primary key."""
        conn = self._db.get_connection()
        async with conn.execute(
            "SELECT * FROM mem_files WHERE id = ?", (file_id,)
        ) as cur:
            row = await cur.fetchone()
            return dict(row) if row else None

    # ── mem_chunks ───────────────────────────────────────────────────────

    async def insert_chunks(
        self,
        file_id: int,
        chunks: list[dict[str, Any]],
    ) -> list[int]:
        """Insert multiple chunks and return their row ids."""
        ids: list[int] = []
        for ch in chunks:
            cursor = await self._db.execute_write(
                """
                INSERT INTO mem_chunks (file_id, chunk_index, content, heading, token_count)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    file_id,
                    ch["chunk_index"],
                    ch["content"],
                    ch.get("heading", ""),
                    ch.get("token_count", 0),
                ),
            )
            ids.append(cursor.lastrowid)  # type: ignore[arg-type]
        return ids

    async def delete_chunks_by_file(self, file_id: int) -> None:
        await self._db.execute_write(
            "DELETE FROM mem_chunks WHERE file_id = ?", (file_id,)
        )

    async def get_chunk(self, chunk_id: int) -> dict[str, Any] | None:
        conn = self._db.get_connection()
        async with conn.execute(
            "SELECT * FROM mem_chunks WHERE id = ?", (chunk_id,)
        ) as cur:
            row = await cur.fetchone()
            return dict(row) if row else None

    async def get_chunks_by_file(self, file_id: int) -> list[dict[str, Any]]:
        conn = self._db.get_connection()
        async with conn.execute(
            "SELECT * FROM mem_chunks WHERE file_id = ? ORDER BY chunk_index",
            (file_id,),
        ) as cur:
            return [dict(r) for r in await cur.fetchall()]

    # ── mem_chunks_vec ───────────────────────────────────────────────────

    async def upsert_vectors(
        self, vectors: list[tuple[int, bytes]]
    ) -> None:
        """Insert or replace embedding blobs. *vectors* is a list of (chunk_id, blob)."""
        for chunk_id, blob in vectors:
            await self._db.execute_write(
                """
                INSERT INTO mem_chunks_vec (chunk_id, embedding)
                VALUES (?, ?)
                ON CONFLICT(chunk_id) DO UPDATE SET embedding=excluded.embedding
                """,
                (chunk_id, blob),
            )

    async def get_all_vectors(self) -> list[tuple[int, bytes]]:
        conn = self._db.get_connection()
        async with conn.execute(
            "SELECT chunk_id, embedding FROM mem_chunks_vec"
        ) as cur:
            return [(row[0], row[1]) for row in await cur.fetchall()]

    # ── FTS search ───────────────────────────────────────────────────────

    async def fts_search(
        self, query: str, *, limit: int = 20
    ) -> list[dict[str, Any]]:
        """Full-text search via FTS5 MATCH. Returns results with BM25 scores normalised to 0-1."""
        conn = self._db.get_connection()
        # bm25() returns negative values where more-negative = better match.
        async with conn.execute(
            """
            SELECT
                mc.id          AS chunk_id,
                mc.file_id,
                mc.content,
                mc.heading,
                mc.token_count,
                bm25(mem_chunks_fts) AS raw_score
            FROM mem_chunks_fts
            JOIN mem_chunks mc ON mc.id = mem_chunks_fts.rowid
            WHERE mem_chunks_fts MATCH ?
            ORDER BY raw_score
            LIMIT ?
            """,
            (query, limit),
        ) as cur:
            rows = [dict(r) for r in await cur.fetchall()]

        if not rows:
            return []

        # Normalise: raw BM25 scores are negative; convert to 0-1 range.
        raw_scores = [r["raw_score"] for r in rows]
        best = min(raw_scores)  # most negative = best
        worst = max(raw_scores)
        span = worst - best if worst != best else 1.0

        for r in rows:
            r["score"] = (worst - r["raw_score"]) / span
            del r["raw_score"]

        return rows

    # ── mem_embedding_cache ──────────────────────────────────────────────

    async def get_cached_embedding(self, content_hash: str) -> bytes | None:
        conn = self._db.get_connection()
        async with conn.execute(
            "SELECT embedding FROM mem_embedding_cache WHERE hash = ?",
            (content_hash,),
        ) as cur:
            row = await cur.fetchone()
            return row[0] if row else None  # type: ignore[index]

    async def cache_embedding(
        self, content_hash: str, model: str, embedding: bytes
    ) -> None:
        await self._db.execute_write(
            """
            INSERT INTO mem_embedding_cache (hash, model, embedding)
            VALUES (?, ?, ?)
            ON CONFLICT(hash) DO UPDATE SET
                model=excluded.model,
                embedding=excluded.embedding,
                created_at=strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
            """,
            (content_hash, model, embedding),
        )

    # ── mem_recalls ──────────────────────────────────────────────────────

    async def record_recall(
        self,
        chunk_id: int,
        query: str,
        score: float,
        session_id: str = "",
    ) -> None:
        await self._db.execute_write(
            """
            INSERT INTO mem_recalls (chunk_id, query, score, session_id)
            VALUES (?, ?, ?, ?)
            """,
            (chunk_id, query, score, session_id),
        )

    async def get_recall_stats(
        self, chunk_id: int
    ) -> dict[str, Any]:
        """Return recall count and average score for a chunk."""
        conn = self._db.get_connection()
        async with conn.execute(
            """
            SELECT COUNT(*) AS cnt, COALESCE(AVG(score), 0.0) AS avg_score
            FROM mem_recalls WHERE chunk_id = ?
            """,
            (chunk_id,),
        ) as cur:
            row = await cur.fetchone()
            return {"count": row[0], "avg_score": row[1]}  # type: ignore[index]

    async def get_recent_recalls(
        self, *, limit: int = 50
    ) -> list[dict[str, Any]]:
        conn = self._db.get_connection()
        async with conn.execute(
            "SELECT * FROM mem_recalls ORDER BY recalled_at DESC LIMIT ?",
            (limit,),
        ) as cur:
            return [dict(r) for r in await cur.fetchall()]

    # ── mem_meta ─────────────────────────────────────────────────────────

    async def get_meta(self, key: str) -> str | None:
        conn = self._db.get_connection()
        async with conn.execute(
            "SELECT value FROM mem_meta WHERE key = ?", (key,)
        ) as cur:
            row = await cur.fetchone()
            return row[0] if row else None  # type: ignore[index]

    async def set_meta(self, key: str, value: str) -> None:
        await self._db.execute_write(
            """
            INSERT INTO mem_meta (key, value)
            VALUES (?, ?)
            ON CONFLICT(key) DO UPDATE SET
                value=excluded.value,
                updated_at=strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
            """,
            (key, value),
        )
