from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from decoded.db.models import Paper


class PapersRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def upsert(self, data: dict) -> tuple[Paper, bool]:
        """Insert or update by arxiv_id. Returns (paper, is_new)."""
        stmt = (
            insert(Paper)
            .values(**data)
            .on_conflict_do_nothing(index_elements=["arxiv_id"])
            .returning(Paper)
        )
        result = await self.session.execute(stmt)
        row = result.scalar_one_or_none()

        if row is not None:
            return row, True

        # Already existed — fetch it
        existing = await self.session.execute(
            select(Paper).where(Paper.arxiv_id == data["arxiv_id"])
        )
        return existing.scalar_one(), False

    async def exists(self, arxiv_id: str) -> bool:
        stmt = select(Paper.id).where(Paper.arxiv_id == arxiv_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none() is not None