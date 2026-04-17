"""Embedding providers for the memory subsystem."""

from __future__ import annotations

import logging

from polarsclaw.memory.config import MemoryConfig
from polarsclaw.memory.embeddings.base import EmbeddingProvider

logger = logging.getLogger(__name__)

__all__ = [
    "EmbeddingProvider",
    "create_embedding_provider",
]


def create_embedding_provider(config: MemoryConfig) -> EmbeddingProvider | None:
    """Factory with fallback chain: configured provider -> local -> None (FTS-only).

    Returns ``None`` when no embedding provider is available, signalling
    the search layer to operate in FTS-only mode.
    """
    # Try configured provider first
    if config.embedding_provider == "openai":
        try:
            from polarsclaw.memory.embeddings.remote import OpenAIEmbeddingProvider

            return OpenAIEmbeddingProvider(
                model=config.embedding_model,
                dimension=config.embedding_dim,
            )
        except Exception:
            logger.warning("OpenAI embeddings unavailable, falling back to local")

    # Try local sentence-transformers
    if config.embedding_provider in ("local", "openai"):  # openai falls back here
        try:
            from polarsclaw.memory.embeddings.local import SentenceTransformerProvider

            return SentenceTransformerProvider(model_name=config.embedding_model)
        except Exception:
            logger.warning(
                "Local embeddings unavailable (sentence-transformers not installed)"
            )

    # No provider available — FTS-only mode
    logger.info("No embedding provider available; memory search will use FTS-only mode")
    return None
