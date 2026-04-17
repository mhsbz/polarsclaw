"""Interactive chat command."""
from __future__ import annotations

import asyncio
import uuid

import click
from rich.console import Console
from rich.markdown import Markdown


@click.command()
@click.option("--session", "session_id", default=None, help="Resume session by ID")
@click.option("--model", default=None, help="Override model")
@click.pass_context
def chat(ctx: click.Context, session_id: str | None, model: str | None) -> None:
    """Start interactive chat session."""
    asyncio.run(_chat_loop(ctx, session_id, model))


async def _chat_loop(
    ctx: click.Context,
    session_id: str | None,
    model: str | None,
) -> None:
    console = Console()

    # --- 1. Build application context ---
    try:
        from polarsclaw.app import build_app, cleanup_app
    except ImportError:
        console.print("[red]App module not available yet. Install dependencies first.[/red]")
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
        console.print("[yellow]Settings module not ready — using defaults.[/yellow]")

    try:
        app = await build_app(settings)
    except Exception as exc:
        console.print(f"[red]Failed to initialise app: {exc}[/red]")
        return

    # --- 2. Create agent ---
    agent = None
    try:
        from polarsclaw.agents.factory import create_agent

        agent = create_agent(app)
    except ImportError:
        console.print("[yellow]Agent factory not available — echo mode active.[/yellow]")

    # --- 3. Session ---
    if session_id is None:
        session_id = uuid.uuid4().hex[:12]
    console.print(f"[dim]Session: {session_id}[/dim]")
    console.print("[dim]Type /quit or /exit to leave. Ctrl+C to cancel current response.[/dim]\n")

    # --- 4. REPL ---
    try:
        while True:
            try:
                user_input = console.input("[bold green]You:[/bold green] ")
            except (EOFError, KeyboardInterrupt):
                console.print("\n[dim]Bye![/dim]")
                break

            text = user_input.strip()
            if not text:
                continue
            if text.lower() in {"/quit", "/exit", "quit", "exit"}:
                console.print("[dim]Bye![/dim]")
                break

            # --- Get response ---
            try:
                if agent is not None:
                    response_text = ""
                    if hasattr(agent, "stream"):
                        async for chunk in agent.stream(text, session_id=session_id):
                            response_text += chunk
                            # Live streaming could be added here
                    else:
                        response_text = await agent.run(text, session_id=session_id)
                else:
                    # Echo mode fallback
                    response_text = f"*(echo)* {text}"

                console.print()
                console.print(Markdown(response_text))
                console.print()
            except KeyboardInterrupt:
                console.print("\n[yellow]Response cancelled.[/yellow]\n")
            except Exception as exc:
                console.print(f"\n[red]Error: {exc}[/red]\n")
    finally:
        try:
            from polarsclaw.app import cleanup_app as _cleanup

            await _cleanup(app)
        except Exception:
            pass
