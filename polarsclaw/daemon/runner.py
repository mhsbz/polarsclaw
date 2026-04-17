"""Main daemon event loop — starts gateway, cron, and queue processor."""

from __future__ import annotations

import asyncio
import logging
import signal
from datetime import datetime, time as dtime, timedelta, timezone

from polarsclaw.app import AppContext, build_app, cleanup_app
from polarsclaw.config.settings import Settings

logger = logging.getLogger(__name__)


async def _daily_session_reset(ctx: AppContext) -> None:
    """Sleep until midnight UTC, then reset daily sessions. Repeats forever."""
    while True:
        now = datetime.now(timezone.utc)
        midnight = datetime.combine(now.date(), dtime(0, 0), tzinfo=timezone.utc)
        if midnight <= now:
            midnight += timedelta(days=1)
        seconds_until = (midnight - now).total_seconds()
        logger.debug("Daily reset in %.0f seconds.", seconds_until)
        await asyncio.sleep(seconds_until)
        logger.info("Daily session reset triggered.")
        # Placeholder — actual reset logic can be added later


async def _run_gateway(ctx: AppContext) -> None:
    """Start the HTTP/WebSocket gateway."""
    import uvicorn

    from polarsclaw.gateway import create_gateway

    app = create_gateway(
        settings=ctx.settings,
        command_queue=ctx.command_queue,
        router=ctx.router,
        session_mgr=ctx.session_manager,
    )

    config = uvicorn.Config(
        app,
        host=ctx.settings.gateway.host,
        port=ctx.settings.gateway.port,
        log_level=ctx.settings.log_level.lower(),
    )
    server = uvicorn.Server(config)
    await server.serve()


async def _run_queue_processor(ctx: AppContext) -> None:
    """Process the command queue, routing messages to agents."""

    async def _handler(session_id: str, request_id: str, message: str) -> str:
        """Route a queued message to the appropriate agent and return the reply."""
        try:
            agent_loop = ctx.router.resolve(
                peer_id=None,
                channel_id=None,
                roles=None,
                account_id=None,
            )
        except Exception:
            # Fallback to first agent
            agent_loop = next(iter(ctx.agents.values()), None)

        if agent_loop is None:
            return "No agent available to handle this request."

        result = await agent_loop.run(session_id=session_id, message=message)
        return result

    await ctx.command_queue.start(_handler)


async def run_daemon(settings: Settings | None = None) -> None:
    """Start the full daemon: gateway + cron + queue processor.

    This is the main entry point for the PolarsClaw daemon. It:
    1. Builds the full application context (wiring all subsystems)
    2. Starts the gateway server
    3. Starts the queue processor
    4. Starts the daily session reset task
    5. Waits for a shutdown signal (SIGTERM/SIGINT)
    6. Performs graceful cleanup
    """
    loop = asyncio.get_running_loop()
    shutdown_event = asyncio.Event()

    def _handle_signal() -> None:
        logger.info("Received shutdown signal.")
        shutdown_event.set()

    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, _handle_signal)

    # ── Build the full application context ─────────────────────────────
    if settings is None:
        settings = Settings()

    ctx = await build_app(settings)
    logger.info("Application context built successfully.")

    # ── Launch background tasks ────────────────────────────────────────
    tasks: list[asyncio.Task] = []
    tasks.append(asyncio.create_task(_run_gateway(ctx), name="gateway"))
    tasks.append(asyncio.create_task(_run_queue_processor(ctx), name="queue-processor"))
    tasks.append(asyncio.create_task(_daily_session_reset(ctx), name="daily-reset"))

    logger.info("Daemon running (gateway=%s:%d). Waiting for shutdown signal...",
                ctx.settings.gateway.host, ctx.settings.gateway.port)

    await shutdown_event.wait()

    # ── Graceful shutdown ──────────────────────────────────────────────
    logger.info("Shutting down daemon...")
    for task in tasks:
        task.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)

    await cleanup_app(ctx)
    logger.info("Daemon stopped cleanly.")
