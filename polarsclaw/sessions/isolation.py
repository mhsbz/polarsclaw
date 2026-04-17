"""DM isolation — deterministic session-key generation based on scope."""

from __future__ import annotations

from polarsclaw.types import DMScope


def resolve_session_key(
    agent_id: str,
    peer_id: str | None,
    channel_id: str | None,
    dm_scope: DMScope,
) -> str:
    """Return a deterministic session key for the given scope.

    - ``MAIN``: all conversations share one session per agent.
    - ``PER_PEER``: each peer gets their own session.
    - ``PER_CHANNEL_PEER``: each (channel, peer) pair gets its own session.
    """
    if dm_scope == DMScope.MAIN:
        return f"session:{agent_id}"
    if dm_scope == DMScope.PER_PEER:
        return f"session:{agent_id}:{peer_id or '_'}"
    # PER_CHANNEL_PEER
    return f"session:{agent_id}:{channel_id or '_'}:{peer_id or '_'}"
