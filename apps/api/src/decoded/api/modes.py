from __future__ import annotations

from datetime import datetime
from typing import Optional

import structlog
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from decoded.auth.clerk import get_optional_user
from decoded.config import settings
from decoded.db.base import get_session
from decoded.db.models import ModeStatus, Paper, User
from decoded.db.repositories.explanation_modes import ExplanationModesRepository
from decoded.modes.schemas import ALL_MODES
from decoded.db.repositories.credits import CreditsRepository, InsufficientCredits
from decoded.modes.pipeline import generate_mode
from decoded.auth.clerk import get_current_user

logger = structlog.get_logger()

router = APIRouter(prefix="/v1/papers/{arxiv_id}/modes", tags=["modes"])


class ModeInfo(BaseModel):
    mode: str
    status: str
    cached: bool
    content: Optional[dict] = None
    generated_at: Optional[datetime] = None


class ModesListResponse(BaseModel):
    arxiv_id: str
    modes: list[ModeInfo]
    credits_remaining: Optional[int] = None
    plan: Optional[str] = None


async def _load_paper(session: AsyncSession, arxiv_id: str) -> Paper:
    stmt = select(Paper).where(Paper.arxiv_id == arxiv_id)
    paper = (await session.execute(stmt)).scalar_one_or_none()
    if paper is None:
        raise HTTPException(status_code=404, detail=f"Paper {arxiv_id} não encontrado")
    return paper


@router.get("", response_model=ModesListResponse)
async def list_modes(
    arxiv_id: str,
    user: Optional[User] = Depends(get_optional_user),
    session: AsyncSession = Depends(get_session),
) -> ModesListResponse:
    """
    Lista todos os modos com status. Conteúdo incluído apenas para os prontos.
    Funciona sem autenticação — modos em cache são públicos.
    """
    paper = await _load_paper(session, arxiv_id)

    repo = ExplanationModesRepository(session)
    existing = await repo.list_for_paper(paper.id, settings.mode_prompt_version)

    modes: list[ModeInfo] = []
    for mode_name in ALL_MODES:
        row = existing.get(mode_name)

        if row is None:
            modes.append(
                ModeInfo(mode=mode_name, status="pending", cached=False)
            )
            continue

        modes.append(
            ModeInfo(
                mode=mode_name,
                status=row.status.value,
                cached=row.status == ModeStatus.READY,
                content=row.content if row.status == ModeStatus.READY else None,
                generated_at=row.updated_at if row.status == ModeStatus.READY else None,
            )
        )

    return ModesListResponse(
        arxiv_id=arxiv_id,
        modes=modes,
        credits_remaining=user.credits_remaining if user else None,
        plan=user.plan if user else None,
    )


@router.get("/{mode}", response_model=ModeInfo)
async def get_mode(
    arxiv_id: str,
    mode: str,
    session: AsyncSession = Depends(get_session),
) -> ModeInfo:
    """Busca um modo específico. Só retorna se estiver em cache."""
    if mode not in ALL_MODES:
        raise HTTPException(status_code=400, detail=f"Modo desconhecido: {mode}")

    paper = await _load_paper(session, arxiv_id)
    repo = ExplanationModesRepository(session)
    row = await repo.get(paper.id, mode, settings.mode_prompt_version)

    if row is None:
        return ModeInfo(mode=mode, status="pending", cached=False)

    return ModeInfo(
        mode=mode,
        status=row.status.value,
        cached=row.status == ModeStatus.READY,
        content=row.content if row.status == ModeStatus.READY else None,
        generated_at=row.updated_at if row.status == ModeStatus.READY else None,
    )

class GenerateModeResponse(BaseModel):
    mode: str
    status: str
    cached: bool
    content: Optional[dict] = None
    error: Optional[str] = None
    credits_remaining: Optional[int] = None
    cost_usd: Optional[float] = None


@router.post("/{mode}/generate", response_model=GenerateModeResponse)
async def generate(
    arxiv_id: str,
    mode: str,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> GenerateModeResponse:
    """
    Gera um modo. Gasta um crédito, exceto se já estiver em cache.

    Cache hit não cobra — quem já pagou pela geração beneficia todo mundo depois.
    """
    if mode not in ALL_MODES:
        raise HTTPException(status_code=400, detail=f"Modo desconhecido: {mode}")

    paper = await _load_paper(session, arxiv_id)
    modes_repo = ExplanationModesRepository(session)
    credits_repo = CreditsRepository(session)

    # Cache hit é sempre grátis
    existing = await modes_repo.get(paper.id, mode, settings.mode_prompt_version)
    if existing is not None and existing.status == ModeStatus.READY:
        return GenerateModeResponse(
            mode=mode,
            status="ready",
            cached=True,
            content=existing.content,
            credits_remaining=user.credits_remaining,
            cost_usd=0.0,
        )

    # Gasta o crédito antes de gerar
    try:
        remaining = await credits_repo.spend(user, paper.id, mode)
        await session.commit()
    except InsufficientCredits as e:
        raise HTTPException(status_code=402, detail=str(e))

    if not settings.anthropic_api_key:
        await credits_repo.refund(user, paper.id, mode, reason="api_not_configured")
        await session.commit()
        raise HTTPException(status_code=503, detail="Geração indisponível")

    result = await generate_mode(
        arxiv_id=arxiv_id,
        mode=mode,
        anthropic_api_key=settings.anthropic_api_key,
        fast_model=settings.decoder_model_fast,
        deep_model=settings.decoder_model_deep,
        user_id=user.id,
    )

    # Estorna se falhou
    if result.get("status") in ("failed", "not_applicable"):
        remaining = await credits_repo.refund(user, paper.id, mode)
        await session.commit()

    return GenerateModeResponse(
        mode=mode,
        status=result.get("status", "failed"),
        cached=result.get("cached", False),
        content=result.get("content"),
        error=result.get("error"),
        credits_remaining=remaining,
        cost_usd=result.get("cost_usd"),
    )