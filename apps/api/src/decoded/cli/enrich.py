import asyncio
import sys

import structlog

from decoded.config import settings
from decoded.ingestion.enricher import enrich_pending_papers
from decoded.logging import configure_logging

logger = structlog.get_logger()


async def main() -> int:
    configure_logging("INFO")
    logger.info("cli.start", command="enrich")
    try:
        result = await enrich_pending_papers(
            limit=50,
            openalex_email=settings.openalex_email,
            s2_api_key=settings.semantic_scholar_api_key,
        )
        logger.info("cli.done", **result)
        return 0
    except Exception as e:
        logger.error("cli.failed", error=str(e))
        return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))