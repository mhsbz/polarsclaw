"""LangChain tools that expose MemoryCore to the agent."""

from __future__ import annotations

from typing import TYPE_CHECKING

from langchain_core.tools import BaseTool, tool

if TYPE_CHECKING:
    from polarsclaw.memory import MemoryCore


def make_memory_core_tools(memory_core: MemoryCore) -> list[BaseTool]:
    """Return tools wired to *memory_core*."""

    @tool
    async def memory_search(
        query: str,
        limit: int = 10,
        file_filter: str | None = None,
    ) -> str:
        """Search long-term memory for relevant information.

        Args:
            query: Natural-language search query.
            limit: Max results to return (default 10).
            file_filter: Optional substring to filter file paths.
        """
        results = await memory_core.search(query, limit=limit)
        if not results:
            return "No relevant memories found."

        lines: list[str] = []
        for i, r in enumerate(results, 1):
            snippet = r.content[:300].replace("\n", " ")
            lines.append(
                f"{i}. [{r.file_path}] "
                f"{r.heading or '(no heading)'} "
                f"(score={r.score:.3f})\n   {snippet}"
            )
        return "\n\n".join(lines)

    @tool
    async def memory_get(
        path: str,
        from_line: int | None = None,
        num_lines: int | None = None,
    ) -> str:
        """Read a memory file from the workspace.

        Args:
            path: Relative path to the file (e.g. "MEMORY.md").
            from_line: Optional 1-based start line.
            num_lines: Optional number of lines to return.
        """
        content = await memory_core.get_file(path)
        if content is None:
            return f"File not found: {path}"

        if from_line is not None or num_lines is not None:
            all_lines = content.splitlines()
            start = (from_line or 1) - 1
            end = start + (num_lines or len(all_lines))
            content = "\n".join(all_lines[start:end])

        return content

    return [memory_search, memory_get]  # type: ignore[list-item]
