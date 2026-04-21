"""Main daemon event loop — starts gateway, cron, and queue processor."""

from __future__ import annotations

import asyncio
import logging
import signal
from datetime import datetime, time as dtime, timedelta, timezone

from polarsclaw.app import AppContext, build_app, cleanup_app
from polarsclaw.config.settings import Settings
from polarsclaw.runtime import dispatch_message

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
        await ctx.session_manager.daily_reset()


async def _run_gateway(ctx: AppContext) -> None:
    """Start the HTTP/WebSocket gateway."""
    import uvicorn

    from polarsclaw.gateway import create_gateway

    app = create_gateway(
        settings=ctx.settings,
        command_queue=ctx.command_queue,
        router=ctx.router,
        session_mgr=ctx.session_manager,
        bridge=ctx.gateway_bridge,
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
        result = await dispatch_message(
            ctx,
            content=message,
            session_id=session_id,
            on_token=lambda chunk: ctx.gateway_bridge.stream(request_id, chunk),
        )
        return result.response

    await ctx.command_queue.start(
        _handler,
        on_done=ctx.gateway_bridge.done,
        on_error=lambda request_id, exc: ctx.gateway_bridge.error(request_id, str(exc)),
    )


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
