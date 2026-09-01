from __future__ import annotations

from datetime import datetime

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, Field
from sqlalchemy import desc, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from decoded.api.deps import rate_limited
from decoded.cache.client import cache_get, cache_set
from decoded.db.base import get_session
from decoded.db.models import Paper, Podcast, PodcastStatus
from decoded.podcast.prompts import PODCAST_PROMPT_VERSION
from decoded.podcast.schemas import PODCAST_SCHEMA_VERSION
from decoded.config import settings
from decoded.podcast.rss import build_feed

logger = structlog.get_logger()

router = APIRouter(prefix="/v1/podcasts", tags=["podcasts"])

CACHE_TTL = 3600


class ChapterOut(BaseModel):
    title: str
    start_seconds: int
    end_seconds: int


class PodcastOut(BaseModel):
    arxiv_id: str
    title: str
    status: str
    audio_url: str | None = None
    duration_seconds: int | None = None
    chapters: list[ChapterOut] = Field(default_factory=list)
    published_at: datetime | None = None


class PodcastListItem(BaseModel):
    arxiv_id: str
    title: str
    one_sentence: str | None = None
    audio_url: str
    duration_seconds: int
    published_at: datetime


class PodcastListResponse(BaseModel):
    episodes: list[PodcastListItem] = Field(default_factory=list)
    total: int


@router.get("/feed.xml", include_in_schema=False)
async def podcast_feed(
    session: AsyncSession = Depends(get_session),
) -> Response:
    """
    Feed RSS.

    Sem rate limit: apps de podcast fazem polling agressivo, e bloquear
    um cliente significa o assinante parar de receber episódios.
    """
    cached = await cache_get("podcasts:feed")
    if cached is not None:
        return Response(content=cached["xml"], media_type="application/rss+xml")

    from decoded.db.models import DecodedContent
    from decoded.decoding.prompts import VERSION as DECODE_VERSION

    rows = (
        await session.execute(
            select(Podcast, Paper)
            .join(Paper, Paper.id == Podcast.paper_id)
            .where(
                Podcast.status == PodcastStatus.READY,
                Podcast.audio_url.isnot(None),
            )
            .order_by(desc(Paper.published_at))
            .limit(300)
        )
    ).all()

    descriptions: dict[int, str] = {}
    if rows:
        for dc in (
            await session.execute(
                select(DecodedContent).where(
                    DecodedContent.paper_id.in_([p.id for _pod, p in rows]),
                    DecodedContent.section == "one_sentence",
                    DecodedContent.prompt_version == DECODE_VERSION,
                )
            )
        ).scalars().all():
            text = (dc.content or {}).get("text")
            if text:
                descriptions[dc.paper_id] = text

    episodes = [
        {
            "arxiv_id": paper.arxiv_id,
            "title": paper.title,
            "description": descriptions.get(paper.id, paper.title),
            "audio_url": podcast.audio_url,
            "duration_seconds": podcast.duration_seconds or 0,
            "size_bytes": podcast.audio_bytes or 0,
            "published_at": paper.published_at,
        }
        for podcast, paper in rows
    ]

    xml = build_feed(
        episodes=episodes,
        site_url=settings.site_url,
        feed_url=f"{settings.site_url}/feed.xml",
        cover_url=f"{settings.site_url}/podcast-cover.png",
    )

    await cache_set("podcasts:feed", {"xml": xml}, CACHE_TTL)

    return Response(content=xml, media_type="application/rss+xml")


@router.get("", response_model=PodcastListResponse)
async def list_podcasts(
    limit: int = Query(default=50, ge=1, le=200),
    session: AsyncSession = Depends(get_session),
    _rl: None = Depends(rate_limited("default")),
) -> PodcastListResponse:
    """Episódios prontos, mais recentes primeiro."""
    cache_key = f"podcasts:list:{limit}"
    cached = await cache_get(cache_key)
    if cached is not None:
        return PodcastListResponse.model_validate(cached)

    from decoded.db.models import DecodedContent
    from decoded.decoding.prompts import VERSION as DECODE_VERSION

    rows = (
        await session.execute(
            select(Podcast, Paper)
            .join(Paper, Paper.id == Podcast.paper_id)
            .where(
                Podcast.status == PodcastStatus.READY,
                Podcast.audio_url.isnot(None),
            )
            .order_by(desc(Paper.published_at))
            .limit(limit)
        )
    ).all()

    if not rows:
        return PodcastListResponse(episodes=[], total=0)

    paper_ids = [p.id for _pod, p in rows]
    one_sentences: dict[int, str] = {}
    for dc in (
        await session.execute(
            select(DecodedContent).where(
                DecodedContent.paper_id.in_(paper_ids),
                DecodedContent.section == "one_sentence",
                DecodedContent.prompt_version == DECODE_VERSION,
            )
        )
    ).scalars().all():
        text = (dc.content or {}).get("text")
        if text:
            one_sentences[dc.paper_id] = text

    episodes = [
        PodcastListItem(
            arxiv_id=paper.arxiv_id,
            title=paper.title,
            one_sentence=one_sentences.get(paper.id),
            audio_url=podcast.audio_url,
            duration_seconds=podcast.duration_seconds or 0,
            published_at=paper.published_at,
        )
        for podcast, paper in rows
    ]

    response = PodcastListResponse(episodes=episodes, total=len(episodes))
    await cache_set(cache_key, response.model_dump(mode="json"), CACHE_TTL)
    return response


@router.get("/{arxiv_id}", response_model=PodcastOut)
async def get_podcast(
    arxiv_id: str,
    session: AsyncSession = Depends(get_session),
    _rl: None = Depends(rate_limited("default")),
) -> PodcastOut:
    """Episódio de um paper. Retorna status mesmo quando não está pronto."""
    row = (
        await session.execute(
            select(Podcast, Paper.title, Paper.published_at)
            .join(Paper, Paper.id == Podcast.paper_id)
            .where(
                Paper.arxiv_id == arxiv_id,
                Podcast.schema_version == PODCAST_SCHEMA_VERSION,
                Podcast.prompt_version == PODCAST_PROMPT_VERSION,
            )
        )
    ).one_or_none()

    if row is None:
        return PodcastOut(arxiv_id=arxiv_id, title="", status="pending")

    podcast, title, published_at = row

    return PodcastOut(
        arxiv_id=arxiv_id,
        title=title,
        status=podcast.status.value,
        audio_url=podcast.audio_url if podcast.status == PodcastStatus.READY else None,
        duration_seconds=podcast.duration_seconds,
        chapters=[ChapterOut(**c) for c in (podcast.chapters or [])],
        published_at=published_at,
    )


@router.post("/{arxiv_id}/play", status_code=204)
async def record_play(
    arxiv_id: str,
    session: AsyncSession = Depends(get_session),
    _rl: None = Depends(rate_limited("default")),
) -> None:
    """
    Registra um play.

    Disparado quando o áudio realmente começa a tocar, não no clique —
    a diferença entre intenção e escuta.
    """
    paper_id = (
        await session.execute(select(Paper.id).where(Paper.arxiv_id == arxiv_id))
    ).scalar_one_or_none()

    if paper_id is None:
        return

    await session.execute(
        update(Podcast)
        .where(
            Podcast.paper_id == paper_id,
            Podcast.schema_version == PODCAST_SCHEMA_VERSION,
            Podcast.prompt_version == PODCAST_PROMPT_VERSION,
        )
        .values(play_count=Podcast.play_count + 1)
    )
    await session.commit()