"""CLI para clustering e snapshots.

Uso:
    poetry run python -m decoded.cli.topics cluster
    poetry run python -m decoded.cli.topics cluster --min-cluster-size 8
    poetry run python -m decoded.cli.topics snapshots
    poetry run python -m decoded.cli.topics momentum
"""

import argparse
import asyncio
import json
import sys

import structlog

from decoded.config import settings
from decoded.logging import configure_logging
from decoded.topics.clustering import cluster_and_store
from decoded.topics.snapshots import build_snapshots, compute_momentum

logger = structlog.get_logger()


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["cluster", "snapshots", "momentum"])
    parser.add_argument("--min-cluster-size", type=int, default=5)
    parser.add_argument("--limit", type=int, default=5000)
    parser.add_argument("--weeks", type=int, default=12)
    args = parser.parse_args()

    configure_logging("INFO")

    if args.command == "cluster":
        if not settings.anthropic_api_key:
            logger.error("cli.failed", reason="ANTHROPIC_API_KEY não definida")
            return 1

        result = await cluster_and_store(
            qdrant_url=settings.qdrant_url,
            qdrant_api_key=settings.qdrant_api_key,
            anthropic_api_key=settings.anthropic_api_key,
            naming_model=settings.decoder_model_fast,
            min_cluster_size=args.min_cluster_size,
            limit=args.limit,
        )

        if "error" in result:
            logger.error("cli.failed", **result)
            return 1

        print("\n" + "=" * 68)
        print(f"  {result['topics_found']} tópicos · {result['outliers']} outliers")
        print(f"  {result['papers_clustered']} papers · ${result['naming_cost_usd']}")
        print("=" * 68)
        for t in result["topics"][:20]:
            print(f"  {t['count']:>4}  {t['name']}")
        print()
        return 0

    if args.command == "snapshots":
        result = await build_snapshots(weeks_back=args.weeks)
        logger.info("cli.done", **result)
        return 0

    if args.command == "momentum":
        rows = await compute_momentum(weeks=4)
        print("\n" + "=" * 68)
        print(f"  {'CHANGE':>8}  {'RECENT':>7} {'PRIOR':>6}  TOPIC")
        print("=" * 68)
        for r in rows[:25]:
            arrow = "↑" if r["change"] > 0.25 else "↓" if r["change"] < -0.25 else "·"
            print(
                f"  {r['change']:>+7.1%} {arrow}  {r['recent_papers']:>7} "
                f"{r['prior_papers']:>6}  {r['name']}"
            )
        print()
        return 0

    return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))