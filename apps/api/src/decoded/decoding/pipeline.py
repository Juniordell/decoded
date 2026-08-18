from __future__ import annotations

from typing import Iterable

import structlog
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from decoded.db.base import async_session_factory
from decoded.db.models import IngestionStatus, Paper
from decoded.db.repositories.decoded_contents import DecodedContentsRepository
from decoded.decoding.generator import GenerationResult, SectionGenerator

logger = structlog.get_logger()

# Section name → generator method name on SectionGenerator
FAST_SECTIONS = {
    "one_sentence": "one_sentence",
    "sixty_second": "sixty_second",
}


async def decode_paper(
    arxiv_id: str,
    anthropic_api_key: str,
    fast_model: str,
    sections: Iterable[str] | None = None,
) -> dict:
    """
    Generate the given sections for one paper (by arxiv_id), store results.
    Default: all fast sections (one_sentence, sixty_second).
    """
    sections = list(sections) if sections else list(FAST_SECTIONS.keys())
    log = logger.bind(arxiv_id=arxiv_id, sections=sections)
    log.info("decode.start")

    async with async_session_factory() as session, SectionGenerator(
        api_key=anthropic_api_key,
        fast_model=fast_model,
    ) as gen:
        # Load the paper
        stmt = (
            select(Paper)
            .options(selectinload(Paper.parsed_content))
            .where(Paper.arxiv_id == arxiv_id)
        )
        result = await session.execute(stmt)
        paper = result.scalar_one_or_none()

        if paper is None:
            log.error("decode.paper_not_found")
            return {"error": "paper_not_found"}

        decoded_repo = DecodedContentsRepository(session)

        outcomes: dict[str, dict] = {}
        total_cost = 0.0

        for section_name in sections:
            method_name = FAST_SECTIONS.get(section_name)
            if not method_name:
                log.warning("decode.unknown_section", section=section_name)
                continue

            method = getattr(gen, method_name)
            try:
                result: GenerationResult = await method(
                    title=paper.title,
                    abstract=paper.abstract,
                )

                await decoded_repo.upsert_section(
                    paper_id=paper.id,
                    section=section_name,
                    content=result.content,
                    model=result.model,
                    prompt_version=result.prompt_version,
                    input_tokens=result.input_tokens,
                    output_tokens=result.output_tokens,
                    cost_usd=result.cost_usd,
                    latency_ms=result.latency_ms,
                )
                await session.commit()

                outcomes[section_name] = {
                    "cost_usd": round(result.cost_usd, 6),
                    "latency_ms": result.latency_ms,
                    "cache_hit_tokens": result.cache_read_tokens,
                }
                total_cost += result.cost_usd

            except Exception as e:
                await session.rollback()
                log.error("decode.section_failed", section=section_name, error=str(e))
                outcomes[section_name] = {"error": str(e)}

        # Update paper status if all decoded sections succeeded
        if all("error" not in v for v in outcomes.values()):
            paper.status = IngestionStatus.DECODED
            await session.commit()

        log.info("decode.done", total_cost_usd=round(total_cost, 6), outcomes=outcomes)
        return {"arxiv_id": arxiv_id, "total_cost_usd": total_cost, "outcomes": outcomes}