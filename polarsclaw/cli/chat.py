"""Interactive chat command."""
from __future__ import annotations

import asyncio

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
        from polarsclaw.config.settings import Settings
        from polarsclaw.runtime import dispatch_message
    except ImportError:
        console.print("[red]App module not available. Install dependencies first.[/red]")
        return

    config_path = (ctx.obj or {}).get("config_path")
    try:
        settings = Settings.from_file(config_path) if config_path else Settings()
    except Exception as exc:
        console.print(f"[red]Failed to load settings: {exc}[/red]")
        return

    # Override model if specified
    if model:
        settings.agent.model = model

    console.print("[dim]Starting PolarsClaw...[/dim]")

    try:
        app = await build_app(settings)
    except Exception as exc:
        console.print(f"[red]Failed to initialise app: {exc}[/red]")
        return

    # --- 2. Get the default agent ---
    agent = None
    if app.agents:
        default_id = next(iter(app.agents))
        agent = app.agents[default_id]
        console.print(f"[dim]Agent: {default_id} (model={settings.agent.model})[/dim]")
    else:
        console.print("[yellow]No agent available — echo mode.[/yellow]")

    # --- 3. Session ---
    active_session_id = session_id
    console.print(f"[dim]Session: {active_session_id or '(auto)'}[/dim]")
    console.print("[dim]Type /quit or /exit to leave. Ctrl+C to cancel.[/dim]\n")

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
                    console.print()
                    response_text = ""
                    try:
                        result = await dispatch_message(
                            app,
                            content=text,
                            session_id=active_session_id,
                            on_token=_stream_console(console, response_text := []),
                        )
                        active_session_id = result.session.id
                        if response_text:
                            console.print()
                        else:
                            raise RuntimeError("Stream returned empty response")
                    except Exception:
                        result = await dispatch_message(
                            app,
                            content=text,
                            session_id=active_session_id,
                        )
                        active_session_id = result.session.id
                        response_text = result.response
                        if response_text:
                            console.print(Markdown(response_text))
                        else:
                            console.print("[yellow]No response from agent.[/yellow]")
                    console.print()
                else:
                    console.print(f"\n*(echo)* {text}\n")

            except KeyboardInterrupt:
                if agent:
                    await agent.cancel()
                console.print("\n[yellow]Cancelled.[/yellow]\n")
            except Exception as exc:
                console.print(f"\n[red]Error: {exc}[/red]\n")
    finally:
        try:
            await cleanup_app(app)
        except Exception:
            pass


def _stream_console(console: Console, collected: list[str]):
    async def _callback(chunk: str) -> None:
        collected.append(chunk)
        console.print(chunk, end="", highlight=False)

    return _callback
