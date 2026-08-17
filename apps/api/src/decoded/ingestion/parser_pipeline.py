from __future__ import annotations

import structlog
from sqlalchemy import select

from decoded.db.base import async_session_factory
from decoded.db.models import IngestionStatus, Paper, RunStatus
from decoded.db.repositories.ingestion_runs import IngestionRunsRepository
from decoded.db.repositories.parsed_contents import ParsedContentsRepository
from decoded.parsing.router import ParserRouter

logger = structlog.get_logger()


async def parse_enriched_papers(
    llamaparse_api_key: str,
    limit: int = 10,
) -> dict:
    """
    Parse the next N papers with status=ENRICHED.
    """
    log = logger.bind(source="parser")
    log.info("parse.start", limit=limit)

    router = ParserRouter(llamaparse_api_key=llamaparse_api_key)

    async with async_session_factory() as session:
        runs_repo = IngestionRunsRepository(session)
        parsed_repo = ParsedContentsRepository(session)

        run = await runs_repo.start(source="parser")
        await session.commit()

        stmt = (
            select(Paper)
            .where(Paper.status == IngestionStatus.ENRICHED)
            .order_by(Paper.priority_score.desc(), Paper.published_at.desc())
            .limit(limit)
        )
        result = await session.execute(stmt)
        papers = list(result.scalars().all())

        log.info("parse.papers_selected", count=len(papers))

        parsed = 0
        errors = 0

        for paper in papers:
            paper_log = log.bind(arxiv_id=paper.arxiv_id, title=paper.title[:50])
            try:
                parser = router.pick(paper)
                paper_log.info("parse.routing", parser=parser.name)

                result = await parser.parse(paper.pdf_url)

                await parsed_repo.upsert(
                    paper_id=paper.id,
                    data={
                        "parser": result.parser,
                        "markdown": result.markdown,
                        "figures": result.figures,
                        "equations": result.equations,
                        "parse_ms": result.parse_ms,
                    },
                )
                paper.status = IngestionStatus.PARSED
                await session.commit()
                parsed += 1
                paper_log.info("parse.ok", parse_ms=result.parse_ms, chars=len(result.markdown))

            except Exception as e:
                errors += 1
                paper_log.error("parse.failed", error=str(e))
                await session.rollback()

        await runs_repo.finish(
            run,
            status=RunStatus.SUCCESS,
            papers_found=len(papers),
            papers_new=parsed,
            errors=errors,
        )
        await session.commit()

        log.info("parse.done", parsed=parsed, errors=errors)
        return {"parsed": parsed, "errors": errors}