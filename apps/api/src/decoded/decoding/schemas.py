"""Pydantic schemas for decoded paper content.

The full DecodedPaper is composed of 7 independent sections. Each section
is generated separately (different prompts, different models, different costs)
and stored in the same JSONB column keyed by section name.

Schema version bumps when we change field shapes so old decoded content
can be identified and (optionally) re-generated.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

SCHEMA_VERSION = 1


# ============================================================
# 1. One-Sentence
# ============================================================
class OneSentence(BaseModel):
    """20-word max punch line. What this paper does, in one sentence."""

    text: str = Field(
        ...,
        description="One sentence, under 20 words, that captures what this paper does. "
                    "Plain language. No jargon.",
        max_length=200,
    )


# ============================================================
# 2. 60-Second Read
# ============================================================
class SixtySecondRead(BaseModel):
    """Three short paragraphs. Problem, approach, result."""

    problem: str = Field(
        ...,
        description="What problem is this paper trying to solve? 2-3 sentences.",
        max_length=600,
    )
    approach: str = Field(
        ...,
        description="What did the authors try? 2-3 sentences.",
        max_length=600,
    )
    result: str = Field(
        ...,
        description="What did they find? 2-3 sentences.",
        max_length=600,
    )


# ============================================================
# 3. Deep Dive
# ============================================================
class DeepDiveSection(BaseModel):
    heading: str = Field(..., max_length=80)
    body: str = Field(..., max_length=2000)


class DeepDive(BaseModel):
    """Structured 5-minute walkthrough."""

    setup: DeepDiveSection = Field(
        ...,
        description="What came before this paper. Context a smart non-expert needs.",
    )
    idea: DeepDiveSection = Field(
        ...,
        description="The key insight or hypothesis.",
    )
    method: DeepDiveSection = Field(
        ...,
        description="How they did it. Math replaced by plain description or pseudocode.",
    )
    results: DeepDiveSection = Field(
        ...,
        description="What they observed, with numbers where relevant.",
    )
    implications: DeepDiveSection = Field(
        ...,
        description="What this changes. What it doesn't change. Limitations.",
    )


# ============================================================
# 4. Vocabulary
# ============================================================
class VocabTerm(BaseModel):
    term: str = Field(..., max_length=80)
    definition: str = Field(
        ...,
        description="One-sentence plain-language definition, contextual to this paper.",
        max_length=400,
    )


class Vocabulary(BaseModel):
    """Technical terms that a non-expert would trip on, each defined."""

    terms: list[VocabTerm] = Field(default_factory=list, max_length=20)


# ============================================================
# 5. Analogies
# ============================================================
class Analogy(BaseModel):
    """One analogy for a core mechanism in the paper."""

    concept: str = Field(
        ...,
        description="The technical concept being explained (e.g. 'attention mechanism').",
        max_length=200,
    )
    analogy: str = Field(
        ...,
        description="The plain-world analogy. 2-4 sentences.",
        max_length=800,
    )


class AnalogySet(BaseModel):
    """Three candidate analogies for one concept — before judging."""
    concept: str = Field(..., max_length=200)
    candidates: list[Analogy] = Field(default_factory=list, max_length=3)


class ConceptList(BaseModel):
    """Just a list of concept names to generate analogies for."""
    concepts: list[str] = Field(default_factory=list, max_length=5)


class ExtractedTerms(BaseModel):
    terms: list[str] = Field(default_factory=list, max_length=15)


class Analogies(BaseModel):
    items: list[Analogy] = Field(default_factory=list, max_length=5)


# ============================================================
# 6. Figures Explained
# ============================================================
class FigureExplained(BaseModel):
    figure_ref: str = Field(
        ...,
        description="Reference to the figure (e.g. 'Figure 2', 'Table 1').",
        max_length=40,
    )
    caption_from_paper: str | None = Field(
        default=None,
        description="The original caption from the paper, if available.",
        max_length=1000,
    )
    plain_language: str = Field(
        ...,
        description="What this figure shows, explained for a non-expert.",
        max_length=2000,
    )
    key_insight: str = Field(
        ...,
        description="One sentence: why this figure matters.",
        max_length=400,
    )


class FiguresExplained(BaseModel):
    items: list[FigureExplained] = Field(default_factory=list, max_length=10)


# ============================================================
# 7. So What
# ============================================================
class SoWhat(BaseModel):
    """Why should the reader care?"""

    matters_because: str = Field(
        ...,
        description="Why this paper matters. Concrete impact, not hype.",
        max_length=800,
    )
    who_benefits: str = Field(
        ...,
        description="Which audiences (engineers, researchers, businesses) benefit and how.",
        max_length=600,
    )
    open_question: str = Field(
        ...,
        description="One follow-up question the paper leaves open.",
        max_length=300,
    )


# ============================================================
# Full decoded paper
# ============================================================
class DecodedSectionKey(str):
    ONE_SENTENCE = "one_sentence"
    SIXTY_SECOND = "sixty_second"
    DEEP_DIVE = "deep_dive"
    VOCABULARY = "vocabulary"
    ANALOGIES = "analogies"
    FIGURES = "figures"
    SO_WHAT = "so_what"


class DecodedPaper(BaseModel):
    """Full decoded content. Any subset of sections may be present."""

    schema_version: int = SCHEMA_VERSION
    one_sentence: OneSentence | None = None
    sixty_second: SixtySecondRead | None = None
    deep_dive: DeepDive | None = None
    vocabulary: Vocabulary | None = None
    analogies: Analogies | None = None
    figures: FiguresExplained | None = None
    so_what: SoWhat | None = None


# ============================================================
# Generation metadata (stored alongside sections)
# ============================================================
class SectionGeneration(BaseModel):
    """Metadata for one generated section."""

    section: Literal[
        "one_sentence",
        "sixty_second",
        "deep_dive",
        "vocabulary",
        "analogies",
        "figures",
        "so_what",
    ]
    model: str
    prompt_version: str
    input_tokens: int
    output_tokens: int
    cost_usd: float
    latency_ms: int
    schema_version: int = SCHEMA_VERSION