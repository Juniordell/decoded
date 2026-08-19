import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from sqlalchemy import select  # noqa: E402

from decoded.db.base import async_session_factory  # noqa: E402
from decoded.db.models import IngestionStatus, Paper  # noqa: E402


async def main() -> None:
    async with async_session_factory() as session:
        stmt = (
            select(Paper)
            .where(Paper.status.in_([IngestionStatus.PARSED, IngestionStatus.EMBEDDED, IngestionStatus.DECODED]))
            .order_by(Paper.priority_score.desc())
            .limit(40)
        )
        result = await session.execute(stmt)
        papers = list(result.scalars().all())

    # Agrupa por categoria primária pra garantir diversidade
    by_cat: dict[str, list] = {}
    for p in papers:
        cat = (p.categories or ["unknown"])[0]
        by_cat.setdefault(cat, []).append(p)

    print(f"\n{len(papers)} papers candidatos, {len(by_cat)} categorias\n")

    suggestions = []
    for cat, group in sorted(by_cat.items(), key=lambda x: -len(x[1])):
        top = group[0]
        suggestions.append(
            {
                "arxiv_id": top.arxiv_id,
                "type": "TODO: empirical | theory | survey | benchmark | position",
                "notes": f"[{cat}] {top.title[:70]}",
            }
        )
        print(f"{cat:12} · {top.arxiv_id} · prio {top.priority_score:.1f} · {top.title[:60]}")

    print("\n--- JSON pra colar em evals/golden/papers.json ---\n")
    print(json.dumps({"version": 1, "papers": suggestions}, indent=2))


if __name__ == "__main__":
    asyncio.run(main())