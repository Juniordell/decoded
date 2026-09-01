"""Decodificação noturna dos papers de maior prioridade.

Usa Batch API (50% do preço) com teto de gasto explícito. Sem o teto,
um dia de arXiv anormalmente grande vira uma conta anormalmente grande.
"""

from __future__ import annotations

import structlog
from prefect import flow, get_run_logger, task
from sqlalchemy import func, select

from decoded.config import settings
from decoded.db.base import async_session_factory
from decoded.db.models import DecodedContent, IngestionStatus, Paper
from decoded.decoding.batch_pipeline import decode_papers_batch
from decoded.decoding.prompts import VERSION as PROMPT_VERSION
from decoded.logging import configure_logging
from decoded.observability.tracing import flush as flush_tracing
from decoded.observability.tracing import init_tracing

logger = structlog.get_logger()


async def _spent_today() -> float:
    """Gasto de decodificação nas últimas 24h."""
    async with async_session_factory() as session:
        return (
            await session.execute(
                select(func.coalesce(func.sum(DecodedContent.cost_usd), 0.0)).where(
                    DecodedContent.created_at
                    >= func.now() - func.cast("1 day", type_=None)
                )
            )
        ).scalar_one() or 0.0


@task(name="select-papers-to-decode")
async def select_task(limit: int, min_priority: float) -> list[str]:
    """
    Escolhe os papers de maior prioridade ainda não decodificados.

    Exige texto parseado — sem ele o deep dive não tem fonte.
    """
    logger = get_run_logger()

    async with async_session_factory() as session:
        decoded_ids = select(DecodedContent.paper_id).where(
            DecodedContent.section == "one_sentence",
            DecodedContent.prompt_version == PROMPT_VERSION,
        )

        stmt = (
            select(Paper.arxiv_id)
            .where(
                Paper.id.notin_(decoded_ids),
                Paper.priority_score >= min_priority,
                Paper.status.in_(
                    [IngestionStatus.PARSED, IngestionStatus.EMBEDDED]
                ),
            )
            .order_by(Paper.priority_score.desc(), Paper.published_at.desc())
            .limit(limit)
        )
        arxiv_ids = [r for r in (await session.execute(stmt)).scalars().all()]

    logger.info(f"Selected {len(arxiv_ids)} papers to decode")
    return arxiv_ids


@task(name="batch-decode", retries=1, retry_delay_seconds=600)
async def decode_task(arxiv_ids: list[str], sections: list[str]) -> dict:
    logger = get_run_logger()

    if not arxiv_ids:
        return {"skipped": True, "reason": "nothing_to_decode"}

    if not settings.anthropic_api_key:
        logger.warning("ANTHROPIC_API_KEY ausente")
        return {"skipped": True, "reason": "no_api_key"}

    logger.info(f"Batch decoding {len(arxiv_ids)} papers")
    return await decode_papers_batch(
        arxiv_ids=arxiv_ids,
        anthropic_api_key=settings.anthropic_api_key,
        fast_model=settings.decoder_model_fast,
        deep_model=settings.decoder_model_deep,
        sections=sections,
        wait=True,
    )


@flow(
    name="decoded-nightly-decode",
    log_prints=True,
    description="Decodifica os papers de maior prioridade via Batch API.",
)
async def nightly_decode_flow(
    limit: int = 20,
    min_priority: float = 2.0,
    daily_budget_usd: float = 5.0,
    sections: list[str] | None = None,
) -> dict:
    """
    Decodificação noturna com teto de gasto.

    O teto é verificado antes de submeter, não depois. Uma vez que o
    batch está na fila da Anthropic, você já vai pagar por ele.
    """
    configure_logging("INFO")
    init_tracing()
    log = get_run_logger()

    sections = sections or ["one_sentence", "sixty_second", "deep_dive"]

    try:
        spent = await _spent_today()
        log.info(f"Spent in last 24h: ${spent:.2f} of ${daily_budget_usd:.2f}")

        if spent >= daily_budget_usd:
            log.warning("Daily budget exhausted, skipping")
            return {"skipped": True, "spent_today": round(spent, 4)}

        # Estimativa conservadora: ~$0.10/paper com as três seções em batch
        remaining = daily_budget_usd - spent
        affordable = int(remaining / 0.10)
        effective_limit = min(limit, max(affordable, 0))

        if effective_limit == 0:
            log.warning("Budget too tight for even one paper")
            return {"skipped": True, "spent_today": round(spent, 4)}

        arxiv_ids = await select_task(effective_limit, min_priority)
        result = await decode_task(arxiv_ids, sections)

    finally:
        flush_tracing()

    log.info(f"Nightly decode complete: {result}")
    return result