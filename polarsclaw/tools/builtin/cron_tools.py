"""Cron tools with dependency injection via closure."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from langchain_core.tools import BaseTool, tool

if TYPE_CHECKING:
    from polarsclaw.cron.scheduler import CronScheduler


def make_cron_tools(scheduler: CronScheduler) -> list[BaseTool]:
    """Factory that creates cron tools with *scheduler* captured via closure."""

    @tool
    async def create_cron(name: str, schedule: str, task: str) -> str:
        """Create a new cron job.

        Args:
            name: Unique name for the job.
            schedule: Cron expression (e.g. '0 9 * * *') or interval (e.g. '5m').
            task: The task/prompt to execute on schedule.
        """
        try:
            job = await scheduler.add_job(name, schedule, task)
            return json.dumps({"ok": True, "job_id": job.id, "name": job.name})
        except Exception as exc:
            return json.dumps({"ok": False, "error": str(exc)})

    @tool
    async def list_crons() -> str:
        """List all scheduled cron jobs."""
        jobs = await scheduler.list_jobs()
        return json.dumps(
            [
                {
                    "id": j.id,
                    "name": j.name,
                    "schedule": j.schedule,
                    "type": j.schedule_type.value,
                    "enabled": j.enabled,
                    "task": j.task,
                }
                for j in jobs
            ],
            indent=2,
        )

    @tool
    async def delete_cron(cron_id: int) -> str:
        """Delete a cron job by ID.

        Args:
            cron_id: The ID of the cron job to delete.
        """
        try:
            await scheduler.remove_job(cron_id)
            return json.dumps({"ok": True, "deleted": cron_id})
        except Exception as exc:
            return json.dumps({"ok": False, "error": str(exc)})

    @tool
    async def cron_history(cron_id: int, limit: int = 10) -> str:
        """Show execution history for a cron job.

        Args:
            cron_id: The cron job ID.
            limit: Maximum number of results to return.
        """
        from polarsclaw.storage.repositories import CronRepo

        repo = CronRepo(scheduler._db)
        results = await repo.list_results(cron_id, limit=limit)
        return json.dumps(results, indent=2, default=str)

    return [create_cron, list_crons, delete_cron, cron_history]
