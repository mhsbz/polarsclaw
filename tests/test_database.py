"""Tests for polarsclaw.storage.database."""

from __future__ import annotations

from pathlib import Path

import pytest

from polarsclaw.storage.database import Database
from polarsclaw.storage.migrations import CURRENT_VERSION


class TestDatabase:
    async def test_initialize_creates_tables(self, tmp_db: Database) -> None:
        db = tmp_db.get_connection()
        async with db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        ) as cur:
            tables = {row[0] for row in await cur.fetchall()}
        for expected in ("sessions", "messages", "memories", "cron_jobs", "cron_results", "schema_version", "plugin_state"):
            assert expected in tables, f"Missing table: {expected}"

    async def test_fts5_table_exists(self, tmp_db: Database) -> None:
        db = tmp_db.get_connection()
        async with db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='memories_fts'"
        ) as cur:
            row = await cur.fetchone()
        assert row is not None

    async def test_wal_mode_enabled(self, tmp_db: Database) -> None:
        db = tmp_db.get_connection()
        async with db.execute("PRAGMA journal_mode") as cur:
            row = await cur.fetchone()
        assert row[0] == "wal"

    async def test_migrations_idempotent(self, tmp_path: Path) -> None:
        db = Database(tmp_path / "test.db")
        await db.initialize()
        # Run again — should not raise
        await db._run_migrations()
        conn = db.get_connection()
        async with conn.execute("SELECT MAX(version) FROM schema_version") as cur:
            row = await cur.fetchone()
        assert row[0] == CURRENT_VERSION
        await db.close()

    async def test_execute_write(self, tmp_db: Database) -> None:
        await tmp_db.execute_write(
            "INSERT INTO sessions (id, title, scope, metadata, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
            ("test-id", "Test", "main", "{}", "2024-01-01", "2024-01-01"),
        )
        conn = tmp_db.get_connection()
        async with conn.execute("SELECT id FROM sessions WHERE id='test-id'") as cur:
            row = await cur.fetchone()
        assert row is not None
