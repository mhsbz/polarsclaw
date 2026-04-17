"""Plugin manifest and state models."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class PluginManifest(BaseModel):
    """Metadata extracted from a discovered plugin entry-point."""

    name: str
    version: str = "0.0.0"
    entry_point: str = Field(
        ..., description="Dotted import path, e.g. 'my_plugin.main'."
    )
    description: str = ""


class PluginState(BaseModel):
    """Runtime state for a loaded plugin."""

    name: str
    enabled: bool = True
    config: dict[str, object] = Field(default_factory=dict)
    loaded_at: datetime | None = None
