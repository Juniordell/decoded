"""Flow de ingestão: arXiv → enriquecimento → parsing → embedding.

Roda de hora em hora. Cada etapa é independente o suficiente para que
a falha de uma não impeça as outras de progredir no que já têm.
"""

from __future__ import annotations

from datetime import timedelta

from prefect import flow, get_run_logger, task
from prefect.tasks import task_input_hash

from decoded.config import settings
from decoded.embeddings.pipeline import embed_parsed_papers
from decoded.ingestion.arxiv_poller import run_arxiv_poll
from decoded.ingestion.enricher import enrich_pending_papers
from decoded.ingestion.parser_pipeline import parse_enriched_papers
from decoded.logging import configure_logging
from decoded.observability.tracing import flush as flush_tracing
from decoded.observability.tracing import init_tracing


@task(
    name="arxiv-poll",
    retries=3,
    retry_delay_seconds=[30, 120, 600],
    cache_key_fn=task_input_hash,
    cache_expiration=timedelta(minutes=30),
)
async def poll_arxiv_task(lookback_hours: int, max_results: int) -> dict:
    logger = get_run_logger()
    logger.info(f"Polling arXiv: {lookback_hours}h, max {max_results}")
    return await run_arxiv_poll(
        lookback_hours=lookback_hours,
        max_results=max_results,
    )


@task(name="enrich-papers", retries=2, retry_delay_seconds=[60, 300])
async def enrich_task(limit: int) -> dict:
    logger = get_run_logger()
    logger.info(f"Enriching up to {limit} papers")
    return await enrich_pending_papers(
        limit=limit,
        openalex_email=settings.openalex_email,
        s2_api_key=settings.semantic_scholar_api_key,
    )


@task(name="parse-papers", retries=2, retry_delay_seconds=[60, 300])
async def parse_task(limit: int) -> dict:
    logger = get_run_logger()

    if not settings.llama_cloud_api_key:
        logger.warning("LLAMA_CLOUD_API_KEY ausente — pulando parsing")
        return {"parsed": 0, "errors": 0, "skipped": True}

    logger.info(f"Parsing up to {limit} papers")
    return await parse_enriched_papers(
        llamaparse_api_key=settings.llama_cloud_api_key,
        limit=limit,
    )


@task(name="embed-papers", retries=2, retry_delay_seconds=[60, 300])
async def embed_task(limit: int) -> dict:
    logger = get_run_logger()

    if not settings.openai_api_key:
        logger.warning("OPENAI_API_KEY ausente — pulando embedding")
        return {"embedded": 0, "errors": 0, "skipped": True}

    logger.info(f"Embedding up to {limit} papers")
    return await embed_parsed_papers(
        openai_api_key=settings.openai_api_key,
        qdrant_url=settings.qdrant_url,
        embedding_model_small=settings.embedding_model_small,
        embedding_model_large=settings.embedding_model_large,
        limit=limit,
        qdrant_api_key=settings.qdrant_api_key,
    )


@flow(
    name="decoded-ingestion",
    log_prints=True,
    description="arXiv → enrich → parse → embed. Horário.",
)
async def ingestion_flow(
    lookback_hours: int = 2,
    poll_max: int = 100,
    enrich_limit: int = 100,
    parse_limit: int = 10,
    embed_limit: int = 100,
) -> dict:
    configure_logging("INFO")
    init_tracing()
    logger = get_run_logger()

    results: dict = {}

    try:
        logger.info("=== 1/4 arXiv ===")
        results["poll"] = await poll_arxiv_task(lookback_hours, poll_max)

        logger.info("=== 2/4 enrichment ===")
        results["enrich"] = await enrich_task(enrich_limit)

        logger.info("=== 3/4 parsing ===")
        results["parse"] = await parse_task(parse_limit)

        logger.info("=== 4/4 embedding ===")
        results["embed"] = await embed_task(embed_limit)

    finally:
        flush_tracing()

    logger.info(f"Ingestion complete: {results}")
    return results