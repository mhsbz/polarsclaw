"""Embedding providers for the memory subsystem."""

from __future__ import annotations

from polarsclaw.memory.config import MemoryConfig
from polarsclaw.memory.embeddings.base import EmbeddingProvider
from polarsclaw.memory.embeddings.local import SentenceTransformerProvider
from polarsclaw.memory.embeddings.remote import OpenAIEmbeddingProvider

__all__ = [
    "EmbeddingProvider",
    "SentenceTransformerProvider",
    "OpenAIEmbeddingProvider",
    "create_embedding_provider",
]


def create_embedding_provider(config: MemoryConfig) -> EmbeddingProvider:
    """Factory that returns the appropriate provider based on config."""
    if config.embedding_provider == "openai":
        return OpenAIEmbeddingProvider(
            model=config.embedding_model,
            dimension=config.embedding_dim,
        )
    return SentenceTransformerProvider(
        model_name=config.embedding_model,
    )
