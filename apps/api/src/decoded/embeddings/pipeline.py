from __future__ import annotations

import uuid

import structlog
from qdrant_client import AsyncQdrantClient
from qdrant_client.models import PointStruct
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from decoded.db.base import async_session_factory
from decoded.db.models import IngestionStatus, Paper, RunStatus
from decoded.db.repositories.ingestion_runs import IngestionRunsRepository
from decoded.embeddings.chunker import chunk_markdown
from decoded.embeddings.openai_client import EmbeddingsClient
from decoded.embeddings.qdrant_setup import (
    ABSTRACTS_COLLECTION,
    CHUNKS_COLLECTION,
    ensure_collections,
)

logger = structlog.get_logger()


def _point_id(*parts: str | int) -> str:
    """Deterministic UUID from parts — so re-embedding overwrites."""
    return str(uuid.uuid5(uuid.NAMESPACE_URL, ":".join(str(p) for p in parts)))


async def embed_parsed_papers(
    openai_api_key: str,
    qdrant_url: str,
    embedding_model_small: str,
    embedding_model_large: str,
    limit: int = 10,
    qdrant_api_key: str | None = None,
) -> dict:
    """
    Embed the next N papers with status=PARSED.
    Push abstract vectors to paper_abstracts collection.
    Push chunk vectors to paper_chunks collection.
    """
    log = logger.bind(source="embedder")
    log.info("embed.start", limit=limit)

    qdrant = AsyncQdrantClient(url=qdrant_url, api_key=qdrant_api_key)
    await ensure_collections(qdrant)

    async with async_session_factory() as session, EmbeddingsClient(openai_api_key) as embedder:
        runs_repo = IngestionRunsRepository(session)
        run = await runs_repo.start(source="embedder")
        await session.commit()

        stmt = (
            select(Paper)
            .options(selectinload(Paper.parsed_content))
            .where(Paper.status == IngestionStatus.PARSED)
            .order_by(Paper.priority_score.desc(), Paper.published_at.desc())
            .limit(limit)
        )
        result = await session.execute(stmt)
        papers = list(result.scalars().all())

        log.info("embed.papers_selected", count=len(papers))

        embedded = 0
        errors = 0

        for paper in papers:
            paper_log = log.bind(arxiv_id=paper.arxiv_id)
            try:
                # 1. Abstract embedding (title + abstract, large model)
                abstract_text = f"{paper.title}\n\n{paper.abstract}"
                [abstract_vec] = await embedder.embed(
                    [abstract_text], model=embedding_model_large
                )

                await qdrant.upsert(
                    collection_name=ABSTRACTS_COLLECTION,
                    points=[
                        PointStruct(
                            id=_point_id("abstract", paper.arxiv_id),
                            vector=abstract_vec,
                            payload={
                                "paper_id": paper.id,
                                "arxiv_id": paper.arxiv_id,
                                "title": paper.title,
                                "published_at": paper.published_at.isoformat(),
                                "categories": paper.categories,
                                "priority_score": paper.priority_score,
                            },
                        )
                    ],
                )

                # 2. Chunk embeddings (small model, many vectors)
                if paper.parsed_content and paper.parsed_content.markdown:
                    chunks = chunk_markdown(paper.parsed_content.markdown)
                    if chunks:
                        chunk_vecs = await embedder.embed_batched(
                            [c.text for c in chunks],
                            model=embedding_model_small,
                            batch_size=100,
                        )
                        await qdrant.upsert(
                            collection_name=CHUNKS_COLLECTION,
                            points=[
                                PointStruct(
                                    id=_point_id("chunk", paper.arxiv_id, c.order),
                                    vector=vec,
                                    payload={
                                        "paper_id": paper.id,
                                        "arxiv_id": paper.arxiv_id,
                                        "order": c.order,
                                        "section": c.section,
                                        "text": c.text,
                                    },
                                )
                                for c, vec in zip(chunks, chunk_vecs)
                            ],
                        )
                        paper_log.info("embed.chunks_ok", count=len(chunks))
                    else:
                        paper_log.warning("embed.no_chunks")
                else:
                    paper_log.warning("embed.no_parsed_content")

                paper.status = IngestionStatus.EMBEDDED
                await session.commit()
                embedded += 1
                paper_log.info("embed.paper_ok")

            except Exception as e:
                errors += 1
                paper_log.error("embed.failed", error=str(e))
                await session.rollback()

        await runs_repo.finish(
            run,
            status=RunStatus.SUCCESS,
            papers_found=len(papers),
            papers_new=embedded,
            errors=errors,
        )
        await session.commit()

    await qdrant.close()

    log.info("embed.done", embedded=embedded, errors=errors)
    return {"embedded": embedded, "errors": errors}