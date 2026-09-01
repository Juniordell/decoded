from __future__ import annotations

from datetime import datetime
from typing import Optional

import structlog
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import BackgroundTasks

from decoded.api.deps import rate_limited
from decoded.auth.clerk import get_optional_user
from decoded.config import settings
from decoded.db.base import get_session
from decoded.db.models import ModeStatus, Paper, User
from decoded.db.repositories.explanation_modes import ExplanationModesRepository
from decoded.modes.schemas import ALL_MODES
from decoded.db.repositories.credits import CreditsRepository, InsufficientCredits
from decoded.modes.pipeline import generate_mode
from decoded.auth.clerk import get_current_user
from decoded.db.base import async_session_factory
from decoded.observability.product import track

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
    _rl: None = Depends(rate_limited("mode_poll")),
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
    poll_after_ms: Optional[int] = Field(
        default=None,
        description="Se status=generating, esperar isto antes do próximo GET",
    )


async def _generate_in_background(
    arxiv_id: str,
    mode: str,
    user_id: int,
    paper_id: int,
) -> None:
    """
    Roda depois da resposta HTTP.

    Sessão própria — a do request já fechou. Estorno em caso de falha
    acontece aqui, não no handler.
    """
    from decoded.db.repositories.credits import CreditsRepository

    log = logger.bind(arxiv_id=arxiv_id, mode=mode, user_id=user_id)

    try:
        result = await generate_mode(
            arxiv_id=arxiv_id,
            mode=mode,
            anthropic_api_key=settings.anthropic_api_key,
            fast_model=settings.decoder_model_fast,
            deep_model=settings.decoder_model_deep,
            user_id=user_id,
        )

        if result.get("status") in ("failed", "not_applicable"):
            async with async_session_factory() as session:
                user = (
                    await session.execute(select(User).where(User.id == user_id))
                ).scalar_one_or_none()
                if user is not None:
                    credits = CreditsRepository(session)
                    await credits.refund(user, paper_id, mode)
                    await session.commit()
                    log.info("mode.refunded", reason=result.get("status"))
        async with async_session_factory() as session:
            clerk_id = (
                await session.execute(
                    select(User.clerk_user_id).where(User.id == user_id)
                )
            ).scalar_one_or_none()

        if clerk_id:
            track(
                clerk_id,
                "mode_generation_completed",
                {
                    "mode": mode,
                    "arxiv_id": arxiv_id,
                    "status": result.get("status"),
                    "cost_usd": result.get("cost_usd", 0),
                    "latency_ms": result.get("latency_ms", 0),
                },
            )

        log.info("mode.background_done", status=result.get("status"))

    except Exception as e:
        log.error("mode.background_failed", error=str(e))
        async with async_session_factory() as session:
            user = (
                await session.execute(select(User).where(User.id == user_id))
            ).scalar_one_or_none()
            if user is not None:
                credits = CreditsRepository(session)
                await credits.refund(user, paper_id, mode, reason="background_error")
                await session.commit()


@router.post("/{mode}/generate", response_model=GenerateModeResponse)
async def generate(
    arxiv_id: str,
    mode: str,
    background: BackgroundTasks,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
    _rl: None = Depends(rate_limited("mode_generate")),
) -> GenerateModeResponse:
    """
    Dispara a geração de um modo. Retorna imediatamente.

    Cache hit devolve o conteúdo na hora, de graça.
    Caso contrário gasta o crédito, agenda a geração, e devolve
    status=generating. O cliente faz polling no GET.
    """
    if mode not in ALL_MODES:
        raise HTTPException(status_code=400, detail=f"Modo desconhecido: {mode}")

    paper = await _load_paper(session, arxiv_id)
    modes_repo = ExplanationModesRepository(session)
    credits_repo = CreditsRepository(session)

    existing = await modes_repo.get(paper.id, mode, settings.mode_prompt_version)

    # Cache hit — grátis
    if existing is not None and existing.status == ModeStatus.READY:
        return GenerateModeResponse(
            mode=mode,
            status="ready",
            cached=True,
            content=existing.content,
            credits_remaining=user.credits_remaining,
            cost_usd=0.0,
        )

    # Já está gerando — não cobra de novo
    if existing is not None and existing.status == ModeStatus.GENERATING:
        return GenerateModeResponse(
            mode=mode,
            status="generating",
            cached=False,
            credits_remaining=user.credits_remaining,
            poll_after_ms=3000,
        )

    if not settings.anthropic_api_key:
        raise HTTPException(status_code=503, detail="Geração indisponível")

    # Cobra antes de agendar
    try:
        remaining = await credits_repo.spend(user, paper.id, mode)
        await session.commit()
    except InsufficientCredits as e:
        raise HTTPException(status_code=402, detail=str(e))

    background.add_task(
        _generate_in_background,
        arxiv_id=arxiv_id,
        mode=mode,
        user_id=user.id,
        paper_id=paper.id,
    )

    logger.info("mode.queued", arxiv_id=arxiv_id, mode=mode, user_id=user.id)

    return GenerateModeResponse(
        mode=mode,
        status="generating",
        cached=False,
        credits_remaining=remaining,
        poll_after_ms=3000,
    )