from __future__ import annotations

import re

import instructor
import structlog
from anthropic import AsyncAnthropic
from pydantic import BaseModel, Field

from decoded.decoding.generator import _compute_cost

logger = structlog.get_logger()


class TopicName(BaseModel):
    name: str = Field(
        ...,
        description="Nome do tópico em Title Case, 2-5 palavras",
        max_length=80,
    )
    description: str = Field(
        ...,
        description="Uma frase explicando o que une esses papers",
        max_length=300,
    )


TOPIC_NAMING_SYSTEM = """You name research topics discovered by clustering.

You receive keywords extracted from a cluster of AI papers plus a few of their titles. Produce a name and a one-sentence description.

RULES FOR THE NAME:

- 2 to 5 words, Title Case.
- Specific enough that someone could guess what's in the cluster.
- Use the field's own vocabulary. If the papers are about KV cache compression, say "KV Cache Compression" — not "Memory Optimization Techniques."
- No filler: skip "Advances in", "Novel Approaches to", "A Study of", "Techniques for".
- Prefer the concrete noun over the abstract one. "Speculative Decoding" beats "Inference Acceleration Methods".

GOOD NAMES:
- Speculative Decoding
- Reward Model Calibration
- Long Context Retrieval
- Multimodal Instruction Tuning
- Benchmark Contamination
- Sparse Mixture of Experts
- Chain-of-Thought Faithfulness

BAD NAMES:
- Advances in Language Models        (filler + too broad)
- Neural Network Optimization        (could be anything)
- AI Safety Research                 (a whole field, not a topic)
- Novel Transformer Architectures    (filler)
- Miscellaneous Topics               (never)

RULES FOR THE DESCRIPTION:

One sentence naming what these papers have in common — the shared problem or shared method. Not a definition of the terms.

Good: "Papers on making inference faster by having a small model draft tokens that a large model verifies in batch."

Bad: "This topic covers various papers related to decoding strategies in language models."

WHEN THE KEYWORDS ARE INCOHERENT:

Clustering sometimes produces a group with no real theme. If the keywords and titles genuinely don't share a subject, name it after the closest common thread and say so plainly in the description. Never invent coherence that isn't there.

OUTPUT: return the structured object. No preamble."""


def slugify(name: str) -> str:
    slug = re.sub(r"[^a-z0-9\s-]", "", name.lower())
    slug = re.sub(r"[\s_]+", "-", slug.strip())
    return slug[:100]


class TopicNamer:
    def __init__(self, api_key: str, model: str) -> None:
        self._raw = AsyncAnthropic(api_key=api_key)
        self._client = instructor.from_anthropic(self._raw)
        self._model = model
        self.total_cost = 0.0

    async def close(self) -> None:
        await self._raw.close()

    async def __aenter__(self) -> "TopicNamer":
        return self

    async def __aexit__(self, *args) -> None:
        await self.close()

    async def name_topic(
        self,
        keywords: list[str],
        sample_titles: list[str],
    ) -> TopicName:
        user = (
            f"Keywords (most distinguishing first):\n"
            + ", ".join(keywords[:15])
            + "\n\nSample paper titles from this cluster:\n"
            + "\n".join(f"- {t}" for t in sample_titles[:8])
        )

        result, raw = await self._client.messages.create_with_completion(
            model=self._model,
            max_tokens=400,
            system=[
                {
                    "type": "text",
                    "text": TOPIC_NAMING_SYSTEM,
                    "cache_control": {"type": "ephemeral"},
                }
            ],
            messages=[{"role": "user", "content": user}],
            response_model=TopicName,
            max_retries=2,
        )

        usage = (
            raw.usage.model_dump()
            if hasattr(raw.usage, "model_dump")
            else dict(raw.usage)
        )
        self.total_cost += _compute_cost(usage, self._model)

        return result