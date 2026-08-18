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
from prefect.blocks.system import Secret

openai_key = Secret.load("openai-api-key").get()

# ---------- tasks ----------
@task(
    name="arxiv-poll",
    retries=3,
    retry_delay_seconds=[30, 120, 600],  # 30s, 2m, 10m
    cache_key_fn=task_input_hash,
    cache_expiration=timedelta(minutes=30),  # don't re-poll if run recently
)
async def poll_arxiv_task(lookback_hours: int, max_results: int) -> dict:
    logger = get_run_logger()
    logger.info(f"Polling arXiv (lookback={lookback_hours}h, max={max_results})")
    return await run_arxiv_poll(
        lookback_hours=lookback_hours,
        max_results=max_results,
    )


@task(
    name="enrich-papers",
    retries=2,
    retry_delay_seconds=[60, 300],
)
async def enrich_task(limit: int) -> dict:
    logger = get_run_logger()
    logger.info(f"Enriching up to {limit} papers")
    return await enrich_pending_papers(
        limit=limit,
        openalex_email=settings.openalex_email,
        s2_api_key=settings.semantic_scholar_api_key,
    )


@task(
    name="parse-papers",
    retries=2,
    retry_delay_seconds=[60, 300],
)
async def parse_task(limit: int) -> dict:
    logger = get_run_logger()

    if not settings.llama_cloud_api_key:
        logger.warning("LLAMA_CLOUD_API_KEY not set — skipping parse stage")
        return {"parsed": 0, "errors": 0, "skipped": True}

    logger.info(f"Parsing up to {limit} papers")
    return await parse_enriched_papers(
        llamaparse_api_key=settings.llama_cloud_api_key,
        limit=limit,
    )


@task(
    name="embed-papers",
    retries=2,
    retry_delay_seconds=[60, 300],
)
async def embed_task(limit: int) -> dict:
    logger = get_run_logger()

    if not settings.openai_api_key:
        logger.warning("OPENAI_API_KEY not set — skipping embed stage")
        return {"embedded": 0, "errors": 0, "skipped": True}

    logger.info(f"Embedding up to {limit} papers")
    return await embed_parsed_papers(
        openai_api_key=settings.openai_api_key,
        qdrant_url=settings.qdrant_url,
        embedding_model_small=settings.embedding_model_small,
        embedding_model_large=settings.embedding_model_large,
        limit=limit,
    )


# ---------- flow ----------
@flow(
    name="decoded-ingestion",
    log_prints=True,
    description="Ingest → enrich → parse → embed. Runs hourly.",
)
async def ingestion_flow(
    lookback_hours: int = 2,
    poll_max: int = 100,
    enrich_limit: int = 50,
    parse_limit: int = 5,   # small while developing (LlamaParse quota)
    embed_limit: int = 10,
) -> dict:
    """Full pipeline, one stage at a time. Later stages only run if earlier ones succeed."""
    configure_logging("INFO")
    logger = get_run_logger()

    logger.info("=== Stage 1: arXiv poll ===")
    poll_result = await poll_arxiv_task(lookback_hours, poll_max)
    logger.info(f"Poll: {poll_result}")

    logger.info("=== Stage 2: enrichment ===")
    enrich_result = await enrich_task(enrich_limit)
    logger.info(f"Enrich: {enrich_result}")

    logger.info("=== Stage 3: parsing ===")
    parse_result = await parse_task(parse_limit)
    logger.info(f"Parse: {parse_result}")

    logger.info("=== Stage 4: embedding ===")
    embed_result = await embed_task(embed_limit)
    logger.info(f"Embed: {embed_result}")

    return {
        "poll": poll_result,
        "enrich": enrich_result,
        "parse": parse_result,
        "embed": embed_result,
    }