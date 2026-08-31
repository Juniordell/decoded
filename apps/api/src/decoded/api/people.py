from __future__ import annotations

from typing import Optional

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import delete, desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from decoded.api.deps import rate_limited
from decoded.api.schemas import (
    AuthorCard,
    AuthorDetail,
    AuthorTopic,
    CoAuthor,
    FollowRequest,
    FollowResponse,
    InstitutionCard,
    InstitutionDetail,
    InstitutionsListResponse,
    PaperCard,
    PeopleListResponse,
)
from decoded.auth.clerk import get_current_user, get_optional_user
from decoded.cache.client import cache_get, cache_set
from decoded.db.base import get_session
from decoded.db.models import (
    Author,
    DecodedContent,
    Follow,
    Institution,
    Paper,
    Topic,
    User,
    paper_authors,
    paper_topics,
)
from decoded.decoding.prompts import VERSION as PROMPT_VERSION

logger = structlog.get_logger()

router = APIRouter(prefix="/v1", tags=["people"])

CACHE_TTL = 1800


async def _paper_cards(
    session: AsyncSession, papers: list[Paper]
) -> list[PaperCard]:
    """Monta cards com one_sentence em batch."""
    if not papers:
        return []

    one_sentences: dict[int, str] = {}
    section_counts: dict[int, int] = {}

    stmt = select(DecodedContent).where(
        DecodedContent.paper_id.in_([p.id for p in papers]),
        DecodedContent.prompt_version == PROMPT_VERSION,
    )
    for row in (await session.execute(stmt)).scalars().all():
        section_counts[row.paper_id] = section_counts.get(row.paper_id, 0) + 1
        if row.section == "one_sentence":
            text = (row.content or {}).get("text")
            if text:
                one_sentences[row.paper_id] = text

    return [
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


async def _is_following(
    session: AsyncSession,
    user: Optional[User],
    target_type: str,
    target_id: int,
) -> bool:
    if user is None:
        return False
    stmt = select(Follow.id).where(
        Follow.user_id == user.id,
        Follow.target_type == target_type,
        Follow.target_id == target_id,
    )
    return (await session.execute(stmt)).scalar_one_or_none() is not None


# ============================================================
# Autores
# ============================================================
@router.get("/authors", response_model=PeopleListResponse)
async def list_authors(
    limit: int = Query(default=50, ge=1, le=200),
    min_papers: int = Query(default=2, ge=1),
    session: AsyncSession = Depends(get_session),
    _rl: None = Depends(rate_limited("default")),
) -> PeopleListResponse:
    """Autores mais ativos no corpus."""
    cache_key = f"authors:list:{limit}:{min_papers}"
    cached = await cache_get(cache_key)
    if cached is not None:
        return PeopleListResponse.model_validate(cached)

    stmt = (
        select(Author)
        .where(Author.paper_count >= min_papers)
        .order_by(desc(Author.paper_count), desc(Author.total_citations))
        .limit(limit)
    )
    authors = list((await session.execute(stmt)).scalars().all())

    response = PeopleListResponse(
        authors=[
            AuthorCard(
                slug=a.slug,
                name=a.name,
                affiliation=a.affiliation,
                paper_count=a.paper_count,
                total_citations=a.total_citations,
                is_disambiguated=a.is_disambiguated,
            )
            for a in authors
        ],
        total=len(authors),
    )
    await cache_set(cache_key, response.model_dump(mode="json"), CACHE_TTL)
    return response


@router.get("/authors/{slug}", response_model=AuthorDetail)
async def get_author(
    slug: str,
    paper_limit: int = Query(default=20, ge=1, le=50),
    user: Optional[User] = Depends(get_optional_user),
    session: AsyncSession = Depends(get_session),
    _rl: None = Depends(rate_limited("default")),
) -> AuthorDetail:
    author = (
        await session.execute(select(Author).where(Author.slug == slug))
    ).scalar_one_or_none()

    if author is None:
        raise HTTPException(status_code=404, detail=f"Autor {slug} não encontrado")

    # --- Intervalo de publicação ---
    range_stmt = (
        select(
            func.min(Paper.published_at).label("first"),
            func.max(Paper.published_at).label("latest"),
        )
        .select_from(paper_authors)
        .join(Paper, Paper.id == paper_authors.c.paper_id)
        .where(paper_authors.c.author_id == author.id)
    )
    date_range = (await session.execute(range_stmt)).one()

    # --- Tópicos ---
    topic_stmt = (
        select(Topic.slug, Topic.name, func.count(Paper.id).label("n"))
        .select_from(paper_authors)
        .join(Paper, Paper.id == paper_authors.c.paper_id)
        .join(paper_topics, paper_topics.c.paper_id == Paper.id)
        .join(Topic, Topic.id == paper_topics.c.topic_id)
        .where(paper_authors.c.author_id == author.id, Topic.is_active.is_(True))
        .group_by(Topic.slug, Topic.name)
        .order_by(desc("n"))
        .limit(6)
    )
    topics = [
        AuthorTopic(slug=r.slug, name=r.name, paper_count=int(r.n))
        for r in (await session.execute(topic_stmt)).all()
    ]

    # --- Coautores ---
    # Self-join na tabela de associação: quem mais aparece nos mesmos papers
    pa2 = paper_authors.alias("pa2")
    coauthor_stmt = (
        select(Author.slug, Author.name, func.count().label("shared"))
        .select_from(paper_authors)
        .join(pa2, pa2.c.paper_id == paper_authors.c.paper_id)
        .join(Author, Author.id == pa2.c.author_id)
        .where(
            paper_authors.c.author_id == author.id,
            pa2.c.author_id != author.id,
        )
        .group_by(Author.slug, Author.name)
        .order_by(desc("shared"))
        .limit(10)
    )
    coauthors = [
        CoAuthor(slug=r.slug, name=r.name, shared_papers=int(r.shared))
        for r in (await session.execute(coauthor_stmt)).all()
    ]

    # --- Papers ---
    paper_stmt = (
        select(Paper)
        .join(paper_authors, paper_authors.c.paper_id == Paper.id)
        .where(paper_authors.c.author_id == author.id)
        .order_by(desc(Paper.published_at))
        .limit(paper_limit)
    )
    papers = list((await session.execute(paper_stmt)).scalars().all())

    institution_slug = None
    if author.institution_id:
        institution_slug = (
            await session.execute(
                select(Institution.slug).where(Institution.id == author.institution_id)
            )
        ).scalar_one_or_none()

    return AuthorDetail(
        slug=author.slug,
        name=author.name,
        affiliation=author.affiliation,
        institution_slug=institution_slug,
        paper_count=author.paper_count,
        total_citations=author.total_citations,
        is_disambiguated=author.is_disambiguated,
        first_paper_at=date_range.first,
        latest_paper_at=date_range.latest,
        topics=topics,
        coauthors=coauthors,
        papers=await _paper_cards(session, papers),
        is_following=await _is_following(session, user, "author", author.id),
    )


# ============================================================
# Instituições
# ============================================================
@router.get("/institutions", response_model=InstitutionsListResponse)
async def list_institutions(
    limit: int = Query(default=50, ge=1, le=200),
    session: AsyncSession = Depends(get_session),
    _rl: None = Depends(rate_limited("default")),
) -> InstitutionsListResponse:
    cache_key = f"institutions:list:{limit}"
    cached = await cache_get(cache_key)
    if cached is not None:
        return InstitutionsListResponse.model_validate(cached)

    stmt = (
        select(Institution)
        .where(Institution.paper_count > 0)
        .order_by(desc(Institution.paper_count))
        .limit(limit)
    )
    institutions = list((await session.execute(stmt)).scalars().all())

    response = InstitutionsListResponse(
        institutions=[
            InstitutionCard(
                slug=i.slug,
                name=i.name,
                country_code=i.country_code,
                paper_count=i.paper_count,
                author_count=i.author_count,
                total_citations=i.total_citations,
            )
            for i in institutions
        ],
        total=len(institutions),
    )
    await cache_set(cache_key, response.model_dump(mode="json"), CACHE_TTL)
    return response


@router.get("/institutions/{slug}", response_model=InstitutionDetail)
async def get_institution(
    slug: str,
    paper_limit: int = Query(default=20, ge=1, le=50),
    user: Optional[User] = Depends(get_optional_user),
    session: AsyncSession = Depends(get_session),
    _rl: None = Depends(rate_limited("default")),
) -> InstitutionDetail:
    inst = (
        await session.execute(select(Institution).where(Institution.slug == slug))
    ).scalar_one_or_none()

    if inst is None:
        raise HTTPException(status_code=404, detail=f"Instituição {slug} não encontrada")

    top_authors = list(
        (
            await session.execute(
                select(Author)
                .where(Author.institution_id == inst.id)
                .order_by(desc(Author.paper_count))
                .limit(12)
            )
        ).scalars().all()
    )

    topic_stmt = (
        select(Topic.slug, Topic.name, func.count(func.distinct(Paper.id)).label("n"))
        .select_from(Author)
        .join(paper_authors, paper_authors.c.author_id == Author.id)
        .join(Paper, Paper.id == paper_authors.c.paper_id)
        .join(paper_topics, paper_topics.c.paper_id == Paper.id)
        .join(Topic, Topic.id == paper_topics.c.topic_id)
        .where(Author.institution_id == inst.id, Topic.is_active.is_(True))
        .group_by(Topic.slug, Topic.name)
        .order_by(desc("n"))
        .limit(8)
    )
    topics = [
        AuthorTopic(slug=r.slug, name=r.name, paper_count=int(r.n))
        for r in (await session.execute(topic_stmt)).all()
    ]

    paper_stmt = (
        select(Paper)
        .distinct()
        .join(paper_authors, paper_authors.c.paper_id == Paper.id)
        .join(Author, Author.id == paper_authors.c.author_id)
        .where(Author.institution_id == inst.id)
        .order_by(desc(Paper.published_at))
        .limit(paper_limit)
    )
    papers = list((await session.execute(paper_stmt)).scalars().all())

    return InstitutionDetail(
        slug=inst.slug,
        name=inst.name,
        country_code=inst.country_code,
        paper_count=inst.paper_count,
        author_count=inst.author_count,
        total_citations=inst.total_citations,
        top_authors=[
            AuthorCard(
                slug=a.slug,
                name=a.name,
                affiliation=a.affiliation,
                paper_count=a.paper_count,
                total_citations=a.total_citations,
                is_disambiguated=a.is_disambiguated,
            )
            for a in top_authors
        ],
        topics=topics,
        papers=await _paper_cards(session, papers),
        is_following=await _is_following(session, user, "institution", inst.id),
    )


# ============================================================
# Seguir
# ============================================================
@router.post("/follows", response_model=FollowResponse)
async def toggle_follow(
    body: FollowRequest,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> FollowResponse:
    """Segue ou deixa de seguir um autor, instituição ou tópico."""
    target_id: int | None = None

    if body.target_type == "author":
        target_id = (
            await session.execute(select(Author.id).where(Author.slug == body.slug))
        ).scalar_one_or_none()
    elif body.target_type == "institution":
        target_id = (
            await session.execute(
                select(Institution.id).where(Institution.slug == body.slug)
            )
        ).scalar_one_or_none()
    elif body.target_type == "topic":
        target_id = (
            await session.execute(select(Topic.id).where(Topic.slug == body.slug))
        ).scalar_one_or_none()

    if target_id is None:
        raise HTTPException(status_code=404, detail=f"{body.target_type} não encontrado")

    existing = (
        await session.execute(
            select(Follow).where(
                Follow.user_id == user.id,
                Follow.target_type == body.target_type,
                Follow.target_id == target_id,
            )
        )
    ).scalar_one_or_none()

    if existing is not None:
        await session.execute(delete(Follow).where(Follow.id == existing.id))
        await session.commit()
        return FollowResponse(
            target_type=body.target_type, slug=body.slug, following=False
        )

    session.add(
        Follow(user_id=user.id, target_type=body.target_type, target_id=target_id)
    )
    await session.commit()

    logger.info(
        "follow.created",
        user_id=user.id,
        target_type=body.target_type,
        slug=body.slug,
    )
    return FollowResponse(
        target_type=body.target_type, slug=body.slug, following=True
    )


@router.get("/follows", response_model=list[FollowResponse])
async def list_follows(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> list[FollowResponse]:
    """Tudo que o usuário segue. Alimenta o digest."""
    follows = list(
        (
            await session.execute(select(Follow).where(Follow.user_id == user.id))
        ).scalars().all()
    )

    out: list[FollowResponse] = []

    by_type: dict[str, list[int]] = {}
    for f in follows:
        by_type.setdefault(f.target_type, []).append(f.target_id)

    models = {"author": Author, "institution": Institution, "topic": Topic}

    for target_type, ids in by_type.items():
        model = models.get(target_type)
        if model is None:
            continue
        rows = (
            await session.execute(select(model.id, model.slug).where(model.id.in_(ids)))
        ).all()
        for r in rows:
            out.append(
                FollowResponse(target_type=target_type, slug=r.slug, following=True)
            )

    return out