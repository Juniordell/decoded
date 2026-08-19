"""CLI for batch decoding.

Usage:
    # Decode specific papers
    poetry run python -m decoded.cli.batch_decode --arxiv-ids 2608.06221,2608.06222

    # Decode top N by priority that aren't decoded yet
    poetry run python -m decoded.cli.batch_decode --top 10

    # Submit without waiting (check later)
    poetry run python -m decoded.cli.batch_decode --top 10 --no-wait
"""

import argparse
import asyncio
import sys

import structlog
from sqlalchemy import select

from decoded.config import settings
from decoded.db.base import async_session_factory
from decoded.db.models import IngestionStatus, Paper
from decoded.decoding.batch_pipeline import decode_papers_batch
from decoded.logging import configure_logging

logger = structlog.get_logger()


async def _top_undecoded(limit: int) -> list[str]:
    """Get top-N papers by priority that have parsed content but aren't decoded."""
    async with async_session_factory() as session:
        stmt = (
            select(Paper.arxiv_id)
            .where(Paper.status.in_([IngestionStatus.EMBEDDED, IngestionStatus.PARSED]))
            .order_by(Paper.priority_score.desc(), Paper.published_at.desc())
            .limit(limit)
        )
        result = await session.execute(stmt)
        return [row for row in result.scalars().all()]


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--arxiv-ids", help="Comma-separated arXiv IDs")
    parser.add_argument("--top", type=int, help="Decode top N undecoded papers by priority")
    parser.add_argument(
        "--sections",
        default="one_sentence,sixty_second,deep_dive,figures",
        help="Comma-separated section names (batchable only)",
    )
    parser.add_argument(
        "--no-wait",
        action="store_true",
        help="Submit the batch and exit without waiting for results",
    )
    args = parser.parse_args()

    configure_logging("INFO")

    if not settings.anthropic_api_key:
        logger.error("cli.failed", reason="ANTHROPIC_API_KEY not set")
        return 1

    if args.arxiv_ids:
        arxiv_ids = [x.strip() for x in args.arxiv_ids.split(",") if x.strip()]
    elif args.top:
        arxiv_ids = await _top_undecoded(args.top)
        logger.info("cli.selected_papers", count=len(arxiv_ids), arxiv_ids=arxiv_ids)
    else:
        logger.error("cli.failed", reason="provide --arxiv-ids or --top")
        return 1

    if not arxiv_ids:
        logger.warning("cli.no_papers")
        return 0

    sections = [s.strip() for s in args.sections.split(",") if s.strip()]

    result = await decode_papers_batch(
        arxiv_ids=arxiv_ids,
        anthropic_api_key=settings.anthropic_api_key,
        fast_model=settings.decoder_model_fast,
        deep_model=settings.decoder_model_deep,
        sections=sections,
        wait=not args.no_wait,
    )

    if "error" in result:
        logger.error("cli.failed", **result)
        return 1

    logger.info("cli.done", **result)
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))