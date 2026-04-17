"""Execute a skill as a sub-agent."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from langchain_core.messages import HumanMessage

if TYPE_CHECKING:
    from langgraph.checkpoint.base import BaseCheckpointSaver

    from polarsclaw.config.settings import AgentConfig
    from polarsclaw.skills.parser import SkillEntry

logger = logging.getLogger(__name__)


async def execute_skill(
    skill: "SkillEntry",
    message: str,
    agent_config: "AgentConfig",
    checkpointer: "BaseCheckpointSaver",
) -> str:
    """Run *skill* as a sub-agent and return the response string.

    Strategy:
    1. Try ``deep_agents.create_deep_agent`` with the skill markdown as
       the system prompt.
    2. Fall back to ``langgraph.prebuilt.create_react_agent`` if
       DeepAgents is unavailable.
    """
    system_prompt = skill.content or skill.description

    # ── Attempt 1: DeepAgents ──────────────────────────────────────────
    try:
        from deep_agents import create_deep_agent  # type: ignore[import-untyped]

        agent = create_deep_agent(
            model=agent_config.model,
            system_prompt=system_prompt,
            checkpointer=checkpointer,
        )
        result = await agent.ainvoke(
            {"messages": [HumanMessage(content=message)]},
        )
        response = result["messages"][-1].content
        logger.info("Skill '%s' executed via DeepAgents", skill.name)
        return str(response)

    except (ImportError, Exception) as exc:
        logger.debug(
            "DeepAgents unavailable for skill '%s', falling back: %s",
            skill.name,
            exc,
        )

    # ── Attempt 2: LangGraph create_react_agent ────────────────────────
    from langchain_core.messages import SystemMessage
    from langgraph.prebuilt import create_react_agent

    agent = create_react_agent(
        model=agent_config.model,
        tools=[],
        checkpointer=checkpointer,
        prompt=SystemMessage(content=system_prompt),
    )
    result = await agent.ainvoke(
        {"messages": [HumanMessage(content=message)]},
    )
    response = result["messages"][-1].content
    logger.info("Skill '%s' executed via LangGraph react agent", skill.name)
    return str(response)
