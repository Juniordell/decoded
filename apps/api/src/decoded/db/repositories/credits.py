"""Consumo e reposição de créditos."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import structlog
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from decoded.db.models import CreditLedger, User

logger = structlog.get_logger()

FREE_WEEKLY_CREDITS = 3
PRO_UNLIMITED = True


class InsufficientCredits(Exception):
    pass


class CreditsRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def maybe_reset(self, user: User) -> User:
        """Repõe créditos se a janela semanal expirou."""
        now = datetime.now(timezone.utc)

        if user.credits_reset_at is not None and user.credits_reset_at > now:
            return user

        user.credits_remaining = FREE_WEEKLY_CREDITS
        user.credits_reset_at = now + timedelta(days=7)

        self.session.add(
            CreditLedger(
                user_id=user.id,
                delta=FREE_WEEKLY_CREDITS,
                reason="weekly_reset",
                balance_after=FREE_WEEKLY_CREDITS,
            )
        )
        await self.session.flush()
        logger.info("credits.reset", user_id=user.id)
        return user

    async def spend(
        self,
        user: User,
        paper_id: int,
        mode: str,
    ) -> int:
        """
        Gasta um crédito. Levanta InsufficientCredits se não houver saldo.
        Retorna o saldo restante.
        """
        if user.plan == "pro" and PRO_UNLIMITED:
            self.session.add(
                CreditLedger(
                    user_id=user.id,
                    delta=0,
                    reason="pro_unlimited",
                    paper_id=paper_id,
                    mode=mode,
                    balance_after=user.credits_remaining,
                )
            )
            await self.session.flush()
            return user.credits_remaining

        await self.maybe_reset(user)

        if user.credits_remaining <= 0:
            raise InsufficientCredits(
                f"Sem créditos. Reposição em {user.credits_reset_at.isoformat()}"
            )

        user.credits_remaining -= 1
        new_balance = user.credits_remaining

        self.session.add(
            CreditLedger(
                user_id=user.id,
                delta=-1,
                reason="mode_generation",
                paper_id=paper_id,
                mode=mode,
                balance_after=new_balance,
            )
        )
        await self.session.flush()

        logger.info(
            "credits.spent",
            user_id=user.id,
            paper_id=paper_id,
            mode=mode,
            remaining=new_balance,
        )
        return new_balance

    async def refund(
        self,
        user: User,
        paper_id: int,
        mode: str,
        reason: str = "generation_failed",
    ) -> int:
        """Devolve um crédito quando a geração falha."""
        if user.plan == "pro" and PRO_UNLIMITED:
            return user.credits_remaining

        user.credits_remaining += 1
        new_balance = user.credits_remaining

        self.session.add(
            CreditLedger(
                user_id=user.id,
                delta=1,
                reason=reason,
                paper_id=paper_id,
                mode=mode,
                balance_after=new_balance,
            )
        )
        await self.session.flush()

        logger.info("credits.refunded", user_id=user.id, mode=mode, reason=reason)
        return new_balance