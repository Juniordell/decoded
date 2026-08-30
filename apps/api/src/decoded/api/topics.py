from __future__ import annotations

import hashlib
from datetime import datetime, timedelta, timezone

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import case, desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from decoded.api.deps import rate_limited
from decoded.api.schemas import (
    PaperCard,
    PulseResponse,
    TopicAuthor,
    TopicCard,
    TopicDetail,
    TopicPoint,
    TopicsListResponse,
)
from decoded.cache.client import cache_get, cache_set
from decoded.db.base import get_session
from decoded.db.models import (
    Author,
    DecodedContent,
    Paper,
    Topic,
    TopicSnapshot,
    paper_authors,
    paper_topics,
)
from decoded.decoding.prompts import VERSION as PROMPT_VERSION
from decoded.topics.snapshots import week_start

logger = structlog.get_logger()

router = APIRouter(prefix="/v1/topics", tags=["topics"])

TOPICS_CACHE_TTL = 1800  # 30 min — clustering roda semanalmente
MOMENTUM_WEEKS = 4


async def _momentum_for(
    session: AsyncSession,
    topic_ids: list[int],
    weeks: int = MOMENTUM_WEEKS,
) -> dict[int, tuple[int, int, float, str]]:
    """
    Momentum em batch. Retorna {topic_id: (recentes, anteriores, variação, rótulo)}.

    Uma query para as duas janelas em vez de duas por tópico.
    """
    if not topic_ids:
        return {}

    current = week_start(datetime.now(timezone.utc))
    recent_start = current - timedelta(weeks=weeks)
    prior_start = recent_start - timedelta(weeks=weeks)

    stmt = (
        select(
            TopicSnapshot.topic_id,
            func.sum(
                case(
                    (TopicSnapshot.window_start >= recent_start, TopicSnapshot.paper_count),
                    else_=0,
                )
            ).label("recent"),
            func.sum(
                case(
                    (
                        (TopicSnapshot.window_start >= prior_start)
                        & (TopicSnapshot.window_start < recent_start),
                        TopicSnapshot.paper_count,
                    ),
                    else_=0,
                )
            ).label("prior"),
        )
        .where(
            TopicSnapshot.topic_id.in_(topic_ids),
            TopicSnapshot.window_start >= prior_start,
        )
        .group_by(TopicSnapshot.topic_id)
    )

    out: dict[int, tuple[int, int, float, str]] = {}
    for row in (await session.execute(stmt)).all():
        recent = int(row.recent or 0)
        prior = int(row.prior or 0)

        if prior == 0:
            change = 1.0 if recent >= 3 else 0.0
            label = "new" if recent >= 3 else "quiet"
        else:
            change = (recent - prior) / prior
            label = (
                "rising" if change > 0.25
                else "cooling" if change < -0.25
                else "steady"
            )

        out[int(row.topic_id)] = (recent, prior, round(change, 3), label)

    for tid in topic_ids:
        out.setdefault(tid, (0, 0, 0.0, "quiet"))

    return out


def _to_card(topic: Topic, momentum: tuple[int, int, float, str]) -> TopicCard:
    recent, _prior, change, label = momentum
    return TopicCard(
        slug=topic.slug,
        name=topic.name,
        description=topic.description,
        keywords=(topic.keywords or [])[:6],
        paper_count=topic.paper_count,
        recent_papers=recent,
        momentum=change,
        momentum_label=label,
    )


@router.get("", response_model=TopicsListResponse)
async def list_topics(
    sort: str = Query(default="size", pattern="^(size|momentum|name)$"),
    limit: int = Query(default=60, ge=1, le=200),
    session: AsyncSession = Depends(get_session),
    _rl: None = Depends(rate_limited("default")),
) -> TopicsListResponse:
    """Todos os tópicos ativos."""
    cache_key = f"topics:list:{sort}:{limit}"
    cached = await cache_get(cache_key)
    if cached is not None:
        return TopicsListResponse.model_validate(cached)

    stmt = select(Topic).where(Topic.is_active.is_(True))
    if sort == "name":
        stmt = stmt.order_by(Topic.name)
    else:
        stmt = stmt.order_by(desc(Topic.paper_count))
    stmt = stmt.limit(limit)

    topics = list((await session.execute(stmt)).scalars().all())
    momentum = await _momentum_for(session, [t.id for t in topics])

    cards = [_to_card(t, momentum[t.id]) for t in topics]

    if sort == "momentum":
        cards.sort(key=lambda c: -c.momentum)

    clustered_at = max(
        (t.last_clustered_at for t in topics if t.last_clustered_at),
        default=None,
    )

    response = TopicsListResponse(
        topics=cards,
        total=len(cards),
        clustered_at=clustered_at,
    )
    await cache_set(cache_key, response.model_dump(mode="json"), TOPICS_CACHE_TTL)
    return response


@router.get("/pulse", response_model=PulseResponse)
async def field_pulse(
    session: AsyncSession = Depends(get_session),
    _rl: None = Depends(rate_limited("default")),
) -> PulseResponse:
    """
    Visão geral: o que está subindo, esfriando, emergindo, e o que é maior.

    Esta é a home do Field Pulse.
    """
    cached = await cache_get("topics:pulse")
    if cached is not None:
        return PulseResponse.model_validate(cached)

    topics = list(
        (
            await session.execute(select(Topic).where(Topic.is_active.is_(True)))
        ).scalars().all()
    )

    if not topics:
        return PulseResponse(total_topics=0, total_papers=0, weeks_covered=0)

    momentum = await _momentum_for(session, [t.id for t in topics])
    cards = [(t, _to_card(t, momentum[t.id])) for t in topics]

    # Tópicos com histórico dos dois lados podem ser comparados
    with_history = [
        c for t, c in cards
        if momentum[t.id][1] > 0 and momentum[t.id][0] + momentum[t.id][1] >= 4
    ]
    rising = sorted(
        [c for c in with_history if c.momentum_label == "rising"],
        key=lambda c: -c.momentum,
    )[:6]
    cooling = sorted(
        [c for c in with_history if c.momentum_label == "cooling"],
        key=lambda c: c.momentum,
    )[:6]

    # Sem histórico anterior — novos, não em ascensão
    emerging = sorted(
        [c for t, c in cards if momentum[t.id][3] == "new"],
        key=lambda c: -c.recent_papers,
    )[:6]

    largest = sorted([c for _t, c in cards], key=lambda c: -c.paper_count)[:8]

    weeks = (
        await session.execute(
            select(func.count(func.distinct(TopicSnapshot.window_start)))
        )
    ).scalar_one()

    total_papers = sum(t.paper_count for t in topics)

    response = PulseResponse(
        rising=rising,
        cooling=cooling,
        emerging=emerging,
        largest=largest,
        total_topics=len(topics),
        total_papers=total_papers,
        weeks_covered=int(weeks or 0),
        clustered_at=max(
            (t.last_clustered_at for t in topics if t.last_clustered_at),
            default=None,
        ),
    )
    await cache_set("topics:pulse", response.model_dump(mode="json"), TOPICS_CACHE_TTL)
    return response


@router.get("/{slug}", response_model=TopicDetail)
async def get_topic(
    slug: str,
    paper_limit: int = Query(default=20, ge=1, le=50),
    weeks: int = Query(default=12, ge=4, le=52),
    session: AsyncSession = Depends(get_session),
    _rl: None = Depends(rate_limited("default")),
) -> TopicDetail:
    """Detalhe de um tópico: série temporal, autores, papers."""
    digest = hashlib.sha256(f"{slug}:{paper_limit}:{weeks}".encode()).hexdigest()[:12]
    cache_key = f"topics:detail:{digest}"
    cached = await cache_get(cache_key)
    if cached is not None:
        return TopicDetail.model_validate(cached)

    topic = (
        await session.execute(select(Topic).where(Topic.slug == slug))
    ).scalar_one_or_none()

    if topic is None:
        raise HTTPException(status_code=404, detail=f"Tópico {slug} não encontrado")

    momentum = (await _momentum_for(session, [topic.id]))[topic.id]
    recent, prior, change, label = momentum

    # --- Série temporal ---
    cutoff = week_start(datetime.now(timezone.utc)) - timedelta(weeks=weeks)
    snap_stmt = (
        select(TopicSnapshot)
        .where(
            TopicSnapshot.topic_id == topic.id,
            TopicSnapshot.window_start >= cutoff,
        )
        .order_by(TopicSnapshot.window_start)
    )
    snapshots = list((await session.execute(snap_stmt)).scalars().all())

    # Preenche semanas sem papers com zero — senão o gráfico mente
    by_week = {s.window_start: s for s in snapshots}
    timeline: list[TopicPoint] = []
    current = week_start(datetime.now(timezone.utc))
    for w in range(weeks):
        wk = cutoff + timedelta(weeks=w)
        if wk > current:
            break
        s = by_week.get(wk)
        timeline.append(
            TopicPoint(
                week=wk,
                papers=s.paper_count if s else 0,
                citations=s.total_citations if s else 0,
                mean_priority=round(s.mean_priority, 2) if s else 0.0,
                hn_mentions=s.hn_mentions if s else 0,
            )
        )

    # --- Autores dominantes ---
    author_stmt = (
        select(
            Author.name,
            Author.affiliation,
            func.count(Paper.id).label("papers"),
            func.coalesce(func.sum(Paper.citation_count), 0).label("citations"),
        )
        .join(paper_authors, paper_authors.c.author_id == Author.id)
        .join(Paper, Paper.id == paper_authors.c.paper_id)
        .join(paper_topics, paper_topics.c.paper_id == Paper.id)
        .where(paper_topics.c.topic_id == topic.id)
        .group_by(Author.id, Author.name, Author.affiliation)
        .order_by(desc("papers"), desc("citations"))
        .limit(8)
    )
    top_authors = [
        TopicAuthor(
            name=r.name,
            affiliation=r.affiliation,
            paper_count=int(r.papers),
            total_citations=int(r.citations),
        )
        for r in (await session.execute(author_stmt)).all()
    ]

    # --- Papers ---
    paper_stmt = (
        select(Paper)
        .join(paper_topics, paper_topics.c.paper_id == Paper.id)
        .where(paper_topics.c.topic_id == topic.id)
        .order_by(desc(Paper.priority_score), desc(Paper.published_at))
        .limit(paper_limit)
    )
    papers = list((await session.execute(paper_stmt)).scalars().all())

    # one_sentence em batch
    one_sentences: dict[int, str] = {}
    section_counts: dict[int, int] = {}
    if papers:
        dc_stmt = select(DecodedContent).where(
            DecodedContent.paper_id.in_([p.id for p in papers]),
            DecodedContent.prompt_version == PROMPT_VERSION,
        )
        for row in (await session.execute(dc_stmt)).scalars().all():
            section_counts[row.paper_id] = section_counts.get(row.paper_id, 0) + 1
            if row.section == "one_sentence":
                text = (row.content or {}).get("text")
                if text:
                    one_sentences[row.paper_id] = text

    cards = [
        PaperCard(
            arxiv_id=p.arxiv_id,
            title=p.title,
            one_sentence=one_sentences.get(p.id),
            authors=[],
            published_at=p.published_at,
            categories=p.categories or [],
            priority_score=p.priority_score,
            citation_count=p.citation_count,
            hn_mentions=p.hn_mentions,
            is_decoded=section_counts.get(p.id, 0) > 0,
            decoded_sections=[],
        )
        for p in papers
    ]

    response = TopicDetail(
        slug=topic.slug,
        name=topic.name,
        description=topic.description,
        keywords=topic.keywords or [],
        paper_count=topic.paper_count,
        recent_papers=recent,
        prior_papers=prior,
        momentum=change,
        momentum_label=label,
        timeline=timeline,
        top_authors=top_authors,
        papers=cards,
        last_clustered_at=topic.last_clustered_at,
    )

    await cache_set(cache_key, response.model_dump(mode="json"), TOPICS_CACHE_TTL)
    return response