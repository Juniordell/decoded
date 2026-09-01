"""Flow semanal: clustering, pessoas, digest.

Roda uma vez por semana. A ordem importa — o digest depende de tópicos
e autores atualizados para personalizar corretamente.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from prefect import flow, get_run_logger, task

from decoded.config import settings
from decoded.digest.builder import build_all
from decoded.digest.sender import send_pending
from decoded.logging import configure_logging
from decoded.observability.product import (
    init_product_analytics,
    shutdown_product_analytics,
)
from decoded.observability.tracing import flush as flush_tracing
from decoded.observability.tracing import init_tracing
from decoded.people.backfill import backfill_people
from decoded.topics.clustering import cluster_and_store
from decoded.topics.snapshots import build_snapshots


@task(name="cluster-topics", retries=1, retry_delay_seconds=300)
async def cluster_task(min_cluster_size: int, limit: int) -> dict:
    logger = get_run_logger()

    if not settings.anthropic_api_key:
        logger.warning("ANTHROPIC_API_KEY ausente — pulando clustering")
        return {"skipped": True}

    logger.info(f"Clustering up to {limit} papers")
    return await cluster_and_store(
        qdrant_url=settings.qdrant_url,
        qdrant_api_key=settings.qdrant_api_key,
        anthropic_api_key=settings.anthropic_api_key,
        naming_model=settings.decoder_model_fast,
        min_cluster_size=min_cluster_size,
        limit=limit,
    )


@task(name="build-snapshots", retries=2, retry_delay_seconds=60)
async def snapshots_task(weeks_back: int) -> dict:
    logger = get_run_logger()
    logger.info(f"Building {weeks_back} weeks of snapshots")
    return await build_snapshots(weeks_back=weeks_back)


@task(name="backfill-people", retries=1, retry_delay_seconds=120)
async def people_task() -> dict:
    logger = get_run_logger()
    logger.info("Rebuilding authors and institutions")
    return await backfill_people()


@task(name="build-digests", retries=1, retry_delay_seconds=120)
async def build_digests_task(target_week: datetime, force: bool) -> dict:
    logger = get_run_logger()
    logger.info(f"Building digests for week of {target_week.date()}")
    return await build_all(
        target_week=target_week,
        anthropic_api_key=settings.anthropic_api_key,
        subject_model=settings.digest_subject_model,
        force=force,
    )


@task(name="send-digests", retries=2, retry_delay_seconds=[300, 900])
async def send_digests_task(target_week: datetime, dry_run: bool) -> dict:
    logger = get_run_logger()

    if not settings.resend_api_key and not dry_run:
        logger.warning("RESEND_API_KEY ausente — pulando envio")
        return {"skipped": True}

    logger.info(f"Sending digests for week of {target_week.date()}")
    return await send_pending(
        api_key=settings.resend_api_key or "",
        from_email=settings.digest_from_email,
        site_url=settings.site_url,
        reply_to=settings.digest_reply_to,
        target_week=target_week,
        daily_cap=settings.digest_daily_cap,
        rate_per_second=settings.digest_send_rate_per_second,
        dry_run=dry_run,
    )


@flow(
    name="decoded-weekly",
    log_prints=True,
    description="Clustering, pessoas e digest. Semanal.",
)
async def weekly_flow(
    min_cluster_size: int = 5,
    cluster_limit: int = 5000,
    snapshot_weeks: int = 12,
    skip_send: bool = False,
    dry_run_send: bool = False,
    force_rebuild: bool = False,
) -> dict:
    """
    Ciclo semanal completo.

    A ordem é obrigatória: o digest usa tópicos e autores para
    personalizar, então precisa que os dois estejam atualizados.
    """
    configure_logging("INFO")
    init_tracing()
    init_product_analytics()
    logger = get_run_logger()

    target_week = datetime.now(timezone.utc) - timedelta(weeks=1)
    results: dict = {}

    try:
        logger.info("=== 1/5 clustering ===")
        results["cluster"] = await cluster_task(min_cluster_size, cluster_limit)

        logger.info("=== 2/5 snapshots ===")
        results["snapshots"] = await snapshots_task(snapshot_weeks)

        logger.info("=== 3/5 people ===")
        results["people"] = await people_task()

        logger.info("=== 4/5 building digests ===")
        results["digests_built"] = await build_digests_task(
            target_week, force_rebuild
        )

        if skip_send:
            logger.info("=== 5/5 sending SKIPPED ===")
            results["digests_sent"] = {"skipped": True, "reason": "skip_send"}
        else:
            logger.info("=== 5/5 sending ===")
            results["digests_sent"] = await send_digests_task(
                target_week, dry_run_send
            )

    finally:
        shutdown_product_analytics()
        flush_tracing()

    logger.info(f"Weekly complete: {results}")
    return results