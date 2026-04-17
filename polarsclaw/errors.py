"""PolarsClaw exception hierarchy."""

from __future__ import annotations


class PolarsClawError(Exception):
    """Base exception for all PolarsClaw errors."""


# ── Config ───────────────────────────────────────────────────────────────────


class ConfigError(PolarsClawError):
    """Raised when configuration is invalid or cannot be loaded."""


class ConfigNotFoundError(ConfigError):
    """Raised when a config file is missing."""


# ── Storage ──────────────────────────────────────────────────────────────────


class StorageError(PolarsClawError):
    """Base class for storage/database errors."""


class MigrationError(StorageError):
    """Raised when a database migration fails."""


class RecordNotFoundError(StorageError):
    """Raised when a requested record does not exist."""


# ── Agent / Routing ─────────────────────────────────────────────────────────


class AgentError(PolarsClawError):
    """Raised when an agent encounters an unrecoverable error."""


class AgentTimeoutError(AgentError):
    """Raised when an agent execution exceeds the configured timeout."""


class RoutingError(PolarsClawError):
    """Raised when message routing fails (no matching skill, etc.)."""


# ── Gateway ──────────────────────────────────────────────────────────────────


class GatewayError(PolarsClawError):
    """Raised for WebSocket / HTTP gateway errors."""


class SessionError(PolarsClawError):
    """Raised for session lifecycle errors."""


class SessionNotFoundError(SessionError):
    """Raised when a session cannot be found."""


# ── Plugin ───────────────────────────────────────────────────────────────────


class PluginError(PolarsClawError):
    """Raised when a plugin fails to load or execute."""


class PluginLoadError(PluginError):
    """Raised when a plugin cannot be discovered or loaded."""
