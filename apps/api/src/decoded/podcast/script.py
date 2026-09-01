from __future__ import annotations

import re
import time

import instructor
import structlog
from anthropic import AsyncAnthropic

from decoded.decoding.generator import _compute_cost
from decoded.observability.tracing import record_generation
from decoded.podcast.prompts import PODCAST_PROMPT_VERSION, SCRIPT_SYSTEM
from decoded.podcast.schemas import PodcastScript

logger = structlog.get_logger()

# Ritmo típico de TTS: ~15 caracteres por segundo em fala natural
CHARS_PER_SECOND = 15.0

# Padrões que sobrevivem ao prompt e quebram o TTS
LEFTOVER_PATTERNS = [
    (re.compile(r"\*\*(.+?)\*\*"), r"\1"),      # negrito
    (re.compile(r"\*(.+?)\*"), r"\1"),          # itálico
    (re.compile(r"`(.+?)`"), r"\1"),            # código
    (re.compile(r"^\s*[-•*]\s+", re.M), ""),    # bullets
    (re.compile(r"^\s*#{1,6}\s+", re.M), ""),   # headings
    (re.compile(r"\s*\([^)]{0,60}\)"), ""),     # parênteses curtos
    (re.compile(r"\s*\[[^\]]{0,60}\]"), ""),    # colchetes curtos
    (re.compile(r"\s+"), " "),                  # espaço colapsado
]


def clean_for_speech(text: str) -> str:
    """
    Última barreira antes do TTS.

    O prompt pede texto limpo, mas markdown escapa com frequência
    suficiente para justificar uma limpeza determinística.
    """
    out = text
    for pattern, replacement in LEFTOVER_PATTERNS:
        out = pattern.sub(replacement, out)
    return out.strip()


def estimate_seconds(text: str) -> int:
    return int(len(text) / CHARS_PER_SECOND)


class ScriptWriter:
    def __init__(self, api_key: str, model: str) -> None:
        self._raw = AsyncAnthropic(api_key=api_key)
        self._client = instructor.from_anthropic(self._raw)
        self._model = model
        self.total_cost = 0.0

    async def close(self) -> None:
        await self._raw.close()

    async def __aenter__(self) -> "ScriptWriter":
        return self

    async def __aexit__(self, *args) -> None:
        await self.close()

    async def write(
        self,
        title: str,
        one_sentence: str | None,
        sixty_second: dict | None,
        deep_dive_text: str,
        analogies: list[dict] | None = None,
    ) -> PodcastScript:
        parts = [f"Paper title: {title}"]

        if one_sentence:
            parts.append(f"\nOne sentence: {one_sentence}")

        if sixty_second:
            parts.append(
                "\nSixty-second read:\n"
                f"PROBLEM: {sixty_second.get('problem', '')}\n"
                f"APPROACH: {sixty_second.get('approach', '')}\n"
                f"RESULT: {sixty_second.get('result', '')}"
            )

        if deep_dive_text:
            parts.append(f"\n---\n\nDeep dive:\n\n{deep_dive_text}")

        # Analogias ajudam o roteiro a explicar sem apoio visual
        if analogies:
            lines = []
            for a in analogies[:2]:
                lines.append(f"- {a.get('concept')}: {a.get('analogy', '')[:400]}")
            if lines:
                parts.append("\n---\n\nAnalogies available:\n" + "\n".join(lines))

        user_content = "\n".join(parts)

        start = time.perf_counter()

        result, raw = await self._client.messages.create_with_completion(
            model=self._model,
            max_tokens=4000,
            system=[
                {
                    "type": "text",
                    "text": SCRIPT_SYSTEM,
                    "cache_control": {"type": "ephemeral"},
                }
            ],
            messages=[{"role": "user", "content": user_content}],
            response_model=PodcastScript,
            max_retries=2,
        )

        latency_ms = int((time.perf_counter() - start) * 1000)
        usage = (
            raw.usage.model_dump()
            if hasattr(raw.usage, "model_dump")
            else dict(raw.usage)
        )
        cost = _compute_cost(usage, self._model)
        self.total_cost += cost

        # Limpeza determinística em cada campo
        result.intro = clean_for_speech(result.intro)
        result.outro = clean_for_speech(result.outro)
        for chapter in result.chapters:
            chapter.body = clean_for_speech(chapter.body)

        result.estimated_seconds = estimate_seconds(result.full_text)

        logger.info(
            "script.generated",
            model=self._model,
            chapters=len(result.chapters),
            chars=len(result.full_text),
            estimated_seconds=result.estimated_seconds,
            cost_usd=round(cost, 6),
            latency_ms=latency_ms,
        )

        record_generation(
            name="podcast.script",
            model=self._model,
            input={"title": title, "chars": len(user_content)},
            output=result.model_dump(),
            usage={
                "input": usage.get("input_tokens", 0),
                "output": usage.get("output_tokens", 0),
            },
            cost_usd=cost,
            latency_ms=latency_ms,
            metadata={"prompt_version": PODCAST_PROMPT_VERSION},
        )

        return result