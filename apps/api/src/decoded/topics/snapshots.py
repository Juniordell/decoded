"""Snapshots semanais por tópico — a base do Field Pulse."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import structlog
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert

from decoded.db.base import async_session_factory
from decoded.db.models import Paper, Topic, TopicSnapshot, paper_topics

logger = structlog.get_logger()


def week_start(dt: datetime) -> datetime:
    """Segunda-feira 00:00 UTC da semana de dt."""
    monday = dt - timedelta(days=dt.weekday())
    return monday.replace(hour=0, minute=0, second=0, microsecond=0)


async def build_snapshots(weeks_back: int = 12) -> dict:
    """
    Calcula snapshots por tópico e por semana.

    Reconstrói tudo em vez de fazer incremental — o clustering reatribui
    papers a cada execução, então snapshots antigos ficariam com base
    numa atribuição que não existe mais.
    """
    log = logger.bind(source="snapshots")
    now = datetime.now(timezone.utc)
    current_week = week_start(now)
    earliest = current_week - timedelta(weeks=weeks_back)

    log.info("snapshots.start", weeks=weeks_back, from_date=earliest.date().isoformat())

    written = 0

    async with async_session_factory() as session:
        topics = (
            (await session.execute(select(Topic).where(Topic.is_active.is_(True))))
            .scalars()
            .all()
        )

        for topic in topics:
            for w in range(weeks_back):
                w_start = earliest + timedelta(weeks=w)
                w_end = w_start + timedelta(weeks=1)

                stmt = (
                    select(
                        func.count(Paper.id).label("n"),
                        func.coalesce(func.sum(Paper.citation_count), 0).label("citations"),
                        func.coalesce(func.avg(Paper.priority_score), 0.0).label("priority"),
                        func.coalesce(func.sum(Paper.hn_mentions), 0).label("hn"),
                    )
                    .join(paper_topics, paper_topics.c.paper_id == Paper.id)
                    .where(
                        paper_topics.c.topic_id == topic.id,
                        Paper.published_at >= w_start,
                        Paper.published_at < w_end,
                    )
                )
                row = (await session.execute(stmt)).one()

                if row.n == 0:
                    continue

                await session.execute(
                    insert(TopicSnapshot)
                    .values(
                        topic_id=topic.id,
                        window_start=w_start,
                        window_end=w_end,
                        paper_count=row.n,
                        total_citations=int(row.citations),
                        mean_priority=float(row.priority),
                        hn_mentions=int(row.hn),
                    )
                    .on_conflict_do_update(
                        constraint="uq_topic_snapshots_topic_window",
                        set_={
                            "paper_count": row.n,
                            "total_citations": int(row.citations),
                            "mean_priority": float(row.priority),
                            "hn_mentions": int(row.hn),
                        },
                    )
                )
                written += 1

        await session.commit()

    log.info("snapshots.done", written=written, topics=len(topics))
    return {"snapshots_written": written, "topics": len(topics)}


async def compute_momentum(weeks: int = 4) -> list[dict]:
    """
    Compara as últimas N semanas com as N anteriores.

    Retorna tópicos ordenados por variação relativa — o que está
    esquentando e o que está esfriando.
    """
    now = datetime.now(timezone.utc)
    current_week = week_start(now)

    recent_start = current_week - timedelta(weeks=weeks)
    prior_start = recent_start - timedelta(weeks=weeks)

    async with async_session_factory() as session:
        topics = (
            (await session.execute(select(Topic).where(Topic.is_active.is_(True))))
            .scalars()
            .all()
        )

        out: list[dict] = []

        for topic in topics:
            recent = (
                await session.execute(
                    select(func.coalesce(func.sum(TopicSnapshot.paper_count), 0)).where(
                        TopicSnapshot.topic_id == topic.id,
                        TopicSnapshot.window_start >= recent_start,
                    )
                )
            ).scalar_one()

            prior = (
                await session.execute(
                    select(func.coalesce(func.sum(TopicSnapshot.paper_count), 0)).where(
                        TopicSnapshot.topic_id == topic.id,
                        TopicSnapshot.window_start >= prior_start,
                        TopicSnapshot.window_start < recent_start,
                    )
                )
            ).scalar_one()

            if recent + prior < 3:
                continue  # ruído

            if prior == 0:
                change = float("inf") if recent >= 3 else 0.0
                label = "new"
            else:
                change = (recent - prior) / prior
                label = "rising" if change > 0.25 else "cooling" if change < -0.25 else "steady"

            out.append(
                {
                    "topic_id": topic.id,
                    "slug": topic.slug,
                    "name": topic.name,
                    "recent_papers": int(recent),
                    "prior_papers": int(prior),
                    "change": round(change, 3),
                    "label": label,
                }
            )

    return sorted(
        out,
        key=lambda x: (x["label"] == "new", -x["change"] if x["change"] != float("inf") else 0),
    )