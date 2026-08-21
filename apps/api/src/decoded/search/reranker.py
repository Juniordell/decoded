from __future__ import annotations

from dataclasses import dataclass

import cohere
import structlog
from tenacity import retry, stop_after_attempt, wait_exponential

logger = structlog.get_logger()


@dataclass
class RerankedDoc:
    index: int          # posição na lista original
    relevance_score: float


class Reranker:
    def __init__(self, api_key: str, model: str = "rerank-v3.5") -> None:
        self._client = cohere.AsyncClientV2(api_key=api_key)
        self._model = model

    async def close(self) -> None:
        pass  # o cliente da Cohere não expõe close explícito

    async def __aenter__(self) -> "Reranker":
        return self

    async def __aexit__(self, *args) -> None:
        await self.close()

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        reraise=True,
    )
    async def rerank(
        self,
        query: str,
        documents: list[str],
        top_n: int = 10,
    ) -> list[RerankedDoc]:
        """
        Reordena documentos por relevância à query.
        Retorna índices da lista original + score, em ordem decrescente.
        """
        if not documents:
            return []

        response = await self._client.rerank(
            model=self._model,
            query=query,
            documents=documents,
            top_n=min(top_n, len(documents)),
        )

        return [
            RerankedDoc(index=r.index, relevance_score=r.relevance_score)
            for r in response.results
        ]