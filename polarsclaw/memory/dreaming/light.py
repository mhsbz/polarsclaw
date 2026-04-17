"""Light sleep — re-index memory files and deduplicate near-identical chunks."""

from __future__ import annotations

import logging
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from polarsclaw.memory.config import MemoryConfig
    from polarsclaw.memory.db import MemoryDB
    from polarsclaw.memory.embeddings.base import EmbeddingProvider
    from polarsclaw.memory.indexer import FileIndexer

logger = logging.getLogger(__name__)


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    """Compute cosine similarity between two vectors."""
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


class LightSleep:
    """Re-indexes memory files and deduplicates near-identical chunks."""

    def __init__(
        self,
        indexer: FileIndexer,
        db: MemoryDB,
        embedder: EmbeddingProvider,
        config: MemoryConfig,
    ) -> None:
        self._indexer = indexer
        self._db = db
        self._embedder = embedder
        self._config = config

    async def run(self) -> dict:
        """Execute light sleep: re-index, deduplicate, report.

        Returns:
            Dict with keys: files_indexed, chunks_deduped, report_path.
        """
        workspace = self._config.workspace
        memory_dir = workspace / "memory"

        # 1. Re-index all memory files
        files_indexed = 0
        if memory_dir.exists():
            files_indexed += await self._indexer.index_directory(memory_dir)
        memory_md = workspace / "MEMORY.md"
        if memory_md.exists():
            await self._indexer.index_file(memory_md)
            files_indexed += 1

        # 2. Deduplicate near-identical chunks
        chunks = await self._db.get_all_chunks()
        chunks_deduped = 0

        if len(chunks) > 1:
            # Get embeddings for all chunks
            contents = [c["content"] for c in chunks]
            embeddings_array = await self._embedder.embed(contents)
            embeddings = [embeddings_array[i].tolist() for i in range(len(contents))]

            # Build mapping: chunk_id -> (embedding, chunk)
            chunk_data = list(zip(chunks, embeddings))

            # Find near-duplicates (similarity > 0.95)
            to_remove: set[str] = set()
            for i in range(len(chunk_data)):
                if chunk_data[i][0]["chunk_id"] in to_remove:
                    continue
                for j in range(i + 1, len(chunk_data)):
                    if chunk_data[j][0]["chunk_id"] in to_remove:
                        continue
                    sim = _cosine_similarity(chunk_data[i][1], chunk_data[j][1])
                    if sim > 0.95:
                        # Keep the chunk from the more recent file
                        ci, cj = chunk_data[i][0], chunk_data[j][0]
                        ts_i = ci.get("created_at", "")
                        ts_j = cj.get("created_at", "")
                        # Remove the older one
                        if ts_i >= ts_j:
                            to_remove.add(cj["chunk_id"])
                        else:
                            to_remove.add(ci["chunk_id"])

            # Remove duplicates from DB
            for chunk_id in to_remove:
                await self._db.delete_chunk(chunk_id)
            chunks_deduped = len(to_remove)

        # 3. Write summary report
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        report_dir = workspace / "memory" / "dreaming" / "light"
        report_dir.mkdir(parents=True, exist_ok=True)
        report_path = report_dir / f"{today}.md"

        report_lines = [
            f"# Light Sleep Report — {today}",
            "",
            f"- **Files indexed:** {files_indexed}",
            f"- **Chunks deduplicated:** {chunks_deduped}",
            f"- **Total chunks remaining:** {len(chunks) - chunks_deduped}",
            "",
        ]
        if chunks_deduped > 0:
            report_lines.append("## Removed Duplicates")
            report_lines.append("")
            for cid in sorted(to_remove):
                report_lines.append(f"- `{cid}`")
            report_lines.append("")

        report_path.write_text("\n".join(report_lines), encoding="utf-8")
        logger.info(
            "Light sleep complete: %d indexed, %d deduped, report at %s",
            files_indexed,
            chunks_deduped,
            report_path,
        )

        return {
            "files_indexed": files_indexed,
            "chunks_deduped": chunks_deduped,
            "report_path": str(report_path),
        }
