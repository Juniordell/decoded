from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Iterable

import arxiv
import structlog
from tenacity import retry, stop_after_attempt, wait_exponential

from decoded.db.base import async_session_factory
from decoded.db.models import IngestionStatus, RunStatus
from decoded.db.repositories.ingestion_runs import IngestionRunsRepository
from decoded.db.repositories.papers import PapersRepository

logger = structlog.get_logger()

# arXiv categories relevant to Decoded
DEFAULT_CATEGORIES = ["cs.AI", "cs.CL", "cs.LG", "cs.CV"]

# arXiv rate limit: 1 request per 3 seconds. We'll be gentle.
ARXIV_DELAY_SECONDS = 3.0


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=30),
    reraise=True,
)
def _fetch_from_arxiv(
    categories: list[str],
    since: datetime,
    max_results: int,
) -> Iterable[arxiv.Result]:
    """Blocking call to arXiv. Wrapped for retries."""
    # arXiv query syntax: cat:cs.AI OR cat:cs.CL OR ...
    query = " OR ".join(f"cat:{c}" for c in categories)

    client = arxiv.Client(
        page_size=100,
        delay_seconds=ARXIV_DELAY_SECONDS,
        num_retries=3,
    )

    search = arxiv.Search(
        query=query,
        max_results=max_results,
        sort_by=arxiv.SortCriterion.SubmittedDate,
        sort_order=arxiv.SortOrder.Descending,
    )

    for result in client.results(search):
        if result.published < since:
            # Older than window — arXiv results are ordered desc, so we can stop
            break
        yield result


def _result_to_dict(result: arxiv.Result) -> dict:
    """Turn an arxiv.Result into a dict matching our Paper model."""
    arxiv_id = result.get_short_id()  # e.g. "2401.12345v1"
    # Normalize — strip version so 2401.12345v1 and 2401.12345v2 dedupe
    arxiv_id_clean = arxiv_id.split("v")[0]

    return {
        "arxiv_id": arxiv_id_clean,
        "title": result.title.strip(),
        "abstract": result.summary.strip(),
        "published_at": result.published,
        "arxiv_updated_at": result.updated,
        "pdf_url": result.pdf_url,
        "categories": [c for c in result.categories],
        "status": IngestionStatus.FETCHED,
        "extra": {
            "arxiv_id_versioned": arxiv_id,
            "authors_raw": [a.name for a in result.authors],
            "primary_category": result.primary_category,
            "comment": result.comment,
            "doi": result.doi,
        },
    }


async def run_arxiv_poll(
    categories: list[str] | None = None,
    lookback_hours: int = 24,
    max_results: int = 200,
) -> dict:
    """
    Fetch recent arXiv papers, upsert to DB, log the run.
    Returns run stats.
    """
    categories = categories or DEFAULT_CATEGORIES
    since = datetime.now(timezone.utc) - timedelta(hours=lookback_hours)

    log = logger.bind(source="arxiv", lookback_hours=lookback_hours)
    log.info("poll.start", categories=categories)

    async with async_session_factory() as session:
        runs_repo = IngestionRunsRepository(session)
        papers_repo = PapersRepository(session)

        run = await runs_repo.start(source="arxiv")
        await session.commit()

        found = 0
        new = 0
        errors = 0
        error_samples: list[str] = []

        try:
            for result in _fetch_from_arxiv(categories, since, max_results):
                found += 1
                try:
                    data = _result_to_dict(result)
                    _, is_new = await papers_repo.upsert(data)
                    if is_new:
                        new += 1
                        log.info(
                            "paper.upserted",
                            arxiv_id=data["arxiv_id"],
                            title=data["title"][:60],
                            is_new=True,
                        )
                except Exception as e:
                    errors += 1
                    error_samples.append(f"{result.get_short_id()}: {e}")
                    log.warning("paper.error", arxiv_id=result.get_short_id(), error=str(e))

            await session.commit()

            await runs_repo.finish(
                run,
                status=RunStatus.SUCCESS,
                papers_found=found,
                papers_new=new,
                errors=errors,
                log={"error_samples": error_samples[:10]},
            )
            await session.commit()

            log.info("poll.done", found=found, new=new, errors=errors)
            return {"found": found, "new": new, "errors": errors}

        except Exception as e:
            log.error("poll.failed", error=str(e))
            await session.rollback()
            await runs_repo.finish(
                run,
                status=RunStatus.FAILED,
                papers_found=found,
                errors=errors + 1,
                log={"fatal": str(e), "error_samples": error_samples[:10]},
            )
            await session.commit()
            raise