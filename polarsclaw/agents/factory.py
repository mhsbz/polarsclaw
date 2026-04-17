"""Factory function for creating configured AgentLoop instances."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from langgraph.checkpoint.base import BaseCheckpointSaver

    from polarsclaw.config.settings import AgentConfig, Settings
    from polarsclaw.context.engine import ContextEngine
    from polarsclaw.skills.registry import SkillRegistry
    from polarsclaw.tools.registry import ToolRegistry

from polarsclaw.agents.loop import AgentLoop

logger = logging.getLogger(__name__)


async def create_agent(
    agent_config: "AgentConfig",
    tool_registry: "ToolRegistry",
    skill_registry: "SkillRegistry | None",
    checkpointer: "BaseCheckpointSaver",
    settings: "Settings",
    context_engine: "ContextEngine | None" = None,
) -> AgentLoop:
    """Create a fully configured and built :class:`AgentLoop`.

    Steps:
    1. Resolve the tool set from *tool_registry* using the scopes / tool names
       declared in *agent_config*.
    2. If a *skill_registry* is provided, convert matching skills into
       LangChain-compatible tools and merge them in.
    3. Construct the :class:`AgentLoop`, call :meth:`~AgentLoop.build`, and
       return the ready-to-use instance.

    Parameters
    ----------
    agent_config:
        Declarative agent configuration (model, tools, system prompt, etc.).
    tool_registry:
        Central registry of available LangChain ``BaseTool`` instances.
    skill_registry:
        Optional skill registry whose entries can be exposed as tools.
    checkpointer:
        LangGraph checkpoint saver for conversation persistence.
    settings:
        Application-wide settings.
    context_engine:
        Optional context engine for compaction / retrieval-augmented generation.

    Returns
    -------
    AgentLoop
        A built agent loop ready to accept :meth:`~AgentLoop.run` or
        :meth:`~AgentLoop.stream` calls.
    """

    # ---- 1. Resolve tools from registry --------------------------------
    tools = tool_registry.get_tools(agent_config)

    # ---- 2. Merge skill-based tools ------------------------------------
    # (skill tools are a future extension — for now skills run as sub-agents)

    # ---- 3. Build the loop ---------------------------------------------
    loop = AgentLoop(
        agent_config=agent_config,
        tools=list(tools),
        checkpointer=checkpointer,
        settings=settings,
        context_engine=context_engine,
    )
    await loop.build()

    logger.info(
        "Agent created (model=%s, tools=%d)",
        agent_config.model,
        len(tools),
    )
    return loop
