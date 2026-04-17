"""Tool registry with groups, profiles, and allow/deny filtering."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from langchain_core.tools import BaseTool

from polarsclaw.tools.groups import get_builtin_groups
from polarsclaw.tools.profiles import get_profile_groups

if TYPE_CHECKING:
    from polarsclaw.config.settings import AgentConfig


class ToolRegistry:
    """Central registry for all tools available to agents."""

    def __init__(self) -> None:
        self._tools: dict[str, BaseTool] = {}
        self._tool_groups: dict[str, set[str]] = {}  # group_name -> set of tool names

        # Seed built-in groups
        for group_name, tool_names in get_builtin_groups().items():
            self._tool_groups[group_name] = set(tool_names)

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    def register(self, tool: BaseTool, groups: list[str] | None = None) -> None:
        """Register a tool, optionally assigning it to groups."""
        self._tools[tool.name] = tool
        for group in groups or []:
            self._tool_groups.setdefault(group, set()).add(tool.name)

    def unregister(self, tool_name: str) -> None:
        """Remove a tool from the registry and all groups."""
        self._tools.pop(tool_name, None)
        for members in self._tool_groups.values():
            members.discard(tool_name)

    # ------------------------------------------------------------------
    # Querying
    # ------------------------------------------------------------------

    def get_tools(self, agent_config: AgentConfig) -> list[BaseTool]:
        """Get tools filtered by agent config (profile, allow/deny lists).

        Resolution order:
        1. Start with profile tools (based on ``agent_config.tool_profile``).
        2. If ``agent_config.tools`` is non-empty, treat it as an *allow list*
           and intersect with the profile set.
        3. Remove any tools matching the deny list (``agent_config.deny_tools``
           if the attribute exists).

        Both allow and deny lists support ``"group:xxx"`` entries which expand
        to all tool names registered under that group.
        """
        # 1. Profile base set
        profile_names = self._resolve_profile(agent_config.tool_profile)

        # 2. Allow list
        allow_list: list[str] = getattr(agent_config, "tools", []) or []
        if allow_list:
            allowed = self._expand_names(allow_list)
            profile_names = profile_names & allowed

        # 3. Deny list
        deny_list: list[str] = getattr(agent_config, "deny_tools", []) or []
        if deny_list:
            denied = self._expand_names(deny_list)
            profile_names -= denied

        return [self._tools[n] for n in profile_names if n in self._tools]

    def get_group(self, group_name: str) -> list[BaseTool]:
        """Get all registered tools in a group."""
        names = self._tool_groups.get(group_name, set())
        return [self._tools[n] for n in names if n in self._tools]

    def get_profile(self, profile_name: str) -> list[BaseTool]:
        """Get tools for a profile (full, coding, minimal)."""
        names = self._resolve_profile(profile_name)
        return [self._tools[n] for n in names if n in self._tools]

    def list_all(self) -> list[BaseTool]:
        """List all registered tools."""
        return list(self._tools.values())

    def get(self, name: str) -> BaseTool | None:
        """Get a specific tool by name."""
        return self._tools.get(name)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _resolve_profile(self, profile_name: str) -> set[str]:
        """Return the set of tool names for a given profile."""
        group_names = get_profile_groups(profile_name)
        result: set[str] = set()
        for g in group_names:
            result |= self._tool_groups.get(g, set())
        return result

    def _expand_names(self, names: list[str]) -> set[str]:
        """Expand a mixed list of tool names and ``group:xxx`` refs."""
        result: set[str] = set()
        for name in names:
            if name.startswith("group:"):
                result |= self._tool_groups.get(name, set())
            else:
                result.add(name)
        return result
