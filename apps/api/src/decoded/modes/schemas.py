"""Schemas para os cinco modos de explicação.

Cada modo tem shape próprio porque explica coisas diferentes. Um schema
genérico ("content: str") jogaria fora a estrutura que o frontend usa
pra renderizar cada modo do jeito certo.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator

MODE_SCHEMA_VERSION = 1

ModeName = Literal["math", "analogy", "story", "diagram", "code"]


# ============================================================
# math
# ============================================================
class EquationExplained(BaseModel):
    latex: str = Field(
        ...,
        description="A equação em LaTeX, sem delimitadores ($ ou \\[).",
        max_length=1200,
    )
    label: str = Field(
        ...,
        description="Como o paper se refere a ela (ex: 'Equation 3', 'the loss function').",
        max_length=100,
    )
    plain_reading: str = Field(
        ...,
        description="Como ler a equação em voz alta, em linguagem comum.",
        max_length=600,
    )
    what_each_symbol_means: list[str] = Field(
        default_factory=list,
        description="Um item por símbolo: 'θ — os parâmetros do modelo'.",
        max_length=12,
    )
    why_it_matters: str = Field(
        ...,
        description="O que essa equação faz pelo argumento do paper.",
        max_length=500,
    )


class MathMode(BaseModel):
    intuition: str = Field(
        ...,
        description="A ideia matemática central em 2-4 frases, antes de qualquer notação.",
        max_length=1000,
    )
    equations: list[EquationExplained] = Field(
        default_factory=list,
        max_length=6,
    )
    the_trick: str | None = Field(
        default=None,
        description="Se há um truque matemático que faz tudo funcionar, qual é.",
        max_length=600,
    )


# ============================================================
# analogy
# ============================================================
class RichAnalogy(BaseModel):
    concept: str = Field(..., max_length=150)
    domain: str = Field(
        ...,
        description="O domínio cotidiano usado (ex: 'cooking', 'traffic', 'hiring').",
        max_length=60,
    )
    setup: str = Field(
        ...,
        description="O cenário cotidiano, antes de conectar ao paper.",
        max_length=700,
    )
    mapping: list[str] = Field(
        ...,
        description="Correspondências explícitas: 'o chef → o modelo base'.",
        max_length=6,
    )
    where_it_breaks: str = Field(
        ...,
        description="Onde a analogia falha. Toda analogia falha em algum ponto.",
        max_length=400,
    )


class AnalogyMode(BaseModel):
    analogies: list[RichAnalogy] = Field(default_factory=list, max_length=4)


# ============================================================
# story
# ============================================================
class StoryBeat(BaseModel):
    year: str | None = Field(
        default=None,
        description="Ano ou período, se identificável.",
        max_length=20,
    )
    heading: str = Field(..., max_length=100)
    body: str = Field(..., max_length=1500)


class StoryMode(BaseModel):
    beats: list[StoryBeat] = Field(
        ...,
        description="Narrativa cronológica terminando neste paper.",
        max_length=7,
    )
    where_it_leaves_us: str = Field(
        ...,
        description="O estado do campo depois deste paper.",
        max_length=800,
    )


# ============================================================
# diagram
# ============================================================
class DiagramMode(BaseModel):
    mermaid: str = Field(
        ...,
        description="Código Mermaid válido. Flowchart, sequenceDiagram ou stateDiagram.",
        max_length=4000,
    )
    diagram_type: Literal["flowchart", "sequence", "state", "class"] = "flowchart"
    caption: str = Field(
        ...,
        description="O que o diagrama mostra, em 1-2 frases.",
        max_length=400,
    )
    walkthrough: list[str] = Field(
        default_factory=list,
        description="Passo a passo do fluxo, um item por etapa.",
        max_length=10,
    )

    @field_validator("mermaid")
    @classmethod
    def strip_fences(cls, v: str) -> str:
        """Remove cercas de markdown se o modelo incluir."""
        v = v.strip()
        if v.startswith("```"):
            lines = v.split("\n")
            lines = lines[1:]
            if lines and lines[-1].strip().startswith("```"):
                lines = lines[:-1]
            v = "\n".join(lines).strip()
        return v


# ============================================================
# code
# ============================================================
class CodeMode(BaseModel):
    language: str = Field(default="python", max_length=30)
    code: str = Field(
        ...,
        description="O algoritmo central como código executável e comentado.",
        max_length=6000,
    )
    what_it_does: str = Field(
        ...,
        description="O que o código faz, em 2-3 frases.",
        max_length=600,
    )
    example_usage: str | None = Field(
        default=None,
        description="Uma chamada de exemplo com entrada e saída esperada.",
        max_length=1200,
    )
    caveats: list[str] = Field(
        default_factory=list,
        description="O que foi simplificado em relação ao paper.",
        max_length=5,
    )

    @field_validator("code")
    @classmethod
    def strip_fences(cls, v: str) -> str:
        v = v.strip()
        if v.startswith("```"):
            lines = v.split("\n")
            lines = lines[1:]
            if lines and lines[-1].strip().startswith("```"):
                lines = lines[:-1]
            v = "\n".join(lines).strip()
        return v


# ============================================================
# Registry
# ============================================================
MODE_SCHEMAS: dict[str, type[BaseModel]] = {
    "math": MathMode,
    "analogy": AnalogyMode,
    "story": StoryMode,
    "diagram": DiagramMode,
    "code": CodeMode,
}

ALL_MODES: list[str] = list(MODE_SCHEMAS.keys())


class ModeAvailability(BaseModel):
    """Quais modos existem para um paper e quais podem ser gerados."""

    mode: ModeName
    cached: bool
    generating: bool = False