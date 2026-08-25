import asyncio
import sys

import structlog

from decoded.config import settings
from decoded.embeddings.pipeline import embed_parsed_papers
from decoded.logging import configure_logging

logger = structlog.get_logger()


async def main() -> int:
    configure_logging("INFO")

    if not settings.openai_api_key:
        logger.error("cli.failed", reason="OPENAI_API_KEY not set")
        return 1

    logger.info("cli.start", command="embed")
    try:
        result = await embed_parsed_papers(
            openai_api_key=settings.openai_api_key,
            qdrant_url=settings.qdrant_url,
            embedding_model_small=settings.embedding_model_small,
            embedding_model_large=settings.embedding_model_large,
            limit=10,
            qdrant_api_key=settings.qdrant_api_key,
        )
        logger.info("cli.done", **result)
        return 0
    except Exception as e:
        logger.error("cli.failed", error=str(e))
        return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))