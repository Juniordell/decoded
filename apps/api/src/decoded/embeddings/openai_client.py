from __future__ import annotations

import asyncio

import structlog
from openai import AsyncOpenAI
from tenacity import retry, stop_after_attempt, wait_exponential

logger = structlog.get_logger()


class EmbeddingsClient:
    def __init__(self, api_key: str) -> None:
        self._client = AsyncOpenAI(api_key=api_key)

    async def close(self) -> None:
        await self._client.close()

    async def __aenter__(self) -> "EmbeddingsClient":
        return self

    async def __aexit__(self, *args) -> None:
        await self.close()

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=15),
        reraise=True,
    )
    async def embed(self, texts: list[str], model: str) -> list[list[float]]:
        """Embed a batch of texts. Returns vectors in same order."""
        if not texts:
            return []
        resp = await self._client.embeddings.create(model=model, input=texts)
        return [d.embedding for d in resp.data]

    async def embed_batched(
        self,
        texts: list[str],
        model: str,
        batch_size: int = 100,
    ) -> list[list[float]]:
        """Embed a large list, chunked into API-friendly batches."""
        vectors: list[list[float]] = []
        for i in range(0, len(texts), batch_size):
            batch = texts[i : i + batch_size]
            vectors.extend(await self.embed(batch, model))
        return vectors