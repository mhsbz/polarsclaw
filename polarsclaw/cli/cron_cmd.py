"""CLI commands for cron job management."""

from __future__ import annotations

import asyncio
import json

import click
from rich.console import Console
from rich.table import Table

from polarsclaw.config.settings import Settings
from polarsclaw.storage.database import Database
from polarsclaw.storage.repositories import CronRepo


def _run(coro):
    """Run an async coroutine synchronously."""
    return asyncio.get_event_loop().run_until_complete(coro)


@click.group("cron")
def cron_group() -> None:
    """Manage scheduled cron jobs."""


@cron_group.command("list")
def list_crons() -> None:
    """List all cron jobs."""
    console = Console()
    settings = Settings.from_file()
    db = Database(settings.db_path)

    async def _list():
        await db.initialize()
        repo = CronRepo(db)
        jobs = await repo.list()
        await db.close()
        return jobs

    jobs = _run(_list())

    if not jobs:
        console.print("[dim]No cron jobs found.[/dim]")
        return

    table = Table(title="Cron Jobs")
    table.add_column("ID", justify="right", style="cyan")
    table.add_column("Name", style="bold")
    table.add_column("Schedule")
    table.add_column("Type")
    table.add_column("Enabled", justify="center")

    for j in jobs:
        payload = j.get("payload", "{}")
        if isinstance(payload, str):
            payload = json.loads(payload)
        enabled = "✓" if j.get("enabled") else "✗"
        table.add_row(
            str(j["id"]),
            j["name"],
            j["schedule"],
            j.get("type", "cron"),
            enabled,
        )

    console.print(table)


@cron_group.command("history")
@click.argument("job_id", type=int)
@click.option("--limit", default=10, help="Number of results to show.")
def cron_history(job_id: int, limit: int) -> None:
    """Show execution history for a cron job."""
    console = Console()
    settings = Settings.from_file()
    db = Database(settings.db_path)

    async def _history():
        await db.initialize()
        repo = CronRepo(db)
        results = await repo.list_results(job_id, limit=limit)
        await db.close()
        return results

    results = _run(_history())

    if not results:
        console.print(f"[dim]No execution history for job {job_id}.[/dim]")
        return

    table = Table(title=f"Cron History — Job {job_id}")
    table.add_column("ID", justify="right", style="cyan")
    table.add_column("Status")
    table.add_column("Started", style="dim")
    table.add_column("Finished", style="dim")
    table.add_column("Output", max_width=40, overflow="ellipsis")

    for r in results:
        status_style = "green" if r["status"] == "success" else "red"
        table.add_row(
            str(r["id"]),
            f"[{status_style}]{r['status']}[/{status_style}]",
            r.get("started_at", ""),
            r.get("finished_at", ""),
            (r.get("output") or r.get("error") or "")[:80],
        )

    console.print(table)
