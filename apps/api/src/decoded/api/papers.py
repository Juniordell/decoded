"""Endpoints de papers: feed, detalhe e sitemap."""

from __future__ import annotations

import hashlib
from datetime import datetime

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from decoded.api.deps import rate_limited
from decoded.api.schemas import (
    AuthorOut,
    FeedResponse,
    PaperCard,
    PaperDetail,
)
from decoded.cache.client import cache_get, cache_set
from decoded.db.base import get_session
from decoded.db.models import DecodedContent, Paper
from decoded.decoding.prompts import VERSION as PROMPT_VERSION

logger = structlog.get_logger()

router = APIRouter(prefix="/v1/papers", tags=["papers"])

FEED_CACHE_TTL = 300      # 5 minutos, alinhado com o ISR do frontend
PAPER_CACHE_TTL = 3600    # 1 hora, conteúdo decodificado é estável


# ============================================================
# Helpers
# ============================================================
async def _decoded_map_for(
    session: AsyncSession, paper_ids: list[int]
) -> dict[int, dict[str, dict]]:
    """Carrega todas as seções decodificadas para um conjunto de papers."""
    if not paper_ids:
        return {}

    stmt = select(DecodedContent).where(
        DecodedContent.paper_id.in_(paper_ids),
        DecodedContent.prompt_version == PROMPT_VERSION,
    )
    result = await session.execute(stmt)

    out: dict[int, dict[str, dict]] = {}
    for row in result.scalars().all():
        out.setdefault(row.paper_id, {})[row.section] = row.content
    return out


def _feed_cache_key(
    limit: int, offset: int, category: str | None, decoded_only: bool
) -> str:
    raw = f"{limit}:{offset}:{category or ''}:{decoded_only}"
    digest = hashlib.sha256(raw.encode()).hexdigest()[:16]
    return f"feed:{digest}"


# ============================================================
# Feed
# ============================================================
@router.get("", response_model=FeedResponse)
async def list_papers(
    limit: int = Query(default=20, ge=1, le=50),
    offset: int = Query(default=0, ge=0),
    category: str | None = Query(default=None, description="Filtra por categoria arXiv"),
    decoded_only: bool = Query(default=False, description="Só papers já decodificados"),
    session: AsyncSession = Depends(get_session),
    _rl: None = Depends(rate_limited("default")),
) -> FeedResponse:
    """Feed principal, ordenado por priority_score. Cacheado por 5 minutos."""
    cache_key = _feed_cache_key(limit, offset, category, decoded_only)

    cached = await cache_get(cache_key)
    if cached is not None:
        logger.info("feed.cache_hit", key=cache_key)
        return FeedResponse.model_validate(cached)

    stmt = select(Paper).options(selectinload(Paper.authors))

    if category:
        stmt = stmt.where(Paper.categories.any(category))

    if decoded_only:
        decoded_ids = select(DecodedContent.paper_id).where(
            DecodedContent.section == "one_sentence",
            DecodedContent.prompt_version == PROMPT_VERSION,
        )
        stmt = stmt.where(Paper.id.in_(decoded_ids))

    count_stmt = select(func.count()).select_from(stmt.subquery())
    total = (await session.execute(count_stmt)).scalar_one()

    stmt = (
        stmt.order_by(Paper.priority_score.desc(), Paper.published_at.desc())
        .limit(limit + 1)
        .offset(offset)
    )
    result = await session.execute(stmt)
    papers = list(result.scalars().all())

    has_more = len(papers) > limit
    papers = papers[:limit]

    decoded_map = await _decoded_map_for(session, [p.id for p in papers])

    cards = []
    for p in papers:
        sections = decoded_map.get(p.id, {})
        one_sentence = (sections.get("one_sentence") or {}).get("text")

        cards.append(
            PaperCard(
                arxiv_id=p.arxiv_id,
                title=p.title,
                one_sentence=one_sentence,
                authors=[a.name for a in p.authors[:5]],
                published_at=p.published_at,
                categories=p.categories or [],
                priority_score=p.priority_score,
                citation_count=p.citation_count,
                hn_mentions=p.hn_mentions,
                is_decoded=bool(sections),
                decoded_sections=sorted(sections.keys()),
            )
        )

    response = FeedResponse(
        papers=cards,
        total=total,
        has_more=has_more,
        next_cursor=str(offset + limit) if has_more else None,
    )

    await cache_set(cache_key, response.model_dump(mode="json"), FEED_CACHE_TTL)
    return response


# ============================================================
# Detalhe
# ============================================================
@router.get("/{arxiv_id}", response_model=PaperDetail)
async def get_paper(
    arxiv_id: str,
    session: AsyncSession = Depends(get_session),
    _rl: None = Depends(rate_limited("default")),
) -> PaperDetail:
    """Detalhe completo de um paper, com todo o conteúdo decodificado."""
    cache_key = f"paper:{arxiv_id}:{PROMPT_VERSION}"

    cached = await cache_get(cache_key)
    if cached is not None:
        logger.info("paper.cache_hit", arxiv_id=arxiv_id)
        return PaperDetail.model_validate(cached)

    stmt = (
        select(Paper)
        .options(selectinload(Paper.authors))
        .where(Paper.arxiv_id == arxiv_id)
    )
    result = await session.execute(stmt)
    paper = result.scalar_one_or_none()

    if paper is None:
        raise HTTPException(status_code=404, detail=f"Paper {arxiv_id} não encontrado")

    decoded_map = await _decoded_map_for(session, [paper.id])
    sections = decoded_map.get(paper.id, {})

    decoded_at: datetime | None = None
    if sections:
        ts_stmt = select(func.max(DecodedContent.created_at)).where(
            DecodedContent.paper_id == paper.id,
            DecodedContent.prompt_version == PROMPT_VERSION,
        )
        decoded_at = (await session.execute(ts_stmt)).scalar_one_or_none()

    hn_url = ((paper.extra or {}).get("hn") or {}).get("top_story_url")

    response = PaperDetail(
        arxiv_id=paper.arxiv_id,
        title=paper.title,
        abstract=paper.abstract,
        authors=[
            AuthorOut(name=a.name, affiliation=a.affiliation) for a in paper.authors
        ],
        published_at=paper.published_at,
        categories=paper.categories or [],
        pdf_url=paper.pdf_url,
        priority_score=paper.priority_score,
        citation_count=paper.citation_count,
        hn_mentions=paper.hn_mentions,
        hn_url=hn_url,
        decoded=sections,
        decoded_at=decoded_at,
    )

    # Só cacheia papers decodificados — os pendentes mudam quando decodificam
    if sections:
        await cache_set(cache_key, response.model_dump(mode="json"), PAPER_CACHE_TTL)

    return response


# ============================================================
# Sitemap
# ============================================================
class SitemapEntry(BaseModel):
    arxiv_id: str
    updated_at: datetime
    is_decoded: bool


class SitemapResponse(BaseModel):
    entries: list[SitemapEntry]
    total: int


@router.get("/sitemap/entries", response_model=SitemapResponse)
async def sitemap_entries(
    limit: int = Query(default=5000, ge=1, le=50000),
    session: AsyncSession = Depends(get_session),
) -> SitemapResponse:
    """
    Lista enxuta pro sitemap. Papers decodificados marcados, porque
    recebem prioridade maior no XML gerado pelo frontend.
    """
    cache_key = f"sitemap:{limit}:{PROMPT_VERSION}"

    cached = await cache_get(cache_key)
    if cached is not None:
        return SitemapResponse.model_validate(cached)

    decoded_ids_stmt = select(DecodedContent.paper_id).where(
        DecodedContent.section == "one_sentence",
        DecodedContent.prompt_version == PROMPT_VERSION,
    )
    decoded_ids = set((await session.execute(decoded_ids_stmt)).scalars().all())

    stmt = (
        select(Paper.id, Paper.arxiv_id, Paper.updated_at)
        .order_by(Paper.priority_score.desc(), Paper.published_at.desc())
        .limit(limit)
    )
    rows = (await session.execute(stmt)).all()

    entries = [
        SitemapEntry(
            arxiv_id=row.arxiv_id,
            updated_at=row.updated_at,
            is_decoded=row.id in decoded_ids,
        )
        for row in rows
    ]

    response = SitemapResponse(entries=entries, total=len(entries))
    await cache_set(cache_key, response.model_dump(mode="json"), FEED_CACHE_TTL)
    return response