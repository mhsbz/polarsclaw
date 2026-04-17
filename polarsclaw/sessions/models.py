"""Session-specific models (re-exports core types + extras)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

# Re-export the core Message type for convenience
from polarsclaw.types import Message as Message  # noqa: F401


class Session(BaseModel):
    """Hydrated session object returned by SessionManager."""

    id: str
    title: str | None = None
    scope: str = "main"
    peer_id: str | None = None
    channel_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime


class SessionSummary(BaseModel):
    """Lightweight session summary for listings."""

    id: str
    title: str | None = None
    scope: str = "main"
    message_count: int = 0
    updated_at: datetime
