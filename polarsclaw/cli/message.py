"""Single-shot message command."""
from __future__ import annotations

import asyncio
import uuid

import click
from rich.console import Console
from rich.markdown import Markdown


@click.command()
@click.argument("text")
@click.option("--session", "session_id", default=None, help="Session ID")
@click.option("--model", default=None, help="Override model")
@click.pass_context
def message(ctx: click.Context, text: str, session_id: str | None, model: str | None) -> None:
    """Send a single message and print the response."""
    asyncio.run(_send_message(ctx, text, session_id, model))


async def _send_message(
    ctx: click.Context,
    text: str,
    session_id: str | None,
    model: str | None,
) -> None:
    console = Console()

    # --- Build app ---
    try:
        from polarsclaw.app import build_app, cleanup_app
    except ImportError:
        console.print("[red]App module not available yet.[/red]")
        return

    settings = None
    config_path = (ctx.obj or {}).get("config_path")
    try:
        from polarsclaw.config.settings import Settings

        if config_path:
            settings = Settings.from_file(config_path)
        else:
            settings = Settings()
        if model:
            settings.default_model = model
    except ImportError:
        pass

    try:
        app = await build_app(settings)
    except Exception as exc:
        console.print(f"[red]Failed to initialise app: {exc}[/red]")
        return

    try:
        # --- Create agent ---
        agent = None
        try:
            from polarsclaw.agents.factory import create_agent

            agent = create_agent(app)
        except ImportError:
            pass

        if session_id is None:
            session_id = uuid.uuid4().hex[:12]

        # --- Run ---
        if agent is not None:
            response_text = await agent.run(text, session_id=session_id)
        else:
            response_text = f"*(echo)* {text}"

        console.print(Markdown(response_text))
    finally:
        try:
            await cleanup_app(app)
        except Exception:
            pass
