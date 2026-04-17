"""Agent execution loop wrapping DeepAgents create_deep_agent()."""

from __future__ import annotations

import asyncio
import logging
from typing import Any, AsyncIterator, Awaitable, Callable, TYPE_CHECKING

from langchain_core.messages import HumanMessage
from langchain_core.tools import BaseTool
from langgraph.checkpoint.base import BaseCheckpointSaver

from polarsclaw.agents.streaming import StreamAdapter

if TYPE_CHECKING:
    from polarsclaw.config.settings import AgentConfig, Settings
    from polarsclaw.context.engine import ContextEngine

logger = logging.getLogger(__name__)


class AgentLoop:
    """Manages a single agent's lifecycle: build, run, stream, cancel."""

    def __init__(
        self,
        agent_config: "AgentConfig",
        tools: list[BaseTool],
        checkpointer: BaseCheckpointSaver,
        settings: "Settings",
        context_engine: "ContextEngine | None" = None,
    ) -> None:
        self._config = agent_config
        self._tools = tools
        self._checkpointer = checkpointer
        self._settings = settings
        self._context_engine = context_engine
        self._graph: Any = None
        self._current_task: asyncio.Task[Any] | None = None

    # ------------------------------------------------------------------
    # Build
    # ------------------------------------------------------------------

    async def build(self) -> None:
        """Build the agent graph using DeepAgents.

        Configures:
        - ``LocalShellBackend`` for real filesystem + shell access
        - ``skills`` from ``~/.polarsclaw/skills/`` and agent config
        - ``memory`` from ``AGENTS.md`` files in workspace / config dir
        - Optional compaction middleware from the context engine
        """
        from pathlib import Path

        from deepagents import (  # type: ignore[import-untyped]
            FilesystemPermission,
            SubAgent,
            create_deep_agent,
        )
        from deepagents.backends import LocalShellBackend  # type: ignore[import-untyped]

        from polarsclaw.agents.providers import resolve_model

        llm = resolve_model(
            self._config.model,
            self._settings,
            temperature=self._config.temperature,
            max_tokens=self._config.max_tokens,
        )

        system_prompt = self._config.system_prompt or ""

        # ---- Backend: real filesystem + shell ----------------------------
        workspace = self._config.workspace or Path.cwd()
        backend = LocalShellBackend(
            root_dir=str(workspace),
            virtual_mode=False,
            inherit_env=True,
            timeout=self._config.timeout,
        )

        # ---- Skills: discover from config dir + agent config -------------
        skill_sources: list[str] = []
        # Default skill directory
        default_skill_dir = Path.home() / ".agents" / "skills"
        if default_skill_dir.is_dir():
            skill_sources.append(str(default_skill_dir))
        # Additional skill dirs from agent config
        for s in self._config.skills:
            p = Path(s).expanduser()
            if p.is_dir():
                skill_sources.append(str(p))

        # ---- Memory: AGENTS.md files ------------------------------------
        memory_sources: list[str] = []
        # Workspace AGENTS.md
        workspace_agents = Path(workspace) / "AGENTS.md"
        if workspace_agents.is_file():
            memory_sources.append(str(workspace_agents))
        # Config dir AGENTS.md
        config_agents = self._settings.config_dir / "AGENTS.md"
        if config_agents.is_file():
            memory_sources.append(str(config_agents))

        # ---- Compaction middleware from context engine --------------------
        compaction_middleware: Any = None
        if (
            self._context_engine is not None
            and getattr(self._context_engine, "owns_compaction", False)
        ):
            compaction_middleware = getattr(
                self._context_engine, "compaction_middleware", None
            )

        # ---- Sub-agents from config --------------------------------------
        subagents: list[dict[str, Any]] = []
        for sa_cfg in self._config.subagents:
            sa: dict[str, Any] = {
                "name": sa_cfg.name,
                "description": sa_cfg.description,
                "system_prompt": sa_cfg.system_prompt,
            }
            if sa_cfg.model:
                sa["model"] = resolve_model(
                    sa_cfg.model, self._settings,
                    temperature=self._config.temperature,
                    max_tokens=self._config.max_tokens,
                )
            if sa_cfg.skills:
                sa["skills"] = [
                    str(Path(s).expanduser()) for s in sa_cfg.skills
                    if Path(s).expanduser().is_dir()
                ]
            subagents.append(sa)

        # ---- Filesystem permissions --------------------------------------
        # NOTE: DeepAgents permissions are incompatible with LocalShellBackend
        # (SandboxBackendProtocol). Only apply when using FilesystemBackend.
        permissions: list[FilesystemPermission] = []
        if not hasattr(backend, "execute"):
            for perm_cfg in self._config.permissions:
                permissions.append(FilesystemPermission(
                    operations=perm_cfg.operations,  # type: ignore[arg-type]
                    paths=perm_cfg.paths,
                    mode=perm_cfg.mode,  # type: ignore[arg-type]
                ))
        elif self._config.permissions:
            logger.debug(
                "Skipping filesystem permissions — incompatible with shell-enabled backend"
            )

        # ---- Cache (SQLite-backed via LangGraph) -------------------------
        cache: Any = None
        try:
            from langgraph.cache.sqlite import SqliteCache  # type: ignore[import-untyped]
            cache_path = self._settings.config_dir / "cache.db"
            cache = SqliteCache(path=str(cache_path))
        except ImportError:
            logger.debug("SqliteCache not available, running without cache")

        # ---- Build -------------------------------------------------------
        builder_kwargs: dict[str, Any] = {
            "model": llm,
            "tools": self._tools,
            "checkpointer": self._checkpointer,
            "backend": backend,
            "name": self._config.id,
        }
        if system_prompt:
            builder_kwargs["system_prompt"] = system_prompt
        if skill_sources:
            builder_kwargs["skills"] = skill_sources
        if memory_sources:
            builder_kwargs["memory"] = memory_sources
        if subagents:
            builder_kwargs["subagents"] = subagents
        if permissions:
            builder_kwargs["permissions"] = permissions
        if cache is not None:
            builder_kwargs["cache"] = cache
        if compaction_middleware is not None:
            builder_kwargs["middleware"] = [compaction_middleware]

        self._graph = create_deep_agent(**builder_kwargs)
        logger.info(
            "AgentLoop built with DeepAgents (model=%s, backend=%s, skills=%d, memory=%d, subagents=%d)",
            self._config.model, workspace, len(skill_sources), len(memory_sources), len(subagents),
        )

    # ------------------------------------------------------------------
    # Run
    # ------------------------------------------------------------------

    async def run(
        self,
        message: str,
        session_id: str,
        on_token: Callable[[str], Awaitable[None]] | None = None,
    ) -> str:
        """Run the agent with *message* and return the final text response.

        Parameters
        ----------
        message:
            The user message to send to the agent.
        session_id:
            Thread / session identifier for checkpoint persistence.
        on_token:
            Optional async callback invoked for each streamed token (useful for
            live UIs even when the caller only needs the final answer).

        Raises
        ------
        polarsclaw.errors.AgentTimeoutError
            If the agent does not respond within ``agent_config.timeout`` seconds.
        RuntimeError
            If :meth:`build` has not been called yet.
        """
        if self._graph is None:
            raise RuntimeError("AgentLoop.build() must be called before run()")

        from polarsclaw.errors import AgentTimeoutError

        config = self._make_config(session_id)
        inputs = {"messages": [HumanMessage(content=message)]}

        timeout = self._config.timeout

        async def _invoke() -> str:
            if on_token is not None:
                # Stream internally so we can fire the callback, but still
                # collect the full answer.
                collected: list[str] = []
                async for token in self._stream_tokens(inputs, config):
                    collected.append(token)
                    await on_token(token)
                return "".join(collected)

            result = await self._graph.ainvoke(inputs, config=config)
            return self._extract_response(result)

        loop = asyncio.get_running_loop()
        self._current_task = loop.create_task(_invoke())

        try:
            if timeout and timeout > 0:
                return await asyncio.wait_for(self._current_task, timeout=timeout)
            return await self._current_task
        except asyncio.TimeoutError:
            self._current_task.cancel()
            raise AgentTimeoutError(
                f"Agent did not respond within {timeout}s (session={session_id})"
            )
        finally:
            self._current_task = None

    # ------------------------------------------------------------------
    # Stream
    # ------------------------------------------------------------------

    async def stream(self, message: str, session_id: str) -> AsyncIterator[str]:
        """Yield response tokens as they are produced by the agent."""
        if self._graph is None:
            raise RuntimeError("AgentLoop.build() must be called before stream()")

        from polarsclaw.errors import AgentTimeoutError

        config = self._make_config(session_id)
        inputs = {"messages": [HumanMessage(content=message)]}
        timeout = self._config.timeout

        start = asyncio.get_event_loop().time()
        async for token in self._stream_tokens(inputs, config):
            if timeout and timeout > 0:
                elapsed = asyncio.get_event_loop().time() - start
                if elapsed > timeout:
                    raise AgentTimeoutError(
                        f"Agent stream exceeded {timeout}s (session={session_id})"
                    )
            yield token

    # ------------------------------------------------------------------
    # Cancel
    # ------------------------------------------------------------------

    async def cancel(self) -> None:
        """Cancel the currently running task, if any."""
        if self._current_task is not None and not self._current_task.done():
            self._current_task.cancel()
            try:
                await self._current_task
            except (asyncio.CancelledError, Exception):
                pass
            finally:
                self._current_task = None
            logger.info("AgentLoop run cancelled")

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _make_config(self, session_id: str) -> dict[str, Any]:
        """Build the LangGraph invocation config."""
        return {
            "configurable": {"thread_id": session_id},
        }

    async def _stream_tokens(
        self,
        inputs: dict[str, Any],
        config: dict[str, Any],
    ) -> AsyncIterator[str]:
        """Stream tokens from DeepAgents."""
        raw_stream = self._graph.astream_events(inputs, config=config, version="v2")
        async for token in StreamAdapter.adapt(raw_stream):
            yield token

    @staticmethod
    def _extract_response(result: dict[str, Any]) -> str:
        """Pull the final assistant text from an invoke result."""
        messages = result.get("messages", [])
        if not messages:
            return ""
        last = messages[-1]
        content = getattr(last, "content", "")
        if isinstance(content, str):
            return content
        # Handle list-of-blocks format
        if isinstance(content, list):
            parts: list[str] = []
            for block in content:
                if isinstance(block, str):
                    parts.append(block)
                elif isinstance(block, dict) and block.get("type") == "text":
                    parts.append(block.get("text", ""))
            return "".join(parts)
        return str(content)
