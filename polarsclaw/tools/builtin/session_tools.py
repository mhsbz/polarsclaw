"""Session tools — list and switch sessions via the agent."""

from __future__ import annotations

from langchain_core.tools import BaseTool, tool

from polarsclaw.storage.database import Database
from polarsclaw.storage.repositories import SessionRepo


def make_session_tools(db: Database) -> list[BaseTool]:
    """Factory that returns session tools with *db* injected via closure."""

    repo = SessionRepo(db)

    @tool
    async def list_sessions(limit: int = 10) -> str:
        """List recent chat sessions.

        Args:
            limit: Maximum number of sessions to return.
        """
        sessions = await repo.list(limit=limit)
        if not sessions:
            return "No sessions found."

        lines = []
        for s in sessions:
            title = s.get("title") or "(untitled)"
            sid = s["id"]
            updated = s.get("updated_at", "")
            lines.append(f"- `{sid}` — {title} (updated: {updated})")
        return "\n".join(lines)

    @tool
    async def switch_session(session_id: str) -> str:
        """Switch to a different session by ID.

        Note: This signals intent to the agent loop — the actual context switch
        happens at the loop level.

        Args:
            session_id: The session ID to switch to.
        """
        # Validate the session exists
        session = await repo.get(session_id)
        title = session.get("title") or "(untitled)"
        return (
            f"Switching to session `{session_id}` — {title}. "
            "The next message will use this session's context."
        )

    return [list_sessions, switch_session]  # type: ignore[list-item]
