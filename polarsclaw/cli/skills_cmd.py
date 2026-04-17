"""CLI commands for skill management."""

from __future__ import annotations

from pathlib import Path

import click
from rich.console import Console
from rich.table import Table

from polarsclaw.config.settings import DEFAULT_CONFIG_DIR


@click.group("skills")
def skills_group() -> None:
    """Manage PolarsClaw skills."""


@skills_group.command("list")
def list_skills() -> None:
    """List discovered skills."""
    skills_dir = DEFAULT_CONFIG_DIR / "skills"
    console = Console()

    if not skills_dir.exists():
        console.print("[dim]No skills directory found.[/dim]")
        console.print(f"Create it at: {skills_dir}")
        return

    skill_files = sorted(skills_dir.glob("*.py"))
    if not skill_files:
        console.print("[dim]No skills found.[/dim]")
        return

    table = Table(title="Discovered Skills")
    table.add_column("Name", style="cyan")
    table.add_column("Path", style="dim")
    table.add_column("Size", justify="right")

    for f in skill_files:
        name = f.stem
        size = f"{f.stat().st_size:,} B"
        table.add_row(name, str(f), size)

    console.print(table)


@skills_group.command("path")
def skills_path() -> None:
    """Print the skills directory path."""
    click.echo(DEFAULT_CONFIG_DIR / "skills")
