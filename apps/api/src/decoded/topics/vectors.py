from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import structlog
from qdrant_client import AsyncQdrantClient

from decoded.embeddings.qdrant_setup import ABSTRACTS_COLLECTION

logger = structlog.get_logger()


@dataclass
class PaperVectors:
    arxiv_ids: list[str]
    paper_ids: list[int]
    titles: list[str]
    abstracts_text: list[str]
    vectors: np.ndarray


async def fetch_paper_vectors(
    qdrant_url: str,
    qdrant_api_key: str | None,
    limit: int = 5000,
) -> PaperVectors:
    """
    Puxa todos os vetores de abstract com payload.

    Usa scroll em vez de search — queremos tudo, não os mais próximos
    de alguma query.
    """
    client = AsyncQdrantClient(url=qdrant_url, api_key=qdrant_api_key)

    arxiv_ids: list[str] = []
    paper_ids: list[int] = []
    titles: list[str] = []
    vectors: list[list[float]] = []

    offset = None
    fetched = 0

    try:
        while fetched < limit:
            batch_size = min(256, limit - fetched)
            points, offset = await client.scroll(
                collection_name=ABSTRACTS_COLLECTION,
                limit=batch_size,
                offset=offset,
                with_payload=True,
                with_vectors=True,
            )

            if not points:
                break

            for point in points:
                payload = point.payload or {}
                vec = point.vector

                # Coleção com vetor único devolve lista direto;
                # com vetores nomeados devolve dict
                if isinstance(vec, dict):
                    vec = next(iter(vec.values()), None)
                if not vec:
                    continue

                arxiv_ids.append(payload.get("arxiv_id", ""))
                paper_ids.append(payload.get("paper_id", 0))
                titles.append(payload.get("title", ""))
                vectors.append(vec)

            fetched += len(points)

            if offset is None:
                break

    finally:
        await client.close()

    logger.info("vectors.fetched", count=len(vectors))

    return PaperVectors(
        arxiv_ids=arxiv_ids,
        paper_ids=paper_ids,
        titles=titles,
        abstracts_text=titles,  # preenchido pelo caller a partir do Postgres
        vectors=np.array(vectors, dtype=np.float32) if vectors else np.empty((0, 0)),
    )