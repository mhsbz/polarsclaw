"""OpenAI-compatible remote embedding provider."""

from __future__ import annotations

import logging
import os

import httpx
import numpy as np

from polarsclaw.memory.embeddings.base import EmbeddingProvider

logger = logging.getLogger(__name__)

_DEFAULT_BASE_URL = "https://api.openai.com/v1"
_MAX_RETRIES = 3
_BATCH_SIZE = 256


class OpenAIEmbeddingProvider(EmbeddingProvider):
    """Embedding provider that calls the OpenAI embeddings API."""

    def __init__(
        self,
        model: str = "text-embedding-3-small",
        dimension: int = 1536,
        *,
        api_key: str | None = None,
        base_url: str | None = None,
    ) -> None:
        self._model = model
        self._dimension = dimension
        self._api_key = api_key or os.environ.get("OPENAI_API_KEY", "")
        self._base_url = (base_url or os.environ.get("OPENAI_BASE_URL", _DEFAULT_BASE_URL)).rstrip("/")

    async def embed(self, texts: list[str]) -> np.ndarray:
        """Embed *texts* via the OpenAI API with batching and retry."""
        all_embeddings: list[list[float]] = []

        async with httpx.AsyncClient(timeout=60.0) as client:
            for start in range(0, len(texts), _BATCH_SIZE):
                batch = texts[start : start + _BATCH_SIZE]
                data = await self._request_with_retry(client, batch)
                # Sort by index to guarantee order
                data.sort(key=lambda d: d["index"])
                all_embeddings.extend(d["embedding"] for d in data)

        return np.array(all_embeddings, dtype=np.float32)

    async def _request_with_retry(
        self, client: httpx.AsyncClient, texts: list[str]
    ) -> list[dict]:
        last_exc: Exception | None = None
        for attempt in range(_MAX_RETRIES):
            try:
                resp = await client.post(
                    f"{self._base_url}/embeddings",
                    headers={
                        "Authorization": f"Bearer {self._api_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "input": texts,
                        "model": self._model,
                    },
                )
                resp.raise_for_status()
                return resp.json()["data"]  # type: ignore[no-any-return]
            except (httpx.HTTPStatusError, httpx.TransportError) as exc:
                last_exc = exc
                wait = 2 ** attempt
                logger.warning(
                    "OpenAI embedding request failed (attempt %d/%d): %s — retrying in %ds",
                    attempt + 1,
                    _MAX_RETRIES,
                    exc,
                    wait,
                )
                import asyncio
                await asyncio.sleep(wait)

        raise RuntimeError(
            f"OpenAI embedding request failed after {_MAX_RETRIES} attempts"
        ) from last_exc

    def dimension(self) -> int:
        return self._dimension
