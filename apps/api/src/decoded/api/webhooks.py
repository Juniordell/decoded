"""Webhooks do Resend.

Assinatura verificada via Svix, o padrão que o Resend usa. Sem
verificação, qualquer um pode forjar eventos e corromper suas métricas.
"""

from __future__ import annotations

from datetime import datetime, timezone

import structlog
from fastapi import APIRouter, Depends, Header, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from decoded.config import settings
from decoded.db.base import get_session
from decoded.db.models import Digest, DigestPreference, DigestStatus, User
from decoded.observability.product import track

logger = structlog.get_logger()

router = APIRouter(prefix="/v1/webhooks", tags=["webhooks"])


def _verify_signature(
    payload: bytes,
    svix_id: str,
    svix_timestamp: str,
    svix_signature: str,
) -> dict:
    """Valida a assinatura e devolve o payload decodificado."""
    if not settings.resend_webhook_secret:
        raise HTTPException(status_code=503, detail="Webhook não configurado")

    try:
        from svix.webhooks import Webhook

        wh = Webhook(settings.resend_webhook_secret)
        return wh.verify(
            payload,
            {
                "svix-id": svix_id,
                "svix-timestamp": svix_timestamp,
                "svix-signature": svix_signature,
            },
        )
    except Exception as e:
        logger.warning("webhook.invalid_signature", error=str(e))
        raise HTTPException(status_code=401, detail="Assinatura inválida")


@router.post("/resend", status_code=204)
async def resend_webhook(
    request: Request,
    svix_id: str = Header(..., alias="svix-id"),
    svix_timestamp: str = Header(..., alias="svix-timestamp"),
    svix_signature: str = Header(..., alias="svix-signature"),
    session: AsyncSession = Depends(get_session),
) -> None:
    """
    Recebe eventos de entrega e engajamento.

    Tipos relevantes:
      email.delivered, email.opened, email.clicked,
      email.bounced, email.complained
    """
    raw = await request.body()
    payload = _verify_signature(raw, svix_id, svix_timestamp, svix_signature)

    event_type = payload.get("type", "")
    data = payload.get("data", {})
    message_id = data.get("email_id") or data.get("id")

    if not message_id:
        logger.warning("webhook.no_message_id", event=event_type)
        return

    log = logger.bind(event=event_type, message_id=message_id)

    digest = (
        await session.execute(
            select(Digest).where(Digest.provider_message_id == message_id)
        )
    ).scalar_one_or_none()

    if digest is None:
        log.info("webhook.digest_not_found")
        return

    now = datetime.now(timezone.utc)

    clerk_id = (
        await session.execute(
            select(User.clerk_user_id).where(User.id == digest.user_id)
        )
    ).scalar_one_or_none()

    if event_type == "email.opened" and digest.opened_at is None:
        digest.opened_at = now
        if clerk_id:
            track(clerk_id, "digest_opened", {"digest_id": digest.id})
        log.info("webhook.opened", digest_id=digest.id)

    elif event_type == "email.clicked":
        if digest.clicked_at is None:
            digest.clicked_at = now
        # Um clique implica abertura, mesmo que o pixel tenha sido bloqueado
        if digest.opened_at is None:
            digest.opened_at = now
        if clerk_id:
            track(clerk_id, "digest_clicked", {"digest_id": digest.id})
        log.info("webhook.clicked", digest_id=digest.id)


    elif event_type in ("email.bounced", "email.complained"):
        digest.status = DigestStatus.FAILED
        digest.error = f"{event_type}: {data.get('reason', '')}"[:2000]

        # Bounce permanente ou reclamação de spam: para de enviar.
        # Continuar destrói a reputação do domínio.
        prefs = (
            await session.execute(
                select(DigestPreference).where(
                    DigestPreference.user_id == digest.user_id
                )
            )
        ).scalar_one_or_none()
        if prefs is not None:
            prefs.enabled = False

        log.warning("webhook.bounce_or_complaint", digest_id=digest.id)

    await session.commit()