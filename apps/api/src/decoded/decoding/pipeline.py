from __future__ import annotations

from typing import Iterable

import structlog
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from decoded.db.base import async_session_factory
from decoded.db.models import IngestionStatus, Paper
from decoded.db.repositories.decoded_contents import DecodedContentsRepository
from decoded.decoding.generator import GenerationResult, SectionGenerator
from decoded.decoding.figure_extractor import (
    download_pdf,
    extract_figures_from_pdf_bytes,
)
from decoded.decoding.prompts import VERSION

logger = structlog.get_logger()

# Section name → generator method name on SectionGenerator
# Fast sections use only the abstract (Haiku)
FAST_SECTIONS = {
    "one_sentence": "one_sentence",
    "sixty_second": "sixty_second",
}

DEEP_SECTIONS = {
    "deep_dive": "deep_dive",
}

VISION_SECTIONS = {
    "figures": "figures",
}

# Didactic sections need the deep_dive to already exist
DIDACTIC_SECTIONS = {
    "vocabulary": "vocabulary",
    "analogies": "analogies",
}

ALL_SECTIONS = {**FAST_SECTIONS, **DEEP_SECTIONS, **VISION_SECTIONS, **DIDACTIC_SECTIONS}

def _flatten_deep_dive(dd_content: dict) -> str:
    """Turn the DeepDive JSON structure into flat text for downstream sections."""
    parts = []
    for section_key in ("setup", "idea", "method", "results", "implications"):
        section = dd_content.get(section_key)
        if section:
            heading = section.get("heading", section_key)
            body = section.get("body", "")
            parts.append(f"## {heading}\n\n{body}")
    return "\n\n".join(parts)

async def decode_paper(
    arxiv_id: str,
    anthropic_api_key: str,
    fast_model: str,
    deep_model: str,
    sections: Iterable[str] | None = None,
) -> dict:
    """
    Generate the given sections for one paper (by arxiv_id), store results.
    Default: all sections.
    """
    sections = list(sections) if sections else list(ALL_SECTIONS.keys())
    log = logger.bind(arxiv_id=arxiv_id, sections=sections)
    log.info("decode.start")

    async with async_session_factory() as session, SectionGenerator(
        api_key=anthropic_api_key,
        fast_model=fast_model,
    ) as gen:
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
            decoded_repo = DecodedContentsRepository(session)

            # Preload existing decoded sections (needed by didactic sections)
            existing_sections = await decoded_repo.get_all_sections(
                paper_id=paper.id,
                prompt_version=VERSION,
            )

            outcomes: dict[str, dict] = {}
            total_cost = 0.0
            if section_name not in ALL_SECTIONS:
                log.warning("decode.unknown_section", section=section_name)
                continue

            try:
                # Route to the right method
                if section_name in FAST_SECTIONS:
                    method = getattr(gen, ALL_SECTIONS[section_name])
                    gen_result: GenerationResult = await method(
                        title=paper.title,
                        abstract=paper.abstract,
                    )
                elif section_name in DEEP_SECTIONS:
                    if not paper.parsed_content or not paper.parsed_content.markdown:
                        log.warning(
                            "decode.no_parsed_content",
                            section=section_name,
                            hint="run parse stage first",
                        )
                        outcomes[section_name] = {"error": "no_parsed_content"}
                        continue

                    method = getattr(gen, ALL_SECTIONS[section_name])
                    gen_result = await method(
                        title=paper.title,
                        abstract=paper.abstract,
                        full_text=paper.parsed_content.markdown,
                        deep_model=deep_model,
                    )

                elif section_name in VISION_SECTIONS:
                    log.info("figures.extracting", pdf_url=paper.pdf_url)
                    pdf_bytes = await download_pdf(paper.pdf_url)
                    extraction = extract_figures_from_pdf_bytes(pdf_bytes)

                    log.info(
                        "figures.extracted",
                        found=extraction.total_images_found,
                        kept=len(extraction.figures),
                        skipped_small=extraction.skipped_small,
                        skipped_large=extraction.skipped_large,
                    )

                    if not extraction.figures:
                        outcomes[section_name] = {"skipped": "no_figures_found"}
                        continue

                    figures_data = [
                        {
                            "image_b64": f.to_b64(),
                            "media_type": f.media_type,
                            "nearby_text": f.nearby_text,
                        }
                        for f in extraction.figures
                    ]
                    gen_result = await gen.figures(
                        figures_data=figures_data,
                        deep_model=deep_model,
                    )

                elif section_name in DIDACTIC_SECTIONS:
                    # Need deep_dive as source material
                    deep_dive_row = existing_sections.get("deep_dive")
                    if deep_dive_row is None:
                        log.warning(
                            "decode.no_deep_dive",
                            section=section_name,
                            hint="generate deep_dive first",
                        )
                        outcomes[section_name] = {"error": "no_deep_dive"}
                        continue

                    # Flatten the deep_dive JSON into text
                    dd_content = deep_dive_row.content
                    deep_dive_text = _flatten_deep_dive(dd_content)

                    method = getattr(gen, DIDACTIC_SECTIONS[section_name])
                    gen_result = await method(deep_dive_text=deep_dive_text)

                else:
                    continue

                await decoded_repo.upsert_section(
                    paper_id=paper.id,
                    section=section_name,
                    content=gen_result.content,
                    model=gen_result.model,
                    prompt_version=gen_result.prompt_version,
                    input_tokens=gen_result.input_tokens,
                    output_tokens=gen_result.output_tokens,
                    cost_usd=gen_result.cost_usd,
                    latency_ms=gen_result.latency_ms,
                )
                await session.commit()

                outcomes[section_name] = {
                    "cost_usd": round(gen_result.cost_usd, 6),
                    "latency_ms": gen_result.latency_ms,
                    "input_tokens": gen_result.input_tokens,
                    "output_tokens": gen_result.output_tokens,
                }
                total_cost += gen_result.cost_usd

            except Exception as e:
                await session.rollback()
                log.error("decode.section_failed", section=section_name, error=str(e))
                outcomes[section_name] = {"error": str(e)}

        if all("error" not in v for v in outcomes.values()):
            paper.status = IngestionStatus.DECODED
            await session.commit()

        log.info("decode.done", total_cost_usd=round(total_cost, 6), outcomes=outcomes)
        return {"arxiv_id": arxiv_id, "total_cost_usd": total_cost, "outcomes": outcomes}