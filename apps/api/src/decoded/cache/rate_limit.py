"""Rate limiting por janela deslizante, sobre Redis.

Janela fixa é mais simples mas permite o dobro do limite na virada:
10 requisições às 11:59:59 e mais 10 às 12:00:01. A janela deslizante
usa um sorted set com timestamps e não tem esse buraco.
"""

from __future__ import annotations

import time
from dataclasses import dataclass

import structlog

from decoded.cache.client import get_redis

logger = structlog.get_logger()


@dataclass
class RateLimitResult:
    allowed: bool
    remaining: int
    limit: int
    reset_in_seconds: int


# Limites por rota. (requisições, janela em segundos)
LIMITS = {
    "search": (30, 60),           # 30 buscas por minuto
    "mode_generate": (10, 3600),  # 10 gerações por hora
    "mode_poll": (120, 60),       # polling é frequente por natureza
    "default": (100, 60),
}


async def check_rate_limit(
    identifier: str,
    bucket: str = "default",
) -> RateLimitResult:
    """
    Verifica e registra uma requisição.

    identifier: user_id, ou IP para anônimos.
    Se o Redis estiver fora, libera — indisponibilidade de cache não
    pode virar indisponibilidade de serviço.
    """
    limit, window = LIMITS.get(bucket, LIMITS["default"])

    r = await get_redis()
    if r is None:
        return RateLimitResult(True, limit, limit, 0)

    key = f"rl:{bucket}:{identifier}"
    now = time.time()
    cutoff = now - window

    try:
        pipe = r.pipeline()
        pipe.zremrangebyscore(key, 0, cutoff)   # descarta o que saiu da janela
        pipe.zcard(key)                          # conta o que sobrou
        pipe.zadd(key, {str(now): now})          # registra esta
        pipe.expire(key, window + 10)            # limpeza automática
        results = await pipe.execute()

        count_before = results[1]

        if count_before >= limit:
            await r.zrem(key, str(now))  # desfaz o registro
            oldest = await r.zrange(key, 0, 0, withscores=True)
            reset_in = int(oldest[0][1] + window - now) if oldest else window
            return RateLimitResult(False, 0, limit, max(reset_in, 1))

        return RateLimitResult(
            allowed=True,
            remaining=limit - count_before - 1,
            limit=limit,
            reset_in_seconds=window,
        )

    except Exception as e:
        logger.warning("rate_limit.failed", error=str(e))
        return RateLimitResult(True, limit, limit, 0)