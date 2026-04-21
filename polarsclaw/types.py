"""Shared types and data models for PolarsClaw."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


# ── Enums ────────────────────────────────────────────────────────────────────


class DMScope(str, Enum):
    """Scope for direct-message sessions."""

    MAIN = "main"
    PER_PEER = "per-peer"
    PER_CHANNEL_PEER = "per-channel-peer"


class ScheduleType(str, Enum):
    """Type of cron/schedule trigger."""

    CRON = "cron"
    AT = "at"
    EVERY = "every"


class QueueMode(str, Enum):
    """How queued messages are dispatched to agents."""

    COLLECT = "collect"
    STEER = "steer"
    FOLLOWUP = "followup"
    INTERRUPT = "interrupt"


class WSMessageType(str, Enum):
    """WebSocket frame types exchanged between gateway and clients."""

    HELLO = "hello"
    ACK = "ack"
    MESSAGE = "message"
    STREAM = "stream"
    ERROR = "error"
    DONE = "done"


# ── Pydantic models ─────────────────────────────────────────────────────────


class WSMessage(BaseModel):
    """A single WebSocket message envelope."""

    type: WSMessageType
    data: dict[str, Any] = Field(default_factory=dict)
    session_id: str | None = None
    request_id: str | None = None


class Message(BaseModel):
    """A persisted chat message."""

    id: int
    session_id: str
    role: str
    content: str
    timestamp: datetime


class Memory(BaseModel):
    """A key-value memory entry (optionally scoped to a session)."""

    id: int
    key: str
    value: str
    type: str = "general"
    session_id: str | None = None
    created_at: datetime
    updated_at: datetime


class CronExecutionResult(BaseModel):
    """Persisted result metadata for one cron execution."""

    id: int
    job_id: int
    status: str
    output: str | None = None
    error: str | None = None
    session_id: str | None = None
    task: str | None = None
    duration_ms: int | None = None
    started_at: datetime
    finished_at: datetime | None = None
