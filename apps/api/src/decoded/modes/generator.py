"""Gerador dos modos de explicação."""

from __future__ import annotations

import time
from dataclasses import dataclass

import instructor
import structlog
from anthropic import AsyncAnthropic

from decoded.decoding.generator import PRICES, _compute_cost
from decoded.decoding.token_utils import budget_for_full_text, truncate_to_tokens
from decoded.modes.prompts import MODE_PROMPT_VERSION, MODE_PROMPTS
from decoded.modes.schemas import MODE_SCHEMAS
from decoded.observability.tracing import record_generation
from decoded.modes.mermaid import sanitize, validate

logger = structlog.get_logger()

# Quais modos precisam do paper inteiro vs só do deep dive
NEEDS_FULL_TEXT = {"math", "code"}

# Roteamento de modelo por modo
FAST_MODES = {"analogy"}


@dataclass
class ModeResult:
    content: dict
    model: str
    prompt_version: str
    input_tokens: int
    output_tokens: int
    cost_usd: float
    latency_ms: int


class ModeGenerator:
    def __init__(self, api_key: str, fast_model: str, deep_model: str) -> None:
        self._raw = AsyncAnthropic(api_key=api_key)
        self._client = instructor.from_anthropic(self._raw)
        self._fast_model = fast_model
        self._deep_model = deep_model

    async def close(self) -> None:
        await self._raw.close()

    async def __aenter__(self) -> "ModeGenerator":
        return self

    async def __aexit__(self, *args) -> None:
        await self.close()

    def _model_for(self, mode: str) -> str:
        return self._fast_model if mode in FAST_MODES else self._deep_model

    def _max_tokens_for(self, mode: str) -> int:
        return {
            "math": 4000,
            "analogy": 3000,
            "story": 4000,
            "diagram": 2500,
            "code": 3000,
        }.get(mode, 3000)

    def _build_user_content(
        self,
        mode: str,
        title: str,
        abstract: str,
        deep_dive_text: str,
        full_text: str | None,
        system_prompt: str,
    ) -> str:
        parts = [f"Paper title: {title}", "", f"Abstract:\n{abstract}"]

        if deep_dive_text:
            parts.extend(["", "---", "", f"Decoded deep dive:\n\n{deep_dive_text}"])

        if mode in NEEDS_FULL_TEXT and full_text:
            budget = budget_for_full_text(title, abstract, system_prompt)
            # Reserva espaço para o deep dive que já entrou
            budget = max(1000, budget - len(deep_dive_text) // 4)
            safe = truncate_to_tokens(full_text, budget)
            parts.extend(["", "---", "", f"Full paper text:\n\n{safe}"])

        return "\n".join(parts)

    async def generate(
        self,
        mode: str,
        title: str,
        abstract: str,
        deep_dive_text: str = "",
        full_text: str | None = None,
    ) -> ModeResult:
        if mode not in MODE_SCHEMAS:
            raise ValueError(f"Modo desconhecido: {mode}")

        schema = MODE_SCHEMAS[mode]
        system_prompt = MODE_PROMPTS[mode]
        model = self._model_for(mode)
        max_tokens = self._max_tokens_for(mode)

        user_content = self._build_user_content(
            mode, title, abstract, deep_dive_text, full_text, system_prompt
        )

        start = time.perf_counter()

        result, raw = await self._client.messages.create_with_completion(
            model=model,
            max_tokens=max_tokens,
            system=[
                {
                    "type": "text",
                    "text": system_prompt,
                    "cache_control": {"type": "ephemeral"},
                }
            ],
            messages=[{"role": "user", "content": user_content}],
            response_model=schema,
            max_retries=2,
        )

        latency_ms = int((time.perf_counter() - start) * 1000)
        usage = (
            raw.usage.model_dump()
            if hasattr(raw.usage, "model_dump")
            else dict(raw.usage)
        )
        cost = _compute_cost(usage, model)

        logger.info(
            "mode.generated",
            mode=mode,
            model=model,
            input_tokens=usage.get("input_tokens", 0),
            output_tokens=usage.get("output_tokens", 0),
            cost_usd=round(cost, 6),
            latency_ms=latency_ms,
        )

        record_generation(
            name=f"mode.{mode}",
            model=model,
            input={"user_content_chars": len(user_content), "mode": mode},
            output=result.model_dump(),
            usage={
                "input": usage.get("input_tokens", 0),
                "output": usage.get("output_tokens", 0),
            },
            cost_usd=cost,
            latency_ms=latency_ms,
            metadata={"mode": mode, "prompt_version": MODE_PROMPT_VERSION},
        )

        content = result.model_dump()

        # Diagramas passam por validação e limpeza
        if mode == "diagram":
            raw_mermaid = content.get("mermaid", "")
            problems = validate(raw_mermaid)
            if problems:
                cleaned = sanitize(raw_mermaid)
                still = validate(cleaned)
                logger.warning(
                    "mermaid.sanitized",
                    problems_before=problems,
                    problems_after=still,
                )
                content["mermaid"] = cleaned

        return ModeResult(
            content=content,
            model=model,
            prompt_version=MODE_PROMPT_VERSION,
            input_tokens=usage.get("input_tokens", 0),
            output_tokens=usage.get("output_tokens", 0),
            cost_usd=cost,
            latency_ms=latency_ms,
        )