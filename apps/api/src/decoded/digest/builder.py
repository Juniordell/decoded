from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone

import structlog
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from decoded.db.base import async_session_factory
from decoded.db.models import Digest, DigestPreference, DigestStatus, User
from decoded.digest.selection import ScoredPaper, load_follows, select_for_user
from decoded.digest.subject import SubjectWriter

logger = structlog.get_logger()


def week_start(dt: datetime) -> datetime:
    monday = dt - timedelta(days=dt.weekday())
    return monday.replace(hour=0, minute=0, second=0, microsecond=0)


async def get_or_create_preferences(
    session: AsyncSession, user: User
) -> DigestPreference:
    prefs = (
        await session.execute(
            select(DigestPreference).where(DigestPreference.user_id == user.id)
        )
    ).scalar_one_or_none()

    if prefs is not None:
        return prefs

    prefs = DigestPreference(
        user_id=user.id,
        enabled=True,
        max_papers=6,
        include_general=True,
        unsubscribe_token=secrets.token_urlsafe(32),
    )
    session.add(prefs)
    await session.flush()
    return prefs


def _serialize(sp: ScoredPaper) -> dict:
    return {
        "arxiv_id": sp.paper.arxiv_id,
        "title": sp.paper.title,
        "one_sentence": sp.one_sentence,
        "reason": sp.primary_reason,
        "is_decoded": sp.is_decoded,
        "published_at": sp.paper.published_at.isoformat(),
        "citation_count": sp.paper.citation_count,
        "hn_mentions": sp.paper.hn_mentions,
        "score": round(sp.score, 3),
    }


async def build_for_user(
    user_id: int,
    target_week: datetime | None = None,
    anthropic_api_key: str | None = None,
    subject_model: str = "claude-haiku-4-5-20251001",
    force: bool = False,
) -> dict:
    """
    Monta o digest de um usuário para uma semana.

    Idempotente: se já existe digest para a mesma semana, retorna sem
    reconstruir, a menos que force=True.
    """
    week = week_start(target_week or (datetime.now(timezone.utc) - timedelta(weeks=1)))
    log = logger.bind(user_id=user_id, week=week.date().isoformat())

    async with async_session_factory() as session:
        user = (
            await session.execute(select(User).where(User.id == user_id))
        ).scalar_one_or_none()

        if user is None:
            return {"error": "user_not_found"}

        if not user.email:
            log.info("digest.no_email")
            return {"status": "skipped", "reason": "no_email"}

        prefs = await get_or_create_preferences(session, user)
        await session.commit()

        if not prefs.enabled:
            log.info("digest.disabled")
            return {"status": "skipped", "reason": "disabled"}

        existing = (
            await session.execute(
                select(Digest).where(
                    Digest.user_id == user.id, Digest.week_start == week
                )
            )
        ).scalar_one_or_none()

        if existing is not None and not force:
            log.info("digest.already_exists", status=existing.status.value)
            return {
                "status": existing.status.value,
                "digest_id": existing.id,
                "paper_count": existing.paper_count,
                "cached": True,
            }

        selected = await select_for_user(
            session=session,
            user=user,
            week_start=week,
            max_papers=prefs.max_papers,
            include_general=prefs.include_general,
        )

        if not selected:
            log.info("digest.nothing_to_send")
            await session.execute(
                insert(Digest)
                .values(
                    user_id=user.id,
                    week_start=week,
                    status=DigestStatus.SKIPPED,
                    content={"reason": "no_relevant_papers"},
                    paper_count=0,
                )
                .on_conflict_do_update(
                    constraint="uq_digests_user_week",
                    set_={"status": DigestStatus.SKIPPED, "paper_count": 0},
                )
            )
            await session.commit()
            return {"status": "skipped", "reason": "no_relevant_papers"}

        papers = [_serialize(sp) for sp in selected]
        follows = await load_follows(session, user)

        # --- Assunto ---
        subject_text = None
        preview_text = None
        subject_cost = 0.0

        if anthropic_api_key:
            try:
                async with SubjectWriter(anthropic_api_key, subject_model) as writer:
                    result = await writer.write(papers)
                    subject_text = result.subject
                    preview_text = result.preview
                    subject_cost = writer.total_cost
            except Exception as e:
                log.warning("digest.subject_failed", error=str(e))

        if not subject_text:
            # Fallback determinístico
            subject_text = papers[0]["title"][:80]
            preview_text = f"Plus {len(papers) - 1} more from this week."

        content = {
            "papers": papers,
            "preview": preview_text,
            "following": {
                "topics": list(follows.topic_names.values()),
                "authors": list(follows.author_names.values()),
                "institutions": list(follows.institution_names.values()),
            },
            "personalized": not follows.is_empty,
            "unsubscribe_token": prefs.unsubscribe_token,
            "subject_cost_usd": round(subject_cost, 6),
        }

        stmt = (
            insert(Digest)
            .values(
                user_id=user.id,
                week_start=week,
                status=DigestStatus.PENDING,
                content=content,
                paper_count=len(papers),
                subject=subject_text[:300],
            )
            .on_conflict_do_update(
                constraint="uq_digests_user_week",
                set_={
                    "status": DigestStatus.PENDING,
                    "content": content,
                    "paper_count": len(papers),
                    "subject": subject_text[:300],
                    "error": None,
                },
            )
            .returning(Digest.id)
        )
        digest_id = (await session.execute(stmt)).scalar_one()
        await session.commit()

    log.info(
        "digest.built",
        digest_id=digest_id,
        papers=len(papers),
        personalized=content["personalized"],
        subject=subject_text[:60],
    )

    return {
        "status": "pending",
        "digest_id": digest_id,
        "paper_count": len(papers),
        "subject": subject_text,
        "personalized": content["personalized"],
        "cost_usd": round(subject_cost, 6),
    }


async def build_all(
    target_week: datetime | None = None,
    anthropic_api_key: str | None = None,
    subject_model: str = "claude-haiku-4-5-20251001",
    force: bool = False,
) -> dict:
    """Monta o digest para todos os usuários com email."""
    async with async_session_factory() as session:
        users = list(
            (
                await session.execute(select(User).where(User.email.isnot(None)))
            ).scalars().all()
        )

    logger.info("digest.build_all_start", users=len(users))

    built = 0
    skipped = 0
    errors = 0
    total_cost = 0.0

    for user in users:
        try:
            result = await build_for_user(
                user_id=user.id,
                target_week=target_week,
                anthropic_api_key=anthropic_api_key,
                subject_model=subject_model,
                force=force,
            )
            if result.get("status") == "pending":
                built += 1
                total_cost += result.get("cost_usd", 0.0)
            else:
                skipped += 1
        except Exception as e:
            errors += 1
            logger.error("digest.build_failed", user_id=user.id, error=str(e))

    logger.info(
        "digest.build_all_done",
        built=built,
        skipped=skipped,
        errors=errors,
        cost_usd=round(total_cost, 4),
    )

    return {
        "users": len(users),
        "built": built,
        "skipped": skipped,
        "errors": errors,
        "total_cost_usd": round(total_cost, 4),
    }