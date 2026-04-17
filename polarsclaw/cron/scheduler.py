"""Full CronScheduler using APScheduler."""

from __future__ import annotations

import json
import logging
from typing import Any, Callable

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.triggers.date import DateTrigger
from croniter import croniter

from polarsclaw.cron.models import CronJob, CronResult
from polarsclaw.storage.database import Database
from polarsclaw.storage.repositories import CronRepo
from polarsclaw.types import ScheduleType

logger = logging.getLogger(__name__)


def _parse_every(expr: str) -> dict[str, Any]:
    """Parse 'every' expressions like '5m', '1h', '30s' into IntervalTrigger kwargs."""
    expr = expr.strip().lower()
    units = {"s": "seconds", "m": "minutes", "h": "hours", "d": "days"}
    for suffix, kwarg in units.items():
        if expr.endswith(suffix):
            return {kwarg: int(expr[: -len(suffix)])}
    raise ValueError(f"Invalid 'every' expression: {expr!r}. Use e.g. '5m', '1h', '30s'.")


class CronScheduler:
    """Manages scheduled jobs backed by APScheduler + SQLite."""

    def __init__(self, db: Database, *, timezone: str = "UTC") -> None:
        self._db = db
        self._repo = CronRepo(db)
        self._timezone = timezone
        self._scheduler = AsyncIOScheduler(timezone=timezone)
        self._agent_factory: Callable | None = None

    def set_agent_factory(self, factory: Callable) -> None:
        """Set the callable used to create agents for job execution."""
        self._agent_factory = factory

    async def start(self) -> None:
        """Load active jobs from DB and start the scheduler."""
        jobs = await self._repo.list(enabled_only=True)
        for row in jobs:
            job = self._row_to_cronjob(row)
            self._register_job(job)
        self._scheduler.start()
        logger.info("CronScheduler started with %d active jobs.", len(jobs))

    async def stop(self) -> None:
        """Shut down the scheduler gracefully."""
        self._scheduler.shutdown(wait=True)
        logger.info("CronScheduler stopped.")

    async def add_job(
        self,
        name: str,
        schedule: str,
        task: str,
        schedule_type: ScheduleType = ScheduleType.CRON,
    ) -> CronJob:
        """Validate, save to DB, and register a new job."""
        # Validate cron expression
        if schedule_type == ScheduleType.CRON:
            if not croniter.is_valid(schedule):
                raise ValueError(f"Invalid cron expression: {schedule!r}")
        elif schedule_type == ScheduleType.EVERY:
            _parse_every(schedule)  # validates

        job_id = await self._repo.create(
            name,
            schedule,
            type=schedule_type.value,
            payload={"task": task},
            enabled=True,
        )
        row = await self._repo.get(job_id)
        job = self._row_to_cronjob(row)
        self._register_job(job)
        logger.info("Added cron job %d: %s", job.id, job.name)
        return job

    async def remove_job(self, job_id: int) -> bool:
        """Remove a job from scheduler and DB."""
        ap_id = f"cron_{job_id}"
        try:
            self._scheduler.remove_job(ap_id)
        except Exception:
            pass
        await self._repo.delete(job_id)
        logger.info("Removed cron job %d.", job_id)
        return True

    async def list_jobs(self) -> list[CronJob]:
        """List all cron jobs."""
        rows = await self._repo.list()
        return [self._row_to_cronjob(r) for r in rows]

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _register_job(self, job: CronJob) -> None:
        """Register a CronJob with the APScheduler."""
        trigger = self._make_trigger(job)
        self._scheduler.add_job(
            self._execute_wrapper,
            trigger=trigger,
            id=f"cron_{job.id}",
            args=[job],
            replace_existing=True,
        )

    def _make_trigger(self, job: CronJob) -> Any:
        """Build an APScheduler trigger from a CronJob."""
        if job.schedule_type == ScheduleType.CRON:
            return CronTrigger.from_crontab(job.schedule, timezone=self._timezone)
        elif job.schedule_type == ScheduleType.EVERY:
            kwargs = _parse_every(job.schedule)
            return IntervalTrigger(**kwargs, timezone=self._timezone)
        elif job.schedule_type == ScheduleType.AT:
            return DateTrigger(run_date=job.schedule, timezone=self._timezone)
        raise ValueError(f"Unknown schedule type: {job.schedule_type}")

    async def _execute_wrapper(self, job: CronJob) -> None:
        """Wrapper that delegates to execute_cron_job."""
        from polarsclaw.cron.executor import execute_cron_job

        await execute_cron_job(job, self._agent_factory, self._db)

    @staticmethod
    def _row_to_cronjob(row: dict[str, Any]) -> CronJob:
        payload = row.get("payload", "{}")
        if isinstance(payload, str):
            payload = json.loads(payload)
        return CronJob(
            id=row["id"],
            name=row["name"],
            schedule=row["schedule"],
            schedule_type=ScheduleType(row.get("type", "cron")),
            task=payload.get("task", ""),
            enabled=bool(row.get("enabled", True)),
            created_at=row["created_at"],
        )
