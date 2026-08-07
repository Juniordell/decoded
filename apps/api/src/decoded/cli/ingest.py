import asyncio
import sys

import structlog

from decoded.ingestion.arxiv_poller import run_arxiv_poll
from decoded.logging import configure_logging

logger = structlog.get_logger()


async def main() -> int:
    configure_logging("INFO")
    logger.info("cli.start", command="arxiv-poll")
    try:
        result = await run_arxiv_poll(lookback_hours=24, max_results=200)
        logger.info("cli.done", **result)
        return 0
    except Exception as e:
        logger.error("cli.failed", error=str(e))
        return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))