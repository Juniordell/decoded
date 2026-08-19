from __future__ import annotations

import re
from dataclasses import dataclass

import textstat

# Jargão que os prompts mandam evitar. Se aparecer, é violação.
JARGON_BLACKLIST = {
    "ablation", "ablate", "sota", "state-of-the-art", "state of the art",
    "novel approach", "novel framework", "novel method",
    "leverage", "leveraging", "leverages",
    "utilize", "utilizing", "utilizes",
    "empirically demonstrate", "empirically show",
    "groundbreaking", "revolutionary", "pioneering",
    "paradigm shift", "comprehensive analysis",
    "underlying mechanisms", "rich representations",
    "efficacy", "efficacious",
}

# Preâmbulos que os prompts proíbem
PREAMBLE_PATTERNS = [
    r"^in this (paper|work|study)",
    r"^this (paper|work|study) (presents|proposes|introduces|explores|investigates)",
    r"^the authors (propose|present|introduce)",
    r"^we (propose|present|introduce)",
    r"^here is",
    r"^sure[,!]",
]


@dataclass
class MetricResult:
    name: str
    value: float
    passed: bool
    detail: str = ""


def count_words(text: str) -> int:
    return len(text.split())


def find_jargon(text: str) -> list[str]:
    lower = text.lower()
    return sorted(term for term in JARGON_BLACKLIST if term in lower)


def has_preamble(text: str) -> bool:
    lower = text.strip().lower()
    return any(re.search(p, lower) for p in PREAMBLE_PATTERNS)


def readability_grade(text: str) -> float:
    """Flesch-Kincaid grade level. Alvo: 8-12 (ensino médio)."""
    if not text.strip():
        return 0.0
    return textstat.flesch_kincaid_grade(text)


# ============================================================
# one_sentence
# ============================================================
def eval_one_sentence(content: dict) -> list[MetricResult]:
    text = content.get("text", "")
    results = []

    words = count_words(text)
    results.append(
        MetricResult(
            name="word_count",
            value=float(words),
            passed=words <= 20,
            detail=f"{words} palavras (limite 20)",
        )
    )

    jargon = find_jargon(text)
    results.append(
        MetricResult(
            name="jargon_free",
            value=float(len(jargon)),
            passed=len(jargon) == 0,
            detail=f"jargão: {jargon}" if jargon else "limpo",
        )
    )

    preamble = has_preamble(text)
    results.append(
        MetricResult(
            name="no_preamble",
            value=0.0 if preamble else 1.0,
            passed=not preamble,
            detail="tem preâmbulo" if preamble else "ok",
        )
    )

    return results


# ============================================================
# sixty_second
# ============================================================
def eval_sixty_second(content: dict) -> list[MetricResult]:
    results = []
    fields = ["problem", "approach", "result"]

    for field in fields:
        text = content.get(field, "")

        present = bool(text.strip())
        results.append(
            MetricResult(
                name=f"{field}_present",
                value=1.0 if present else 0.0,
                passed=present,
                detail="ok" if present else "vazio",
            )
        )

        if not present:
            continue

        sentences = textstat.sentence_count(text)
        results.append(
            MetricResult(
                name=f"{field}_sentence_count",
                value=float(sentences),
                passed=2 <= sentences <= 4,
                detail=f"{sentences} frases (alvo 2-3)",
            )
        )

        jargon = find_jargon(text)
        results.append(
            MetricResult(
                name=f"{field}_jargon_free",
                value=float(len(jargon)),
                passed=len(jargon) == 0,
                detail=f"jargão: {jargon}" if jargon else "limpo",
            )
        )

    # O RESULT deve conter números
    result_text = content.get("result", "")
    has_numbers = bool(re.search(r"\d", result_text))
    results.append(
        MetricResult(
            name="result_has_numbers",
            value=1.0 if has_numbers else 0.0,
            passed=has_numbers,
            detail="ok" if has_numbers else "sem números no RESULT",
        )
    )

    return results


# ============================================================
# deep_dive
# ============================================================
GENERIC_HEADINGS = {
    "setup", "idea", "method", "results", "implications",
    "introduction", "background", "conclusion", "overview",
    "the setup", "the idea", "the method", "the results",
}


def eval_deep_dive(content: dict) -> list[MetricResult]:
    results = []
    sections = ["setup", "idea", "method", "results", "implications"]

    for key in sections:
        section = content.get(key) or {}
        heading = section.get("heading", "")
        body = section.get("body", "")

        present = bool(body.strip())
        results.append(
            MetricResult(
                name=f"{key}_present",
                value=1.0 if present else 0.0,
                passed=present,
                detail="ok" if present else "vazio",
            )
        )

        if not present:
            continue

        # Heading não pode ser genérico
        generic = heading.strip().lower() in GENERIC_HEADINGS
        results.append(
            MetricResult(
                name=f"{key}_heading_specific",
                value=0.0 if generic else 1.0,
                passed=not generic,
                detail=f"heading genérico: '{heading}'" if generic else f"'{heading}'",
            )
        )

        # Tamanho razoável
        words = count_words(body)
        results.append(
            MetricResult(
                name=f"{key}_length",
                value=float(words),
                passed=40 <= words <= 250,
                detail=f"{words} palavras (alvo 40-250)",
            )
        )

        jargon = find_jargon(body)
        results.append(
            MetricResult(
                name=f"{key}_jargon_free",
                value=float(len(jargon)),
                passed=len(jargon) <= 1,  # tolerância de 1 no deep dive
                detail=f"jargão: {jargon}" if jargon else "limpo",
            )
        )

    # Legibilidade agregada
    all_bodies = " ".join(
        (content.get(k) or {}).get("body", "") for k in sections
    )
    grade = readability_grade(all_bodies)
    results.append(
        MetricResult(
            name="readability_grade",
            value=grade,
            passed=6.0 <= grade <= 16.0,
            detail=f"Flesch-Kincaid {grade:.1f} (alvo 6-16)",
        )
    )

    return results


# ============================================================
# vocabulary
# ============================================================
def eval_vocabulary(content: dict) -> list[MetricResult]:
    results = []
    terms = content.get("terms", [])

    count = len(terms)
    results.append(
        MetricResult(
            name="term_count",
            value=float(count),
            passed=3 <= count <= 20,
            detail=f"{count} termos (alvo 3-20)",
        )
    )

    if not terms:
        return results

    # Definições não podem ser longas demais
    too_long = [t["term"] for t in terms if count_words(t.get("definition", "")) > 35]
    results.append(
        MetricResult(
            name="definitions_concise",
            value=float(len(too_long)),
            passed=len(too_long) == 0,
            detail=f"longas demais: {too_long}" if too_long else "ok",
        )
    )

    # Definição não pode conter o próprio termo (circular)
    circular = [
        t["term"]
        for t in terms
        if t.get("term", "").lower() in t.get("definition", "").lower()
    ]
    results.append(
        MetricResult(
            name="definitions_not_circular",
            value=float(len(circular)),
            passed=len(circular) <= 1,
            detail=f"circulares: {circular}" if circular else "ok",
        )
    )

    # Termos duplicados
    seen = [t.get("term", "").lower() for t in terms]
    dupes = len(seen) - len(set(seen))
    results.append(
        MetricResult(
            name="no_duplicate_terms",
            value=float(dupes),
            passed=dupes == 0,
            detail=f"{dupes} duplicados" if dupes else "ok",
        )
    )

    return results


# ============================================================
# analogies
# ============================================================
AI_JARGON_IN_ANALOGY = {
    "neural network", "gradient", "embedding", "transformer",
    "attention mechanism", "backprop", "loss function", "ensemble",
    "fine-tuning", "training data", "parameters", "weights",
}


def eval_analogies(content: dict) -> list[MetricResult]:
    results = []
    items = content.get("items", [])

    count = len(items)
    results.append(
        MetricResult(
            name="analogy_count",
            value=float(count),
            passed=2 <= count <= 5,
            detail=f"{count} analogias (alvo 2-5)",
        )
    )

    if not items:
        return results

    # A analogia em si não pode usar jargão de IA
    contaminated = []
    for item in items:
        analogy_text = item.get("analogy", "").lower()
        found = [j for j in AI_JARGON_IN_ANALOGY if j in analogy_text]
        if found:
            contaminated.append(f"{item.get('concept')}: {found}")

    results.append(
        MetricResult(
            name="analogies_jargon_free",
            value=float(len(contaminated)),
            passed=len(contaminated) == 0,
            detail="; ".join(contaminated) if contaminated else "limpo",
        )
    )

    # Tamanho
    bad_length = [
        item.get("concept")
        for item in items
        if not (25 <= count_words(item.get("analogy", "")) <= 120)
    ]
    results.append(
        MetricResult(
            name="analogies_length",
            value=float(len(bad_length)),
            passed=len(bad_length) == 0,
            detail=f"fora do alvo: {bad_length}" if bad_length else "ok",
        )
    )

    return results


# ============================================================
# figures
# ============================================================
def eval_figures(content: dict) -> list[MetricResult]:
    results = []
    items = content.get("items", [])

    count = len(items)
    results.append(
        MetricResult(
            name="figure_count",
            value=float(count),
            passed=count >= 1,
            detail=f"{count} figuras explicadas",
        )
    )

    if not items:
        return results

    # Todas precisam de plain_language e key_insight
    incomplete = [
        item.get("figure_ref")
        for item in items
        if not item.get("plain_language") or not item.get("key_insight")
    ]
    results.append(
        MetricResult(
            name="figures_complete",
            value=float(len(incomplete)),
            passed=len(incomplete) == 0,
            detail=f"incompletas: {incomplete}" if incomplete else "ok",
        )
    )

    # key_insight deve ser uma frase
    verbose_insights = [
        item.get("figure_ref")
        for item in items
        if count_words(item.get("key_insight", "")) > 40
    ]
    results.append(
        MetricResult(
            name="insights_concise",
            value=float(len(verbose_insights)),
            passed=len(verbose_insights) == 0,
            detail=f"verbosas: {verbose_insights}" if verbose_insights else "ok",
        )
    )

    return results


# ============================================================
# Registry
# ============================================================
EVALUATORS = {
    "one_sentence": eval_one_sentence,
    "sixty_second": eval_sixty_second,
    "deep_dive": eval_deep_dive,
    "vocabulary": eval_vocabulary,
    "analogies": eval_analogies,
    "figures": eval_figures,
}