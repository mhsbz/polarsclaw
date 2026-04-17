"""Tests for polarsclaw.config."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from polarsclaw.config.settings import AgentConfig, Settings


class TestSettingsDefaults:
    def test_loads_defaults(self) -> None:
        s = Settings()
        assert s.log_level == "INFO"
        assert s.skill_match_threshold == 0.7
        assert s.dm_scope == "main"
        assert s.gateway.port == 8765
        assert s.agent.model == "minimax:MiniMax-M2.7-highspeed"
        assert s.cron.enabled is True
        assert s.queue.collect_window == 2.0

    def test_from_file_loads_json(self, tmp_path: Path) -> None:
        cfg = tmp_path / "config.json"
        cfg.write_text(json.dumps({"log_level": "DEBUG", "gateway": {"port": 9999}}))
        s = Settings.from_file(cfg)
        assert s.log_level == "DEBUG"
        assert s.gateway.port == 9999

    def test_from_file_missing_file_uses_defaults(self, tmp_path: Path) -> None:
        s = Settings.from_file(tmp_path / "nonexistent.json")
        assert s.log_level == "INFO"

    def test_from_file_with_overrides(self, tmp_path: Path) -> None:
        cfg = tmp_path / "config.json"
        cfg.write_text(json.dumps({"log_level": "DEBUG"}))
        s = Settings.from_file(cfg, log_level="WARNING")
        assert s.log_level == "WARNING"

    def test_env_var_override(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("POLARSCLAW_LOG_LEVEL", "ERROR")
        s = Settings()
        assert s.log_level == "ERROR"

    def test_nested_env_var(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("POLARSCLAW_GATEWAY__PORT", "1234")
        s = Settings()
        assert s.gateway.port == 1234


class TestAgentConfig:
    def test_defaults(self) -> None:
        ac = AgentConfig()
        assert ac.id == "default"
        assert ac.temperature == 0.7
        assert ac.max_tokens == 4096
        assert ac.streaming is True
        assert ac.tools == []
        assert ac.tool_profile == "full"

    def test_custom_values(self) -> None:
        ac = AgentConfig(id="custom", model="openai:gpt-4", temperature=0.2)
        assert ac.id == "custom"
        assert ac.model == "openai:gpt-4"
        assert ac.temperature == 0.2
