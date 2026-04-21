"""Cron data models."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from polarsclaw.types import ScheduleType


class CronJob(BaseModel):
    """A scheduled cron job."""

    id: int
    name: str
    schedule: str
    schedule_type: ScheduleType = ScheduleType.CRON
    task: str
    enabled: bool = True
    created_at: datetime


class CronResult(BaseModel):
    """Result of a cron job execution."""

    id: int
    job_id: int
    success: bool
    output: str | None = None
    error: str | None = None
    session_id: str | None = None
    task: str | None = None
    executed_at: datetime
    duration_ms: int
