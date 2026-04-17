"""Tests for polarsclaw.plugins."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest
from langchain_core.tools import BaseTool

from polarsclaw.config.settings import Settings
from polarsclaw.context.registry import ContextEngineRegistry
from polarsclaw.plugins.api import PluginAPI
from polarsclaw.plugins.loader import PluginLoader
from polarsclaw.plugins.models import PluginManifest, PluginState
from polarsclaw.tools.registry import ToolRegistry


class TestPluginModels:
    def test_manifest(self) -> None:
        m = PluginManifest(name="test", version="1.0.0", entry_point="test.main")
        assert m.name == "test"
        assert m.version == "1.0.0"

    def test_state_defaults(self) -> None:
        s = PluginState(name="test")
        assert s.enabled is True
        assert s.loaded_at is None
        assert s.config == {}

    def test_state_with_values(self) -> None:
        now = datetime.now(timezone.utc)
        s = PluginState(name="test", enabled=False, loaded_at=now)
        assert s.enabled is False
        assert s.loaded_at == now


class TestPluginLoader:
    def test_discover_with_mocked_entry_points(self) -> None:
        import sys
        settings = Settings()
        loader = PluginLoader(settings)

        mock_ep = MagicMock()
        mock_ep.name = "test-plugin"
        mock_ep.value = "test_plugin.main"
        mock_ep.dist = MagicMock()
        mock_ep.dist.version = "1.0.0"

        if sys.version_info >= (3, 12):
            mock_return = [mock_ep]
        else:
            mock_return = MagicMock()
            mock_return.get.return_value = [mock_ep]

        with patch("importlib.metadata.entry_points", return_value=mock_return):
            manifests = loader.discover()

        assert len(manifests) == 1
        assert manifests[0].name == "test-plugin"

    def test_disabled_plugin_not_loaded(self) -> None:
        settings = Settings()
        settings.plugin.enabled = False
        loader = PluginLoader(settings)

        api = MagicMock(spec=PluginAPI)
        loader._manifests = [
            PluginManifest(name="p1", entry_point="p1.main"),
        ]
        loader.load_all(api)
        api.register_tool.assert_not_called()


class TestPluginAPI:
    def test_register_tool(self) -> None:
        tool_reg = ToolRegistry()
        ctx_reg = ContextEngineRegistry()
        api = PluginAPI(tool_reg, ctx_reg)

        tool = MagicMock(spec=BaseTool)
        tool.name = "plugin_tool"
        api.register_tool(tool, groups=["group:custom"])

        assert tool_reg.get("plugin_tool") is tool
        group_tools = tool_reg.get_group("group:custom")
        assert len(group_tools) == 1
