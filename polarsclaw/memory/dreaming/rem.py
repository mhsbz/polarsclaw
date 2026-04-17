"""REM sleep — extract key conversation points into daily memory notes."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from polarsclaw.memory.config import MemoryConfig
    from polarsclaw.memory.db import MemoryDB
    from polarsclaw.storage.database import Database

logger = logging.getLogger(__name__)


class REMSleep:
    """Extracts daily session highlights and writes them to memory notes."""

    def __init__(
        self,
        db: MemoryDB,
        session_db: Database,
        config: MemoryConfig,
    ) -> None:
        self._db = db
        self._session_db = session_db
        self._config = config

    async def run(self, date: str | None = None) -> Path | None:
        """Extract conversation highlights and write daily notes.

        Args:
            date: Date string in YYYY-MM-DD format. Defaults to today.

        Returns:
            Path to the daily note, or None if no messages found.
        """
        if date is None:
            date = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        # 1. Query today's messages
        conn = self._session_db.get_connection()
        async with conn.execute(
            "SELECT * FROM messages WHERE date(timestamp) = ? ORDER BY timestamp",
            (date,),
        ) as cursor:
            rows = await cursor.fetchall()

        if not rows:
            logger.info("No messages found for %s, skipping REM sleep.", date)
            return None

        # 2. Group messages by session and extract key points
        sessions: dict[str, list[dict[str, Any]]] = {}
        for row in rows:
            sid = row["session_id"]
            sessions.setdefault(sid, []).append(dict(row))

        key_points: list[str] = []
        for session_id, messages in sessions.items():
            session_points = self._extract_session_points(session_id, messages)
            key_points.extend(session_points)

        if not key_points:
            logger.info("No key points extracted for %s.", date)
            return None

        # 3. Write daily note
        workspace = self._config.workspace
        memory_dir = workspace / "memory"
        memory_dir.mkdir(parents=True, exist_ok=True)
        daily_note_path = memory_dir / f"{date}.md"

        section = self._format_session_notes(date, key_points)

        if daily_note_path.exists():
            existing = daily_note_path.read_text(encoding="utf-8")
            if "## Session Notes" not in existing:
                content = existing.rstrip() + "\n\n" + section
            else:
                # Append new points under existing section
                content = existing.rstrip() + "\n" + "\n".join(
                    f"- {p}" for p in key_points
                ) + "\n"
        else:
            content = f"# Daily Notes — {date}\n\n{section}"

        daily_note_path.write_text(content, encoding="utf-8")

        # 4. Write cross-reference report
        rem_report_dir = workspace / "memory" / "dreaming" / "rem"
        rem_report_dir.mkdir(parents=True, exist_ok=True)
        rem_report_path = rem_report_dir / f"{date}.md"

        report_lines = [
            f"# REM Sleep Report — {date}",
            "",
            f"- **Sessions processed:** {len(sessions)}",
            f"- **Key points extracted:** {len(key_points)}",
            f"- **Daily note:** `{daily_note_path}`",
            "",
            "## Sessions",
            "",
        ]
        for sid in sessions:
            report_lines.append(f"- `{sid}` ({len(sessions[sid])} messages)")
        report_lines.append("")
        report_lines.append("## Key Points")
        report_lines.append("")
        for point in key_points:
            report_lines.append(f"- {point}")
        report_lines.append("")

        rem_report_path.write_text("\n".join(report_lines), encoding="utf-8")

        logger.info(
            "REM sleep complete: %d sessions, %d points, daily note at %s",
            len(sessions),
            len(key_points),
            daily_note_path,
        )
        return daily_note_path

    def _extract_session_points(
        self, session_id: str, messages: list[dict[str, Any]]
    ) -> list[str]:
        """Extract key conversation points from a session's messages.

        Takes user messages and the last assistant response per exchange
        to capture the essence of each interaction.
        """
        points: list[str] = []
        i = 0
        while i < len(messages):
            msg = messages[i]
            if msg["role"] == "user":
                user_content = msg["content"].strip()
                # Truncate long messages
                if len(user_content) > 200:
                    user_content = user_content[:200] + "…"

                # Find the last assistant reply before the next user message
                assistant_reply = None
                j = i + 1
                while j < len(messages) and messages[j]["role"] != "user":
                    if messages[j]["role"] == "assistant":
                        assistant_reply = messages[j]["content"].strip()
                    j += 1

                point = f"[{session_id[:8]}] Q: {user_content}"
                if assistant_reply:
                    summary = assistant_reply[:150]
                    if len(assistant_reply) > 150:
                        summary += "…"
                    point += f" → A: {summary}"
                points.append(point)
                i = j
            else:
                i += 1
        return points

    @staticmethod
    def _format_session_notes(date: str, key_points: list[str]) -> str:
        """Format key points as a markdown section."""
        lines = ["## Session Notes", ""]
        for point in key_points:
            lines.append(f"- {point}")
        lines.append("")
        return "\n".join(lines)
