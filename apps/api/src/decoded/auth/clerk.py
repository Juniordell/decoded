from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

import httpx
import jwt
import structlog
from fastapi import Depends, HTTPException, Request
from jwt import PyJWKClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from decoded.config import settings
from decoded.db.base import get_session
from decoded.db.models import User

logger = structlog.get_logger()

# PyJWKClient faz cache das chaves públicas internamente
_jwk_client: PyJWKClient | None = None


def _get_jwk_client() -> PyJWKClient:
    global _jwk_client
    if _jwk_client is None:
        if not settings.clerk_jwks_url:
            raise HTTPException(status_code=503, detail="Clerk não configurado")
        _jwk_client = PyJWKClient(settings.clerk_jwks_url, cache_keys=True)
    return _jwk_client


def _extract_token(request: Request) -> str | None:
    header = request.headers.get("Authorization", "")
    if header.startswith("Bearer "):
        return header[7:]
    return None


def verify_clerk_token(token: str) -> dict:
    """Valida assinatura e claims. Retorna o payload."""
    try:
        signing_key = _get_jwk_client().get_signing_key_from_jwt(token)
        payload = jwt.decode(
            token,
            signing_key.key,
            algorithms=["RS256"],
            issuer=settings.clerk_issuer,
            options={"verify_aud": False},  # Clerk não usa aud por padrão
        )
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expirado")
    except jwt.InvalidTokenError as e:
        logger.warning("auth.invalid_token", error=str(e))
        raise HTTPException(status_code=401, detail="Token inválido")


async def _fetch_clerk_user(clerk_user_id: str) -> dict | None:
    """Busca dados do usuário na API do Clerk (email, nome, avatar)."""
    if not settings.clerk_secret_key:
        return None

    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(
            f"https://api.clerk.com/v1/users/{clerk_user_id}",
            headers={"Authorization": f"Bearer {settings.clerk_secret_key}"},
        )
        if resp.status_code != 200:
            logger.warning("auth.clerk_fetch_failed", status=resp.status_code)
            return None
        return resp.json()


async def _upsert_user(session: AsyncSession, clerk_user_id: str) -> User:
    """Encontra ou cria o usuário local. Enriquece com dados do Clerk na criação."""
    stmt = select(User).where(User.clerk_user_id == clerk_user_id)
    user = (await session.execute(stmt)).scalar_one_or_none()

    if user is not None:
        return user

    # Primeiro login — busca perfil no Clerk
    profile = await _fetch_clerk_user(clerk_user_id)

    email = None
    display_name = None
    avatar_url = None

    if profile:
        emails = profile.get("email_addresses") or []
        primary_id = profile.get("primary_email_address_id")
        for e in emails:
            if e.get("id") == primary_id:
                email = e.get("email_address")
                break
        if email is None and emails:
            email = emails[0].get("email_address")

        first = profile.get("first_name") or ""
        last = profile.get("last_name") or ""
        display_name = f"{first} {last}".strip() or profile.get("username")
        avatar_url = profile.get("image_url")

    user = User(
        clerk_user_id=clerk_user_id,
        email=email,
        display_name=display_name,
        avatar_url=avatar_url,
        plan="free",
        credits_remaining=3,
        credits_reset_at=datetime.now(timezone.utc) + timedelta(days=7),
    )
    session.add(user)
    await session.flush()

    logger.info("auth.user_created", clerk_user_id=clerk_user_id, email=email)
    return user


async def get_current_user(
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> User:
    """Dependency que exige autenticação."""
    token = _extract_token(request)
    if not token:
        raise HTTPException(status_code=401, detail="Autenticação necessária")

    payload = verify_clerk_token(token)
    clerk_user_id = payload.get("sub")
    if not clerk_user_id:
        raise HTTPException(status_code=401, detail="Token sem subject")

    user = await _upsert_user(session, clerk_user_id)
    await session.commit()
    return user


async def get_optional_user(
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> Optional[User]:
    """Dependency que aceita usuário anônimo. Retorna None se não logado."""
    token = _extract_token(request)
    if not token:
        return None

    try:
        payload = verify_clerk_token(token)
        clerk_user_id = payload.get("sub")
        if not clerk_user_id:
            return None
        user = await _upsert_user(session, clerk_user_id)
        await session.commit()
        return user
    except HTTPException:
        return None