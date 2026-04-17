"""Memory tools — save, recall, and list memories via the agent."""

from __future__ import annotations

from langchain_core.tools import BaseTool, tool

from polarsclaw.storage.database import Database
from polarsclaw.storage.repositories import MemoryRepo


def make_memory_tools(db: Database) -> list[BaseTool]:
    """Factory that returns memory tools with *db* injected via closure."""

    repo = MemoryRepo(db)

    @tool
    async def save_memory(key: str, value: str, memory_type: str = "general") -> str:
        """Save a key-value memory for later recall.

        Args:
            key: A short, descriptive key for the memory (e.g. "user_name").
            value: The content to remember.
            memory_type: Category — "general", "preference", "fact", etc.
        """
        await repo.save(key, value, type=memory_type)
        return f"Memory saved: {key} = {value!r} (type={memory_type})"

    @tool
    async def recall_memory(query: str, limit: int = 5) -> str:
        """Search memories by full-text query and return the best matches.

        Args:
            query: Search terms to match against stored memories.
            limit: Maximum number of results to return.
        """
        try:
            results = await repo.search(query, limit=limit)
        except Exception:
            # FTS match can fail on empty/invalid query; fall back to list
            results = await repo.list(limit=limit)

        if not results:
            return "No memories found."

        lines = []
        for m in results:
            lines.append(f"- **{m.key}** ({m.type}): {m.value}")
        return "\n".join(lines)

    @tool
    async def list_memories(memory_type: str | None = None, limit: int = 20) -> str:
        """List recent memories, optionally filtered by type.

        Args:
            memory_type: Filter to a specific type (e.g. "general"). None for all.
            limit: Maximum number of memories to return.
        """
        results = await repo.list(type=memory_type, limit=limit)
        if not results:
            return "No memories stored yet."

        lines = []
        for m in results:
            lines.append(f"- **{m.key}** ({m.type}): {m.value}")
        return "\n".join(lines)

    return [save_memory, recall_memory, list_memories]  # type: ignore[list-item]
