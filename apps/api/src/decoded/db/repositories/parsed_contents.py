from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from decoded.db.models import ParsedContent


class ParsedContentsRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def upsert(self, paper_id: int, data: dict) -> ParsedContent:
        """Insert or replace parsed content for a paper."""
        # Because paper_id is UNIQUE, we do a find-then-update or insert
        existing = await self.session.execute(
            select(ParsedContent).where(ParsedContent.paper_id == paper_id)
        )
        row = existing.scalar_one_or_none()

        if row is not None:
            for k, v in data.items():
                setattr(row, k, v)
            return row

        row = ParsedContent(paper_id=paper_id, **data)
        self.session.add(row)
        await self.session.flush()
        return row