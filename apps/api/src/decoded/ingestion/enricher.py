from __future__ import annotations

import asyncio
from typing import Optional

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from decoded.db.base import async_session_factory
from decoded.db.models import IngestionStatus, Paper, RunStatus
from decoded.db.repositories.ingestion_runs import IngestionRunsRepository
from decoded.external.hackernews import HackerNewsClient
from decoded.external.openalex import OpenAlexClient
from decoded.external.semantic_scholar import SemanticScholarClient
from decoded.ingestion.scoring import compute_priority

logger = structlog.get_logger()


async def _enrich_one(
    paper: Paper,
    openalex: OpenAlexClient,
    s2: SemanticScholarClient,
    hn: HackerNewsClient,
) -> dict:
    """
    Fan out 3 API calls in parallel. Handle partial failure.
    """
    log = logger.bind(arxiv_id=paper.arxiv_id)

    results = await asyncio.gather(
        _safe(openalex.get_by_arxiv_id(paper.arxiv_id), "openalex"),
        _safe(s2.get_by_arxiv_id(paper.arxiv_id), "s2"),
        _safe(hn.search_mentions(paper.arxiv_id, paper.title), "hn"),
    )
    oa_data, s2_data, hn_data = results

    # Merge into paper columns + JSON extras
    updates: dict = {}
    extras: dict = dict(paper.extra or {})

    if oa_data:
        updates["openalex_id"] = oa_data["openalex_id"]
        updates["citation_count"] = oa_data["cited_by_count"]
        extras["openalex"] = oa_data

    if s2_data:
        updates["semantic_scholar_id"] = s2_data["semantic_scholar_id"]
        extras["s2"] = s2_data

    if hn_data:
        updates["hn_mentions"] = hn_data["mentions"]
        extras["hn"] = hn_data

    # Priority score
    affiliations = []
    if oa_data:
        affiliations = [a.get("affiliation") for a in oa_data.get("authorships", [])]

    priority = compute_priority(
        citation_count=updates.get("citation_count", 0),
        hn_mentions=updates.get("hn_mentions", 0),
        hn_points=(hn_data or {}).get("total_points", 0),
        affiliations=affiliations,
        tldr_available=bool(s2_data and s2_data.get("tldr")),
    )
    updates["priority_score"] = priority
    updates["extra"] = extras
    updates["status"] = IngestionStatus.ENRICHED

    log.info(
        "enriched",
        priority=priority,
        citations=updates.get("citation_count", 0),
        hn_mentions=updates.get("hn_mentions", 0),
        sources=[k for k, v in {"oa": oa_data, "s2": s2_data, "hn": hn_data}.items() if v],
    )
    return updates


async def _safe(coro, source: str):
    """Await a coroutine, return None on failure. Never raises."""
    try:
        return await coro
    except Exception as e:
        logger.warning("enrich.source_failed", source=source, error=str(e))
        return None


async def enrich_pending_papers(
    limit: int = 50,
    openalex_email: str | None = None,
    s2_api_key: str | None = None,
) -> dict:
    """
    Enrich the next N papers with status=FETCHED.
    Runs each paper's 3 API calls in parallel.
    Runs papers sequentially (respecting API rate limits).
    """
    log = logger.bind(source="enricher")
    log.info("enrich.start", limit=limit)

    async with async_session_factory() as session:
        runs_repo = IngestionRunsRepository(session)
        run = await runs_repo.start(source="enricher")
        await session.commit()

        # Fetch papers to enrich
        stmt = (
            select(Paper)
            .where(Paper.status == IngestionStatus.FETCHED)
            .order_by(Paper.published_at.desc())
            .limit(limit)
        )
        result = await session.execute(stmt)
        papers = list(result.scalars().all())

        log.info("enrich.papers_selected", count=len(papers))

        enriched = 0
        errors = 0

        async with (
            OpenAlexClient(email=openalex_email) as oa,
            SemanticScholarClient(api_key=s2_api_key) as s2,
            HackerNewsClient() as hn,
        ):
            for paper in papers:
                try:
                    updates = await _enrich_one(paper, oa, s2, hn)
                    for k, v in updates.items():
                        setattr(paper, k, v)
                    await session.commit()
                    enriched += 1
                except Exception as e:
                    errors += 1
                    log.error("enrich.paper_failed", arxiv_id=paper.arxiv_id, error=str(e))
                    await session.rollback()

        await runs_repo.finish(
            run,
            status=RunStatus.SUCCESS if errors == 0 else RunStatus.SUCCESS,  # partial ok
            papers_found=len(papers),
            papers_new=enriched,
            errors=errors,
        )
        await session.commit()

        log.info("enrich.done", enriched=enriched, errors=errors)
        return {"enriched": enriched, "errors": errors}