import asyncio
import sys

import structlog

from decoded.config import settings
from decoded.ingestion.parser_pipeline import parse_enriched_papers
from decoded.logging import configure_logging

logger = structlog.get_logger()


async def main() -> int:
    configure_logging("INFO")

    if not settings.llama_cloud_api_key:
        logger.error("cli.failed", reason="LLAMA_CLOUD_API_KEY not set")
        return 1

    logger.info("cli.start", command="parse")
    try:
        result = await parse_enriched_papers(
            llamaparse_api_key=settings.llama_cloud_api_key,
            limit=5,  # small batch while developing
        )
        logger.info("cli.done", **result)
        return 0
    except Exception as e:
        logger.error("cli.failed", error=str(e))
        return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))