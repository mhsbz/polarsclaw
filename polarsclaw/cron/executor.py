"""Isolated cron job execution."""

from __future__ import annotations

import asyncio
import logging
import time
import traceback
import uuid
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable

from polarsclaw.cron.models import CronJob, CronResult
from polarsclaw.storage.database import Database
from polarsclaw.storage.repositories import MessageRepo
from polarsclaw.storage.repositories import CronRepo
from polarsclaw.sessions.manager import SessionManager
from polarsclaw.types import DMScope

logger = logging.getLogger(__name__)


async def execute_cron_job(
    job: CronJob,
    agent_factory: Callable[[], Awaitable[Any]] | None,
    db: Database,
    *,
    timeout: int = 300,
) -> CronResult:
    """Execute a cron job in an isolated context.

    Creates a fresh agent session, runs the task, captures output/errors,
    measures duration, and stores the result via CronRepo.
    """
    repo = CronRepo(db)
    started_at = datetime.now(timezone.utc)
    start_ns = time.monotonic_ns()

    success = False
    output: str | None = None
    error: str | None = None
    session_id: str | None = None

    try:
        if agent_factory is None:
            raise RuntimeError("No agent factory configured for cron execution.")

        agent = await agent_factory()
        session_mgr = SessionManager(db, dm_scope=DMScope.MAIN)
        message_repo = MessageRepo(db)
        session = await session_mgr.create_with_id(
            f"cron-{job.id}-{uuid.uuid4().hex[:12]}",
            agent.agent_id,
            title=f"[cron] {job.name}",
        )
        session_id = session.id
        await message_repo.add(session_id, "user", job.task, metadata={"source": "cron", "job_id": job.id})
        result = await asyncio.wait_for(
            agent.run(job.task, session_id=session_id),
            timeout=timeout,
        )
        output = str(result) if result is not None else ""
        await message_repo.add(
            session_id,
            "assistant",
            output,
            metadata={"source": "cron", "job_id": job.id},
        )
        success = True
        logger.info("Cron job %d (%s) completed successfully.", job.id, job.name)

    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}\n{traceback.format_exc()}"
        logger.error("Cron job %d (%s) failed: %s", job.id, job.name, exc)

    duration_ms = (time.monotonic_ns() - start_ns) // 1_000_000
    finished_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    started_str = started_at.strftime("%Y-%m-%d %H:%M:%S")

    status = "success" if success else "error"
    result_id = await repo.record_result(
        job.id,
        status,
        output=output,
        error=error,
        session_id=session_id,
        task=job.task,
        duration_ms=duration_ms,
        started_at=started_str,
        finished_at=finished_at,
    )

    return CronResult(
        id=result_id,
        job_id=job.id,
        success=success,
        output=output,
        error=error,
        session_id=session_id,
        task=job.task,
        executed_at=started_at,
        duration_ms=duration_ms,
    )


async def execute_runtime_job(
    job: CronJob,
    callback: Callable[[], Awaitable[Any]],
    db: Database,
) -> CronResult:
    """Execute a scheduler-owned runtime callback and store its result."""
    repo = CronRepo(db)
    started_at = datetime.now(timezone.utc)
    start_ns = time.monotonic_ns()

    success = False
    output: str | None = None
    error: str | None = None

    try:
        result = await callback()
        output = str(result) if result is not None else ""
        success = True
    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}\n{traceback.format_exc()}"
        logger.error("Runtime cron job %d (%s) failed: %s", job.id, job.name, exc)

    duration_ms = (time.monotonic_ns() - start_ns) // 1_000_000
    finished_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    started_str = started_at.strftime("%Y-%m-%d %H:%M:%S")

    result_id = await repo.record_result(
        job.id,
        "success" if success else "error",
        output=output,
        error=error,
        task=job.task,
        duration_ms=duration_ms,
        started_at=started_str,
        finished_at=finished_at,
    )

    return CronResult(
        id=result_id,
        job_id=job.id,
        success=success,
        output=output,
        error=error,
        task=job.task,
        executed_at=started_at,
        duration_ms=duration_ms,
    )
