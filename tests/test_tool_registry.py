"""Tests for polarsclaw.tools.registry."""

from __future__ import annotations

from unittest.mock import MagicMock

from langchain_core.tools import BaseTool

from polarsclaw.config.settings import AgentConfig
from polarsclaw.tools.registry import ToolRegistry


def _make_tool(name: str) -> BaseTool:
    tool = MagicMock(spec=BaseTool)
    tool.name = name
    return tool


class TestToolRegistry:
    def test_register_and_get(self) -> None:
        reg = ToolRegistry()
        t = _make_tool("my_tool")
        reg.register(t)
        assert reg.get("my_tool") is t

    def test_register_with_group(self) -> None:
        reg = ToolRegistry()
        t = _make_tool("my_tool")
        reg.register(t, groups=["group:custom"])
        group_tools = reg.get_group("group:custom")
        assert len(group_tools) == 1
        assert group_tools[0].name == "my_tool"

    def test_get_profile_full(self) -> None:
        reg = ToolRegistry()
        t = _make_tool("save_memory")
        reg.register(t)
        profile_tools = reg.get_profile("full")
        assert any(tool.name == "save_memory" for tool in profile_tools)

    def test_get_profile_minimal(self) -> None:
        reg = ToolRegistry()
        reg.register(_make_tool("save_memory"))
        reg.register(_make_tool("create_cron"))
        minimal = reg.get_profile("minimal")
        names = {t.name for t in minimal}
        assert "save_memory" in names
        assert "create_cron" not in names

    def test_unregister(self) -> None:
        reg = ToolRegistry()
        t = _make_tool("temp")
        reg.register(t, groups=["group:custom"])
        reg.unregister("temp")
        assert reg.get("temp") is None
        assert reg.get_group("group:custom") == []

    def test_list_all(self) -> None:
        reg = ToolRegistry()
        reg.register(_make_tool("a"))
        reg.register(_make_tool("b"))
        assert len(reg.list_all()) == 2

    def test_allow_deny_filtering(self) -> None:
        reg = ToolRegistry()
        reg.register(_make_tool("save_memory"))
        reg.register(_make_tool("recall_memory"))
        reg.register(_make_tool("list_memories"))

        # Allow only specific tools
        cfg = AgentConfig(tools=["save_memory", "recall_memory"])
        tools = reg.get_tools(cfg)
        names = {t.name for t in tools}
        assert "save_memory" in names
        assert "recall_memory" in names
        assert "list_memories" not in names

    def test_group_expansion_in_allow(self) -> None:
        reg = ToolRegistry()
        reg.register(_make_tool("save_memory"))
        reg.register(_make_tool("recall_memory"))
        reg.register(_make_tool("list_memories"))
        cfg = AgentConfig(tools=["group:memory"])
        tools = reg.get_tools(cfg)
        names = {t.name for t in tools}
        assert "save_memory" in names
