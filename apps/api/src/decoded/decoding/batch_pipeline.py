from __future__ import annotations

import structlog
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from decoded.db.base import async_session_factory
from decoded.db.models import IngestionStatus, Paper
from decoded.db.repositories.decoded_contents import DecodedContentsRepository
from decoded.decoding.batch_builder import (
    BatchRequestSpec,
    build_deep_dive_request,
    build_figure_requests,
    build_one_sentence_request,
    build_sixty_second_request,
)
from decoded.decoding.batch_client import BatchClient, BatchResult
from decoded.decoding.batch_schemas import parse_tool_response
from decoded.decoding.figure_extractor import (
    download_pdf,
    extract_figures_from_pdf_bytes,
)
from decoded.decoding.generator import compute_batch_cost
from decoded.decoding.prompts import VERSION
from decoded.decoding.schemas import FiguresExplained

logger = structlog.get_logger()

# Sections supported in batch mode. Vocabulary and analogies are multi-stage
# (each stage depends on the previous), so they stay on the real-time path.
BATCHABLE_SECTIONS = {"one_sentence", "sixty_second", "deep_dive", "figures"}


async def _build_specs_for_paper(
    paper: Paper,
    sections: list[str],
    fast_model: str,
    deep_model: str,
) -> list[BatchRequestSpec]:
    """Build all batch request specs for one paper."""
    specs: list[BatchRequestSpec] = []
    log = logger.bind(arxiv_id=paper.arxiv_id)

    if "one_sentence" in sections:
        specs.append(
            build_one_sentence_request(
                paper.arxiv_id, paper.title, paper.abstract, fast_model
            )
        )

    if "sixty_second" in sections:
        specs.append(
            build_sixty_second_request(
                paper.arxiv_id, paper.title, paper.abstract, fast_model
            )
        )

    if "deep_dive" in sections:
        if paper.parsed_content and paper.parsed_content.markdown:
            specs.append(
                build_deep_dive_request(
                    paper.arxiv_id,
                    paper.title,
                    paper.abstract,
                    paper.parsed_content.markdown,
                    deep_model,
                )
            )
        else:
            log.warning("batch.skip_deep_dive", reason="no_parsed_content")

    if "figures" in sections:
        try:
            pdf_bytes = await download_pdf(paper.pdf_url)
            extraction = extract_figures_from_pdf_bytes(pdf_bytes)
            log.info(
                "batch.figures_extracted",
                found=extraction.total_images_found,
                kept=len(extraction.figures),
            )
            if extraction.figures:
                figures_data = [
                    {
                        "image_b64": f.to_b64(),
                        "media_type": f.media_type,
                        "nearby_text": f.nearby_text,
                    }
                    for f in extraction.figures
                ]
                specs.extend(
                    build_figure_requests(paper.arxiv_id, figures_data, deep_model)
                )
        except Exception as e:
            log.warning("batch.figures_extract_failed", error=str(e))

    return specs


def _group_figure_results(
    results: list[BatchResult],
    specs_by_id: dict[str, BatchRequestSpec],
) -> dict[str, list[tuple[BatchResult, BatchRequestSpec]]]:
    """Group figure results by arxiv_id so they can be merged into one section."""
    grouped: dict[str, list[tuple[BatchResult, BatchRequestSpec]]] = {}
    for result in results:
        spec = specs_by_id.get(result.custom_id)
        if spec is None or spec.section != "figures":
            continue
        grouped.setdefault(spec.arxiv_id, []).append((result, spec))
    return grouped


async def decode_papers_batch(
    arxiv_ids: list[str],
    anthropic_api_key: str,
    fast_model: str,
    deep_model: str,
    sections: list[str] | None = None,
    wait: bool = True,
) -> dict:
    """
    Decode multiple papers via Batch API.

    Submits all requests as one batch, waits for completion, stores results.
    50% cheaper than real-time calls.
    """
    sections = sections or list(BATCHABLE_SECTIONS)
    sections = [s for s in sections if s in BATCHABLE_SECTIONS]

    log = logger.bind(paper_count=len(arxiv_ids), sections=sections)
    log.info("batch_decode.start")

    # ---------- 1. Load papers and build specs ----------
    all_specs: list[BatchRequestSpec] = []

    async with async_session_factory() as session:
        stmt = (
            select(Paper)
            .options(selectinload(Paper.parsed_content))
            .where(Paper.arxiv_id.in_(arxiv_ids))
        )
        result = await session.execute(stmt)
        papers = list(result.scalars().all())

        found_ids = {p.arxiv_id for p in papers}
        missing = set(arxiv_ids) - found_ids
        if missing:
            log.warning("batch_decode.papers_not_found", missing=sorted(missing))

        for paper in papers:
            specs = await _build_specs_for_paper(paper, sections, fast_model, deep_model)
            all_specs.extend(specs)

        paper_id_by_arxiv = {p.arxiv_id: p.id for p in papers}

    if not all_specs:
        log.warning("batch_decode.no_requests")
        return {"error": "no_requests_built"}

    log.info("batch_decode.specs_built", request_count=len(all_specs))

    # ---------- 2. Submit ----------
    requests = [
        {"custom_id": spec.custom_id, "params": spec.request_body}
        for spec in all_specs
    ]
    specs_by_id = {spec.custom_id: spec for spec in all_specs}

    async with BatchClient(api_key=anthropic_api_key) as client:
        batch_id = await client.submit(requests)

        if not wait:
            log.info("batch_decode.submitted_no_wait", batch_id=batch_id)
            return {"batch_id": batch_id, "request_count": len(requests), "status": "submitted"}

        # ---------- 3. Wait ----------
        status = await client.wait_for_completion(batch_id)
        if status != "ended":
            return {"batch_id": batch_id, "error": f"batch_status_{status}"}

        # ---------- 4. Retrieve ----------
        results = await client.retrieve_results(batch_id)

    # ---------- 5. Parse + store ----------
    total_cost = 0.0
    stored = 0
    failed = 0

    figure_groups = _group_figure_results(results, specs_by_id)

    async with async_session_factory() as session:
        decoded_repo = DecodedContentsRepository(session)

        # Non-figure sections: one result per section
        for result in results:
            spec = specs_by_id.get(result.custom_id)
            if spec is None or spec.section == "figures":
                continue

            if not result.succeeded:
                failed += 1
                continue

            try:
                parsed = parse_tool_response(
                    result.content_blocks, spec.response_model, spec.tool_name
                )
                cost = compute_batch_cost(result.usage, spec.request_body["model"])

                await decoded_repo.upsert_section(
                    paper_id=paper_id_by_arxiv[spec.arxiv_id],
                    section=spec.section,
                    content=parsed.model_dump(),
                    model=spec.request_body["model"],
                    prompt_version=VERSION,
                    input_tokens=result.usage.get("input_tokens", 0),
                    output_tokens=result.usage.get("output_tokens", 0),
                    cost_usd=cost,
                    latency_ms=0,  # batch has no meaningful per-request latency
                )
                total_cost += cost
                stored += 1

            except Exception as e:
                failed += 1
                logger.error(
                    "batch_decode.parse_failed",
                    custom_id=result.custom_id,
                    error=str(e),
                )

        # Figures: merge multiple results into one section per paper
        for arxiv_id, entries in figure_groups.items():
            explained = []
            fig_cost = 0.0
            fig_input = 0
            fig_output = 0
            model_name = deep_model

            for result, spec in sorted(entries, key=lambda x: x[0].custom_id):
                if not result.succeeded:
                    continue
                try:
                    parsed = parse_tool_response(
                        result.content_blocks, spec.response_model, spec.tool_name
                    )
                    explained.append(parsed)
                    fig_cost += compute_batch_cost(result.usage, spec.request_body["model"])
                    fig_input += result.usage.get("input_tokens", 0)
                    fig_output += result.usage.get("output_tokens", 0)
                    model_name = spec.request_body["model"]
                except Exception as e:
                    logger.error(
                        "batch_decode.figure_parse_failed",
                        custom_id=result.custom_id,
                        error=str(e),
                    )

            if not explained:
                continue

            wrapped = FiguresExplained(items=explained)
            await decoded_repo.upsert_section(
                paper_id=paper_id_by_arxiv[arxiv_id],
                section="figures",
                content=wrapped.model_dump(),
                model=model_name,
                prompt_version=VERSION,
                input_tokens=fig_input,
                output_tokens=fig_output,
                cost_usd=fig_cost,
                latency_ms=0,
            )
            total_cost += fig_cost
            stored += 1

        await session.commit()

    log.info(
        "batch_decode.done",
        batch_id=batch_id,
        stored=stored,
        failed=failed,
        total_cost_usd=round(total_cost, 4),
        cost_per_paper=round(total_cost / max(len(arxiv_ids), 1), 4),
    )

    return {
        "batch_id": batch_id,
        "papers": len(arxiv_ids),
        "sections_stored": stored,
        "failed": failed,
        "total_cost_usd": round(total_cost, 4),
        "cost_per_paper": round(total_cost / max(len(arxiv_ids), 1), 4),
    }