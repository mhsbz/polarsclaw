"""End-to-end integration tests for PolarsClaw."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from polarsclaw.config.settings import Settings
from polarsclaw.skills.registry import SkillRegistry
from polarsclaw.storage.database import Database
from polarsclaw.storage.repositories import MemoryRepo


class TestMemoryE2E:
    """Save memory in one 'session', recall in another."""

    async def test_memory_persists_across_repos(self, tmp_path: Path) -> None:
        db = Database(tmp_path / "e2e.db")
        await db.initialize()

        repo1 = MemoryRepo(db)
        await repo1.save("user_name", "Alice", type="profile")

        repo2 = MemoryRepo(db)
        mem = await repo2.get("user_name")
        assert mem.value == "Alice"
        assert mem.type == "profile"

        results = await repo2.search("Alice")
        assert len(results) >= 1
        assert results[0].key == "user_name"

        await db.close()


class TestSkillDiscoveryE2E:
    """Create skill files on disk, discover, and match."""

    def _write_skill(self, d: Path, name: str, triggers: list[str]) -> None:
        triggers_yaml = "\n".join(f"  - {t}" for t in triggers)
        (d / f"{name}.md").write_text(
            f"---\nname: {name}\ndescription: {name} skill\ntriggers:\n{triggers_yaml}\n---\nBody\n"
        )

    async def test_discover_and_match(self, tmp_path: Path) -> None:
        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()
        self._write_skill(skills_dir, "weather", ["weather", "forecast"])
        self._write_skill(skills_dir, "reminder", ["remind me", "set reminder"])

        settings = Settings(config_dir=tmp_path, skill_match_threshold=0.7)
        reg = SkillRegistry(skills_dir, settings)
        reg.discover()

        assert len(reg.list()) == 2

        match = reg.match("weather")
        assert match is not None
        assert match.name == "weather"

        match2 = reg.match("remind me to buy milk")
        assert match2 is not None
        assert match2.name == "reminder"

        assert reg.match("completely unrelated query xyz") is None


class TestBuildApp:
    """Test that build_app wires subsystems correctly."""

    async def test_build_app_creates_context(self, tmp_path: Path) -> None:
        settings = Settings(
            config_dir=tmp_path / "config",
            db_path=tmp_path / "app.db",
        )
        (tmp_path / "config" / "skills").mkdir(parents=True, exist_ok=True)

        # Mock create_agent to avoid LLM dependency
        mock_agent = MagicMock()

        with patch(
            "polarsclaw.agents.factory.create_agent",
            new=AsyncMock(return_value=mock_agent),
        ):
            from polarsclaw.app import build_app, cleanup_app

            ctx = await build_app(settings)

            assert ctx.settings is settings
            assert ctx.db is not None
            assert ctx.tool_registry is not None
            assert ctx.skill_registry is not None
            assert ctx.session_manager is not None
            assert ctx.cron_scheduler is not None
            assert ctx.command_queue is not None
            assert ctx.router is not None
            assert len(ctx.agents) >= 1

            await cleanup_app(ctx)
