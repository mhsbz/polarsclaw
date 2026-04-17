"""Isolated cron job execution."""

from __future__ import annotations

import logging
import time
import traceback
from datetime import datetime, timezone
from typing import Any, Callable

from polarsclaw.cron.models import CronJob, CronResult
from polarsclaw.storage.database import Database
from polarsclaw.storage.repositories import CronRepo

logger = logging.getLogger(__name__)


async def execute_cron_job(
    job: CronJob,
    agent_factory: Callable | None,
    db: Database,
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

    try:
        if agent_factory is None:
            raise RuntimeError("No agent factory configured for cron execution.")

        agent = await agent_factory()
        # Run the task as a message through the agent
        result = await agent.run(job.task)
        output = str(result) if result is not None else ""
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
        started_at=started_str,
        finished_at=finished_at,
    )

    return CronResult(
        id=result_id,
        job_id=job.id,
        success=success,
        output=output,
        error=error,
        executed_at=started_at,
        duration_ms=duration_ms,
    )
