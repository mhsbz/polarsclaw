"""Async SQLite database wrapper with WAL mode and write locking."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any, Sequence

import aiosqlite

from polarsclaw.errors import MigrationError, StorageError
from polarsclaw.storage.migrations import CURRENT_VERSION, MIGRATIONS

logger = logging.getLogger(__name__)


class Database:
    """Thin async wrapper around an SQLite database.

    Features:
    - WAL journal mode for concurrent reads.
    - An :class:`asyncio.Lock` serialising all write operations.
    - Automatic schema migration on :meth:`initialize`.
    """

    def __init__(self, db_path: Path | str) -> None:
        self._path = Path(db_path)
        self._write_lock = asyncio.Lock()
        self._db: aiosqlite.Connection | None = None

    # ── lifecycle ────────────────────────────────────────────────────────

    async def initialize(self) -> None:
        """Open the database, enable WAL, and run pending migrations."""
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._db = await aiosqlite.connect(str(self._path))
        self._db.row_factory = aiosqlite.Row

        await self._db.execute("PRAGMA journal_mode=WAL;")
        await self._db.execute("PRAGMA foreign_keys=ON;")
        await self._db.commit()

        await self._run_migrations()
        logger.info("Database initialised at %s", self._path)

    async def close(self) -> None:
        """Close the underlying connection."""
        if self._db is not None:
            await self._db.close()
            self._db = None
            logger.debug("Database connection closed.")

    # ── public helpers ───────────────────────────────────────────────────

    def get_connection(self) -> aiosqlite.Connection:
        """Return the raw ``aiosqlite`` connection (must be initialised)."""
        if self._db is None:
            raise StorageError("Database not initialised — call initialize() first.")
        return self._db

    async def execute_write(
        self,
        sql: str,
        params: Sequence[Any] = (),
    ) -> aiosqlite.Cursor:
        """Execute a single write statement under the write lock.

        Returns the cursor so callers can inspect ``lastrowid``, etc.
        """
        db = self.get_connection()
        async with self._write_lock:
            cursor = await db.execute(sql, params)
            await db.commit()
            return cursor

    async def execute_many(
        self,
        sql: str,
        params_seq: Sequence[Sequence[Any]],
    ) -> None:
        """Execute *sql* for every parameter set in *params_seq*."""
        db = self.get_connection()
        async with self._write_lock:
            await db.executemany(sql, params_seq)
            await db.commit()

    # ── migrations ───────────────────────────────────────────────────────

    async def _current_version(self) -> int:
        """Return the applied schema version (0 if fresh DB)."""
        db = self.get_connection()
        try:
            async with db.execute(
                "SELECT MAX(version) FROM schema_version"
            ) as cursor:
                row = await cursor.fetchone()
                return row[0] if row and row[0] is not None else 0
        except aiosqlite.OperationalError:
            # Table doesn't exist yet.
            return 0

    async def _run_migrations(self) -> None:
        """Apply all outstanding migration steps."""
        current = await self._current_version()
        if current >= CURRENT_VERSION:
            return

        db = self.get_connection()
        for version in range(current + 1, CURRENT_VERSION + 1):
            statements = MIGRATIONS.get(version)
            if statements is None:
                raise MigrationError(f"Missing migration for version {version}")

            logger.info("Applying migration v%d …", version)
            try:
                async with self._write_lock:
                    for stmt in statements:
                        await db.execute(stmt)
                    await db.execute(
                        "INSERT INTO schema_version (version) VALUES (?)",
                        (version,),
                    )
                    await db.commit()
            except Exception as exc:
                raise MigrationError(
                    f"Migration v{version} failed: {exc}"
                ) from exc

        logger.info("Database schema at v%d.", CURRENT_VERSION)
