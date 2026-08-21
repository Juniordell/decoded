from __future__ import annotations

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from decoded.api.schemas import SearchHit, SearchResponse
from decoded.config import settings
from decoded.db.base import get_session
from decoded.search.engine import SearchEngine

logger = structlog.get_logger()

router = APIRouter(prefix="/v1/search", tags=["search"])


@router.get("", response_model=SearchResponse)
async def search(
    q: str = Query(..., min_length=2, max_length=300, description="Query de busca"),
    limit: int = Query(default=10, ge=1, le=25),
    category: str | None = Query(default=None),
    session: AsyncSession = Depends(get_session),
) -> SearchResponse:
    if not settings.openai_api_key:
        raise HTTPException(status_code=503, detail="Busca indisponível: OPENAI_API_KEY ausente")

    categories = [category] if category else None

    async with SearchEngine(
        openai_api_key=settings.openai_api_key,
        qdrant_url=settings.qdrant_url,
        embedding_model=settings.embedding_model_large,
        cohere_api_key=settings.cohere_api_key,
        rerank_model=settings.rerank_model,
    ) as engine:
        outcome = await engine.search(
            session=session,
            query=q,
            retrieve_k=settings.search_retrieve_k,
            return_k=limit,
            categories=categories,
            chunk_embedding_model=settings.embedding_model_small,
        )

    return SearchResponse(
        query=q,
        hits=[
            SearchHit(
                arxiv_id=r.arxiv_id,
                title=r.title,
                one_sentence=r.one_sentence,
                snippet=r.snippet,
                section=r.section,
                score=r.score,
                published_at=r.published_at,
            )
            for r in outcome.results
        ],
        total_found=outcome.total_found,
        reranked=outcome.reranked,
        latency_ms=outcome.latency_ms,
    )