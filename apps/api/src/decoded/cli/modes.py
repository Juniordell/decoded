"""CLI para gerar modos de explicação.

Uso:
    poetry run python -m decoded.cli.modes --arxiv-id 2608.06221
    poetry run python -m decoded.cli.modes --arxiv-id 2608.06221 --modes math,code
    poetry run python -m decoded.cli.modes --arxiv-id 2608.06221 --modes diagram --force
"""

import argparse
import asyncio
import sys

import structlog

from decoded.config import settings
from decoded.logging import configure_logging
from decoded.modes.pipeline import generate_all_modes
from decoded.modes.schemas import ALL_MODES
from decoded.observability.tracing import flush as flush_tracing
from decoded.observability.tracing import init_tracing

logger = structlog.get_logger()


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--arxiv-id", required=True)
    parser.add_argument(
        "--modes",
        default=",".join(ALL_MODES),
        help=f"Modos separados por vírgula. Disponíveis: {', '.join(ALL_MODES)}",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Regenera mesmo se já estiver em cache",
    )
    args = parser.parse_args()

    configure_logging("INFO")
    init_tracing()

    if not settings.anthropic_api_key:
        logger.error("cli.failed", reason="ANTHROPIC_API_KEY não definida")
        return 1

    modes = [m.strip() for m in args.modes.split(",") if m.strip()]

    try:
        result = await generate_all_modes(
            arxiv_id=args.arxiv_id,
            anthropic_api_key=settings.anthropic_api_key,
            fast_model=settings.decoder_model_fast,
            deep_model=settings.decoder_model_deep,
            modes=modes,
            force=args.force,
        )
    finally:
        flush_tracing()

    logger.info(
        "cli.done",
        arxiv_id=result["arxiv_id"],
        total_cost_usd=result["total_cost_usd"],
        statuses={m: r.get("status") for m, r in result["modes"].items()},
    )
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))