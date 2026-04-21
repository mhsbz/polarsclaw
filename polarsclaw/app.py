"""Application context factory — wires all subsystems."""

from __future__ import annotations

import logging
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from polarsclaw.agents.loop import AgentLoop
from polarsclaw.config.settings import AgentConfig, Settings
from polarsclaw.context.registry import ContextEngineRegistry
from polarsclaw.cron.scheduler import CronScheduler
from polarsclaw.gateway.bridge import GatewayBridge
from polarsclaw.plugins.api import PluginAPI
from polarsclaw.plugins.loader import PluginLoader
from polarsclaw.queue.command_queue import CommandQueue
from polarsclaw.runtime import build_agent_factory, resolve_dm_scope
from polarsclaw.routing.bindings import Binding
from polarsclaw.routing.router import MultiAgentRouter
from polarsclaw.sessions.manager import SessionManager
from polarsclaw.skills.registry import SkillRegistry
from polarsclaw.storage.database import Database
from polarsclaw.storage.repositories import MessageRepo
from polarsclaw.tools.registry import ToolRegistry

logger = logging.getLogger(__name__)


@dataclass
class AppContext:
    """Central application context holding all initialised subsystems."""

    settings: Settings
    db: Database
    tool_registry: ToolRegistry
    skill_registry: SkillRegistry
    session_manager: SessionManager
    message_repo: MessageRepo
    cron_scheduler: CronScheduler
    command_queue: CommandQueue
    router: MultiAgentRouter
    plugin_loader: PluginLoader
    plugin_api: PluginAPI
    context_registry: ContextEngineRegistry
    gateway_bridge: GatewayBridge
    checkpoint_conn: sqlite3.Connection | None = None
    checkpointer: Any = None
    memory_core: Any = None  # MemoryCore instance (optional)
    agents: dict[str, AgentLoop] = field(default_factory=dict)


async def build_app(settings: Settings | None = None) -> AppContext:
    """Build and wire all application components.

    Steps:
    1. Load settings
    2. Init DB
    3. Init context engine registry with default
    4. Init plugin system (loader + API)
    5. Load plugins (they register tools / context engines)
    6. Init tool registry with built-in groups + memory/session/cron tools
    7. Init skill registry
    8. Init session manager
    9. Init cron scheduler
    10. Create agents from config (one per agents list entry)
    11. Init multi-agent router with bindings
    12. Init command queue
    13. Return AppContext
    """
    # ── 1. Settings ────────────────────────────────────────────────────
    if settings is None:
        settings = Settings()

    # ── 2. Database ────────────────────────────────────────────────────
    db = Database(settings.db_path)
    await db.initialize()
    logger.info("Database initialised at %s", settings.db_path)

    # ── 3. Context engine registry ─────────────────────────────────────
    context_registry = ContextEngineRegistry()

    # ── 4. Tool registry (empty — plugins and built-ins populate it) ──
    tool_registry = ToolRegistry()

    # ── 5. Plugin system ───────────────────────────────────────────────
    plugin_loader = PluginLoader(settings)
    plugin_api = PluginAPI(tool_registry, context_registry)
    plugin_loader.discover()
    plugin_loader.load_all(plugin_api)

    # ── 6. Register built-in tools ─────────────────────────────────────
    cron_scheduler = CronScheduler(
        db,
        timezone=settings.cron.timezone,
        max_concurrent=settings.cron.max_concurrent,
        default_timeout=settings.cron.default_timeout,
    )

    # Session manager needs to exist before tools reference it
    session_manager = SessionManager(db, dm_scope=resolve_dm_scope(settings.dm_scope))
    message_repo = MessageRepo(db)

    from polarsclaw.tools.builtin import register_all_builtin_tools

    register_all_builtin_tools(
        registry=tool_registry,
        db=db,
        scheduler=cron_scheduler,
        session_mgr=session_manager,
    )

    # ── 7. Skill registry ─────────────────────────────────────────────
    skills_dir = settings.config_dir / "skills"
    skill_registry = SkillRegistry(skills_dir, settings)
    skill_registry.discover()

    # ── 8. (Session manager already created above) ─────────────────────

    # ── 9. Start cron scheduler ────────────────────────────────────────
    await cron_scheduler.start()
    logger.info("Cron scheduler started (tz=%s)", settings.cron.timezone)

    # ── 9.5. Memory subsystem ─────────────────────────────────────────
    memory_core = None
    try:
        from polarsclaw.memory import MemoryCore
        from polarsclaw.memory.config import MemoryConfig

        if isinstance(settings.memory, MemoryConfig):
            mem_cfg = settings.memory
        elif isinstance(settings.memory, dict):
            mem_cfg = MemoryConfig.model_validate(settings.memory)
            if mem_cfg.workspace == Path("."):
                mem_cfg.workspace = Path.cwd()
        else:
            mem_cfg = MemoryConfig(workspace=Path.cwd())
        memory_core = MemoryCore(db=db, config=mem_cfg)
        await memory_core.initialize()
        # Register memory tools with the tool registry
        for mem_tool in memory_core.get_tools():
            tool_registry.register(mem_tool)
        # Register dreaming cron jobs
        await memory_core.register_jobs(cron_scheduler)
        logger.info("Memory subsystem initialised (embedding=%s)", mem_cfg.embedding_provider)
    except Exception:
        logger.warning("Memory subsystem failed to initialise — running without it", exc_info=True)
        memory_core = None

    # ── 10. Create agents from config ──────────────────────────────────
    agents: dict[str, AgentLoop] = {}

    agents_config: list[AgentConfig] = getattr(settings, "agents", []) or []
    if not agents_config:
        # No per-agent list in settings — create a single default agent
        agents_config = [settings.agent]

    from polarsclaw.agents.factory import create_agent

    checkpoint_conn: sqlite3.Connection | None = None
    try:
        from langgraph.checkpoint.sqlite import SqliteSaver

        checkpoint_path = settings.config_dir / "checkpoints.db"
        checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
        checkpoint_conn = sqlite3.connect(str(checkpoint_path), check_same_thread=False)
        checkpointer = SqliteSaver(checkpoint_conn)
    except ImportError:
        checkpointer = None  # type: ignore[assignment]

    default_context_engine = context_registry.default()

    for idx, agent_cfg in enumerate(agents_config):
        agent_id = getattr(agent_cfg, "id", None) or f"agent-{idx}"
        agent_loop = await create_agent(
            agent_config=agent_cfg,
            tool_registry=tool_registry,
            skill_registry=skill_registry,
            checkpointer=checkpointer,
            settings=settings,
            context_engine=default_context_engine,
        )
        agents[agent_id] = agent_loop
        logger.info("Created agent '%s' (model=%s)", agent_id, agent_cfg.model)

    # ── 11. Multi-agent router ─────────────────────────────────────────
    bindings: list[Binding] = []
    raw_bindings: list[Any] = getattr(settings, "bindings", []) or []
    for raw in raw_bindings:
        if isinstance(raw, Binding):
            bindings.append(raw)
        elif isinstance(raw, dict):
            bindings.append(Binding(**raw))

    default_agent_id = next(iter(agents), None)
    router = MultiAgentRouter(
        agents=agents,
        bindings=bindings,
        default_agent=default_agent_id,
    )

    # ── 12. Command queue ──────────────────────────────────────────────
    command_queue = CommandQueue(
        max_concurrency=settings.cron.max_concurrent,
        max_pending=settings.queue.max_pending,
        collect_window_ms=int(settings.queue.collect_window * 1000),
    )
    gateway_bridge = GatewayBridge()

    ctx = AppContext(
        settings=settings,
        db=db,
        tool_registry=tool_registry,
        skill_registry=skill_registry,
        session_manager=session_manager,
        message_repo=message_repo,
        cron_scheduler=cron_scheduler,
        command_queue=command_queue,
        router=router,
        plugin_loader=plugin_loader,
        plugin_api=plugin_api,
        context_registry=context_registry,
        gateway_bridge=gateway_bridge,
        checkpoint_conn=checkpoint_conn,
        checkpointer=checkpointer,
        memory_core=memory_core,
        agents=agents,
    )
    cron_scheduler.set_agent_factory(build_agent_factory(ctx))

    # ── 13. Assemble context ───────────────────────────────────────────
    logger.info(
        "Application wired: %d agent(s), %d tool(s), %d plugin(s)",
        len(agents),
        len(tool_registry.list_all()),
        len(plugin_loader.states),
    )

    return ctx


async def cleanup_app(ctx: AppContext) -> None:
    """Clean up application resources."""
    logger.info("Cleaning up application resources...")

    # Shutdown memory subsystem
    if ctx.memory_core is not None:
        try:
            await ctx.memory_core.shutdown()
        except Exception:
            logger.warning("Error shutting down memory subsystem", exc_info=True)

    # Stop cron scheduler
    try:
        await ctx.cron_scheduler.stop()
    except Exception:
        logger.warning("Error stopping cron scheduler", exc_info=True)

    # Stop command queue
    try:
        await ctx.command_queue.stop()
    except Exception:
        logger.warning("Error stopping command queue", exc_info=True)

    # Close database
    try:
        await ctx.db.close()
    except Exception:
        logger.warning("Error closing database", exc_info=True)

    if ctx.checkpoint_conn is not None:
        try:
            ctx.checkpoint_conn.close()
        except Exception:
            logger.warning("Error closing checkpoint connection", exc_info=True)

    logger.info("Cleanup complete.")
