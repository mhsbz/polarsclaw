"""Deep sleep — promote high-value daily memories to long-term MEMORY.md."""

from __future__ import annotations

import hashlib
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from polarsclaw.memory.config import MemoryConfig
    from polarsclaw.memory.db import MemoryDB
    from polarsclaw.memory.promotion import PromotionCandidate, PromotionScorer

logger = logging.getLogger(__name__)


class DeepSleep:
    """Promotes the highest-scoring daily chunks into MEMORY.md."""

    def __init__(
        self,
        scorer: PromotionScorer,
        db: MemoryDB,
        config: MemoryConfig,
    ) -> None:
        self._scorer = scorer
        self._db = db
        self._config = config

    async def run(self, top_n: int = 10) -> list[PromotionCandidate]:
        """Score daily-note chunks, promote top candidates to MEMORY.md.

        Args:
            top_n: Maximum number of chunks to promote.

        Returns:
            List of promoted candidates.
        """
        # 1. Score all daily-note chunks
        candidates = await self._scorer.score_candidates()

        # 2. Filter: min score > 0.3 and min recall count > 2
        filtered: list[PromotionCandidate] = []
        for c in candidates:
            if c.score <= 0.3:
                continue
            recall_count = await self._db.get_recall_count(c.chunk_id)
            if recall_count <= 2:
                continue
            filtered.append(c)

        # 3. Take top N
        promoted = filtered[:top_n]

        if not promoted:
            logger.info("Deep sleep: no candidates met promotion criteria.")
            return []

        # 4. Append to MEMORY.md
        await self._append_to_memory_md(promoted)

        # 5. Update DREAMS.md
        await self._update_dreams_md(promoted)

        logger.info("Deep sleep: promoted %d chunks to MEMORY.md.", len(promoted))
        return promoted

    async def _append_to_memory_md(
        self, candidates: list[PromotionCandidate]
    ) -> None:
        """Append promoted candidates to MEMORY.md, skipping duplicates."""
        memory_md = self._config.workspace / "MEMORY.md"
        memory_md.parent.mkdir(parents=True, exist_ok=True)

        existing_content = ""
        if memory_md.exists():
            existing_content = memory_md.read_text(encoding="utf-8")

        # Collect existing fingerprints
        existing_fingerprints: set[str] = set()
        for line in existing_content.splitlines():
            if "<!-- polarsclaw:promoted:" in line:
                start = line.index("<!-- polarsclaw:promoted:") + len(
                    "<!-- polarsclaw:promoted:"
                )
                end = line.index(" -->", start)
                existing_fingerprints.add(line[start:end])

        # Build new entries
        new_entries: list[str] = []
        for candidate in candidates:
            fingerprint = hashlib.sha256(
                candidate.content.encode("utf-8")
            ).hexdigest()[:16]
            if fingerprint in existing_fingerprints:
                logger.debug(
                    "Skipping already-promoted chunk %s", candidate.chunk_id
                )
                continue
            new_entries.append(
                f"- {candidate.content}  "
                f"<!-- polarsclaw:promoted:{fingerprint} -->"
            )

        if not new_entries:
            return

        # Ensure "## Promoted Memories" section exists
        if "## Promoted Memories" not in existing_content:
            if existing_content and not existing_content.endswith("\n"):
                existing_content += "\n"
            existing_content += "\n## Promoted Memories\n\n"

        # Append entries
        content = existing_content.rstrip() + "\n" + "\n".join(new_entries) + "\n"
        memory_md.write_text(content, encoding="utf-8")

    async def _update_dreams_md(
        self, candidates: list[PromotionCandidate]
    ) -> None:
        """Append a dated summary entry to DREAMS.md."""
        dreams_md = self._config.workspace / "DREAMS.md"
        dreams_md.parent.mkdir(parents=True, exist_ok=True)

        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        entry_lines = [
            f"## Deep Sleep — {today}",
            "",
            f"Promoted **{len(candidates)}** memories:",
            "",
        ]
        for c in candidates:
            snippet = c.content[:100]
            if len(c.content) > 100:
                snippet += "…"
            entry_lines.append(
                f"- [{c.chunk_id[:8]}] (score={c.score:.3f}) {snippet}"
            )
        entry_lines.append("")

        existing = ""
        if dreams_md.exists():
            existing = dreams_md.read_text(encoding="utf-8")

        if not existing:
            content = "# DREAMS\n\nConsolidation log for PolarsClaw memory.\n\n"
        else:
            content = existing.rstrip() + "\n\n"

        content += "\n".join(entry_lines)
        dreams_md.write_text(content, encoding="utf-8")
