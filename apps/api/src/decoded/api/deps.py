from __future__ import annotations

from typing import Optional

from fastapi import Depends, HTTPException, Request, Response

from decoded.cache.rate_limit import check_rate_limit
from decoded.db.models import User


def _identifier(request: Request, user: Optional[User]) -> str:
    if user is not None:
        return f"user:{user.id}"
    # Atrás de proxy, o IP real vem no header
    forwarded = request.headers.get("x-forwarded-for", "")
    ip = forwarded.split(",")[0].strip() if forwarded else (
        request.client.host if request.client else "unknown"
    )
    return f"ip:{ip}"


def rate_limited(bucket: str):
    """
    Fábrica de dependency.

        @router.get("", dependencies=[Depends(rate_limited("search"))])
    """

    async def dependency(
        request: Request,
        response: Response,
    ) -> None:
        user = getattr(request.state, "user", None)
        identifier = _identifier(request, user)

        result = await check_rate_limit(identifier, bucket)

        response.headers["X-RateLimit-Limit"] = str(result.limit)
        response.headers["X-RateLimit-Remaining"] = str(result.remaining)

        if not result.allowed:
            response.headers["Retry-After"] = str(result.reset_in_seconds)
            raise HTTPException(
                status_code=429,
                detail=f"Rate limit atingido. Tente em {result.reset_in_seconds}s.",
                headers={"Retry-After": str(result.reset_in_seconds)},
            )

    return dependency