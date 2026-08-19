from __future__ import annotations

import asyncio
from dataclasses import dataclass

import structlog
from anthropic import AsyncAnthropic
from pydantic import BaseModel, Field

import instructor

logger = structlog.get_logger()


# ============================================================
# Schemas de saída do judge
# ============================================================
class FaithfulnessVerdict(BaseModel):
    supported_claims: int = Field(..., description="Quantas afirmações são sustentadas pelo paper")
    unsupported_claims: int = Field(..., description="Quantas afirmações NÃO aparecem no paper")
    unsupported_examples: list[str] = Field(
        default_factory=list,
        description="Até 3 exemplos de afirmações não sustentadas",
        max_length=3,
    )
    score: float = Field(..., ge=0.0, le=1.0, description="supported / (supported + unsupported)")


class QualityVerdict(BaseModel):
    score: int = Field(..., ge=1, le=5, description="Nota de 1 a 5")
    reasoning: str = Field(..., max_length=500, description="Justificativa em 1-2 frases")


FAITHFULNESS_SYSTEM = """Você avalia se um texto gerado é fiel ao paper de origem.

Você vai receber:
1. O texto do paper (ou trechos dele)
2. Um texto gerado a partir dele

Sua tarefa: identificar cada afirmação factual do texto gerado e classificar como SUSTENTADA ou NÃO SUSTENTADA pelo paper.

REGRAS:
- Uma afirmação é SUSTENTADA se o paper diz isso, mesmo com palavras diferentes.
- Uma afirmação é NÃO SUSTENTADA se o paper não diz isso, ou diz algo diferente.
- Números específicos (93%, 8500 exemplos) só são sustentados se o número aparece no paper.
- Reformulações e simplificações são sustentadas, desde que preservem o sentido.
- Opiniões e interpretações razoáveis derivadas do paper contam como sustentadas.
- Analogias e explicações didáticas não são afirmações factuais — ignore.

Conte as afirmações sustentadas e não sustentadas. Liste até 3 exemplos de não sustentadas.
Calcule score = sustentadas / (sustentadas + não sustentadas)."""


HEADING_QUALITY_SYSTEM = """Você avalia a qualidade de títulos de seção em conteúdo explicativo.

Um bom título é específico e evocativo. Ele diz algo sobre o conteúdo daquela seção em particular.
Um título ruim é genérico e intercambiável entre papers.

ESCALA:
5 = Específico e memorável. Ex: "O platô que ninguém conseguia quebrar"
4 = Específico mas sem graça. Ex: "Debate em duas etapas"
3 = Levemente específico. Ex: "O método de treinamento"
2 = Quase genérico. Ex: "A abordagem"
1 = Totalmente genérico. Ex: "Método", "Resultados", "Introdução"

Dê a nota e justifique em 1-2 frases."""


ANALOGY_QUALITY_SYSTEM = """Você avalia a qualidade de analogias explicativas.

Uma boa analogia mapeia a RELAÇÃO, não só o conceito. Ela usa um cenário do cotidiano que o leitor conhece visceralmente, e termina ensinando algo concreto sobre a abordagem do paper.

ESCALA:
5 = Mapeia a relação corretamente, cenário vívido, ensina algo concreto
4 = Mapeia a relação, cenário ok, ensina algo
3 = Analogia razoável mas superficial
2 = Analogia vaga ou que mapeia a coisa errada
1 = Não é analogia, ou usa jargão de IA para explicar IA

PENALIZE:
- Usar conceitos de IA/ML dentro da analogia (ensemble, gradiente, embedding)
- Analogias que só dizem "X é como Y" sem explicar o mapeamento
- Cenários abstratos demais

Dê a nota e justifique em 1-2 frases."""


class Judge:
    def __init__(self, api_key: str, model: str = "claude-haiku-4-5-20251001") -> None:
        self._raw = AsyncAnthropic(api_key=api_key)
        self._client = instructor.from_anthropic(self._raw)
        self._model = model

    async def close(self) -> None:
        await self._raw.close()

    async def __aenter__(self) -> "Judge":
        return self

    async def __aexit__(self, *args) -> None:
        await self.close()

    async def faithfulness(
        self,
        source_text: str,
        generated_text: str,
        max_source_chars: int = 30000,
    ) -> FaithfulnessVerdict:
        """Mede se o texto gerado é sustentado pelo paper."""
        source = source_text[:max_source_chars]
        user = (
            f"PAPER:\n\n{source}\n\n"
            f"---\n\nTEXTO GERADO:\n\n{generated_text}"
        )
        result = await self._client.messages.create(
            model=self._model,
            max_tokens=1000,
            system=[{"type": "text", "text": FAITHFULNESS_SYSTEM}],
            messages=[{"role": "user", "content": user}],
            response_model=FaithfulnessVerdict,
            max_retries=2,
        )
        return result

    async def heading_quality(self, headings: list[str]) -> QualityVerdict:
        """Avalia o conjunto de headings de um deep dive."""
        user = "Títulos:\n" + "\n".join(f"- {h}" for h in headings)
        return await self._client.messages.create(
            model=self._model,
            max_tokens=500,
            system=[{"type": "text", "text": HEADING_QUALITY_SYSTEM}],
            messages=[{"role": "user", "content": user}],
            response_model=QualityVerdict,
            max_retries=2,
        )

    async def analogy_quality(self, concept: str, analogy: str) -> QualityVerdict:
        """Avalia uma analogia."""
        user = f"Conceito: {concept}\n\nAnalogia:\n{analogy}"
        return await self._client.messages.create(
            model=self._model,
            max_tokens=500,
            system=[{"type": "text", "text": ANALOGY_QUALITY_SYSTEM}],
            messages=[{"role": "user", "content": user}],
            response_model=QualityVerdict,
            max_retries=2,
        )