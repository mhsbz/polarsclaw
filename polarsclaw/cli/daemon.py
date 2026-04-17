"""CLI commands for the PolarsClaw daemon."""

from __future__ import annotations

import click

from polarsclaw.daemon.process import DaemonProcess


@click.group("daemon")
def daemon_group() -> None:
    """Manage the PolarsClaw background daemon."""


@daemon_group.command()
def start() -> None:
    """Start the daemon in the background."""
    DaemonProcess().start()


@daemon_group.command()
def stop() -> None:
    """Stop the running daemon."""
    DaemonProcess().stop()


@daemon_group.command()
def status() -> None:
    """Show daemon status."""
    result = DaemonProcess().status()
    icon = "🟢" if result == "running" else "🔴"
    click.echo(f"{icon} Daemon is {result}.")
