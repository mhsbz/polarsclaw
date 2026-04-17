"""File indexer — parses, chunks, embeds, and stores documents."""

from __future__ import annotations

import hashlib
import logging
import re
from pathlib import Path

import numpy as np

from polarsclaw.memory.config import MemoryConfig
from polarsclaw.memory.db import MemoryDB
from polarsclaw.memory.embeddings.base import EmbeddingProvider

logger = logging.getLogger(__name__)

_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+)$", re.MULTILINE)


class FileIndexer:
    """Index markdown files into the memory store."""

    def __init__(
        self,
        db: MemoryDB,
        provider: EmbeddingProvider,
        config: MemoryConfig,
    ) -> None:
        self._db = db
        self._provider = provider
        self._config = config

    # ── public API ───────────────────────────────────────────────────────

    async def index_file(self, path: Path | str) -> bool:
        """Index a single file. Returns True if the file was (re-)indexed, False if skipped."""
        path = Path(path)
        if not path.is_file():
            logger.warning("index_file: %s does not exist, skipping", path)
            return False

        content = path.read_text(encoding="utf-8", errors="replace")
        file_hash = hashlib.sha256(content.encode()).hexdigest()
        size = path.stat().st_size

        existing = await self._db.get_file(str(path))
        if existing and existing["hash"] == file_hash:
            logger.debug("Skipping unchanged file: %s", path)
            return False

        # Upsert file record
        file_id = await self._db.upsert_file(
            path=str(path),
            file_type="markdown",
            file_hash=file_hash,
            size=size,
        )

        # Remove old chunks (cascade will also remove vectors via FK)
        await self._db.delete_chunks_by_file(file_id)

        # Parse and chunk
        chunks = self._parse_markdown(content)
        if not chunks:
            return True

        # Store chunks
        chunk_records = [
            {
                "chunk_index": i,
                "content": ch["content"],
                "heading": ch["heading"],
                "token_count": ch["token_count"],
            }
            for i, ch in enumerate(chunks)
        ]
        chunk_ids = await self._db.insert_chunks(file_id, chunk_records)

        # Embed and store vectors
        await self._embed_and_store(chunks, chunk_ids)

        logger.info("Indexed %s (%d chunks)", path, len(chunks))
        return True

    async def index_directory(
        self, root: Path | str, pattern: str = "**/*.md"
    ) -> int:
        """Index all matching files under *root*. Returns number of files indexed."""
        root = Path(root)
        count = 0
        for p in sorted(root.glob(pattern)):
            if await self.index_file(p):
                count += 1
        return count

    # ── internal ─────────────────────────────────────────────────────────

    def _parse_markdown(self, content: str) -> list[dict]:
        """Split markdown into heading-aware, token-bounded chunks."""
        if not content.strip():
            return []

        chunk_size = self._config.chunk_size
        overlap = self._config.chunk_overlap

        # Split content into sections by heading
        sections: list[tuple[str, str]] = []  # (heading, body)
        parts = _HEADING_RE.split(content)

        # parts: [pre-text, '#level', 'title', body, '#level', 'title', body, ...]
        idx = 0
        current_heading = ""

        if parts and not _HEADING_RE.match(parts[0] if parts[0] else ""):
            # Text before the first heading
            pre = parts[0].strip()
            if pre:
                sections.append(("", pre))
            idx = 1

        while idx + 2 < len(parts):
            _level = parts[idx]       # e.g. '##'
            title = parts[idx + 1]    # heading text
            body = parts[idx + 2].strip()
            current_heading = title.strip()
            if body:
                sections.append((current_heading, body))
            idx += 3

        # Handle remaining text
        if idx < len(parts):
            leftover = parts[idx].strip()
            if leftover:
                sections.append((current_heading, leftover))

        # Break each section into token-bounded chunks
        chunks: list[dict] = []
        for heading, text in sections:
            tokens_approx = len(text) // 4
            if tokens_approx <= chunk_size:
                chunks.append({
                    "content": text,
                    "heading": heading,
                    "token_count": tokens_approx,
                })
            else:
                # Split long sections into smaller pieces
                start_char = 0
                while start_char < len(text):
                    end_char = start_char + chunk_size * 4
                    if end_char >= len(text):
                        segment = text[start_char:]
                    else:
                        # Try to break at a sentence or paragraph boundary
                        boundary = text.rfind("\n\n", start_char, end_char)
                        if boundary == -1 or boundary <= start_char:
                            boundary = text.rfind(". ", start_char, end_char)
                        if boundary == -1 or boundary <= start_char:
                            boundary = text.rfind(" ", start_char, end_char)
                        if boundary == -1 or boundary <= start_char:
                            boundary = end_char
                        else:
                            boundary += 1  # include the delimiter
                        segment = text[start_char:boundary]

                    segment = segment.strip()
                    if segment:
                        chunks.append({
                            "content": segment,
                            "heading": heading,
                            "token_count": len(segment) // 4,
                        })

                    # Advance with overlap
                    if end_char >= len(text):
                        break
                    overlap_chars = overlap * 4
                    next_start = start_char + len(segment)
                    start_char = max(start_char + 1, next_start - overlap_chars)

        return chunks

    async def _embed_and_store(
        self,
        chunks: list[dict],
        chunk_ids: list[int],
    ) -> None:
        """Embed chunks, using the cache where possible, and store vectors."""
        model_name = self._config.embedding_model
        texts = [ch["content"] for ch in chunks]
        hashes = [hashlib.sha256(t.encode()).hexdigest() for t in texts]

        # Check cache
        cached: dict[int, bytes] = {}
        uncached_indices: list[int] = []

        for i, h in enumerate(hashes):
            blob = await self._db.get_cached_embedding(h)
            if blob is not None:
                cached[i] = blob
            else:
                uncached_indices.append(i)

        # Embed uncached texts
        if uncached_indices:
            uncached_texts = [texts[i] for i in uncached_indices]
            embeddings = await self._provider.embed(uncached_texts)

            for j, idx in enumerate(uncached_indices):
                blob = embeddings[j].tobytes()
                cached[idx] = blob
                await self._db.cache_embedding(hashes[idx], model_name, blob)

        # Store all vectors
        vectors = [(chunk_ids[i], cached[i]) for i in range(len(chunks))]
        await self._db.upsert_vectors(vectors)
