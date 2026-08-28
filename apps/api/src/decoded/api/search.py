from __future__ import annotations

import hashlib

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from decoded.api.deps import rate_limited
from decoded.api.schemas import SearchHit, SearchResponse
from decoded.cache.client import cache_get, cache_set
from decoded.config import settings
from decoded.db.base import get_session
from decoded.observability.tracing import trace_span
from decoded.search.engine import SearchEngine

logger = structlog.get_logger()

router = APIRouter(prefix="/v1/search", tags=["search"])

SEARCH_CACHE_TTL = 900  # 15 minutos


def _cache_key(query: str, limit: int, category: str | None) -> str:
    """Normaliza a query antes de hashear — 'RLHF' e 'rlhf ' são a mesma busca."""
    normalized = " ".join(query.strip().lower().split())
    raw = f"{normalized}:{limit}:{category or ''}"
    digest = hashlib.sha256(raw.encode()).hexdigest()[:16]
    return f"search:{digest}"


@router.get("", response_model=SearchResponse)
async def search(
    q: str = Query(..., min_length=2, max_length=300, description="Query de busca"),
    limit: int = Query(default=10, ge=1, le=25),
    category: str | None = Query(default=None),
    session: AsyncSession = Depends(get_session),
    _rl: None = Depends(rate_limited("search")),
) -> SearchResponse:
    """
    Busca semântica sobre papers decodificados.

    Cacheada por 15 minutos. Um hit economiza dois embeddings da query
    (as duas coleções usam modelos diferentes) mais uma chamada ao reranker.
    """
    if not settings.openai_api_key:
        raise HTTPException(
            status_code=503,
            detail="Busca indisponível: OPENAI_API_KEY ausente",
        )

    cache_key = _cache_key(q, limit, category)
    cached = await cache_get(cache_key)
    if cached is not None:
        logger.info("search.cache_hit", query=q[:60])
        return SearchResponse.model_validate(cached)

    categories = [category] if category else None

    with trace_span(
        "search",
        input={"query": q, "category": category, "limit": limit},
        tags=["search"],
    ) as span:
        async with SearchEngine(
            openai_api_key=settings.openai_api_key,
            qdrant_url=settings.qdrant_url,
            embedding_model=settings.embedding_model_large,
            cohere_api_key=settings.cohere_api_key,
            rerank_model=settings.rerank_model,
            qdrant_api_key=settings.qdrant_api_key,
        ) as engine:
            outcome = await engine.search(
                session=session,
                query=q,
                retrieve_k=settings.search_retrieve_k,
                return_k=limit,
                categories=categories,
                chunk_embedding_model=settings.embedding_model_small,
            )

        span.update(
            output={
                "hits": len(outcome.results),
                "top_arxiv_ids": [r.arxiv_id for r in outcome.results[:5]],
            },
            metadata={
                "candidates": outcome.total_found,
                "reranked": outcome.reranked,
                "latency_ms": outcome.latency_ms,
            },
        )

    response = SearchResponse(
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

    # Só cacheia resultado útil. Busca vazia costuma ser typo — cachear
    # significaria servir o erro por 15 minutos depois de corrigido.
    if response.hits:
        await cache_set(cache_key, response.model_dump(mode="json"), SEARCH_CACHE_TTL)

    return response