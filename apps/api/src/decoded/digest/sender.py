"""Envio de digests via Resend.

Três garantias que importam:
1. Idempotência — nunca enviar o mesmo digest duas vezes
2. Rate limit — respeitar o limite do provedor, não descobrir na marra
3. Falha isolada — um email que falha não derruba o lote
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

import structlog
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from decoded.db.base import async_session_factory
from decoded.db.models import Digest, DigestStatus, User
from decoded.digest.builder import week_start
from decoded.digest.template import render_html, render_text
from decoded.observability.product import track

logger = structlog.get_logger()


@dataclass
class SendResult:
    sent: int = 0
    skipped: int = 0
    failed: int = 0
    errors: list[str] = field(default_factory=list)
    message_ids: list[str] = field(default_factory=list)


class ResendClient:
    def __init__(
        self,
        api_key: str,
        from_email: str,
        reply_to: str | None = None,
        rate_per_second: float = 2.0,
    ) -> None:
        import resend

        resend.api_key = api_key
        self._resend = resend
        self._from = from_email
        self._reply_to = reply_to
        self._min_interval = 1.0 / rate_per_second if rate_per_second > 0 else 0.0
        self._last_send = 0.0

    async def _throttle(self) -> None:
        """Espaça as chamadas para respeitar o rate limit do provedor."""
        if self._min_interval <= 0:
            return
        now = asyncio.get_event_loop().time()
        elapsed = now - self._last_send
        if elapsed < self._min_interval:
            await asyncio.sleep(self._min_interval - elapsed)
        self._last_send = asyncio.get_event_loop().time()

    async def send(
        self,
        to: str,
        subject: str,
        html: str,
        text: str,
        tags: dict[str, str] | None = None,
    ) -> str:
        """Envia um email. Retorna o message_id do provedor."""
        await self._throttle()

        params: dict = {
            "from": self._from,
            "to": [to],
            "subject": subject,
            "html": html,
            "text": text,
        }
        if self._reply_to:
            params["reply_to"] = self._reply_to
        if tags:
            params["tags"] = [{"name": k, "value": v} for k, v in tags.items()]

        # O SDK do Resend é síncrono; roda em thread para não bloquear o loop
        loop = asyncio.get_running_loop()
        response = await loop.run_in_executor(
            None, lambda: self._resend.Emails.send(params)
        )

        message_id = response.get("id", "")
        if not message_id:
            raise RuntimeError(f"Resend não retornou id: {response}")

        return message_id


async def _sent_today(session: AsyncSession) -> int:
    """Quantos digests já saíram hoje — para respeitar o teto diário."""
    since = datetime.now(timezone.utc).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    return (
        await session.execute(
            select(func.count(Digest.id)).where(
                Digest.status == DigestStatus.SENT,
                Digest.sent_at >= since,
            )
        )
    ).scalar_one()


async def send_pending(
    api_key: str,
    from_email: str,
    site_url: str,
    reply_to: str | None = None,
    target_week: datetime | None = None,
    limit: int | None = None,
    daily_cap: int = 100,
    rate_per_second: float = 2.0,
    dry_run: bool = False,
) -> dict:
    """
    Envia todos os digests pendentes de uma semana.

    Idempotente por status: só pega PENDING, marca SENT ao concluir.
    Um crash no meio deixa os já enviados marcados e os demais pendentes.
    """
    week = week_start(target_week or (datetime.now(timezone.utc) - timedelta(weeks=1)))
    log = logger.bind(week=week.date().isoformat(), dry_run=dry_run)

    result = SendResult()

    async with async_session_factory() as session:
        already_sent = await _sent_today(session)
        remaining_today = max(0, daily_cap - already_sent)

        if remaining_today == 0:
            log.warning("send.daily_cap_reached", cap=daily_cap)
            return {"error": "daily_cap_reached", "sent_today": already_sent}

        # clerk_user_id vem junto porque o PostHog precisa do mesmo
        # distinct_id que o frontend usa — se divergir, a jornada quebra
        stmt = (
            select(Digest, User.email, User.clerk_user_id)
            .join(User, User.id == Digest.user_id)
            .where(
                Digest.week_start == week,
                Digest.status == DigestStatus.PENDING,
                Digest.paper_count > 0,
                User.email.isnot(None),
            )
            .order_by(Digest.id)
        )

        effective_limit = min(limit or remaining_today, remaining_today)
        stmt = stmt.limit(effective_limit)

        rows = (await session.execute(stmt)).all()

    log.info(
        "send.start",
        pending=len(rows),
        sent_today=already_sent,
        remaining_today=remaining_today,
    )

    if not rows:
        return {"sent": 0, "skipped": 0, "failed": 0, "reason": "nothing_pending"}

    client = None
    if not dry_run:
        client = ResendClient(
            api_key=api_key,
            from_email=from_email,
            reply_to=reply_to,
            rate_per_second=rate_per_second,
        )

    for digest, email, clerk_id in rows:
        item_log = log.bind(digest_id=digest.id, email=email)

        try:
            html = render_html(
                subject=digest.subject or "Decoded",
                content=digest.content,
                site_url=site_url,
                week_start=digest.week_start,
            )
            text = render_text(
                subject=digest.subject or "Decoded",
                content=digest.content,
                site_url=site_url,
                week_start=digest.week_start,
            )

            if dry_run:
                item_log.info("send.dry_run", subject=digest.subject)
                result.skipped += 1
                continue

            message_id = await client.send(
                to=email,
                subject=digest.subject or "Decoded",
                html=html,
                text=text,
                tags={
                    "digest_week": week.strftime("%Y-%m-%d"),
                    "papers": str(digest.paper_count),
                },
            )

            # Marca em sessão própria, commit imediato — se o processo cair
            # no meio do lote, o que já saiu fica registrado
            async with async_session_factory() as write_session:
                d = (
                    await write_session.execute(
                        select(Digest).where(Digest.id == digest.id)
                    )
                ).scalar_one()
                d.status = DigestStatus.SENT
                d.sent_at = datetime.now(timezone.utc)
                d.provider_message_id = message_id
                d.error = None
                await write_session.commit()

            if clerk_id:
                track(
                    distinct_id=clerk_id,
                    event="digest_sent",
                    properties={
                        "week": week.strftime("%Y-%m-%d"),
                        "paper_count": digest.paper_count,
                        "personalized": digest.content.get("personalized", False),
                    },
                )

            result.sent += 1
            result.message_ids.append(message_id)
            item_log.info("send.ok", message_id=message_id)

        except Exception as e:
            result.failed += 1
            result.errors.append(f"digest {digest.id}: {e}")
            item_log.error("send.failed", error=str(e))

            async with async_session_factory() as write_session:
                d = (
                    await write_session.execute(
                        select(Digest).where(Digest.id == digest.id)
                    )
                ).scalar_one()
                d.status = DigestStatus.FAILED
                d.error = str(e)[:2000]
                await write_session.commit()

    log.info(
        "send.done",
        sent=result.sent,
        skipped=result.skipped,
        failed=result.failed,
    )

    return {
        "sent": result.sent,
        "skipped": result.skipped,
        "failed": result.failed,
        "errors": result.errors[:10],
    }


async def send_one(
    digest_id: int,
    api_key: str,
    from_email: str,
    site_url: str,
    reply_to: str | None = None,
    override_email: str | None = None,
) -> dict:
    """
    Envia um digest específico. Útil para testar sem disparar o lote.

    override_email permite mandar o digest de outra pessoa para você mesmo,
    para inspeção — sem marcar como enviado.
    """
    async with async_session_factory() as session:
        row = (
            await session.execute(
                select(Digest, User.email, User.clerk_user_id)
                .join(User, User.id == Digest.user_id)
                .where(Digest.id == digest_id)
            )
        ).one_or_none()

    if row is None:
        return {"error": "digest_not_found"}

    digest, user_email, clerk_id = row
    to = override_email or user_email

    if not to:
        return {"error": "no_recipient"}

    html = render_html(
        subject=digest.subject or "Decoded",
        content=digest.content,
        site_url=site_url,
        week_start=digest.week_start,
    )
    text = render_text(
        subject=digest.subject or "Decoded",
        content=digest.content,
        site_url=site_url,
        week_start=digest.week_start,
    )

    client = ResendClient(api_key=api_key, from_email=from_email, reply_to=reply_to)
    message_id = await client.send(
        to=to,
        subject=digest.subject or "Decoded",
        html=html,
        text=text,
        tags={"test": "true"},
    )

    # Só marca como enviado se foi para o destinatário real.
    # Um teste enviado para outro endereço não conta como entrega,
    # e portanto também não gera evento de analytics.
    if override_email is None:
        async with async_session_factory() as session:
            d = (
                await session.execute(select(Digest).where(Digest.id == digest_id))
            ).scalar_one()
            d.status = DigestStatus.SENT
            d.sent_at = datetime.now(timezone.utc)
            d.provider_message_id = message_id
            await session.commit()

        if clerk_id:
            track(
                distinct_id=clerk_id,
                event="digest_sent",
                properties={
                    "week": digest.week_start.strftime("%Y-%m-%d"),
                    "paper_count": digest.paper_count,
                    "personalized": digest.content.get("personalized", False),
                },
            )

    logger.info("send_one.ok", digest_id=digest_id, to=to, message_id=message_id)
    return {"sent": True, "to": to, "message_id": message_id}