"""Cliente Redis com degradação graciosa.

Se o Redis cair, o app continua funcionando — só perde cache e rate limiting.
Cache que derruba a aplicação é pior do que não ter cache.
"""

from __future__ import annotations

import json
from typing import Any

import structlog
from redis.asyncio import Redis, from_url

from decoded.config import settings

logger = structlog.get_logger()

_client: Redis | None = None
_available: bool = True


async def get_redis() -> Redis | None:
    """Cliente singleton. Retorna None se indisponível."""
    global _client, _available

    if not _available:
        return None

    if _client is None:
        try:
            _client = from_url(
                settings.redis_url,
                encoding="utf-8",
                decode_responses=True,
                socket_connect_timeout=2,
                socket_timeout=2,
                health_check_interval=30,
            )
            await _client.ping()
            logger.info("redis.connected", url=settings.redis_url.split("@")[-1])
        except Exception as e:
            logger.warning("redis.unavailable", error=str(e))
            _available = False
            _client = None

    return _client


async def close_redis() -> None:
    global _client
    if _client is not None:
        try:
            await _client.aclose()
        except Exception:
            pass
        _client = None


async def cache_get(key: str) -> Any | None:
    r = await get_redis()
    if r is None:
        return None
    try:
        raw = await r.get(key)
        return json.loads(raw) if raw else None
    except Exception as e:
        logger.warning("cache.get_failed", key=key, error=str(e))
        return None


async def cache_set(key: str, value: Any, ttl_seconds: int) -> bool:
    r = await get_redis()
    if r is None:
        return False
    try:
        await r.setex(key, ttl_seconds, json.dumps(value, default=str))
        return True
    except Exception as e:
        logger.warning("cache.set_failed", key=key, error=str(e))
        return False


async def cache_delete(pattern: str) -> int:
    """Invalida por padrão. Usa SCAN, não KEYS — KEYS trava o Redis."""
    r = await get_redis()
    if r is None:
        return 0
    try:
        deleted = 0
        async for key in r.scan_iter(match=pattern, count=100):
            await r.delete(key)
            deleted += 1
        return deleted
    except Exception as e:
        logger.warning("cache.delete_failed", pattern=pattern, error=str(e))
        return 0