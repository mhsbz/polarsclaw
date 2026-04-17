"""Built-in tool makers for PolarsClaw."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from polarsclaw.cron.scheduler import CronScheduler
    from polarsclaw.sessions.manager import SessionManager
    from polarsclaw.storage.database import Database
    from polarsclaw.tools.registry import ToolRegistry

logger = logging.getLogger(__name__)

__all__ = ["register_all_builtin_tools"]


def register_all_builtin_tools(
    registry: "ToolRegistry",
    db: "Database",
    scheduler: "CronScheduler",
    session_mgr: "SessionManager",
) -> None:
    """Register all built-in tools into *registry* with proper groups.

    This wires the closure-based tool factories (memory, cron, session)
    to their respective dependencies and registers each tool under the
    matching ``group:*`` group.
    """
    from polarsclaw.tools.builtin.cron_tools import make_cron_tools
    from polarsclaw.tools.builtin.session_tools import make_session_tools

    # ── Cron tools ─────────────────────────────────────────────────────
    cron_tools = make_cron_tools(scheduler)
    for tool in cron_tools:
        registry.register(tool, groups=["group:cron"])
    logger.info("Registered %d cron tools", len(cron_tools))

    # ── Session tools ──────────────────────────────────────────────────
    session_tools = make_session_tools(db)
    for tool in session_tools:
        registry.register(tool, groups=["group:session"])
    logger.info("Registered %d session tools", len(session_tools))

    # NOTE: Memory tools (save_memory, recall_memory, list_memories) removed.
    # Replaced by MemoryCore (memory_search, memory_get) + DeepAgents write_file.
