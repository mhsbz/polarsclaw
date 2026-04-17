"""SkillRegistry — discover, match, and list skills from a directory."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING

from polarsclaw.skills.matcher import match_triggers
from polarsclaw.skills.parser import SkillEntry, parse_skill_file

if TYPE_CHECKING:
    from polarsclaw.config.settings import Settings

logger = logging.getLogger(__name__)


class SkillRegistry:
    """Discovers ``.md`` skill files and matches user messages to skills."""

    def __init__(self, skills_dir: Path, settings: "Settings") -> None:
        self._skills_dir = skills_dir
        self._threshold = settings.skill_match_threshold
        self._skills: list[SkillEntry] = []

    # ── Public API ──────────────────────────────────────────────────────

    def discover(self) -> None:
        """Scan *skills_dir* for ``.md`` files and parse each one.

        Re-reads disk every call (no caching) so hot-added skills are picked up.
        """
        self._skills.clear()
        if not self._skills_dir.is_dir():
            logger.debug("Skills directory does not exist: %s", self._skills_dir)
            return

        for md_path in sorted(self._skills_dir.glob("*.md")):
            entry = parse_skill_file(md_path)
            if entry is not None:
                self._skills.append(entry)

        logger.info("Discovered %d skill(s) in %s", len(self._skills), self._skills_dir)

    def match(self, message: str) -> SkillEntry | None:
        """Find the best matching skill for *message*.

        Returns ``None`` if no skill scores above the configured threshold.
        """
        self.discover()

        best_entry: SkillEntry | None = None
        best_score = 0.0

        for skill in self._skills:
            score = match_triggers(message, skill.triggers, self._threshold)
            if score > best_score:
                best_score = score
                best_entry = skill

        if best_score >= self._threshold:
            logger.debug(
                "Matched skill '%s' (score=%.2f) for message: %s",
                best_entry.name if best_entry else "?",
                best_score,
                message[:80],
            )
            return best_entry

        return None

    def list(self) -> list[SkillEntry]:
        """Return all discovered skills (re-scans disk)."""
        self.discover()
        return list(self._skills)

    def get(self, name: str) -> SkillEntry | None:
        """Look up a skill by *name* (re-scans disk)."""
        self.discover()
        for skill in self._skills:
            if skill.name == name:
                return skill
        return None
