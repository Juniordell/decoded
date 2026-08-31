"""CLI para backfill de autores e instituições.

Uso:
    poetry run python -m decoded.cli.people backfill
    poetry run python -m decoded.cli.people backfill --limit 500
    poetry run python -m decoded.cli.people stats
"""

import argparse
import asyncio
import sys

import structlog
from sqlalchemy import func, select

from decoded.db.base import async_session_factory
from decoded.db.models import Author, Institution
from decoded.logging import configure_logging
from decoded.people.backfill import backfill_people

logger = structlog.get_logger()


async def show_stats() -> None:
    async with async_session_factory() as session:
        total_authors = (
            await session.execute(select(func.count(Author.id)))
        ).scalar_one()
        disambiguated = (
            await session.execute(
                select(func.count(Author.id)).where(Author.is_disambiguated.is_(True))
            )
        ).scalar_one()
        total_inst = (
            await session.execute(select(func.count(Institution.id)))
        ).scalar_one()

        top_authors = (
            await session.execute(
                select(Author)
                .where(Author.paper_count > 1)
                .order_by(Author.paper_count.desc(), Author.total_citations.desc())
                .limit(15)
            )
        ).scalars().all()

        top_inst = (
            await session.execute(
                select(Institution)
                .order_by(Institution.paper_count.desc())
                .limit(15)
            )
        ).scalars().all()

    pct = (disambiguated / total_authors * 100) if total_authors else 0

    print("\n" + "=" * 70)
    print(f"  {total_authors} autores  ({disambiguated} desambiguados, {pct:.0f}%)")
    print(f"  {total_inst} instituições")
    print("=" * 70)

    if top_authors:
        print("\n  AUTORES MAIS ATIVOS\n")
        for a in top_authors:
            mark = "✓" if a.is_disambiguated else "~"
            aff = f"  ·  {a.affiliation[:40]}" if a.affiliation else ""
            print(f"  {mark} {a.paper_count:>3} papers  {a.name[:35]:<37}{aff}")

    if top_inst:
        print("\n  INSTITUIÇÕES\n")
        for i in top_inst:
            print(f"    {i.paper_count:>3} papers  {i.name[:50]}")

    print()


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["backfill", "stats"])
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()

    configure_logging("INFO")

    if args.command == "backfill":
        result = await backfill_people(limit=args.limit)
        print("\n" + "=" * 70)
        print(f"  {result['papers_processed']} papers processados")
        print(f"  {result['authors_created']} autores criados")
        print(f"    {result['disambiguated']} via OpenAlex")
        print(f"    {result['name_matched']} agrupados por nome")
        print(f"  {result['institutions_created']} instituições")
        print(f"  {result['links_created']} vínculos")
        if result["errors"]:
            print(f"\n  {len(result['errors'])} erros (primeiros):")
            for e in result["errors"]:
                print(f"    {e}")
        print("=" * 70 + "\n")
        return 0

    await show_stats()
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))