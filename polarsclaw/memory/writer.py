"""DailyMemoryWriter — append-only memory log as Markdown files.

Markdown is the source of truth.  The SQLite / mem_chunks table is a
derived shadow index that can be rebuilt at any time from the .md files.
"""

from __future__ import annotations

import hashlib
import logging
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path

from polarsclaw.memory.config import MemoryConfig

logger = logging.getLogger(__name__)

# Role labels that get a styled prefix in the daily log.
_ROLE_PREFIXES: dict[str, str] = {
    "user": "👤",
    "assistant": "🤖",
    "system": "⚙️",
    "tool": "🔧",
}


class DailyMemoryWriter:
    """Appends conversation turns to daily Markdown log files.

    The written .md files are the canonical memory — human-readable,
    git-versionable, and directly editable.  A SHA-256 fingerprint on each
    entry makes de-duplication possible even when humans reorder content.
    """

    def __init__(self, config: MemoryConfig) -> None:
        self._config = config
        self._workspace = config.workspace

    # ── public API ─────────────────────────────────────────────────────────

    async def append(
        self,
        content: str,
        role: str = "assistant",
        session_id: str | None = None,
    ) -> Path:
        """Append a single turn to today's daily log.

        Args:
            content: The text to record.
            role:    Which agent layer produced this turn
                    (user | assistant | system | tool).
            session_id: Optional session identifier for traceability.

        Returns:
            Path to the file that was written.
        """
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        path = self._workspace / "memory" / f"{today}.md"
        path.parent.mkdir(parents=True, exist_ok=True)

        fingerprint = hashlib.sha256(content.encode("utf-8")).hexdigest()[:16]
        role_icon = _ROLE_PREFIXES.get(role, "📝")
        heading = f"## {role_icon} {role.title()} — {today}"

        lines = [
            heading,
            f"<!-- session:{session_id or uuid.uuid4().hex[:8]} -->",
            "",
            content,
            "",
            f"<!-- polarsclaw:fingerprint:{fingerprint} -->",
            "",
        ]

        entry = "\n".join(lines)
        path.write_text(
            path.read_text(encoding="utf-8") + entry,
            encoding="utf-8",
        )

        logger.debug("Appended entry to %s (fingerprint=%s)", path.name, fingerprint)
        return path

    async def append_session_log(
        self,
        exchanges: list[dict[str, str]],
        session_id: str,
        topic: str | None = None,
    ) -> Path:
        """Append a full session transcript as a single daily log entry.

        Args:
            exchanges: List of {"role": str, "content": str} dicts.
            session_id: Unique session identifier.
            topic: Optional topic label (shown as H3 heading).

        Returns:
            Path to the file that was written.
        """
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        path = self._workspace / "memory" / f"{today}.md"
        path.parent.mkdir(parents=True, exist_ok=True)

        fingerprint_inputs = "|".join(e.get("content", "") for e in exchanges)
        fingerprint = hashlib.sha256(fingerprint_inputs.encode("utf-8")).hexdigest()[:16]

        lines = [
            f"## 💬 Session — {today}{f' — {topic}' if topic else ''}",
            f"<!-- session:{session_id} -->",
            "",
        ]
        for ex in exchanges:
            role = ex.get("role", "assistant")
            content = ex.get("content", "")
            icon = _ROLE_PREFIXES.get(role, "📝")
            lines.append(f"**{icon} {role.title()}:** {content}")
            lines.append("")

        lines.append(f"<!-- polarsclaw:fingerprint:{fingerprint} -->")
        lines.append("")

        entry = "\n".join(lines)
        path.write_text(
            path.read_text(encoding="utf-8") + entry,
            encoding="utf-8",
        )

        logger.debug(
            "Appended session log to %s (session=%s, fingerprint=%s)",
            path.name,
            session_id,
            fingerprint,
        )
        return path

    async def read_daily_log(self, date: datetime | None = None) -> str:
        """Return the raw content of a daily log.

        Args:
            date: Defaults to today (UTC).

        Returns:
            Full file content, or "" if the file does not exist.
        """
        date = date or datetime.now(timezone.utc)
        path = self._workspace / "memory" / f"{date.strftime('%Y-%m-%d')}.md"
        if not path.exists():
            return ""
        return path.read_text(encoding="utf-8")

    # ── utility ─────────────────────────────────────────────────────────────

    @staticmethod
    def extract_fingerprints(content: str) -> set[str]:
        """Parse all polarsclaw fingerprints from a .md content string."""
        return set(re.findall(r"<!-- polarsclaw:fingerprint:([a-f0-9]{16}) -->", content))

    @staticmethod
    def extract_session_anchors(content: str) -> list[str]:
        """Return all session IDs mentioned in HTML comments."""
        return re.findall(r"<!-- session:([a-f0-9]+) -->", content)
