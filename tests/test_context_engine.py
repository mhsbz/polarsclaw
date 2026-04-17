"""Tests for polarsclaw.context."""

from __future__ import annotations

import pytest

from polarsclaw.context.engine import ContextEngine, DefaultContextEngine
from polarsclaw.context.registry import ContextEngineRegistry


class TestDefaultContextEngine:
    def test_owns_compaction_false(self) -> None:
        engine = DefaultContextEngine()
        assert engine.owns_compaction is False

    async def test_ingest_noop(self) -> None:
        engine = DefaultContextEngine()
        await engine.ingest("content", {})  # should not raise

    async def test_assemble_empty(self) -> None:
        engine = DefaultContextEngine()
        assert await engine.assemble("s1") == ""

    async def test_compact_none(self) -> None:
        engine = DefaultContextEngine()
        assert await engine.compact("s1") is None

    def test_satisfies_protocol(self) -> None:
        assert isinstance(DefaultContextEngine(), ContextEngine)


class TestContextEngineRegistry:
    def test_default_exists(self) -> None:
        reg = ContextEngineRegistry()
        d = reg.default()
        assert isinstance(d, DefaultContextEngine)

    def test_register_and_get(self) -> None:
        reg = ContextEngineRegistry()
        engine = DefaultContextEngine()
        reg.register("custom", engine)
        assert reg.get("custom") is engine

    def test_get_missing(self) -> None:
        reg = ContextEngineRegistry()
        assert reg.get("nonexistent") is None

    def test_list(self) -> None:
        reg = ContextEngineRegistry()
        reg.register("extra", DefaultContextEngine())
        engines = reg.list()
        assert "default" in engines
        assert "extra" in engines
        assert len(engines) == 2

    def test_custom_engine_registration(self) -> None:
        class MyEngine:
            @property
            def owns_compaction(self) -> bool:
                return True
            async def ingest(self, content: str, metadata: dict) -> None:
                pass
            async def assemble(self, session_id: str) -> str:
                return "custom"
            async def compact(self, session_id: str) -> str | None:
                return "compacted"

        reg = ContextEngineRegistry()
        reg.register("mine", MyEngine())  # type: ignore[arg-type]
        assert reg.get("mine") is not None
