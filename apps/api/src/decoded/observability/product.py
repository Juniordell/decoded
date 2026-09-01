"""Analytics de produto no backend.

Eventos que o frontend não consegue observar: envio de digest, abertura
por webhook, custo real de geração. Mesmo padrão dos outros wrappers —
degrada em silêncio.
"""

from __future__ import annotations

from typing import Any, Optional

import structlog

from decoded.config import settings

logger = structlog.get_logger()

_client: Optional[Any] = None
_enabled = False


def init_product_analytics() -> None:
    global _client, _enabled

    if not settings.posthog_api_key:
        logger.info("product_analytics.disabled", reason="no api key")
        return

    try:
        from posthog import Posthog

        _client = Posthog(
            project_api_key=settings.posthog_api_key,
            host=settings.posthog_host,
            disable_geoip=False,
        )
        _enabled = True
        logger.info("product_analytics.enabled")
    except Exception as e:
        logger.warning("product_analytics.init_failed", error=str(e))


def shutdown_product_analytics() -> None:
    if _client is not None:
        try:
            _client.shutdown()
        except Exception:
            pass


def track(
    distinct_id: str,
    event: str,
    properties: dict | None = None,
) -> None:
    """
    Registra um evento.

    distinct_id precisa bater com o do frontend — que usa o clerk_user_id.
    Se divergir, o PostHog trata como duas pessoas e a jornada quebra.
    """
    if not _enabled or _client is None:
        return
    try:
        _client.capture(
            distinct_id=distinct_id,
            event=event,
            properties=properties or {},
        )
    except Exception as e:
        logger.warning("product_analytics.track_failed", event=event, error=str(e))


def identify_user(
    distinct_id: str,
    properties: dict | None = None,
) -> None:
    if not _enabled or _client is None:
        return
    try:
        _client.identify(distinct_id=distinct_id, properties=properties or {})
    except Exception as e:
        logger.warning("product_analytics.identify_failed", error=str(e))