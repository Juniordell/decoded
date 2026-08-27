"""Gerador dos modos de explicação."""

from __future__ import annotations

import time
from dataclasses import dataclass

import instructor
import structlog
from anthropic import AsyncAnthropic
from openai import AsyncOpenAI

from decoded.decoding.generator import PRICES, _compute_cost
from decoded.decoding.token_utils import budget_for_full_text, truncate_to_tokens
from decoded.modes.prompts import MODE_PROMPT_VERSION, MODE_PROMPTS
from decoded.modes.schemas import MODE_SCHEMAS
from decoded.observability.tracing import record_generation
from decoded.modes.mermaid import sanitize, validate

OPENAI_PRICES = {
    "gpt-5.6-luna": {"input": 0.20, "output": 1.20},
    "gpt-5.6-terra": {"input": 2.00, "output": 12.00},
}


def _openai_cost(usage: dict, model: str) -> float:
    p = OPENAI_PRICES.get(model)
    if not p:
        return 0.0
    return (
        usage.get("prompt_tokens", 0) * p["input"] / 1_000_000
        + usage.get("completion_tokens", 0) * p["output"] / 1_000_000
    )

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
    def __init__(
        self,
        api_key: str,
        fast_model: str,
        deep_model: str,
        openai_api_key: str | None = None,
        openai_model: str = "gpt-5.6-luna",
    ) -> None:
        self._raw = AsyncAnthropic(api_key=api_key)
        self._client = instructor.from_anthropic(self._raw)
        self._fast_model = fast_model
        self._deep_model = deep_model

        self._openai_raw = (
            AsyncOpenAI(api_key=openai_api_key) if openai_api_key else None
        )
        self._openai_client = (
            instructor.from_openai(self._openai_raw) if self._openai_raw else None
        )
        self._openai_model = openai_model

    async def close(self) -> None:
        await self._raw.close()
        if self._openai_raw is not None:
            await self._openai_raw.close()
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

        # --- Caminho OpenAI (modo analogy) ---
        if mode in FAST_MODES and self._openai_client is not None:
            result, raw = await self._openai_client.chat.completions.create_with_completion(
                model=self._openai_model,
                max_tokens=max_tokens,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_content},
                ],
                response_model=schema,
                max_retries=2,
            )

            latency_ms = int((time.perf_counter() - start) * 1000)
            usage = (
                raw.usage.model_dump()
                if hasattr(raw.usage, "model_dump")
                else dict(raw.usage)
            )
            cost = _openai_cost(usage, self._openai_model)
            model_used = self._openai_model
            in_tokens = usage.get("prompt_tokens", 0)
            out_tokens = usage.get("completion_tokens", 0)

        # --- Caminho Anthropic (demais modos) ---
        else:
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
            model_used = model
            in_tokens = usage.get("input_tokens", 0)
            out_tokens = usage.get("output_tokens", 0)

        logger.info(
            "mode.generated",
            mode=mode,
            model=model_used,
            input_tokens=in_tokens,
            output_tokens=out_tokens,
            cost_usd=round(cost, 6),
            latency_ms=latency_ms,
        )

        content = result.model_dump()

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

        record_generation(
            name=f"mode.{mode}",
            model=model_used,
            input={"user_content_chars": len(user_content), "mode": mode},
            output=content,
            usage={"input": in_tokens, "output": out_tokens},
            cost_usd=cost,
            latency_ms=latency_ms,
            metadata={"mode": mode, "prompt_version": MODE_PROMPT_VERSION},
        )

        return ModeResult(
            content=content,
            model=model_used,
            prompt_version=MODE_PROMPT_VERSION,
            input_tokens=in_tokens,
            output_tokens=out_tokens,
            cost_usd=cost,
            latency_ms=latency_ms,
        )