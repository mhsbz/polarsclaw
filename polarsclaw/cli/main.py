"""PolarsClaw CLI entry point."""
from __future__ import annotations

import click
from pathlib import Path


@click.group()
@click.option("--config", type=click.Path(exists=False), default=None, help="Config file path")
@click.pass_context
def cli(ctx: click.Context, config: str | None) -> None:
    """PolarsClaw — Personal AI Assistant"""
    ctx.ensure_object(dict)
    if config:
        ctx.obj["config_path"] = Path(config)


def _register_commands() -> None:
    """Lazily import and register subcommands for graceful degradation."""
    try:
        from polarsclaw.cli.chat import chat
        cli.add_command(chat)
    except Exception:
        pass

    try:
        from polarsclaw.cli.message import message
        cli.add_command(message)
    except Exception:
        pass

    try:
        from polarsclaw.cli.config_cmd import config_group
        cli.add_command(config_group, "config")
    except Exception:
        pass

    try:
        from polarsclaw.cli.daemon import daemon_group
        cli.add_command(daemon_group, "daemon")
    except Exception:
        pass

    try:
        from polarsclaw.cli.skills_cmd import skills_group
        cli.add_command(skills_group, "skills")
    except Exception:
        pass

    try:
        from polarsclaw.cli.cron_cmd import cron_group
        cli.add_command(cron_group, "cron")
    except Exception:
        pass


_register_commands()


if __name__ == "__main__":
    cli()
