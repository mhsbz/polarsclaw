"""PolarsClaw memory subsystem — MemoryCore facade."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING

from langchain_core.tools import BaseTool

from polarsclaw.memory.config import MemoryConfig
from polarsclaw.memory.db import MemoryDB
from polarsclaw.memory.embeddings import create_embedding_provider
from polarsclaw.memory.indexer import FileIndexer
from polarsclaw.memory.recall_tracker import RecallTracker
from polarsclaw.memory.schema import MEMORY_MIGRATION
from polarsclaw.memory.search import HybridSearcher, SearchResult
from polarsclaw.memory.tools import make_memory_core_tools

if TYPE_CHECKING:
    from polarsclaw.cron.scheduler import CronScheduler
    from polarsclaw.storage.database import Database

logger = logging.getLogger(__name__)

__all__ = ["MemoryCore", "MemoryConfig", "SearchResult"]


class MemoryCore:
    """Single entry-point for the entire memory subsystem.

    Wires together schema migration, embedding, indexing,
    hybrid search, recall tracking, and tool generation.
    """

    def __init__(self, db: Database, config: MemoryConfig) -> None:
        self._db = db
        self._config = config

        # Populated by :meth:`initialize`
        self._memory_db: MemoryDB | None = None
        self._indexer: FileIndexer | None = None
        self._searcher: HybridSearcher | None = None
        self._recall_tracker: RecallTracker | None = None

    # ── lifecycle ────────────────────────────────────────────────────────

    async def initialize(self) -> None:
        """Run DDL migration, create components, index existing files."""

        # 1. Apply memory-specific DDL
        conn = self._db.get_connection()
        for stmt in MEMORY_MIGRATION:
            await conn.execute(stmt)
        await conn.commit()
        logger.info("Memory schema migration applied.")

        # 2. Wire up components
        embedder = create_embedding_provider(self._config)
        self._memory_db = MemoryDB(self._db)
        if embedder is not None:
            self._indexer = FileIndexer(self._memory_db, embedder, self._config)
        else:
            self._indexer = None
            logger.info("No embedding provider — indexing disabled, FTS-only search")
        self._recall_tracker = RecallTracker(self._memory_db)
        self._searcher = HybridSearcher(
            self._memory_db, embedder, self._config
        )
        self._searcher.set_recall_tracker(self._recall_tracker)

        # 3. Index existing memory files
        await self._index_existing_files()

    async def shutdown(self) -> None:
        """Release resources (stop watcher, etc.)."""
        logger.info("MemoryCore shut down.")

    # ── public API ───────────────────────────────────────────────────────

    async def search(
        self,
        query: str,
        limit: int = 10,
        session_id: str | None = None,
    ) -> list[SearchResult]:
        """Hybrid FTS + vector search across all indexed memory."""
        assert self._searcher is not None, "MemoryCore not initialised"
        return await self._searcher.search(
            query, limit=limit, session_id=session_id
        )

    async def get_file(self, path: str) -> str | None:
        """Read a workspace file. Returns *None* if it does not exist."""
        full = Path(self._config.workspace) / path
        if not full.exists():
            return None
        return full.read_text(encoding="utf-8")

    async def index_file(self, path: str) -> int:
        """Index (or re-index) a single file. Returns chunk count (0/1)."""
        if self._indexer is None:
            return 0
        full = Path(self._config.workspace) / path
        indexed = await self._indexer.index_file(full)
        return 1 if indexed else 0

    def get_tools(self) -> list[BaseTool]:
        """Return LangChain tools wired to this MemoryCore."""
        return make_memory_core_tools(self)

    # ── dreaming stubs (Phase 7-9) ───────────────────────────────────────

    async def light_sleep(self) -> None:
        """Phase 7: compress and deduplicate recent memories."""
        logger.info("light_sleep: not yet implemented (Phase 7)")

    async def rem_sleep(self) -> None:
        """Phase 8: discover cross-file connections."""
        logger.info("rem_sleep: not yet implemented (Phase 8)")

    async def deep_sleep(self) -> None:
        """Phase 9: consolidate long-term memory, prune stale data."""
        logger.info("deep_sleep: not yet implemented (Phase 9)")

    def register_jobs(self, scheduler: CronScheduler) -> None:
        """Register dreaming cron jobs with the scheduler.

        Currently no-ops — will be wired when Phases 7-9 land.
        """
        logger.info("Registered memory dreaming cron jobs (stubs).")

    # ── internals ────────────────────────────────────────────────────────

    async def _index_existing_files(self) -> None:
        """Index MEMORY.md, memory/*.md, and DREAMS.md when present."""
        if self._indexer is None:
            logger.info("Indexing skipped (no embedding provider).")
            return

        ws = Path(self._config.workspace)

        files: list[Path] = []

        mem_file = ws / "MEMORY.md"
        if mem_file.exists():
            files.append(mem_file)

        mem_dir = ws / "memory"
        if mem_dir.is_dir():
            files.extend(sorted(mem_dir.glob("*.md")))

        dreams = ws / "DREAMS.md"
        if dreams.exists():
            files.append(dreams)

        count = 0
        for f in files:
            if await self._indexer.index_file(f):
                count += 1

        logger.info(
            "Indexed %d memory files (of %d checked).",
            count,
            len(files),
        )
