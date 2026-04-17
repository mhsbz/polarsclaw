"""ContextEngine protocol and default implementation."""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class ContextEngine(Protocol):
    """Protocol that context engines must satisfy.

    A context engine manages ingestion, assembly, and compaction of
    conversational context for agent sessions.
    """

    @property
    def owns_compaction(self) -> bool:
        """Return True if this engine handles compaction itself."""
        ...

    async def ingest(self, content: str, metadata: dict) -> None:
        """Ingest content into the context store."""
        ...

    async def assemble(self, session_id: str) -> str:
        """Assemble context for a session, returning the context string."""
        ...

    async def compact(self, session_id: str) -> str | None:
        """Compact context for a session.

        Returns the compacted summary, or None if compaction is not owned.
        """
        ...


class DefaultContextEngine:
    """Default engine that delegates to DeepAgents SummarizationMiddleware.

    All operations are no-ops because the DeepAgents framework handles
    ingestion, context assembly, and compaction internally.
    """

    @property
    def owns_compaction(self) -> bool:
        return False

    async def ingest(self, content: str, metadata: dict) -> None:
        pass  # no-op; DeepAgents handles ingestion

    async def assemble(self, session_id: str) -> str:
        return ""  # DeepAgents handles context assembly

    async def compact(self, session_id: str) -> str | None:
        return None  # DeepAgents handles compaction
