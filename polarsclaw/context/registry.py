"""ContextEngineRegistry — named registry for context engines."""

from __future__ import annotations

import logging

from polarsclaw.context.engine import ContextEngine, DefaultContextEngine

logger = logging.getLogger(__name__)


class ContextEngineRegistry:
    """Named registry for :class:`ContextEngine` instances.

    Always contains a ``"default"`` engine (unless explicitly removed).
    """

    def __init__(self) -> None:
        self._engines: dict[str, ContextEngine] = {}
        # Seed with the default engine
        self._engines["default"] = DefaultContextEngine()

    def register(self, name: str, engine: ContextEngine) -> None:
        """Register a context engine under *name*."""
        self._engines[name] = engine
        logger.info("Registered context engine '%s'", name)

    def get(self, name: str) -> ContextEngine | None:
        """Retrieve a context engine by *name*, or ``None``."""
        return self._engines.get(name)

    def default(self) -> ContextEngine:
        """Return the default context engine."""
        engine = self._engines.get("default")
        if engine is None:
            # Fallback: create one on the fly
            engine = DefaultContextEngine()
            self._engines["default"] = engine
        return engine

    def list(self) -> dict[str, ContextEngine]:
        """Return a copy of all registered engines."""
        return dict(self._engines)
