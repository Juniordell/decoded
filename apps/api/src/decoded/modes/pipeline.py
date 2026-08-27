from __future__ import annotations

import structlog
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from decoded.db.base import async_session_factory
from decoded.db.models import ModeStatus, Paper
from decoded.db.repositories.decoded_contents import DecodedContentsRepository
from decoded.db.repositories.explanation_modes import ExplanationModesRepository
from decoded.decoding.pipeline import _flatten_deep_dive
from decoded.decoding.prompts import VERSION as DECODE_PROMPT_VERSION
from decoded.modes.generator import ModeGenerator
from decoded.modes.prompts import MODE_PROMPT_VERSION
from decoded.modes.schemas import ALL_MODES
from decoded.observability.tracing import trace_span
from decoded.config import settings

logger = structlog.get_logger()


async def generate_mode(
    arxiv_id: str,
    mode: str,
    anthropic_api_key: str,
    fast_model: str,
    deep_model: str,
    user_id: int | None = None,
    force: bool = False,
) -> dict:
    """
    Gera um modo para um paper.

    Se já existir em cache, retorna direto sem gastar nada.
    Se outra requisição estiver gerando, retorna status GENERATING.
    """
    if mode not in ALL_MODES:
        return {"error": f"modo desconhecido: {mode}"}

    log = logger.bind(arxiv_id=arxiv_id, mode=mode)

    with trace_span(
        "generate_mode",
        input={"arxiv_id": arxiv_id, "mode": mode},
        tags=["mode", mode],
    ) as span:
        async with async_session_factory() as session:
            stmt = (
                select(Paper)
                .options(selectinload(Paper.parsed_content))
                .where(Paper.arxiv_id == arxiv_id)
            )
            paper = (await session.execute(stmt)).scalar_one_or_none()

            if paper is None:
                return {"error": "paper_not_found"}

            modes_repo = ExplanationModesRepository(session)

            # --- Cache ---
            if not force:
                existing = await modes_repo.get(paper.id, mode, MODE_PROMPT_VERSION)
                if existing is not None:
                    if existing.status == ModeStatus.READY:
                        log.info("mode.cache_hit")
                        span.update(output={"cache_hit": True})
                        return {
                            "mode": mode,
                            "status": "ready",
                            "cached": True,
                            "content": existing.content,
                            "cost_usd": 0.0,
                        }
                    if existing.status == ModeStatus.GENERATING:
                        log.info("mode.already_generating")
                        return {"mode": mode, "status": "generating", "cached": False}
                    if existing.status == ModeStatus.NOT_APPLICABLE:
                        return {
                            "mode": mode,
                            "status": "not_applicable",
                            "cached": False,
                            "error": existing.error,
                        }

            # --- Claim ---
            row, is_new = await modes_repo.claim(
                paper_id=paper.id,
                mode=mode,
                prompt_version=MODE_PROMPT_VERSION,
                user_id=user_id,
            )
            await session.commit()

            if not is_new and not force:
                return {"mode": mode, "status": "generating", "cached": False}

            # --- Material de origem ---
            decoded_repo = DecodedContentsRepository(session)
            sections = await decoded_repo.get_all_sections(
                paper_id=paper.id, prompt_version=DECODE_PROMPT_VERSION
            )

            deep_dive_row = sections.get("deep_dive")
            deep_dive_text = (
                _flatten_deep_dive(deep_dive_row.content) if deep_dive_row else ""
            )

            full_text = (
                paper.parsed_content.markdown
                if paper.parsed_content and paper.parsed_content.markdown
                else None
            )

            if not deep_dive_text and not full_text:
                await modes_repo.fail(
                    row.id,
                    "Sem deep dive nem texto parseado — decodifique o paper primeiro",
                )
                await session.commit()
                return {"mode": mode, "status": "failed", "error": "no_source_material"}

            # --- Geração ---
            try:
                async with ModeGenerator(
                    api_key=anthropic_api_key,
                    fast_model=fast_model,
                    deep_model=deep_model,
                    openai_api_key=settings.openai_api_key,
                    openai_model=settings.openai_analogy_model,
                ) as gen:
                    result = await gen.generate(
                        mode=mode,
                        title=paper.title,
                        abstract=paper.abstract,
                        deep_dive_text=deep_dive_text,
                        full_text=full_text,
                    )

                await modes_repo.complete(
                    row_id=row.id,
                    content=result.content,
                    model=result.model,
                    input_tokens=result.input_tokens,
                    output_tokens=result.output_tokens,
                    cost_usd=result.cost_usd,
                    latency_ms=result.latency_ms,
                )
                await session.commit()

                span.update(
                    output={"cache_hit": False, "mode": mode},
                    metadata={"cost_usd": result.cost_usd},
                )

                log.info("mode.done", cost_usd=round(result.cost_usd, 6))
                return {
                    "mode": mode,
                    "status": "ready",
                    "cached": False,
                    "content": result.content,
                    "cost_usd": result.cost_usd,
                    "latency_ms": result.latency_ms,
                }

            except Exception as e:
                await session.rollback()
                await modes_repo.fail(row.id, str(e))
                await session.commit()
                log.error("mode.failed", error=str(e))
                return {"mode": mode, "status": "failed", "error": str(e)}


async def generate_all_modes(
    arxiv_id: str,
    anthropic_api_key: str,
    fast_model: str,
    deep_model: str,
    modes: list[str] | None = None,
    force: bool = False,
) -> dict:
    """Gera vários modos em sequência. Para uso via CLI, não via API."""
    modes = modes or ALL_MODES
    results: dict[str, dict] = {}
    total_cost = 0.0

    for mode in modes:
        result = await generate_mode(
            arxiv_id=arxiv_id,
            mode=mode,
            anthropic_api_key=anthropic_api_key,
            fast_model=fast_model,
            deep_model=deep_model,
            force=force,
        )
        results[mode] = result
        total_cost += result.get("cost_usd", 0.0)

    return {
        "arxiv_id": arxiv_id,
        "modes": results,
        "total_cost_usd": round(total_cost, 6),
    }