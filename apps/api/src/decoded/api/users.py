from __future__ import annotations

from datetime import datetime

import structlog
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from decoded.api.schemas import PaperCard
from decoded.auth.clerk import get_current_user
from decoded.db.base import get_session
from decoded.db.models import DecodedContent, Paper, ReadEvent, SavedPaper, User
from decoded.decoding.prompts import VERSION as PROMPT_VERSION

logger = structlog.get_logger()

router = APIRouter(prefix="/v1/me", tags=["users"])


class MeResponse(BaseModel):
    email: str | None
    display_name: str | None
    avatar_url: str | None
    plan: str
    credits_remaining: int
    credits_reset_at: datetime | None
    saved_count: int


class SavedResponse(BaseModel):
    papers: list[PaperCard]
    total: int


class ToggleSaveRequest(BaseModel):
    arxiv_id: str


class ToggleSaveResponse(BaseModel):
    arxiv_id: str
    saved: bool


@router.get("", response_model=MeResponse)
async def get_me(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> MeResponse:
    count_stmt = select(func.count()).select_from(SavedPaper).where(
        SavedPaper.user_id == user.id
    )
    saved_count = (await session.execute(count_stmt)).scalar_one()

    return MeResponse(
        email=user.email,
        display_name=user.display_name,
        avatar_url=user.avatar_url,
        plan=user.plan,
        credits_remaining=user.credits_remaining,
        credits_reset_at=user.credits_reset_at,
        saved_count=saved_count,
    )


@router.get("/saved", response_model=SavedResponse)
async def list_saved(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> SavedResponse:
    stmt = (
        select(Paper)
        .join(SavedPaper, SavedPaper.paper_id == Paper.id)
        .options(selectinload(Paper.authors))
        .where(SavedPaper.user_id == user.id)
        .order_by(SavedPaper.created_at.desc())
    )
    papers = list((await session.execute(stmt)).scalars().all())

    # one_sentence de cada
    paper_ids = [p.id for p in papers]
    one_sentences: dict[int, str] = {}
    section_counts: dict[int, int] = {}

    if paper_ids:
        dc_stmt = select(DecodedContent).where(
            DecodedContent.paper_id.in_(paper_ids),
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
            authors=[a.name for a in p.authors[:5]],
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

    return SavedResponse(papers=cards, total=len(cards))


@router.post("/saved", response_model=ToggleSaveResponse)
async def toggle_save(
    body: ToggleSaveRequest,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> ToggleSaveResponse:
    """Salva ou remove um paper da biblioteca do usuário."""
    paper_stmt = select(Paper).where(Paper.arxiv_id == body.arxiv_id)
    paper = (await session.execute(paper_stmt)).scalar_one_or_none()
    if paper is None:
        raise HTTPException(status_code=404, detail="Paper não encontrado")

    existing_stmt = select(SavedPaper).where(
        SavedPaper.user_id == user.id,
        SavedPaper.paper_id == paper.id,
    )
    existing = (await session.execute(existing_stmt)).scalar_one_or_none()

    if existing is not None:
        await session.execute(
            delete(SavedPaper).where(SavedPaper.id == existing.id)
        )
        await session.commit()
        return ToggleSaveResponse(arxiv_id=body.arxiv_id, saved=False)

    session.add(SavedPaper(user_id=user.id, paper_id=paper.id))
    await session.commit()
    return ToggleSaveResponse(arxiv_id=body.arxiv_id, saved=True)


@router.get("/saved/{arxiv_id}", response_model=ToggleSaveResponse)
async def is_saved(
    arxiv_id: str,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> ToggleSaveResponse:
    stmt = (
        select(SavedPaper)
        .join(Paper, Paper.id == SavedPaper.paper_id)
        .where(SavedPaper.user_id == user.id, Paper.arxiv_id == arxiv_id)
    )
    found = (await session.execute(stmt)).scalar_one_or_none()
    return ToggleSaveResponse(arxiv_id=arxiv_id, saved=found is not None)


class ReadRequest(BaseModel):
    arxiv_id: str
    section: str | None = None


@router.post("/read", status_code=204)
async def record_read(
    body: ReadRequest,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> None:
    """Registra que o usuário leu um paper. Alimenta personalização na Semana 5."""
    paper_stmt = select(Paper.id).where(Paper.arxiv_id == body.arxiv_id)
    paper_id = (await session.execute(paper_stmt)).scalar_one_or_none()
    if paper_id is None:
        return

    session.add(
        ReadEvent(user_id=user.id, paper_id=paper_id, section=body.section)
    )
    await session.commit()