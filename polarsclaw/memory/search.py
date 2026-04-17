"""Hybrid search combining FTS5 and vector similarity with temporal decay and MMR."""

from __future__ import annotations

import logging
import math
import re
import struct
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
    applies temporal decay, and re-ranks via MMR for diversity."""

    def __init__(
        self,
        db: MemoryDB,
        embedder: EmbeddingProvider,
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
        """Run hybrid search and return the top *limit* results."""

        # 1. Embed query (provider.embed takes list[str], returns ndarray)
        query_array = await self._embedder.embed([query])
        query_vec: np.ndarray = query_array[0]  # shape (D,)

        # 2. FTS5 search (BM25) — already normalised to 0–1 by MemoryDB
        fts_rows = await self._db.fts_search(query, limit=100)
        fts_scores: dict[int, float] = {}
        chunk_data: dict[int, dict] = {}
        for row in fts_rows:
            cid = row["chunk_id"]
            fts_scores[cid] = row["score"]
            chunk_data[cid] = row

        # 3. Vector cosine similarity over all stored embeddings
        all_vecs = await self._db.get_all_vectors()  # list[(chunk_id, blob)]
        vec_scores: dict[int, float] = {}
        for cid, blob in all_vecs:
            n = len(blob) // 4
            emb = np.frombuffer(blob, dtype=np.float32, count=n)
            sim = self._cosine_similarity(query_vec, emb)
            vec_scores[cid] = max(0.0, float(sim))

        # Normalise vector scores to [0, 1]
        if vec_scores:
            mx = max(vec_scores.values()) or 1.0
            vec_scores = {k: v / mx for k, v in vec_scores.items()}

        # Resolve file paths for all candidate chunks
        all_ids = set(fts_scores) | set(vec_scores)
        file_path_cache: dict[int, str] = {}  # file_id -> path

        for cid in all_ids:
            if cid not in chunk_data:
                row = await self._db.get_chunk(cid)
                if row:
                    chunk_data[cid] = row

        # Build SearchResult candidates
        # We need the file path per chunk; look up via file_id -> mem_files
        candidates: list[SearchResult] = []
        cfg = self._config

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
            fused = cfg.vector_weight * vs + cfg.text_weight * fs

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
        results = self._mmr_rerank(
            candidates, query_vec, limit, cfg.mmr_lambda
        )

        # 7. Record recalls
        if self._recall_tracker and results:
            await self._recall_tracker.record(results, query, session_id)

        return results

    # ── helpers ──────────────────────────────────────────────────────────

    @staticmethod
    def _cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
        """Cosine similarity between two vectors."""
        dot = float(np.dot(a, b))
        na = float(np.linalg.norm(a))
        nb = float(np.linalg.norm(b))
        if na == 0.0 or nb == 0.0:
            return 0.0
        return dot / (na * nb)

    @staticmethod
    def _apply_temporal_decay(
        file_path: str, base_score: float, config: MemoryConfig
    ) -> float:
        """Decay score based on date in file path; MEMORY.md is evergreen."""
        # Evergreen files get no decay
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
        query_embedding: np.ndarray,  # noqa: ARG004
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

                # Max Jaccard similarity to any already-selected result
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
