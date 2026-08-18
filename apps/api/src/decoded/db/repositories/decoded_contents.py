from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from decoded.db.models import DecodedContent
from decoded.decoding.schemas import SCHEMA_VERSION


class DecodedContentsRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def upsert_section(
        self,
        paper_id: int,
        section: str,
        content: dict,
        model: str,
        prompt_version: str,
        input_tokens: int,
        output_tokens: int,
        cost_usd: float,
        latency_ms: int,
    ) -> DecodedContent:
        """Store one generated section. Overwrites if same (paper, section, schema, prompt) combo exists."""
        stmt = (
            insert(DecodedContent)
            .values(
                paper_id=paper_id,
                section=section,
                content=content,
                schema_version=SCHEMA_VERSION,
                model=model,
                prompt_version=prompt_version,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                cost_usd=cost_usd,
                latency_ms=latency_ms,
            )
            .on_conflict_do_update(
                constraint="uq_decoded_contents_paper_section_versions",
                set_={
                    "content": insert(DecodedContent).excluded.content,
                    "model": insert(DecodedContent).excluded.model,
                    "input_tokens": insert(DecodedContent).excluded.input_tokens,
                    "output_tokens": insert(DecodedContent).excluded.output_tokens,
                    "cost_usd": insert(DecodedContent).excluded.cost_usd,
                    "latency_ms": insert(DecodedContent).excluded.latency_ms,
                },
            )
            .returning(DecodedContent)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one()

    async def get_all_sections(
        self,
        paper_id: int,
        prompt_version: str = "v1",
    ) -> dict[str, DecodedContent]:
        """Return all decoded sections for a paper, keyed by section name."""
        stmt = select(DecodedContent).where(
            DecodedContent.paper_id == paper_id,
            DecodedContent.schema_version == SCHEMA_VERSION,
            DecodedContent.prompt_version == prompt_version,
        )
        result = await self.session.execute(stmt)
        return {row.section: row for row in result.scalars().all()}