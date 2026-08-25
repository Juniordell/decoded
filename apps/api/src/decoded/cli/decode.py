"""CLI for decoding a specific paper.

Usage:
    poetry run python -m decoded.cli.decode --arxiv-id 2401.12345
    poetry run python -m decoded.cli.decode --arxiv-id 2401.12345 --sections one_sentence
    poetry run python -m decoded.cli.decode --arxiv-id 2401.12345 --sections one_sentence,sixty_second
"""

import argparse
import asyncio
import sys

import structlog

from decoded.config import settings
from decoded.decoding.pipeline import decode_paper
from decoded.logging import configure_logging
from decoded.observability.tracing import flush as flush_tracing
from decoded.observability.tracing import init_tracing

logger = structlog.get_logger()


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--arxiv-id", required=True)
    parser.add_argument(
        "--sections",
        default="one_sentence,sixty_second,deep_dive,figures,vocabulary,analogies",
    )
    args = parser.parse_args()

    configure_logging("INFO")
    init_tracing()

    if not settings.anthropic_api_key:
        logger.error("cli.failed", reason="ANTHROPIC_API_KEY not set")
        return 1

    sections = [s.strip() for s in args.sections.split(",") if s.strip()]

    try:
        result = await decode_paper(
            arxiv_id=args.arxiv_id,
            anthropic_api_key=settings.anthropic_api_key,
            fast_model=settings.decoder_model_fast,
            deep_model=settings.decoder_model_deep,
            sections=sections,
        )
    finally:
        flush_tracing()

    if "error" in result:
        logger.error("cli.failed", **result)
        return 1

    logger.info("cli.done", **result)
    return 0

if __name__ == "__main__":
    sys.exit(asyncio.run(main()))