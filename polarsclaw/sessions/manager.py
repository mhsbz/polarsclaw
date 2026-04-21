"""SessionManager — create, resume, and resolve sessions."""

from __future__ import annotations

import json
from datetime import datetime

from polarsclaw.errors import RecordNotFoundError
from polarsclaw.sessions.isolation import resolve_session_key
from polarsclaw.sessions.models import Session
from polarsclaw.storage.database import Database
from polarsclaw.storage.repositories import SessionRepo
from polarsclaw.types import DMScope


class SessionManager:
    """High-level session lifecycle management."""

    def __init__(self, db: Database, dm_scope: DMScope = DMScope.MAIN) -> None:
        self._db = db
        self._repo = SessionRepo(db)
        self._dm_scope = dm_scope
        # Cache: session_key -> session_id (avoids repeated DB lookups)
        self._key_cache: dict[str, str] = {}

    async def create(
        self,
        agent_id: str,
        *,
        session_id: str | None = None,
        peer_id: str | None = None,
        channel_id: str | None = None,
        title: str | None = None,
    ) -> Session:
        """Create a brand-new session."""
        scope = resolve_session_key(agent_id, peer_id, channel_id, self._dm_scope)
        session_id = await self._repo.create(
            session_id=session_id,
            title=title,
            scope=scope,
            peer_id=peer_id,
            channel_id=channel_id,
        )
        row = await self._repo.get(session_id)
        session = _row_to_session(row)
        self._key_cache[scope] = session.id
        return session

    async def resume(self, session_id: str) -> Session:
        """Resume an existing session by ID.

        Raises :class:`RecordNotFoundError` if the session doesn't exist.
        """
        row = await self._repo.get(session_id)
        return _row_to_session(row)

    async def resolve(
        self,
        agent_id: str,
        *,
        peer_id: str | None = None,
        channel_id: str | None = None,
    ) -> Session:
        """Create-or-resume a session based on the current DM scope.

        If a session already exists for the computed key, resume it.
        Otherwise, create a new one.
        """
        key = resolve_session_key(agent_id, peer_id, channel_id, self._dm_scope)

        # Fast path: cached
        if key in self._key_cache:
            try:
                return await self.resume(self._key_cache[key])
            except RecordNotFoundError:
                del self._key_cache[key]

        # Slow path: search by scope
        existing = await self._repo.list(scope=key, limit=1)
        if existing:
            session = _row_to_session(existing[0])
            self._key_cache[key] = session.id
            return session

        # Nothing found — create
        return await self.create(agent_id, peer_id=peer_id, channel_id=channel_id)

    async def create_with_id(
        self,
        session_id: str,
        agent_id: str,
        *,
        peer_id: str | None = None,
        channel_id: str | None = None,
        title: str | None = None,
    ) -> Session:
        """Create a session with an explicit ID for external callers."""
        return await self.create(
            agent_id,
            session_id=session_id,
            peer_id=peer_id,
            channel_id=channel_id,
            title=title,
        )

    async def list_all(
        self,
        *,
        scope: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Session]:
        """List sessions as typed models."""
        rows = await self._repo.list(scope=scope, limit=limit, offset=offset)
        return [_row_to_session(row) for row in rows]

    async def daily_reset(self) -> int:
        """Archive (delete) sessions that haven't been updated today.

        Returns the number of sessions archived.
        """
        db = self._db.get_connection()
        today = datetime.utcnow().strftime("%Y-%m-%d")
        async with db.execute(
            "SELECT id FROM sessions WHERE updated_at < ?", (today,)
        ) as cursor:
            rows = await cursor.fetchall()

        count = 0
        for row in rows:
            await self._repo.delete(row["id"])
            count += 1

        # Clear cache since sessions may have been removed
        self._key_cache.clear()
        return count


def _row_to_session(row: dict) -> Session:
    """Convert a raw DB row dict to a Session model."""
    metadata = row.get("metadata", "{}")
    if isinstance(metadata, str):
        metadata = json.loads(metadata)
    return Session(
        id=row["id"],
        title=row.get("title"),
        scope=row.get("scope", "main"),
        peer_id=row.get("peer_id"),
        channel_id=row.get("channel_id"),
        metadata=metadata,
        created_at=datetime.fromisoformat(row["created_at"]),
        updated_at=datetime.fromisoformat(row["updated_at"]),
    )
