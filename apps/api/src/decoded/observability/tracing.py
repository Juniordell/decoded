from __future__ import annotations

from contextlib import asynccontextmanager, contextmanager
from typing import Any, Optional

import structlog

from decoded.config import settings

logger = structlog.get_logger()

_client: Optional[Any] = None
_enabled: bool = False


def init_tracing() -> None:
    """Chamado no startup. Silencioso se as chaves não existirem."""
    global _client, _enabled

    if not settings.langfuse_public_key or not settings.langfuse_secret_key:
        logger.info("tracing.disabled", reason="langfuse keys not set")
        return

    try:
        from langfuse import Langfuse

        _client = Langfuse(
            public_key=settings.langfuse_public_key,
            secret_key=settings.langfuse_secret_key,
            host=settings.langfuse_host,
        )
        _enabled = True
        logger.info("tracing.enabled", host=settings.langfuse_host)
    except Exception as e:
        logger.warning("tracing.init_failed", error=str(e))


def flush() -> None:
    """Força envio dos eventos pendentes. Chamado no shutdown."""
    if _client is not None:
        try:
            _client.flush()
        except Exception as e:
            logger.warning("tracing.flush_failed", error=str(e))


def is_enabled() -> bool:
    return _enabled


@contextmanager
def trace_span(
    name: str,
    *,
    input: Any = None,
    metadata: dict | None = None,
    user_id: str | None = None,
    session_id: str | None = None,
    tags: list[str] | None = None,
):
    if not _enabled or _client is None:
        yield _NoOpSpan()
        return

    obs = None
    try:
        obs = _client.start_observation(
            as_type="span",
            name=name,
            input=input,
            metadata=metadata or {},
        )
        if user_id or session_id or tags:
            try:
                obs.update_trace(
                    user_id=user_id,
                    session_id=session_id,
                    tags=tags or [],
                )
            except Exception:
                pass
        yield _LangfuseSpan(obs)
    except Exception as e:
        logger.warning("tracing.span_failed", name=name, error=str(e))
        yield _NoOpSpan()
    finally:
        if obs is not None:
            try:
                obs.end()
            except Exception:
                pass


def record_generation(
    name: str,
    *,
    model: str,
    input: Any,
    output: Any,
    usage: dict | None = None,
    cost_usd: float | None = None,
    latency_ms: int | None = None,
    metadata: dict | None = None,
) -> None:
    if not _enabled or _client is None:
        return

    try:
        gen = _client.start_observation(
            as_type="generation",
            name=name,
            model=model,
            input=input,
            metadata={
                **(metadata or {}),
                **({"latency_ms": latency_ms} if latency_ms else {}),
            },
        )
        gen.update(
            output=output,
            usage_details=usage or {},
            cost_details={"total": cost_usd} if cost_usd is not None else {},
        )
        gen.end()
    except Exception as e:
        logger.warning("tracing.generation_failed", name=name, error=str(e))


class _LangfuseSpan:
    def __init__(self, span: Any) -> None:
        self._span = span

    def update(self, **kwargs: Any) -> None:
        try:
            self._span.update(**kwargs)
        except Exception:
            pass

    def score(self, name: str, value: float, comment: str | None = None) -> None:
        try:
            self._span.score(name=name, value=value, comment=comment)
        except Exception:
            pass


class _NoOpSpan:
    def update(self, **kwargs: Any) -> None:
        pass

    def score(self, name: str, value: float, comment: str | None = None) -> None:
        pass