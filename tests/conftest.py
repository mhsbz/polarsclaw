"""Shared fixtures for PolarsClaw tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from polarsclaw.config.settings import Settings
from polarsclaw.storage.database import Database
from polarsclaw.storage.repositories import CronRepo, MemoryRepo, MessageRepo, SessionRepo


@pytest.fixture
def tmp_settings(tmp_path: Path) -> Settings:
    """Settings wired to temp directories."""
    return Settings(
        config_dir=tmp_path / "config",
        db_path=tmp_path / "test.db",
    )


@pytest.fixture
async def tmp_db(tmp_path: Path) -> Database:
    """Initialized Database in a temp directory."""
    db = Database(tmp_path / "test.db")
    await db.initialize()
    yield db  # type: ignore[misc]
    await db.close()


@pytest.fixture
def memory_repo(tmp_db: Database) -> MemoryRepo:
    return MemoryRepo(tmp_db)


@pytest.fixture
def message_repo(tmp_db: Database) -> MessageRepo:
    return MessageRepo(tmp_db)


@pytest.fixture
def session_repo(tmp_db: Database) -> SessionRepo:
    return SessionRepo(tmp_db)


@pytest.fixture
def cron_repo(tmp_db: Database) -> CronRepo:
    return CronRepo(tmp_db)
