"""File watcher that monitors memory files and triggers re-indexing."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import TYPE_CHECKING

import watchfiles

if TYPE_CHECKING:
    from polarsclaw.memory.config import MemoryConfig
    from polarsclaw.memory.indexer import FileIndexer

logger = logging.getLogger(__name__)


class FileWatcher:
    """Watches memory files for changes and triggers re-indexing."""

    def __init__(self, indexer: FileIndexer, config: MemoryConfig) -> None:
        self._indexer = indexer
        self._config = config
        self._task: asyncio.Task[None] | None = None

    @property
    def workspace(self) -> Path:
        return self._config.workspace

    def _watch_paths(self) -> list[Path]:
        """Return the list of paths to monitor for changes."""
        return [
            self.workspace / "MEMORY.md",
            self.workspace / "memory",
            self.workspace / "DREAMS.md",
        ]

    async def start(self) -> None:
        """Launch the background file-watching task."""
        if self._task is not None and not self._task.done():
            logger.warning("FileWatcher is already running.")
            return
        self._task = asyncio.create_task(self._run(), name="file-watcher")
        logger.info("FileWatcher started, monitoring %s", self._watch_paths())

    async def stop(self) -> None:
        """Cancel the background task."""
        if self._task is not None and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            logger.info("FileWatcher stopped.")
        self._task = None

    async def _run(self) -> None:
        """Watch for file changes and trigger indexing."""
        watch_paths = [p for p in self._watch_paths() if p.exists()]
        if not watch_paths:
            logger.warning("No watch paths exist yet, waiting for them to appear...")
            # Wait until at least one path exists
            while True:
                await asyncio.sleep(5)
                watch_paths = [p for p in self._watch_paths() if p.exists()]
                if watch_paths:
                    break

        logger.info("Watching paths: %s", watch_paths)
        try:
            async for changes in watchfiles.awatch(*watch_paths):
                for change_type, changed_path_str in changes:
                    changed_path = Path(changed_path_str)
                    if changed_path.suffix == ".md":
                        logger.debug(
                            "Detected %s on %s, re-indexing...",
                            change_type.name,
                            changed_path,
                        )
                        try:
                            await self._indexer.index_file(changed_path)
                        except Exception:
                            logger.exception(
                                "Error indexing %s after change", changed_path
                            )
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("FileWatcher encountered an unexpected error")
