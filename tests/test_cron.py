"""Tests for polarsclaw.cron."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from polarsclaw.cron.executor import execute_cron_job
from polarsclaw.cron.models import CronJob, CronResult
from polarsclaw.cron.scheduler import CronScheduler
from polarsclaw.storage.database import Database
from polarsclaw.types import ScheduleType


class TestCronModels:
    def test_cron_job(self) -> None:
        job = CronJob(
            id=1, name="test", schedule="0 9 * * *",
            schedule_type=ScheduleType.CRON, task="do stuff",
            created_at=datetime.now(timezone.utc),
        )
        assert job.name == "test"
        assert job.enabled is True

    def test_cron_result(self) -> None:
        r = CronResult(
            id=1, job_id=1, success=True, output="ok",
            executed_at=datetime.now(timezone.utc), duration_ms=100,
        )
        assert r.success is True
        assert r.duration_ms == 100


class TestCronScheduler:
    async def test_add_and_list_jobs(self, tmp_db: Database) -> None:
        sched = CronScheduler(tmp_db)
        await sched.start()
        job = await sched.add_job("test-job", "*/5 * * * *", "do work")
        assert job.name == "test-job"
        jobs = await sched.list_jobs()
        assert len(jobs) == 1
        await sched.stop()

    async def test_remove_job(self, tmp_db: Database) -> None:
        sched = CronScheduler(tmp_db)
        await sched.start()
        job = await sched.add_job("rm-job", "0 0 * * *", "cleanup")
        result = await sched.remove_job(job.id)
        assert result is True
        jobs = await sched.list_jobs()
        assert len(jobs) == 0
        await sched.stop()

    async def test_invalid_cron_expression(self, tmp_db: Database) -> None:
        sched = CronScheduler(tmp_db)
        await sched.start()
        with pytest.raises(ValueError, match="Invalid cron"):
            await sched.add_job("bad", "not-a-cron", "task")
        await sched.stop()


class TestExecuteCronJob:
    async def test_success(self, tmp_db: Database) -> None:
        job = CronJob(
            id=1, name="ok-job", schedule="* * * * *",
            schedule_type=ScheduleType.CRON, task="hello",
            created_at=datetime.now(timezone.utc),
        )
        # Need a cron_jobs row for the FK
        from polarsclaw.storage.repositories import CronRepo
        repo = CronRepo(tmp_db)
        real_id = await repo.create("ok-job", "* * * * *", payload={"task": "hello"})
        job.id = real_id

        agent = AsyncMock()
        agent.run.return_value = "done"
        factory = AsyncMock(return_value=agent)
        result = await execute_cron_job(job, factory, tmp_db)
        assert result.success is True
        assert result.output == "done"

    async def test_failure(self, tmp_db: Database) -> None:
        from polarsclaw.storage.repositories import CronRepo
        repo = CronRepo(tmp_db)
        real_id = await repo.create("fail-job", "* * * * *")

        job = CronJob(
            id=real_id, name="fail-job", schedule="* * * * *",
            schedule_type=ScheduleType.CRON, task="boom",
            created_at=datetime.now(timezone.utc),
        )
        agent = AsyncMock()
        agent.run.side_effect = RuntimeError("kaboom")
        factory = AsyncMock(return_value=agent)
        result = await execute_cron_job(job, factory, tmp_db)
        assert result.success is False
        assert "kaboom" in (result.error or "")

    async def test_no_factory(self, tmp_db: Database) -> None:
        from polarsclaw.storage.repositories import CronRepo
        repo = CronRepo(tmp_db)
        real_id = await repo.create("nofac", "* * * * *")

        job = CronJob(
            id=real_id, name="nofac", schedule="* * * * *",
            schedule_type=ScheduleType.CRON, task="x",
            created_at=datetime.now(timezone.utc),
        )
        result = await execute_cron_job(job, None, tmp_db)
        assert result.success is False
        assert "No agent factory" in (result.error or "")
