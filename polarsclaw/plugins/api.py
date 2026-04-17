"""PluginAPI — the object handed to each plugin's ``register()`` function."""

from __future__ import annotations

import logging
from typing import Any

from langchain_core.tools import BaseTool

from polarsclaw.context.engine import ContextEngine
from polarsclaw.context.registry import ContextEngineRegistry
from polarsclaw.tools.registry import ToolRegistry

logger = logging.getLogger(__name__)


class PluginAPI:
    """Facade exposed to plugins during their ``register(api)`` call.

    Provides controlled access to the tool and context-engine registries
    without leaking the full application internals.
    """

    def __init__(
        self,
        tool_registry: ToolRegistry,
        context_registry: ContextEngineRegistry,
    ) -> None:
        self._tool_registry = tool_registry
        self._context_registry = context_registry

    def register_tool(self, tool: BaseTool, groups: list[str] | None = None) -> None:
        """Register a tool (optionally into groups) so agents can use it."""
        self._tool_registry.register(tool, groups=groups)
        logger.info("Plugin registered tool '%s'", tool.name)

    def register_context_engine(self, name: str, engine: ContextEngine) -> None:
        """Register a context engine by *name*."""
        self._context_registry.register(name, engine)
        logger.info("Plugin registered context engine '%s'", name)
