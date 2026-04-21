"""Local sentence-transformers embedding provider."""

from __future__ import annotations

import asyncio
import logging
from functools import lru_cache

import numpy as np

from polarsclaw.memory.embeddings.base import EmbeddingProvider

logger = logging.getLogger(__name__)


@lru_cache(maxsize=4)
def _load_model(model_name: str):  # noqa: ANN202
    """Lazily load and cache a SentenceTransformer model."""
    from sentence_transformers import SentenceTransformer

    logger.info("Loading sentence-transformer model: %s", model_name)
    return SentenceTransformer(model_name, local_files_only=True)


class SentenceTransformerProvider(EmbeddingProvider):
    """Embedding provider backed by a local sentence-transformers model."""

    def __init__(self, model_name: str = "all-MiniLM-L6-v2") -> None:
        self._model_name = model_name

    def _get_model(self):  # noqa: ANN202
        return _load_model(self._model_name)

    async def embed(self, texts: list[str]) -> np.ndarray | None:
        """Encode *texts* on a thread so the event loop stays free.

        Returns ``None`` if the model fails to load or encode.
        """
        try:
            model = self._get_model()
        except Exception:
            logger.warning("Failed to load sentence-transformer model: %s", self._model_name)
            return None

        def _encode() -> np.ndarray:
            return model.encode(texts, show_progress_bar=False, convert_to_numpy=True)

        try:
            result = await asyncio.to_thread(_encode)
            return result.astype(np.float32)
        except Exception:
            logger.warning("sentence-transformer encode failed", exc_info=True)
            return None

    def dimension(self) -> int:
        return self._get_model().get_sentence_embedding_dimension()  # type: ignore[return-value]
