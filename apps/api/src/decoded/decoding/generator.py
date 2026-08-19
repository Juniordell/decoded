from __future__ import annotations

import time
from dataclasses import dataclass

import instructor
import structlog
from anthropic import AsyncAnthropic
from anthropic.types.message import Message

from decoded.decoding.prompts import (
    ANALOGY_GENERATE_SYSTEM,
    ANALOGY_JUDGE_SYSTEM,
    CONCEPT_EXTRACT_SYSTEM,
    DEEP_DIVE_SYSTEM,
    FIGURE_EXPLANATION_SYSTEM,
    ONE_SENTENCE_SYSTEM,
    SIXTY_SECOND_SYSTEM,
    VOCAB_DEFINE_SYSTEM,
    VOCAB_EXTRACT_SYSTEM,
    VERSION,
)
from decoded.decoding.schemas import (
    Analogies,
    Analogy,
    AnalogySet,
    ConceptList,
    DeepDive,
    ExtractedTerms,
    FigureExplained,
    FiguresExplained,
    OneSentence,
    SixtySecondRead,
    VocabTerm,
    Vocabulary,
)

logger = structlog.get_logger()


# ============================================================
# Pricing (USD per 1M tokens) — Haiku 4.5 as of 2026
# ============================================================
PRICES = {
    "claude-haiku-4-5-20251001": {
        "input": 1.00,             # per 1M tokens
        "output": 5.00,            # per 1M tokens
        "cache_write": 1.25,       # per 1M tokens (25% premium on first write)
        "cache_read": 0.10,        # per 1M tokens (90% discount on reads)
    },
    "claude-sonnet-4-6": {
        "input": 3.00,
        "output": 15.00,
        "cache_write": 3.75,
        "cache_read": 0.30,
    },
}


@dataclass
class GenerationResult:
    """What a generator call returns."""
    content: dict  # validated Pydantic → dict
    model: str
    prompt_version: str
    input_tokens: int
    output_tokens: int
    cache_read_tokens: int
    cache_write_tokens: int
    cost_usd: float
    latency_ms: int


def _compute_cost(usage: dict, model: str) -> float:
    """Compute USD cost from token usage. Handles cache tokens separately."""
    prices = PRICES.get(model, {})
    if not prices:
        return 0.0

    input_tokens = usage.get("input_tokens", 0)
    output_tokens = usage.get("output_tokens", 0)
    cache_read = usage.get("cache_read_input_tokens", 0) or 0
    cache_write = usage.get("cache_creation_input_tokens", 0) or 0

    # Anthropic reports input_tokens EXCLUDING cache reads/writes
    return (
        (input_tokens * prices["input"] / 1_000_000)
        + (output_tokens * prices["output"] / 1_000_000)
        + (cache_read * prices["cache_read"] / 1_000_000)
        + (cache_write * prices["cache_write"] / 1_000_000)
    )

def _empty_generation(model_obj, model_name: str, start: float) -> GenerationResult:
    """Return an empty GenerationResult when a stage produces nothing worth costing."""
    return GenerationResult(
        content=model_obj.model_dump(),
        model=model_name,
        prompt_version=VERSION,
        input_tokens=0,
        output_tokens=0,
        cache_read_tokens=0,
        cache_write_tokens=0,
        cost_usd=0.0,
        latency_ms=int((time.perf_counter() - start) * 1000),
    )

def compute_batch_cost(usage: dict, model: str) -> float:
    """Batch API costs 50% of standard rates."""
    return _compute_cost(usage, model) * 0.5

class SectionGenerator:
    """Generates decoded sections. Uses Anthropic + Instructor + prompt caching."""

    def __init__(self, api_key: str, fast_model: str) -> None:
        self._raw_client = AsyncAnthropic(api_key=api_key)
        # Instructor wraps the client and adds Pydantic validation
        self._client = instructor.from_anthropic(self._raw_client)
        self._fast_model = fast_model

    async def close(self) -> None:
        await self._raw_client.close()

    async def __aenter__(self) -> "SectionGenerator":
        return self

    async def __aexit__(self, *args) -> None:
        await self.close()

    async def one_sentence(
        self,
        title: str,
        abstract: str,
    ) -> GenerationResult:
        """Generate the one-sentence summary. Haiku, prompt-cached."""
        return await self._generate(
            response_model=OneSentence,
            system_prompt=ONE_SENTENCE_SYSTEM,
            user_content=_paper_context(title, abstract),
            model=self._fast_model,
            max_tokens=100,
        )

    async def sixty_second(
        self,
        title: str,
        abstract: str,
    ) -> GenerationResult:
        """Generate the 3-paragraph 60-second read. Haiku, prompt-cached."""
        return await self._generate(
            response_model=SixtySecondRead,
            system_prompt=SIXTY_SECOND_SYSTEM,
            user_content=_paper_context(title, abstract),
            model=self._fast_model,
            max_tokens=800,
        )

    async def deep_dive(
        self,
        title: str,
        abstract: str,
        full_text: str,
        deep_model: str,
    ) -> GenerationResult:
        """Generate the 5-section deep dive. Sonnet, uses full paper text."""
        from decoded.decoding.token_utils import budget_for_full_text, truncate_to_tokens

        budget = budget_for_full_text(title, abstract, DEEP_DIVE_SYSTEM)
        safe_text = truncate_to_tokens(full_text, budget)

        return await self._generate(
            response_model=DeepDive,
            system_prompt=DEEP_DIVE_SYSTEM,
            user_content=_paper_context_full(title, abstract, safe_text),
            model=deep_model,
            max_tokens=4000,
        )

    async def explain_figure(
        self,
        image_b64: str,
        media_type: str,
        nearby_text: str,
        deep_model: str,
    ) -> tuple[FigureExplained, dict]:
        """Explain a single figure. Returns (parsed, raw_usage_dict)."""
        start = time.perf_counter()

        system_blocks = [
            {
                "type": "text",
                "text": FIGURE_EXPLANATION_SYSTEM,
                "cache_control": {"type": "ephemeral"},
            }
        ]

        user_content = [
            {
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": media_type,
                    "data": image_b64,
                },
            },
            {
                "type": "text",
                "text": f"Text from the same page (for context):\n\n{nearby_text}",
            },
        ]

        result, raw = await self._client.messages.create_with_completion(
            model=deep_model,
            max_tokens=800,
            system=system_blocks,
            messages=[{"role": "user", "content": user_content}],
            response_model=FigureExplained,
            max_retries=2,
        )

        usage = raw.usage.model_dump() if hasattr(raw.usage, "model_dump") else dict(raw.usage)
        usage["_latency_ms"] = int((time.perf_counter() - start) * 1000)
        return result, usage

    async def figures(
        self,
        figures_data: list[dict],
        deep_model: str,
    ) -> GenerationResult:
        """
        Explain a batch of figures. Aggregates cost + latency across all Vision calls.

        figures_data: [{"image_b64": ..., "media_type": ..., "nearby_text": ...}, ...]
        """
        start = time.perf_counter()
        explained: list[FigureExplained] = []

        total_input = 0
        total_output = 0
        total_cache_read = 0
        total_cache_write = 0
        total_cost = 0.0

        for fig in figures_data:
            parsed, usage = await self.explain_figure(
                image_b64=fig["image_b64"],
                media_type=fig["media_type"],
                nearby_text=fig["nearby_text"],
                deep_model=deep_model,
            )
            explained.append(parsed)

            total_input += usage.get("input_tokens", 0)
            total_output += usage.get("output_tokens", 0)
            total_cache_read += usage.get("cache_read_input_tokens", 0) or 0
            total_cache_write += usage.get("cache_creation_input_tokens", 0) or 0
            total_cost += _compute_cost(usage, deep_model)

            logger.info(
                "figure.explained",
                figure_ref=parsed.figure_ref,
                latency_ms=usage["_latency_ms"],
            )

        wrapped = FiguresExplained(items=explained)
        latency_ms = int((time.perf_counter() - start) * 1000)

        return GenerationResult(
            content=wrapped.model_dump(),
            model=deep_model,
            prompt_version=VERSION,
            input_tokens=total_input,
            output_tokens=total_output,
            cache_read_tokens=total_cache_read,
            cache_write_tokens=total_cache_write,
            cost_usd=total_cost,
            latency_ms=latency_ms,
        )

    async def vocabulary(
        self,
        deep_dive_text: str,
    ) -> GenerationResult:
        """
        Two-stage: extract technical terms → define each.
        Uses Haiku for both stages.
        """
        start = time.perf_counter()

        # Stage 1: extract terms
        extract_result, extract_raw = await self._client.messages.create_with_completion(
            model=self._fast_model,
            max_tokens=500,
            system=[
                {
                    "type": "text",
                    "text": VOCAB_EXTRACT_SYSTEM,
                    "cache_control": {"type": "ephemeral"},
                }
            ],
            messages=[{"role": "user", "content": deep_dive_text}],
            response_model=ExtractedTerms,
            max_retries=2,
        )

        terms = extract_result.terms
        if not terms:
            wrapped = Vocabulary(terms=[])
            return _empty_generation(
                wrapped, self._fast_model, start
            )

        # Stage 2: define each term. Batch into one call to save round-trips.
        term_list = "\n".join(f"- {t}" for t in terms)
        user_msg = (
            f"Paper summary (for context):\n\n{deep_dive_text}\n\n"
            f"Terms to define:\n{term_list}"
        )

        define_result, define_raw = await self._client.messages.create_with_completion(
            model=self._fast_model,
            max_tokens=2000,
            system=[
                {
                    "type": "text",
                    "text": VOCAB_DEFINE_SYSTEM,
                    "cache_control": {"type": "ephemeral"},
                }
            ],
            messages=[{"role": "user", "content": user_msg}],
            response_model=Vocabulary,
            max_retries=2,
        )

        latency_ms = int((time.perf_counter() - start) * 1000)

        extract_usage = extract_raw.usage.model_dump() if hasattr(extract_raw.usage, "model_dump") else dict(extract_raw.usage)
        define_usage = define_raw.usage.model_dump() if hasattr(define_raw.usage, "model_dump") else dict(define_raw.usage)

        total_input = extract_usage.get("input_tokens", 0) + define_usage.get("input_tokens", 0)
        total_output = extract_usage.get("output_tokens", 0) + define_usage.get("output_tokens", 0)
        total_cost = _compute_cost(extract_usage, self._fast_model) + _compute_cost(define_usage, self._fast_model)

        logger.info(
            "vocabulary.done",
            terms_extracted=len(terms),
            terms_defined=len(define_result.terms),
            input_tokens=total_input,
            output_tokens=total_output,
            cost_usd=round(total_cost, 6),
            latency_ms=latency_ms,
        )

        return GenerationResult(
            content=define_result.model_dump(),
            model=self._fast_model,
            prompt_version=VERSION,
            input_tokens=total_input,
            output_tokens=total_output,
            cache_read_tokens=(extract_usage.get("cache_read_input_tokens", 0) or 0) + (define_usage.get("cache_read_input_tokens", 0) or 0),
            cache_write_tokens=(extract_usage.get("cache_creation_input_tokens", 0) or 0) + (define_usage.get("cache_creation_input_tokens", 0) or 0),
            cost_usd=total_cost,
            latency_ms=latency_ms,
        )

    async def analogies(
        self,
        deep_dive_text: str,
    ) -> GenerationResult:
        """
        Three-stage: extract concepts → 3 candidates per concept → judge picks best.
        Uses Haiku throughout (cheap, extractive-ish).
        """
        start = time.perf_counter()

        # Stage 1: extract concepts
        concept_result, concept_raw = await self._client.messages.create_with_completion(
            model=self._fast_model,
            max_tokens=300,
            system=[
                {
                    "type": "text",
                    "text": CONCEPT_EXTRACT_SYSTEM,
                    "cache_control": {"type": "ephemeral"},
                }
            ],
            messages=[{"role": "user", "content": deep_dive_text}],
            response_model=ConceptList,
            max_retries=2,
        )

        concepts = concept_result.concepts
        if not concepts:
            wrapped = Analogies(items=[])
            return _empty_generation(wrapped, self._fast_model, start)

        chosen: list[Analogy] = []
        total_input = concept_raw.usage.input_tokens
        total_output = concept_raw.usage.output_tokens
        total_cost = _compute_cost(concept_raw.usage.model_dump() if hasattr(concept_raw.usage, "model_dump") else dict(concept_raw.usage), self._fast_model)
        total_cache_read = concept_raw.usage.cache_read_input_tokens or 0
        total_cache_write = concept_raw.usage.cache_creation_input_tokens or 0

        # Stages 2 + 3: for each concept, generate 3 and judge
        for concept in concepts:
            gen_result, gen_raw = await self._client.messages.create_with_completion(
                model=self._fast_model,
                max_tokens=1500,
                system=[
                    {
                        "type": "text",
                        "text": ANALOGY_GENERATE_SYSTEM,
                        "cache_control": {"type": "ephemeral"},
                    }
                ],
                messages=[
                    {
                        "role": "user",
                        "content": (
                            f"Paper context:\n\n{deep_dive_text[:2000]}\n\n"
                            f"Concept to explain: {concept}\n\n"
                            "Produce three candidate analogies."
                        ),
                    }
                ],
                response_model=AnalogySet,
                max_retries=2,
            )

            gen_usage = gen_raw.usage.model_dump() if hasattr(gen_raw.usage, "model_dump") else dict(gen_raw.usage)
            total_input += gen_usage.get("input_tokens", 0)
            total_output += gen_usage.get("output_tokens", 0)
            total_cost += _compute_cost(gen_usage, self._fast_model)
            total_cache_read += gen_usage.get("cache_read_input_tokens", 0) or 0
            total_cache_write += gen_usage.get("cache_creation_input_tokens", 0) or 0

            if not gen_result.candidates:
                continue

            # Stage 3: judge picks best
            candidates_text = "\n\n".join(
                f"Candidate {i+1}:\nConcept: {c.concept}\nAnalogy: {c.analogy}"
                for i, c in enumerate(gen_result.candidates)
            )

            judge_result, judge_raw = await self._client.messages.create_with_completion(
                model=self._fast_model,
                max_tokens=800,
                system=[
                    {
                        "type": "text",
                        "text": ANALOGY_JUDGE_SYSTEM,
                        "cache_control": {"type": "ephemeral"},
                    }
                ],
                messages=[{"role": "user", "content": candidates_text}],
                response_model=Analogy,
                max_retries=2,
            )

            judge_usage = judge_raw.usage.model_dump() if hasattr(judge_raw.usage, "model_dump") else dict(judge_raw.usage)
            total_input += judge_usage.get("input_tokens", 0)
            total_output += judge_usage.get("output_tokens", 0)
            total_cost += _compute_cost(judge_usage, self._fast_model)
            total_cache_read += judge_usage.get("cache_read_input_tokens", 0) or 0
            total_cache_write += judge_usage.get("cache_creation_input_tokens", 0) or 0

            chosen.append(judge_result)
            logger.info("analogy.chosen", concept=concept)

        wrapped = Analogies(items=chosen)
        latency_ms = int((time.perf_counter() - start) * 1000)

        logger.info(
            "analogies.done",
            concepts=len(concepts),
            chosen=len(chosen),
            input_tokens=total_input,
            output_tokens=total_output,
            cost_usd=round(total_cost, 6),
            latency_ms=latency_ms,
        )

        return GenerationResult(
            content=wrapped.model_dump(),
            model=self._fast_model,
            prompt_version=VERSION,
            input_tokens=total_input,
            output_tokens=total_output,
            cache_read_tokens=total_cache_read,
            cache_write_tokens=total_cache_write,
            cost_usd=total_cost,
            latency_ms=latency_ms,
        )

    async def _generate(
        self,
        response_model,
        system_prompt: str,
        user_content: str,
        model: str,
        max_tokens: int,
    ) -> GenerationResult:
        """Core generation call. Handles caching + retries + cost tracking."""
        start = time.perf_counter()

        # Anthropic prompt caching: mark the system prompt as cache_control="ephemeral".
        # First call writes the cache (25% premium). Subsequent calls within ~5 min
        # read from cache (90% discount).
        system_blocks = [
            {
                "type": "text",
                "text": system_prompt,
                "cache_control": {"type": "ephemeral"},
            }
        ]

        # Instructor's create_with_completion returns (parsed, raw_message)
        # so we can inspect usage for cost tracking
        result, raw = await self._client.messages.create_with_completion(
            model=model,
            max_tokens=max_tokens,
            system=system_blocks,
            messages=[{"role": "user", "content": user_content}],
            response_model=response_model,
            max_retries=2,
        )

        latency_ms = int((time.perf_counter() - start) * 1000)
        usage = raw.usage.model_dump() if hasattr(raw.usage, "model_dump") else dict(raw.usage)
        cost = _compute_cost(usage, model)

        logger.info(
            "generation.done",
            model=model,
            section=response_model.__name__,
            input_tokens=usage.get("input_tokens", 0),
            output_tokens=usage.get("output_tokens", 0),
            cache_read=usage.get("cache_read_input_tokens", 0) or 0,
            cache_write=usage.get("cache_creation_input_tokens", 0) or 0,
            cost_usd=round(cost, 6),
            latency_ms=latency_ms,
        )

        return GenerationResult(
            content=result.model_dump(),
            model=model,
            prompt_version=VERSION,
            input_tokens=usage.get("input_tokens", 0),
            output_tokens=usage.get("output_tokens", 0),
            cache_read_tokens=usage.get("cache_read_input_tokens", 0) or 0,
            cache_write_tokens=usage.get("cache_creation_input_tokens", 0) or 0,
            cost_usd=cost,
            latency_ms=latency_ms,
        )


def _paper_context_full(title: str, abstract: str, full_text: str) -> str:
    """Format full-paper context sent to the LLM."""
    return f"""Paper title: {title}

Paper abstract:
{abstract}

---

Full paper text (parsed from PDF):

{full_text}"""