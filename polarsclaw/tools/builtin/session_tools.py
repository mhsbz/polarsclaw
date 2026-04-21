"""Session tools — list and switch sessions via the agent."""

from __future__ import annotations

from langchain_core.tools import BaseTool, tool

from polarsclaw.sessions.manager import SessionManager


def make_session_tools(session_mgr: SessionManager) -> list[BaseTool]:
    """Factory that returns session tools with *db* injected via closure."""

    @tool
    async def list_sessions(limit: int = 10) -> str:
        """List recent chat sessions.

        Args:
            limit: Maximum number of sessions to return.
        """
        sessions = await session_mgr.list_all(limit=limit)
        if not sessions:
            return "No sessions found."

        lines = []
        for s in sessions:
            title = s.title or "(untitled)"
            sid = s.id
            updated = s.updated_at.isoformat()
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
        session = await session_mgr.resume(session_id)
        title = session.title or "(untitled)"
        return (
            f"Switching to session `{session_id}` — {title}. "
            "The next message will use this session's context."
        )

    return [list_sessions, switch_session]  # type: ignore[list-item]
