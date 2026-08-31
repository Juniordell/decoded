"""Seleção e ranqueamento de papers para o digest semanal.

O usuário segue tópicos, autores e instituições. Numa semana entram
centenas de papers e o email cabe seis. A escolha é o produto.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

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


# Pesos da relevância pessoal. Autor seguido é um sinal mais forte que
# tópico seguido — a pessoa escolheu aquele pesquisador especificamente.
WEIGHT_FOLLOWED_AUTHOR = 5.0
WEIGHT_FOLLOWED_TOPIC = 3.0
WEIGHT_FOLLOWED_INSTITUTION = 2.0
WEIGHT_DECODED = 1.5          # papers decodificados valem mais no email
WEIGHT_PRIORITY = 1.0         # multiplica o priority_score já calculado

# Restrição de diversidade
MAX_PER_TOPIC = 2
MAX_PER_AUTHOR = 2


@dataclass
class ScoredPaper:
    paper: Paper
    score: float
    reasons: list[str] = field(default_factory=list)
    topic_ids: set[int] = field(default_factory=set)
    author_ids: set[int] = field(default_factory=set)
    one_sentence: str | None = None
    is_decoded: bool = False

    @property
    def primary_reason(self) -> str:
        return self.reasons[0] if self.reasons else "High priority this week"


@dataclass
class UserFollows:
    author_ids: set[int] = field(default_factory=set)
    topic_ids: set[int] = field(default_factory=set)
    institution_ids: set[int] = field(default_factory=set)

    author_names: dict[int, str] = field(default_factory=dict)
    topic_names: dict[int, str] = field(default_factory=dict)
    institution_names: dict[int, str] = field(default_factory=dict)

    @property
    def is_empty(self) -> bool:
        return not (self.author_ids or self.topic_ids or self.institution_ids)


async def load_follows(session: AsyncSession, user: User) -> UserFollows:
    """Carrega o que o usuário segue, com os nomes para a copy do email."""
    follows = list(
        (
            await session.execute(select(Follow).where(Follow.user_id == user.id))
        ).scalars().all()
    )

    out = UserFollows()
    by_type: dict[str, list[int]] = {}
    for f in follows:
        by_type.setdefault(f.target_type, []).append(f.target_id)

    if author_ids := by_type.get("author"):
        out.author_ids = set(author_ids)
        rows = (
            await session.execute(
                select(Author.id, Author.name).where(Author.id.in_(author_ids))
            )
        ).all()
        out.author_names = {r.id: r.name for r in rows}

    if topic_ids := by_type.get("topic"):
        out.topic_ids = set(topic_ids)
        rows = (
            await session.execute(
                select(Topic.id, Topic.name).where(Topic.id.in_(topic_ids))
            )
        ).all()
        out.topic_names = {r.id: r.name for r in rows}

    if inst_ids := by_type.get("institution"):
        out.institution_ids = set(inst_ids)
        rows = (
            await session.execute(
                select(Institution.id, Institution.name).where(
                    Institution.id.in_(inst_ids)
                )
            )
        ).all()
        out.institution_names = {r.id: r.name for r in rows}

    return out


async def candidate_papers(
    session: AsyncSession,
    week_start: datetime,
    week_end: datetime,
    limit: int = 400,
) -> list[Paper]:
    """Papers publicados na janela, ordenados por prioridade."""
    stmt = (
        select(Paper)
        .where(
            Paper.published_at >= week_start,
            Paper.published_at < week_end,
        )
        .order_by(Paper.priority_score.desc(), Paper.published_at.desc())
        .limit(limit)
    )
    return list((await session.execute(stmt)).scalars().all())


async def _paper_metadata(
    session: AsyncSession,
    papers: list[Paper],
) -> tuple[dict[int, set[int]], dict[int, set[int]], dict[int, str], set[int]]:
    """
    Carrega tópicos, autores, one_sentence e status de decodificação
    para todos os papers de uma vez. Sem N+1.
    """
    if not papers:
        return {}, {}, {}, set()

    paper_ids = [p.id for p in papers]

    topics_by_paper: dict[int, set[int]] = {}
    rows = (
        await session.execute(
            select(paper_topics.c.paper_id, paper_topics.c.topic_id).where(
                paper_topics.c.paper_id.in_(paper_ids)
            )
        )
    ).all()
    for r in rows:
        topics_by_paper.setdefault(r.paper_id, set()).add(r.topic_id)

    authors_by_paper: dict[int, set[int]] = {}
    rows = (
        await session.execute(
            select(paper_authors.c.paper_id, paper_authors.c.author_id).where(
                paper_authors.c.paper_id.in_(paper_ids)
            )
        )
    ).all()
    for r in rows:
        authors_by_paper.setdefault(r.paper_id, set()).add(r.author_id)

    one_sentences: dict[int, str] = {}
    decoded: set[int] = set()
    rows = (
        await session.execute(
            select(DecodedContent).where(
                DecodedContent.paper_id.in_(paper_ids),
                DecodedContent.prompt_version == PROMPT_VERSION,
            )
        )
    ).scalars().all()
    for row in rows:
        decoded.add(row.paper_id)
        if row.section == "one_sentence":
            text = (row.content or {}).get("text")
            if text:
                one_sentences[row.paper_id] = text

    return topics_by_paper, authors_by_paper, one_sentences, decoded


async def _institution_authors(
    session: AsyncSession,
    institution_ids: set[int],
) -> set[int]:
    """Autores das instituições seguidas."""
    if not institution_ids:
        return set()
    rows = (
        await session.execute(
            select(Author.id).where(Author.institution_id.in_(institution_ids))
        )
    ).all()
    return {r.id for r in rows}


def score_paper(
    paper: Paper,
    follows: UserFollows,
    paper_topics_ids: set[int],
    paper_author_ids: set[int],
    institution_author_ids: set[int],
    is_decoded: bool,
) -> tuple[float, list[str]]:
    """
    Pontua um paper para um usuário.

    A relevância pessoal domina. O priority_score entra como desempate
    entre papers igualmente relevantes, em escala logarítmica para que
    um paper com muitas citações não atropele o interesse declarado.
    """
    score = 0.0
    reasons: list[str] = []

    matched_authors = paper_author_ids & follows.author_ids
    if matched_authors:
        score += WEIGHT_FOLLOWED_AUTHOR * min(len(matched_authors), 2)
        names = [follows.author_names.get(a, "") for a in list(matched_authors)[:2]]
        names = [n for n in names if n]
        if names:
            reasons.append(f"By {' and '.join(names)}, who you follow")

    matched_topics = paper_topics_ids & follows.topic_ids
    if matched_topics:
        score += WEIGHT_FOLLOWED_TOPIC * min(len(matched_topics), 2)
        names = [follows.topic_names.get(t, "") for t in list(matched_topics)[:2]]
        names = [n for n in names if n]
        if names:
            reasons.append(f"In {names[0]}, which you follow")

    if paper_author_ids & institution_author_ids:
        score += WEIGHT_FOLLOWED_INSTITUTION
        reasons.append("From an institution you follow")

    if is_decoded:
        score += WEIGHT_DECODED

    # Log para comprimir a cauda longa de citações
    if paper.priority_score > 0:
        score += WEIGHT_PRIORITY * math.log1p(paper.priority_score)

    if not reasons:
        if paper.citation_count > 10:
            reasons.append(f"Cited {paper.citation_count} times already")
        elif paper.hn_mentions > 0:
            reasons.append("Getting attention on Hacker News")
        else:
            reasons.append("High priority this week")

    return score, reasons


def apply_diversity(
    scored: list[ScoredPaper],
    max_papers: int,
) -> list[ScoredPaper]:
    """
    Seleção gulosa com limites por tópico e por autor.

    Sem isso, alguém que segue "Reward Modeling" recebe seis papers do
    mesmo tópico e o email vira monotema. O limite força variedade sem
    abandonar o ranqueamento.
    """
    selected: list[ScoredPaper] = []
    topic_counts: dict[int, int] = {}
    author_counts: dict[int, int] = {}

    for sp in sorted(scored, key=lambda s: -s.score):
        if len(selected) >= max_papers:
            break

        if any(topic_counts.get(t, 0) >= MAX_PER_TOPIC for t in sp.topic_ids):
            continue
        if any(author_counts.get(a, 0) >= MAX_PER_AUTHOR for a in sp.author_ids):
            continue

        selected.append(sp)
        for t in sp.topic_ids:
            topic_counts[t] = topic_counts.get(t, 0) + 1
        for a in sp.author_ids:
            author_counts[a] = author_counts.get(a, 0) + 1

    # Se a diversidade cortou demais, completa com os melhores restantes
    if len(selected) < max_papers:
        chosen_ids = {sp.paper.id for sp in selected}
        for sp in sorted(scored, key=lambda s: -s.score):
            if len(selected) >= max_papers:
                break
            if sp.paper.id not in chosen_ids:
                selected.append(sp)
                chosen_ids.add(sp.paper.id)

    return selected


async def select_for_user(
    session: AsyncSession,
    user: User,
    week_start: datetime,
    max_papers: int = 6,
    include_general: bool = True,
) -> list[ScoredPaper]:
    """Seleciona e ranqueia os papers da semana para um usuário."""
    week_end = week_start + timedelta(weeks=1)
    log = logger.bind(user_id=user.id, week=week_start.date().isoformat())

    follows = await load_follows(session, user)

    if follows.is_empty and not include_general:
        log.info("digest.no_follows_skip")
        return []

    papers = await candidate_papers(session, week_start, week_end)
    if not papers:
        log.info("digest.no_papers_in_window")
        return []

    topics_by_paper, authors_by_paper, one_sentences, decoded = await _paper_metadata(
        session, papers
    )
    institution_author_ids = await _institution_authors(
        session, follows.institution_ids
    )

    scored: list[ScoredPaper] = []
    for p in papers:
        p_topics = topics_by_paper.get(p.id, set())
        p_authors = authors_by_paper.get(p.id, set())
        is_decoded = p.id in decoded

        score, reasons = score_paper(
            paper=p,
            follows=follows,
            paper_topics_ids=p_topics,
            paper_author_ids=p_authors,
            institution_author_ids=institution_author_ids,
            is_decoded=is_decoded,
        )

        scored.append(
            ScoredPaper(
                paper=p,
                score=score,
                reasons=reasons,
                topic_ids=p_topics,
                author_ids=p_authors,
                one_sentence=one_sentences.get(p.id),
                is_decoded=is_decoded,
            )
        )

    selected = apply_diversity(scored, max_papers)

    log.info(
        "digest.selected",
        candidates=len(scored),
        selected=len(selected),
        personalized=not follows.is_empty,
    )

    return selected