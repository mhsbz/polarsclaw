"""PolarsClaw settings — Pydantic Settings backed by JSON file + env vars."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

DEFAULT_CONFIG_DIR = Path.home() / ".polarsclaw"
DEFAULT_CONFIG_PATH = DEFAULT_CONFIG_DIR / "config.json"
DEFAULT_DB_PATH = DEFAULT_CONFIG_DIR / "polarsclaw.db"


# ── Sub-configs ──────────────────────────────────────────────────────────────


class AgentConfig(BaseModel):
    """Configuration for the LLM agent backend."""

    id: str = "default"
    model: str = "minimax:MiniMax-M2.7"  # provider:model format
    system_prompt: str = "You are PolarsClaw, a helpful personal AI assistant."
    workspace: Path | None = None
    tools: list[str] = Field(default_factory=list)
    tool_profile: str = "full"
    skills: list[str] = Field(default_factory=list)
    timeout: int = 300
    temperature: float = 0.7
    max_tokens: int = 4096
    streaming: bool = True


class ModelProviderConfig(BaseModel):
    """Custom model provider configuration."""

    name: str
    base_url: str
    api: str = "anthropic-messages"  # or "openai-chat"
    auth_header: bool = True  # use Authorization: Bearer header
    api_key_env: str | None = None  # env var name for API key
    api_key: str | None = None  # direct API key (not recommended)
    models: list[str] = Field(default_factory=list)  # available model IDs


class GatewayConfig(BaseModel):
    """WebSocket / HTTP gateway settings."""

    host: str = "127.0.0.1"
    port: int = 8765
    cors_origins: list[str] = Field(default_factory=lambda: ["*"])
    max_connections: int = 16
    heartbeat_interval: float = 30.0
    auth_token: str | None = None


class CronConfig(BaseModel):
    """Scheduled-task defaults."""

    enabled: bool = True
    timezone: str = "UTC"
    max_concurrent: int = 4
    default_timeout: int = 300


class QueueConfig(BaseModel):
    """Message-queue behaviour."""

    max_pending: int = 100
    collect_window: float = 2.0
    default_mode: str = "collect"


class PluginConfig(BaseModel):
    """Plugin discovery and loading."""

    enabled: bool = True
    directories: list[str] = Field(default_factory=list)
    autoload: list[str] = Field(default_factory=list)


# ── Root settings ────────────────────────────────────────────────────────────


class Settings(BaseSettings):
    """Top-level application settings.

    Resolution order (highest priority first):
      1. Environment variables with ``POLARSCLAW_`` prefix
      2. Values in ``~/.polarsclaw/config.json``
      3. Field defaults defined here
    """

    model_config = SettingsConfigDict(
        env_prefix="POLARSCLAW_",
        env_nested_delimiter="__",
        extra="ignore",
    )

    # Sub-configs
    agent: AgentConfig = Field(default_factory=AgentConfig)
    gateway: GatewayConfig = Field(default_factory=GatewayConfig)
    cron: CronConfig = Field(default_factory=CronConfig)
    queue: QueueConfig = Field(default_factory=QueueConfig)
    plugin: PluginConfig = Field(default_factory=PluginConfig)

    # Custom model providers
    providers: dict[str, ModelProviderConfig] = Field(default_factory=dict)

    # Paths
    config_dir: Path = DEFAULT_CONFIG_DIR
    db_path: Path = DEFAULT_DB_PATH

    # Skill routing
    skill_match_threshold: float = 0.7

    # Logging
    log_level: str = "INFO"
    log_json: bool = False

    # DM scope
    dm_scope: str = "main"

    @classmethod
    def from_file(cls, path: Path | str | None = None, **overrides: Any) -> Settings:
        """Load settings from a JSON config file, merged with env vars.

        Parameters
        ----------
        path:
            Path to JSON config.  Defaults to ``~/.polarsclaw/config.json``.
        **overrides:
            Additional keyword overrides applied last.
        """
        path = Path(path) if path else DEFAULT_CONFIG_PATH
        file_values: dict[str, Any] = {}
        if path.exists():
            file_values = json.loads(path.read_text(encoding="utf-8"))
        file_values.update(overrides)
        return cls(**file_values)
