from __future__ import annotations

import re

import dspy
from decoded.config import settings

# Jargão de IA que não pode aparecer dentro da analogia
AI_JARGON = {
    "neural network", "gradient", "embedding", "transformer",
    "attention mechanism", "backprop", "backpropagation",
    "loss function", "ensemble", "fine-tuning", "training data",
    "parameters", "weights", "token", "logits", "inference",
    "model", "algorithm", "dataset",
}


class JudgeAnalogy(dspy.Signature):
    """Judge an analogy strictly. Most analogies are a 3. Reserve 5 for exceptional.

    5 — The mapping is exact: every correspondence holds under scrutiny. The
        everyday scene is specific enough to picture (a named place, a concrete
        action, not "imagine a factory"). where_it_breaks identifies a genuine
        disanalogy that teaches something about the technical concept.

    4 — Mapping is correct, scene is concrete, but where_it_breaks is generic
        ("it's not exactly the same") or the domain is a common choice for this
        concept.

    3 — The analogy is serviceable but shallow. It maps objects rather than
        relationships, or the scene is abstract ("imagine a system that...").
        Default score.

    2 — Mapping has an error, or the analogy restates the concept in different
        words without adding an everyday frame.

    1 — Circular, vacuous, or uses AI/ML terminology inside the analogy.

    Be harsh. A field of analogies that all score 5 is a failure of judgment.
    """

    concept: str = dspy.InputField()
    setup: str = dspy.InputField()
    mapping: str = dspy.InputField()
    where_it_breaks: str = dspy.InputField()

    weakest_element: str = dspy.OutputField(
        desc="Name the single weakest part of this analogy. Every analogy has one."
    )
    score: int = dspy.OutputField(desc="Integer 1-5, following the rubric strictly")


_judge = None
_judge_lm = None


def _get_judge():
    global _judge, _judge_lm
    if _judge is None:
        _judge_lm = dspy.LM(
            settings.dspy_judge_model,
            api_key=settings.openai_api_key,
            max_tokens=500,
        )
        _judge = dspy.Predict(JudgeAnalogy)
    return _judge

def _count_words(text: str) -> int:
    return len(text.split())


def _jargon_hits(text: str) -> list[str]:
    lower = text.lower()
    return [j for j in AI_JARGON if j in lower]


def deterministic_score(pred: dspy.Prediction) -> tuple[float, list[str]]:
    """
    Checagens objetivas. Retorna (fração aprovada, problemas).
    Sem LLM, instantâneo.
    """
    problems: list[str] = []
    checks = 0
    passed = 0

    setup = getattr(pred, "setup", "") or ""
    mapping = getattr(pred, "mapping", "") or ""
    breaks = getattr(pred, "where_it_breaks", "") or ""
    domain = getattr(pred, "domain", "") or ""

    # Setup tem tamanho razoável
    checks += 1
    setup_words = _count_words(setup)
    if 40 <= setup_words <= 160:
        passed += 1
    else:
        problems.append(f"setup tem {setup_words} palavras (alvo 40-160)")

    # Setup não usa jargão de IA
    checks += 1
    hits = _jargon_hits(setup)
    if not hits:
        passed += 1
    else:
        problems.append(f"jargão no setup: {hits}")

    # Mapping tem entradas suficientes com a seta
    checks += 1
    arrows = [ln for ln in mapping.split("\n") if "→" in ln or "->" in ln]
    if 3 <= len(arrows) <= 7:
        passed += 1
    else:
        problems.append(f"{len(arrows)} linhas de mapeamento (alvo 3-7)")

    # where_it_breaks é substancial
    checks += 1
    breaks_words = _count_words(breaks)
    if 20 <= breaks_words <= 120:
        passed += 1
    else:
        problems.append(f"where_it_breaks tem {breaks_words} palavras (alvo 20-120)")

    # Domain é curto
    checks += 1
    if 1 <= _count_words(domain) <= 4:
        passed += 1
    else:
        problems.append(f"domain: {domain!r}")

    # Mapeamento não pode ser identidade ("attention → attention")
    checks += 1
    identity_maps = 0
    for line in arrows:
        sep = "→" if "→" in line else "->"
        parts = [p.strip().lower() for p in line.split(sep, 1)]
        if len(parts) == 2:
            left = set(w for w in parts[0].split() if len(w) > 3)
            right = set(w for w in parts[1].split() if len(w) > 3)
            if left & right:
                identity_maps += 1
    if identity_maps == 0:
        passed += 1
    else:
        problems.append(f"{identity_maps} mapeamentos circulares")

    # where_it_breaks precisa ensinar, não só admitir imperfeição
    checks += 1
    hedges = [
        "not exactly", "isn't perfect", "no analogy is perfect",
        "of course", "obviously", "it's not the same",
        "não é exatamente", "nenhuma analogia é perfeita",
    ]
    breaks_lower = breaks.lower()
    if not any(h in breaks_lower for h in hedges) and _count_words(breaks) >= 30:
        passed += 1
    else:
        problems.append("where_it_breaks é genérico ou curto demais")

    # Setup não repete o nome do conceito literalmente
    checks += 1
    concept_words = set(
        w.lower() for w in getattr(pred, "concept", "").split() if len(w) > 4
    )
    setup_words_set = set(w.lower().strip(".,") for w in setup.split())
    overlap = concept_words & setup_words_set
    if not overlap:
        passed += 1
    else:
        problems.append(f"setup repete termos do conceito: {overlap}")

    return passed / checks if checks else 0.0, problems


def analogy_metric(
    example: dspy.Example,
    pred: dspy.Prediction,
    trace=None,
) -> float:
    """
    Métrica composta. DSPy chama isso para cada candidato.

    60% determinístico (grátis, rápido), 40% LLM judge (caro, subjetivo).
    Durante a compilação DSPy chama isso centenas de vezes, então o peso
    no lado barato importa.
    """
    det_score, _ = deterministic_score(pred)

    # Durante bootstrapping (trace presente), pula o judge para economizar
    if trace is not None:
        return det_score >= 0.8

    try:
        judge = _get_judge()
        with dspy.context(lm=_judge_lm):
            verdict = judge(
                concept=example.concept,
                setup=pred.setup,
                mapping=pred.mapping,
                where_it_breaks=pred.where_it_breaks,
            )
        raw = str(verdict.score).strip()
        match = re.search(r"[1-5]", raw)
        judge_score = (int(match.group()) - 1) / 4 if match else 0.5
    except Exception:
        judge_score = 0.5

    return 0.6 * det_score + 0.4 * judge_score