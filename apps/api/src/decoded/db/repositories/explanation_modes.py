from __future__ import annotations

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from decoded.db.models import ExplanationMode, ModeStatus
from decoded.modes.schemas import MODE_SCHEMA_VERSION


class ExplanationModesRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(
        self,
        paper_id: int,
        mode: str,
        prompt_version: str,
    ) -> ExplanationMode | None:
        stmt = select(ExplanationMode).where(
            ExplanationMode.paper_id == paper_id,
            ExplanationMode.mode == mode,
            ExplanationMode.schema_version == MODE_SCHEMA_VERSION,
            ExplanationMode.prompt_version == prompt_version,
        )
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def list_for_paper(
        self,
        paper_id: int,
        prompt_version: str,
    ) -> dict[str, ExplanationMode]:
        stmt = select(ExplanationMode).where(
            ExplanationMode.paper_id == paper_id,
            ExplanationMode.schema_version == MODE_SCHEMA_VERSION,
            ExplanationMode.prompt_version == prompt_version,
        )
        rows = (await self.session.execute(stmt)).scalars().all()
        return {row.mode: row for row in rows}

    async def claim(
        self,
        paper_id: int,
        mode: str,
        prompt_version: str,
        user_id: int | None,
    ) -> tuple[ExplanationMode, bool]:
        """
        Reserva a geração de um modo.

        Retorna (row, is_new_claim). Se is_new_claim=False, outra requisição
        já está gerando ou o conteúdo já existe — não gere de novo.

        Usa ON CONFLICT DO NOTHING para ser atômico: duas requisições
        simultâneas pro mesmo modo, só uma reserva.
        """
        stmt = (
            insert(ExplanationMode)
            .values(
                paper_id=paper_id,
                mode=mode,
                status=ModeStatus.GENERATING,
                schema_version=MODE_SCHEMA_VERSION,
                prompt_version=prompt_version,
                requested_by_user_id=user_id,
                request_count=1,
            )
            .on_conflict_do_nothing(
                constraint="uq_explanation_modes_paper_mode_versions"
            )
            .returning(ExplanationMode)
        )
        result = await self.session.execute(stmt)
        row = result.scalar_one_or_none()

        if row is not None:
            return row, True

        existing = await self.get(paper_id, mode, prompt_version)
        if existing is None:
            raise RuntimeError("claim falhou sem linha existente")

        # Incrementa o contador de pedidos
        await self.session.execute(
            update(ExplanationMode)
            .where(ExplanationMode.id == existing.id)
            .values(request_count=ExplanationMode.request_count + 1)
        )
        return existing, False

    async def complete(
        self,
        row_id: int,
        content: dict,
        model: str,
        input_tokens: int,
        output_tokens: int,
        cost_usd: float,
        latency_ms: int,
    ) -> None:
        await self.session.execute(
            update(ExplanationMode)
            .where(ExplanationMode.id == row_id)
            .values(
                status=ModeStatus.READY,
                content=content,
                error=None,
                model=model,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                cost_usd=cost_usd,
                latency_ms=latency_ms,
            )
        )

    async def fail(
        self,
        row_id: int,
        error: str,
        not_applicable: bool = False,
    ) -> None:
        await self.session.execute(
            update(ExplanationMode)
            .where(ExplanationMode.id == row_id)
            .values(
                status=ModeStatus.NOT_APPLICABLE
                if not_applicable
                else ModeStatus.FAILED,
                error=error[:2000],
            )
        )