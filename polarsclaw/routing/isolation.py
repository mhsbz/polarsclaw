"""Per-agent tool and skill isolation."""

from __future__ import annotations

from typing import TYPE_CHECKING

from langchain_core.tools import BaseTool

if TYPE_CHECKING:
    from polarsclaw.config.settings import AgentConfig
    from polarsclaw.skills.parser import SkillEntry
    from polarsclaw.skills.registry import SkillRegistry
    from polarsclaw.tools.registry import ToolRegistry


def apply_isolation(
    agent_config: AgentConfig,
    tool_registry: ToolRegistry,
    skill_registry: SkillRegistry,
) -> tuple[list[BaseTool], list[SkillEntry]]:
    """Return the filtered tools and skills an agent is allowed to use.

    Tool filtering is delegated to :pymethod:`ToolRegistry.get_tools` which
    already honours the agent's ``tool_profile``, allow-list (``tools``), and
    deny-list (``deny_tools``).

    Skill filtering uses the agent config's ``skills`` allow-list:
    - If the list is empty / missing, **all** discovered skills are permitted.
    - Otherwise only skills whose ``name`` appears in the list are kept.

    Parameters
    ----------
    agent_config:
        The agent's configuration block.
    tool_registry:
        Global tool registry.
    skill_registry:
        Global skill registry (already discovered).

    Returns
    -------
    tuple[list[BaseTool], list[SkillEntry]]
        ``(filtered_tools, filtered_skills)``
    """
    # ── Tools ──────────────────────────────────────────────────────────
    tools = tool_registry.get_tools(agent_config)

    # ── Skills ─────────────────────────────────────────────────────────
    all_skills = skill_registry.list()
    skill_allowlist: list[str] = getattr(agent_config, "skills", []) or []

    if skill_allowlist:
        allowed_set = set(skill_allowlist)
        skills = [s for s in all_skills if s.name in allowed_set]
    else:
        skills = all_skills

    return tools, skills
