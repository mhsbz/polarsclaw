"""Agent execution loop wrapping DeepAgents create_deep_agent()."""

from __future__ import annotations

import asyncio
import logging
from typing import Any, AsyncIterator, Awaitable, Callable, TYPE_CHECKING

from langchain_core.messages import HumanMessage, SystemMessage
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
        self._using_deep_agent: bool = False

    # ------------------------------------------------------------------
    # Build
    # ------------------------------------------------------------------

    async def build(self) -> None:
        """Build the agent graph.

        Strategy:
        1. Try ``deepagents.create_deep_agent`` for the full-featured path.
        2. Fall back to ``langgraph.prebuilt.create_react_agent`` if the
           deepagents package is not installed.

        When *context_engine* is present and ``owns_compaction`` is set,
        the compaction middleware is composed into the graph so the context
        engine controls token-window management instead of the agent runtime.
        """
        from polarsclaw.agents.providers import resolve_model

        llm = resolve_model(
            self._config.model,
            self._settings,
            temperature=self._config.temperature,
            max_tokens=self._config.max_tokens,
        )

        system_prompt = self._config.system_prompt or ""

        # Optionally attach compaction middleware from the context engine
        compaction_middleware: Any = None
        if (
            self._context_engine is not None
            and getattr(self._context_engine, "owns_compaction", False)
        ):
            compaction_middleware = getattr(
                self._context_engine, "compaction_middleware", None
            )

        # ----- primary path: DeepAgents ------------------------------------
        try:
            from deepagents import create_deep_agent  # type: ignore[import-untyped]

            builder_kwargs: dict[str, Any] = {
                "model": llm,
                "tools": self._tools,
                "checkpointer": self._checkpointer,
            }
            if system_prompt:
                builder_kwargs["system_prompt"] = system_prompt
            if compaction_middleware is not None:
                builder_kwargs["middleware"] = [compaction_middleware]

            self._graph = create_deep_agent(**builder_kwargs)
            self._using_deep_agent = True
            logger.info("AgentLoop built with DeepAgents (model=%s)", self._config.model)
            return

        except ImportError:
            logger.debug("deepagents not installed — falling back to LangGraph react agent")

        # ----- fallback path: LangGraph react agent ------------------------
        from langgraph.prebuilt import create_react_agent

        builder_kwargs = {
            "model": llm,
            "tools": self._tools,
            "checkpointer": self._checkpointer,
        }
        if system_prompt:
            builder_kwargs["prompt"] = system_prompt

        self._graph = create_react_agent(**builder_kwargs)
        self._using_deep_agent = False
        logger.info("AgentLoop built with LangGraph react agent (model=%s)", self._config.model)

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
        """Unified token streaming across DeepAgents and LangGraph backends."""
        if self._using_deep_agent:
            raw_stream = self._graph.astream_events(inputs, config=config, version="v2")
            async for token in StreamAdapter.adapt(raw_stream):
                yield token
        else:
            # LangGraph react agent: astream_events v2
            async for event in self._graph.astream_events(inputs, config=config, version="v2"):
                kind = event.get("event", "")
                if kind == "on_chat_model_stream":
                    chunk = event.get("data", {}).get("chunk")
                    if chunk is not None:
                        text = getattr(chunk, "content", "")
                        if isinstance(text, str) and text:
                            yield text

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
