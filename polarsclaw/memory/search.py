"""Hybrid search combining FTS5 and vector similarity with temporal decay and MMR."""

from __future__ import annotations

import logging
import math
import re
from dataclasses import dataclass
from datetime import datetime, timezone

import numpy as np

from polarsclaw.memory.config import MemoryConfig
from polarsclaw.memory.db import MemoryDB
from polarsclaw.memory.embeddings.base import EmbeddingProvider
from polarsclaw.memory.recall_tracker import RecallTracker

logger = logging.getLogger(__name__)


@dataclass
class SearchResult:
    """A single hybrid search result."""

    chunk_id: int
    file_path: str
    heading: str
    content: str
    score: float
    fts_score: float = 0.0
    vec_score: float = 0.0


class HybridSearcher:
    """Combines BM25 full-text search with vector cosine similarity,
    applies temporal decay, and re-ranks via MMR for diversity.

    Gracefully degrades to FTS-only when no embedder is available.
    """

    def __init__(
        self,
        db: MemoryDB,
        embedder: EmbeddingProvider | None,
        config: MemoryConfig,
    ) -> None:
        self._db = db
        self._embedder = embedder
        self._config = config
        self._recall_tracker: RecallTracker | None = None

    def set_recall_tracker(self, tracker: RecallTracker) -> None:
        self._recall_tracker = tracker

    async def search(
        self,
        query: str,
        limit: int = 10,
        file_filter: str | None = None,
        session_id: str | None = None,
    ) -> list[SearchResult]:
        """Run hybrid search and return the top *limit* results.

        Falls back to FTS-only when embedder is unavailable or embed fails.
        """
        cfg = self._config
        over_fetch = limit * 3

        # 1. FTS5 search (always runs — never depends on embedder)
        fts_rows = await self._db.fts_search(query, limit=over_fetch)
        fts_scores: dict[int, float] = {}
        chunk_data: dict[int, dict] = {}
        for row in fts_rows:
            cid = row["chunk_id"]
            fts_scores[cid] = row["score"]
            chunk_data[cid] = row

        # 2. Vector search (optional — skipped if no embedder or embed fails)
        vec_scores: dict[int, float] = {}
        query_vec: np.ndarray | None = None

        if self._embedder is not None:
            try:
                embed_result = await self._embedder.embed([query])
                if embed_result is not None and len(embed_result) > 0:
                    query_vec = embed_result[0]
                    vec_scores = await self._batch_vector_search(query_vec, over_fetch)
            except Exception:
                logger.warning("Vector search failed, using FTS-only", exc_info=True)

        # 3. Resolve file paths for all candidate chunks
        all_ids = set(fts_scores) | set(vec_scores)
        file_path_cache: dict[int, str] = {}

        for cid in all_ids:
            if cid not in chunk_data:
                row = await self._db.get_chunk(cid)
                if row:
                    chunk_data[cid] = row

        # 4. Build SearchResult candidates with score fusion
        candidates: list[SearchResult] = []

        for cid in all_ids:
            row = chunk_data.get(cid)
            if row is None:
                continue

            file_id = row.get("file_id")
            if file_id not in file_path_cache:
                file_row = await self._db.get_file_by_id(file_id) if file_id else None
                file_path_cache[file_id] = file_row["path"] if file_row else ""
            fp = file_path_cache.get(file_id, "")

            if file_filter and file_filter not in fp:
                continue

            vs = vec_scores.get(cid, 0.0)
            fs = fts_scores.get(cid, 0.0)

            # Fuse: if we have both, weighted sum; if FTS-only, use FTS score directly
            if vec_scores:
                fused = cfg.vector_weight * vs + cfg.text_weight * fs
            else:
                fused = fs

            # 5. Temporal decay
            fused = self._apply_temporal_decay(fp, fused, cfg)

            candidates.append(
                SearchResult(
                    chunk_id=cid,
                    file_path=fp,
                    heading=row.get("heading", ""),
                    content=row["content"],
                    score=fused,
                    fts_score=fs,
                    vec_score=vs,
                )
            )

        candidates.sort(key=lambda r: r.score, reverse=True)

        # 6. MMR re-rank for diversity
        results = self._mmr_rerank(candidates, limit, cfg.mmr_lambda)

        # 7. Record recalls
        if self._recall_tracker and results:
            await self._recall_tracker.record(results, query, session_id)

        return results

    # ── vector search (numpy batch) ─────────────────────────────────────

    async def _batch_vector_search(
        self, query_vec: np.ndarray, limit: int
    ) -> dict[int, float]:
        """Batch cosine similarity using numpy matrix ops — ~100x faster than per-row."""
        all_vecs = await self._db.get_all_vectors()
        if not all_vecs:
            return {}

        ids = [v[0] for v in all_vecs]
        matrix = np.stack(
            [np.frombuffer(v[1], dtype=np.float32) for v in all_vecs]
        )  # (N, D)

        # Batch cosine: (matrix @ query) / (||rows|| * ||query||)
        query_norm = np.linalg.norm(query_vec)
        if query_norm == 0:
            return {}

        row_norms = np.linalg.norm(matrix, axis=1)
        row_norms[row_norms == 0] = 1.0
        scores = (matrix @ query_vec) / (row_norms * query_norm)

        # Top-k via argpartition (O(n) average vs O(n log n) full sort)
        k = min(limit, len(scores))
        top_idx = np.argpartition(scores, -k)[-k:]
        top_idx = top_idx[np.argsort(scores[top_idx])[::-1]]

        # Normalize to [0, 1]
        result = {}
        mx = float(scores[top_idx[0]]) if len(top_idx) > 0 else 1.0
        mx = mx if mx > 0 else 1.0
        for i in top_idx:
            s = max(0.0, float(scores[i]))
            result[ids[i]] = s / mx

        return result

    # ── helpers ──────────────────────────────────────────────────────────

    @staticmethod
    def _apply_temporal_decay(
        file_path: str, base_score: float, config: MemoryConfig
    ) -> float:
        """Decay score based on date in file path; MEMORY.md is evergreen."""
        if "MEMORY.md" in file_path:
            return base_score

        m = re.search(r"(\d{4}-\d{2}-\d{2})", file_path)
        if not m:
            return base_score

        try:
            file_date = datetime.strptime(m.group(1), "%Y-%m-%d").replace(
                tzinfo=timezone.utc
            )
        except ValueError:
            return base_score

        age_days = max(
            0.0,
            (datetime.now(timezone.utc) - file_date).total_seconds() / 86400.0,
        )
        half_life = config.temporal_decay_days
        decay = math.exp(-math.log(2) / half_life * age_days)
        return base_score * decay

    @staticmethod
    def _mmr_rerank(
        candidates: list[SearchResult],
        limit: int,
        lambda_param: float,
    ) -> list[SearchResult]:
        """Maximal Marginal Relevance re-ranking (Jaccard on word tokens)."""
        if not candidates:
            return []

        def _tokens(text: str) -> set[str]:
            return set(text.lower().split())

        selected: list[SearchResult] = []
        remaining = list(candidates)

        while remaining and len(selected) < limit:
            best_idx = -1
            best_mmr = -math.inf

            for i, cand in enumerate(remaining):
                relevance = cand.score

                max_sim = 0.0
                cand_tok = _tokens(cand.content)
                for sel in selected:
                    sel_tok = _tokens(sel.content)
                    inter = len(cand_tok & sel_tok)
                    union = len(cand_tok | sel_tok)
                    if union:
                        max_sim = max(max_sim, inter / union)

                mmr = lambda_param * relevance - (1 - lambda_param) * max_sim
                if mmr > best_mmr:
                    best_mmr = mmr
                    best_idx = i

            selected.append(remaining.pop(best_idx))

        return selected
