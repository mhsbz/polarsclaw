"""SKILL.md parser — extracts YAML frontmatter + markdown body."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

import yaml

logger = logging.getLogger(__name__)

_FRONTMATTER_SEP = "---"


@dataclass
class SkillEntry:
    """A single parsed skill definition."""

    name: str
    description: str
    triggers: list[str] = field(default_factory=list)
    markdown_path: Path | None = None
    _content: str | None = field(default=None, repr=False)

    @property
    def content(self) -> str:
        """Lazily load markdown body from disk."""
        if self._content is not None:
            return self._content
        if self.markdown_path is None or not self.markdown_path.exists():
            return ""
        raw = self.markdown_path.read_text(encoding="utf-8")
        _, body = _split_frontmatter(raw)
        self._content = body
        return self._content


def _split_frontmatter(text: str) -> tuple[str, str]:
    """Split ``---`` delimited YAML frontmatter from the markdown body.

    Returns (frontmatter_str, body_str). Either may be empty.
    """
    stripped = text.lstrip("\n")
    if not stripped.startswith(_FRONTMATTER_SEP):
        return "", text

    end = stripped.find(_FRONTMATTER_SEP, len(_FRONTMATTER_SEP))
    if end == -1:
        return "", text

    fm = stripped[len(_FRONTMATTER_SEP) : end].strip()
    body = stripped[end + len(_FRONTMATTER_SEP) :].strip()
    return fm, body


def parse_skill_file(path: Path) -> SkillEntry | None:
    """Parse a skill markdown file into a :class:`SkillEntry`.

    Returns ``None`` if the file is invalid or missing required fields.
    """
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as exc:
        logger.warning("Cannot read skill file %s: %s", path, exc)
        return None

    fm_str, body = _split_frontmatter(raw)
    if not fm_str:
        logger.warning("Skill file %s has no YAML frontmatter", path)
        return None

    try:
        meta = yaml.safe_load(fm_str)
    except yaml.YAMLError as exc:
        logger.warning("Invalid YAML in %s: %s", path, exc)
        return None

    if not isinstance(meta, dict):
        logger.warning("Frontmatter in %s is not a mapping", path)
        return None

    name = meta.get("name")
    description = meta.get("description", "")
    if not name:
        logger.warning("Skill file %s missing required 'name' field", path)
        return None

    triggers = meta.get("triggers", [])
    if not isinstance(triggers, list):
        triggers = [str(triggers)]

    return SkillEntry(
        name=str(name),
        description=str(description),
        triggers=[str(t) for t in triggers],
        markdown_path=path,
        _content=body,
    )
