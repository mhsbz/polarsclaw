"""Tests for polarsclaw.skills (parser, matcher, registry)."""

from __future__ import annotations

from pathlib import Path

import pytest

from polarsclaw.config.settings import Settings
from polarsclaw.skills.matcher import match_triggers
from polarsclaw.skills.parser import SkillEntry, parse_skill_file
from polarsclaw.skills.registry import SkillRegistry


VALID_SKILL_MD = """\
---
name: greeting
description: Greet the user
triggers:
  - hello
  - hi there
---
# Greeting Skill

Say hello to the user.
"""

NO_NAME_SKILL_MD = """\
---
description: Missing name
triggers:
  - test
---
Body
"""

NO_FRONTMATTER_MD = """\
# Just markdown
No YAML frontmatter here.
"""

MALFORMED_YAML_MD = """\
---
name: [invalid
  yaml: {{
---
Body
"""


class TestParseSkillFile:
    def test_valid(self, tmp_path: Path) -> None:
        p = tmp_path / "greeting.md"
        p.write_text(VALID_SKILL_MD)
        entry = parse_skill_file(p)
        assert entry is not None
        assert entry.name == "greeting"
        assert entry.description == "Greet the user"
        assert "hello" in entry.triggers
        assert "Say hello" in entry.content

    def test_missing_name(self, tmp_path: Path) -> None:
        p = tmp_path / "noname.md"
        p.write_text(NO_NAME_SKILL_MD)
        assert parse_skill_file(p) is None

    def test_no_frontmatter(self, tmp_path: Path) -> None:
        p = tmp_path / "plain.md"
        p.write_text(NO_FRONTMATTER_MD)
        assert parse_skill_file(p) is None

    def test_malformed_yaml(self, tmp_path: Path) -> None:
        p = tmp_path / "bad.md"
        p.write_text(MALFORMED_YAML_MD)
        assert parse_skill_file(p) is None

    def test_nonexistent_file(self, tmp_path: Path) -> None:
        assert parse_skill_file(tmp_path / "nope.md") is None


class TestMatchTriggers:
    def test_exact_match(self) -> None:
        assert match_triggers("hello", ["hello"]) == 1.0

    def test_exact_match_case_insensitive(self) -> None:
        assert match_triggers("HELLO", ["hello"]) == 1.0

    def test_substring_match(self) -> None:
        assert match_triggers("say hello world", ["hello"]) == 0.8

    def test_partial_word_overlap(self) -> None:
        score = match_triggers("check the weather today", ["check weather"])
        assert 0.5 <= score <= 0.7

    def test_no_match(self) -> None:
        assert match_triggers("something else", ["hello", "world"]) == 0.0

    def test_empty_triggers(self) -> None:
        assert match_triggers("hello", []) == 0.0

    def test_best_score_wins(self) -> None:
        score = match_triggers("hello", ["hello", "hi"])
        assert score == 1.0


class TestSkillRegistry:
    def _write_skill(self, d: Path, name: str, triggers: list[str]) -> None:
        triggers_yaml = "\n".join(f"  - {t}" for t in triggers)
        (d / f"{name}.md").write_text(
            f"---\nname: {name}\ndescription: {name} skill\ntriggers:\n{triggers_yaml}\n---\nBody of {name}\n"
        )

    def test_discover(self, tmp_path: Path) -> None:
        self._write_skill(tmp_path, "greet", ["hello", "hi"])
        self._write_skill(tmp_path, "bye", ["goodbye"])
        settings = Settings(config_dir=tmp_path)
        reg = SkillRegistry(tmp_path, settings)
        reg.discover()
        assert len(reg.list()) == 2

    def test_match_message(self, tmp_path: Path) -> None:
        self._write_skill(tmp_path, "greet", ["hello", "hi"])
        settings = Settings(config_dir=tmp_path, skill_match_threshold=0.7)
        reg = SkillRegistry(tmp_path, settings)
        result = reg.match("hello")
        assert result is not None
        assert result.name == "greet"

    def test_match_no_match(self, tmp_path: Path) -> None:
        self._write_skill(tmp_path, "greet", ["hello"])
        settings = Settings(config_dir=tmp_path, skill_match_threshold=0.9)
        reg = SkillRegistry(tmp_path, settings)
        assert reg.match("xyz unrelated") is None

    def test_get_by_name(self, tmp_path: Path) -> None:
        self._write_skill(tmp_path, "greet", ["hello"])
        settings = Settings(config_dir=tmp_path)
        reg = SkillRegistry(tmp_path, settings)
        assert reg.get("greet") is not None
        assert reg.get("nonexistent") is None

    def test_empty_dir(self, tmp_path: Path) -> None:
        settings = Settings(config_dir=tmp_path)
        reg = SkillRegistry(tmp_path, settings)
        reg.discover()
        assert reg.list() == []
