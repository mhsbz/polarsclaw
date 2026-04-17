"""Abstract base class for embedding providers."""

from __future__ import annotations

from abc import ABC, abstractmethod

import numpy as np


class EmbeddingProvider(ABC):
    """Interface every embedding backend must implement."""

    @abstractmethod
    async def embed(self, texts: list[str]) -> np.ndarray:
        """Return an (N, D) float32 array of embeddings for *texts*."""

    @abstractmethod
    def dimension(self) -> int:
        """Return the dimensionality of the embedding vectors."""
