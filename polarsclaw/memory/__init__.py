"""PolarsClaw memory subsystem — MemoryCore facade."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING

from langchain_core.tools import BaseTool

from polarsclaw.memory.config import MemoryConfig
from polarsclaw.memory.db import MemoryDB
from polarsclaw.memory.dreaming.deep import DeepSleep
from polarsclaw.memory.dreaming.light import LightSleep
from polarsclaw.memory.dreaming.rem import REMSleep
from polarsclaw.memory.embeddings import create_embedding_provider
from polarsclaw.memory.indexer import FileIndexer
from polarsclaw.memory.promotion import PromotionScorer
from polarsclaw.memory.recall_tracker import RecallTracker
from polarsclaw.memory.schema import MEMORY_MIGRATION
from polarsclaw.memory.search import HybridSearcher, SearchResult
from polarsclaw.memory.tools import make_memory_core_tools
from polarsclaw.memory.watcher import FileWatcher
from polarsclaw.memory.writer import DailyMemoryWriter

if TYPE_CHECKING:
    from polarsclaw.cron.scheduler import CronScheduler
    from polarsclaw.storage.database import Database

logger = logging.getLogger(__name__)

__all__ = ["MemoryCore", "MemoryConfig", "SearchResult", "DailyMemoryWriter"]


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
        self._watcher: FileWatcher | None = None
        self._light_sleep_job: LightSleep | None = None
        self._rem_sleep_job: REMSleep | None = None
        self._deep_sleep_job: DeepSleep | None = None
        self._writer: DailyMemoryWriter | None = None

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
            self._watcher = FileWatcher(self._indexer, self._config)
        else:
            self._indexer = None
            self._watcher = None
            logger.info("No embedding provider — indexing disabled, FTS-only search")
        self._recall_tracker = RecallTracker(self._memory_db)
        self._searcher = HybridSearcher(
            self._memory_db, embedder, self._config
        )
        self._searcher.set_recall_tracker(self._recall_tracker)
        if self._memory_db is not None:
            self._rem_sleep_job = REMSleep(self._memory_db, self._db, self._config)
        self._writer = DailyMemoryWriter(self._config)

        if embedder is not None and self._indexer is not None and self._memory_db is not None:
            self._light_sleep_job = LightSleep(self._indexer, self._memory_db, embedder, self._config)
            self._deep_sleep_job = DeepSleep(
                PromotionScorer(self._memory_db, self._recall_tracker, embedder, self._config),
                self._memory_db,
                self._config,
            )

        # 3. Index existing memory files
        await self._index_existing_files()
        if self._watcher is not None:
            await self._watcher.start()

    async def shutdown(self) -> None:
        """Release resources (stop watcher, etc.)."""
        if self._watcher is not None:
            await self._watcher.stop()
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

    async def append_memory(
        self,
        content: str,
        role: str = "assistant",
        session_id: str | None = None,
    ) -> str:
        """Append a turn to today's daily memory log.

        The written .md file is the canonical memory — human-readable,
        git-versionable, and directly editable.

        Args:
            content: The text to record.
            role: One of user | assistant | system | tool.
            session_id: Optional session identifier.

        Returns:
            Path to the file that was written (as string).
        """
        assert self._writer is not None, "MemoryCore not initialised"
        path = await self._writer.append(content, role=role, session_id=session_id)
        # Re-index so the new content is searchable immediately.
        if self._indexer is not None:
            await self._indexer.index_file(path)
        return str(path)

    def get_tools(self) -> list[BaseTool]:
        """Return LangChain tools wired to this MemoryCore."""
        return make_memory_core_tools(self)

    # ── dreaming stubs (Phase 7-9) ───────────────────────────────────────

    async def light_sleep(self) -> None:
        """Phase 7: compress and deduplicate recent memories."""
        if self._light_sleep_job is None:
            logger.info("light_sleep unavailable (no embedding/indexer)")
            return
        await self._light_sleep_job.run()

    async def rem_sleep(self) -> None:
        """Phase 8: discover cross-file connections."""
        if self._rem_sleep_job is None:
            logger.info("rem_sleep unavailable")
            return
        await self._rem_sleep_job.run()

    async def deep_sleep(self) -> None:
        """Phase 9: consolidate long-term memory, prune stale data."""
        if self._deep_sleep_job is None:
            logger.info("deep_sleep unavailable (no promotion scorer)")
            return
        await self._deep_sleep_job.run()

    async def register_jobs(self, scheduler: CronScheduler) -> None:
        """Register dreaming cron jobs with the scheduler.

        Registers the three memory dreaming phases with the cron scheduler.
        """
        schedule = self._config.dreaming_schedule
        await scheduler.register_runtime_job(
            "memory-light-sleep",
            schedule.light,
            self.light_sleep,
            task="memory.light_sleep",
        )
        await scheduler.register_runtime_job(
            "memory-rem-sleep",
            schedule.rem,
            self.rem_sleep,
            task="memory.rem_sleep",
        )
        await scheduler.register_runtime_job(
            "memory-deep-sleep",
            schedule.deep,
            self.deep_sleep,
            task="memory.deep_sleep",
        )
        logger.info("Registered memory dreaming cron jobs.")

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
