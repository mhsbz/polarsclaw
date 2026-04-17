"""Config show/set commands."""
from __future__ import annotations

import json

import click
from rich.console import Console
from rich.syntax import Syntax


@click.group("config")
def config_group() -> None:
    """Manage PolarsClaw configuration."""


@config_group.command("show")
@click.pass_context
def config_show(ctx: click.Context) -> None:
    """Show current configuration."""
    console = Console()

    try:
        from polarsclaw.config.settings import Settings

        config_path = (ctx.obj or {}).get("config_path")
        settings = Settings.from_file(config_path) if config_path else Settings()
        data = settings.model_dump() if hasattr(settings, "model_dump") else settings.__dict__
    except ImportError:
        console.print("[yellow]Settings module not available — showing defaults.[/yellow]")
        data = {"status": "settings module not loaded"}
    except Exception as exc:
        console.print(f"[red]Error loading config: {exc}[/red]")
        return

    rendered = json.dumps(data, indent=2, default=str)
    console.print(Syntax(rendered, "json", theme="monokai"))


@config_group.command("set")
@click.argument("key")
@click.argument("value")
@click.pass_context
def config_set(ctx: click.Context, key: str, value: str) -> None:
    """Set a configuration value (dot-notation supported, e.g. llm.model)."""
    console = Console()

    try:
        from polarsclaw.config.settings import Settings

        config_path = (ctx.obj or {}).get("config_path")
        settings = Settings.from_file(config_path) if config_path else Settings()

        # Navigate dot-separated key
        parts = key.split(".")
        obj = settings
        for part in parts[:-1]:
            if isinstance(obj, dict):
                obj = obj[part]
            else:
                obj = getattr(obj, part)

        final_key = parts[-1]

        # Attempt type coercion based on current value
        current = getattr(obj, final_key, None) if not isinstance(obj, dict) else obj.get(final_key)
        if isinstance(current, bool):
            coerced: str | int | float | bool = value.lower() in {"true", "1", "yes"}
        elif isinstance(current, int):
            coerced = int(value)
        elif isinstance(current, float):
            coerced = float(value)
        else:
            coerced = value

        if isinstance(obj, dict):
            obj[final_key] = coerced
        else:
            setattr(obj, final_key, coerced)

        # Persist
        if hasattr(settings, "save"):
            settings.save(config_path)
            console.print(f"[green]Set {key} = {coerced}[/green]")
        else:
            console.print(f"[yellow]Updated in memory: {key} = {coerced} (no save method available)[/yellow]")

    except ImportError:
        console.print("[red]Settings module not available yet.[/red]")
    except Exception as exc:
        console.print(f"[red]Error setting config: {exc}[/red]")
