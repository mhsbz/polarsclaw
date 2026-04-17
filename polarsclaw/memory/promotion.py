"""Promotion scoring — ranks memory chunks for promotion to long-term memory."""

from __future__ import annotations

import logging
import math
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from polarsclaw.memory.config import MemoryConfig
    from polarsclaw.memory.db import MemoryDB
    from polarsclaw.memory.embeddings.base import EmbeddingProvider
    from polarsclaw.memory.recall_tracker import RecallTracker

logger = logging.getLogger(__name__)

# Common stop words to exclude from concept extraction
_STOP_WORDS = frozenset(
    "a an the is are was were be been being have has had do does did will would "
    "shall should may might can could of in to for with on at by from as into "
    "through during before after above below between out off over under again "
    "further then once here there when where why how all both each few more most "
    "other some such no nor not only own same so than too very and but if or "
    "because until while it its he she they them their this that these those i "
    "me my we our you your".split()
)


@dataclass
class PromotionCandidate:
    """A memory chunk scored for potential promotion to MEMORY.md."""

    chunk_id: str
    content: str
    file_path: str
    score: float
    components: dict[str, float] = field(default_factory=dict)


class PromotionScorer:
    """Scores memory chunks across six dimensions for promotion eligibility."""

    def __init__(
        self,
        db: MemoryDB,
        recall_tracker: RecallTracker,
        embedder: EmbeddingProvider,
        config: MemoryConfig,
    ) -> None:
        self._db = db
        self._recall = recall_tracker
        self._embedder = embedder
        self._config = config

    async def score_candidates(
        self, chunk_ids: list[str] | None = None
    ) -> list[PromotionCandidate]:
        """Score chunks and return sorted candidates (highest first).

        Args:
            chunk_ids: Specific chunks to score. If None, scores all chunks
                       from daily note files (memory/YYYY-MM-DD.md).
        """
        if chunk_ids is None:
            # Get chunks from daily note files only
            chunks = await self._db.get_chunks_by_file_pattern("memory/????-??-??.md")
        else:
            chunks = await self._db.get_chunks_by_ids(chunk_ids)

        if not chunks:
            return []

        now = datetime.now(timezone.utc)
        half_life = getattr(self._config, "recency_half_life_days", 14)
        weights = getattr(
            self._config,
            "promotion_weights",
            {
                "frequency": 0.20,
                "relevance": 0.25,
                "diversity": 0.15,
                "recency": 0.15,
                "consolidation": 0.10,
                "conceptual": 0.15,
            },
        )

        candidates: list[PromotionCandidate] = []
        for chunk in chunks:
            cid = chunk["chunk_id"]
            content = chunk["content"]
            created_at_str = chunk.get("created_at", "")

            # 1. Frequency: sigmoid normalization
            freq_count = await self._recall.frequency(cid)
            frequency = freq_count / (freq_count + 5)

            # 2. Relevance: average relevance score
            relevance = await self._recall.avg_relevance(cid)

            # 3. Diversity: unique queries, sigmoid
            uq_count = await self._recall.unique_queries(cid)
            diversity = uq_count / (uq_count + 3)

            # 4. Recency: exponential decay
            recency = 0.5  # default if no timestamp
            if created_at_str:
                try:
                    created_at = datetime.fromisoformat(created_at_str)
                    if created_at.tzinfo is None:
                        created_at = created_at.replace(tzinfo=timezone.utc)
                    age_days = (now - created_at).total_seconds() / 86400
                    recency = math.exp(-math.log(2) / half_life * age_days)
                except (ValueError, TypeError):
                    pass

            # 5. Consolidation: appeared in light sleep report?
            meta = await self._db.get_chunk_meta(cid)
            consolidation = 1.0 if meta.get("light_sleep") else 0.0

            # 6. Conceptual richness
            conceptual = self._conceptual_score(content)

            components = {
                "frequency": frequency,
                "relevance": relevance,
                "diversity": diversity,
                "recency": recency,
                "consolidation": consolidation,
                "conceptual": conceptual,
            }

            score = sum(weights.get(k, 0) * v for k, v in components.items())

            candidates.append(
                PromotionCandidate(
                    chunk_id=cid,
                    content=content,
                    file_path=chunk.get("file_path", ""),
                    score=score,
                    components=components,
                )
            )

        candidates.sort(key=lambda c: c.score, reverse=True)
        return candidates

    @staticmethod
    def _conceptual_score(content: str) -> float:
        """Compute conceptual richness of content."""
        words = re.findall(r"[a-zA-Z]{3,}", content.lower())
        if not words:
            return 0.0
        concepts = [w for w in words if w not in _STOP_WORDS]
        if not words:
            return 0.0
        unique_concepts = len(set(concepts))
        total_words = len(words)
        # Normalize: richness ratio, capped at 1.0
        return min(unique_concepts / total_words, 1.0)
