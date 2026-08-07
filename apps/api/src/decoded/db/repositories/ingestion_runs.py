from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from decoded.db.models import IngestionRun, RunStatus


class IngestionRunsRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def start(self, source: str) -> IngestionRun:
        run = IngestionRun(
            source=source,
            status=RunStatus.RUNNING,
            started_at=datetime.now(timezone.utc),
        )
        self.session.add(run)
        await self.session.flush()
        return run

    async def finish(
        self,
        run: IngestionRun,
        status: RunStatus,
        papers_found: int = 0,
        papers_new: int = 0,
        errors: int = 0,
        log: dict | None = None,
    ) -> None:
        run.status = status
        run.finished_at = datetime.now(timezone.utc)
        run.papers_found = papers_found
        run.papers_new = papers_new
        run.errors = errors
        if log is not None:
            run.log = log
        await self.session.flush()