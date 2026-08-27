"""Métricas específicas por modo de explicação.

Três dos cinco modos produzem artefatos objetivamente verificáveis:
código compila, Mermaid faz parse, LaTeX tem estrutura checável.
Essas checagens são grátis e sem ruído — usa ao máximo antes de
recorrer a judge.
"""

from __future__ import annotations

import ast
import re
import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "src"))

from decoded.modes.mermaid import validate as validate_mermaid  # noqa: E402


@dataclass
class MetricResult:
    name: str
    value: float
    passed: bool
    detail: str = ""


def _words(text: str) -> int:
    return len(text.split())


# ============================================================
# math
# ============================================================
# Comandos que o KaTeX não suporta — se aparecerem, não renderiza
KATEX_UNSUPPORTED = {
    r"\\begin{align}",       # KaTeX quer aligned
    r"\\newcommand",
    r"\\def\b",
    r"\\usepackage",
    r"\\label{",
    r"\\ref{",
    r"\\cite{",
    r"\\includegraphics",
}


def _latex_balanced(latex: str) -> bool:
    """Chaves balanceadas. Desbalanceio é a causa número um de falha."""
    depth = 0
    i = 0
    while i < len(latex):
        if latex[i] == "\\" and i + 1 < len(latex):
            i += 2
            continue
        if latex[i] == "{":
            depth += 1
        elif latex[i] == "}":
            depth -= 1
            if depth < 0:
                return False
        i += 1
    return depth == 0


def _extract_symbols(latex: str) -> set[str]:
    """
    Símbolos gregos e letras isoladas que o glossário deveria cobrir.
    Aproximação deliberada — pega o que costuma faltar.
    """
    greek = set(re.findall(r"\\(alpha|beta|gamma|delta|epsilon|theta|lambda|mu|pi|sigma|tau|phi|psi|omega)", latex))
    # Letras romanas isoladas, fora de comandos
    stripped = re.sub(r"\\[a-zA-Z]+", " ", latex)
    romans = set(re.findall(r"\b([A-Za-z])\b", stripped))
    return greek | romans


def eval_math(content: dict) -> list[MetricResult]:
    results: list[MetricResult] = []

    intuition = content.get("intuition", "") or ""
    equations = content.get("equations", []) or []

    # Intuição existe e tem substância
    w = _words(intuition)
    results.append(
        MetricResult(
            "intuition_present",
            float(w),
            30 <= w <= 200,
            f"{w} palavras (alvo 30-200)",
        )
    )

    # Papers sem matemática são válidos — mas então a intuição carrega tudo
    if not equations:
        results.append(
            MetricResult(
                "no_equations_handled",
                1.0 if w >= 40 else 0.0,
                w >= 40,
                "sem equações, intuição compensa" if w >= 40 else "sem equações e intuição fraca",
            )
        )
        return results

    # LaTeX balanceado
    unbalanced = [
        eq.get("label", f"#{i}")
        for i, eq in enumerate(equations)
        if not _latex_balanced(eq.get("latex", ""))
    ]
    results.append(
        MetricResult(
            "latex_balanced",
            float(len(unbalanced)),
            not unbalanced,
            f"desbalanceadas: {unbalanced}" if unbalanced else "ok",
        )
    )

    # Sem comandos que o KaTeX rejeita
    unsupported: list[str] = []
    for i, eq in enumerate(equations):
        latex = eq.get("latex", "")
        for pattern in KATEX_UNSUPPORTED:
            if re.search(pattern, latex):
                unsupported.append(f"{eq.get('label', i)}: {pattern}")
    results.append(
        MetricResult(
            "katex_compatible",
            float(len(unsupported)),
            not unsupported,
            "; ".join(unsupported[:3]) if unsupported else "ok",
        )
    )

    # Toda equação tem leitura em prosa
    missing_reading = [
        eq.get("label", f"#{i}")
        for i, eq in enumerate(equations)
        if _words(eq.get("plain_reading", "")) < 8
    ]
    results.append(
        MetricResult(
            "plain_readings_present",
            float(len(missing_reading)),
            not missing_reading,
            f"sem leitura: {missing_reading}" if missing_reading else "ok",
        )
    )

    # Cobertura do glossário: símbolos na equação vs símbolos definidos
    coverage_failures: list[str] = []
    for i, eq in enumerate(equations):
        symbols = _extract_symbols(eq.get("latex", ""))
        if not symbols:
            continue
        glossary = " ".join(eq.get("what_each_symbol_means", []) or []).lower()
        uncovered = [s for s in symbols if s.lower() not in glossary]
        # Tolera 40% descoberto — a extração é aproximada
        if symbols and len(uncovered) / len(symbols) > 0.4:
            coverage_failures.append(
                f"{eq.get('label', i)}: {len(uncovered)}/{len(symbols)} sem definição"
            )
    results.append(
        MetricResult(
            "symbol_coverage",
            float(len(coverage_failures)),
            not coverage_failures,
            "; ".join(coverage_failures[:3]) if coverage_failures else "ok",
        )
    )

    return results


# ============================================================
# diagram
# ============================================================
def eval_diagram(content: dict) -> list[MetricResult]:
    results: list[MetricResult] = []

    mermaid = content.get("mermaid", "") or ""
    walkthrough = content.get("walkthrough", []) or []
    caption = content.get("caption", "") or ""

    # Passa no validador — o mesmo que roda em produção
    problems = validate_mermaid(mermaid)
    results.append(
        MetricResult(
            "mermaid_valid",
            float(len(problems)),
            not problems,
            "; ".join(problems[:3]) if problems else "ok",
        )
    )

    # Densidade de nós: menos de 6 não é diagrama, mais de 16 não se lê
    node_ids = set(re.findall(r"\b([A-Za-z][A-Za-z0-9_]*)\s*[\[\({]", mermaid))
    n = len(node_ids)
    results.append(
        MetricResult(
            "node_count",
            float(n),
            5 <= n <= 16,
            f"{n} nós (alvo 5-16)",
        )
    )

    # Walkthrough cobre o diagrama
    results.append(
        MetricResult(
            "walkthrough_covers",
            float(len(walkthrough)),
            len(walkthrough) >= max(3, n // 3),
            f"{len(walkthrough)} passos para {n} nós",
        )
    )

    # Passos do walkthrough explicam, não só nomeiam
    thin = [i for i, s in enumerate(walkthrough) if _words(s) < 8]
    results.append(
        MetricResult(
            "walkthrough_substantive",
            float(len(thin)),
            len(thin) <= len(walkthrough) // 4,
            f"{len(thin)} passos rasos" if thin else "ok",
        )
    )

    # Caption existe
    results.append(
        MetricResult(
            "caption_present",
            float(_words(caption)),
            10 <= _words(caption) <= 60,
            f"{_words(caption)} palavras",
        )
    )

    return results


# ============================================================
# code
# ============================================================
FORBIDDEN_IMPORTS = {
    "torch", "tensorflow", "jax", "transformers", "flax",
    "sklearn", "scipy", "pandas", "datasets", "accelerate",
}

ALLOWED_THIRD_PARTY = {"numpy", "np"}


def eval_code(content: dict) -> list[MetricResult]:
    results: list[MetricResult] = []

    code = content.get("code", "") or ""
    caveats = content.get("caveats", []) or []
    what = content.get("what_it_does", "") or ""

    # Compila? Esta é a checagem que importa mais.
    syntax_ok = True
    syntax_error = ""
    tree = None
    try:
        tree = ast.parse(code)
    except SyntaxError as e:
        syntax_ok = False
        syntax_error = f"linha {e.lineno}: {e.msg}"

    results.append(
        MetricResult(
            "code_parses",
            1.0 if syntax_ok else 0.0,
            syntax_ok,
            syntax_error or "ok",
        )
    )

    if not syntax_ok:
        return results

    # Imports proibidos
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imported.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])

    forbidden = imported & FORBIDDEN_IMPORTS
    results.append(
        MetricResult(
            "no_heavy_deps",
            float(len(forbidden)),
            not forbidden,
            f"imports proibidos: {sorted(forbidden)}" if forbidden else "ok",
        )
    )

    # Tem ao menos uma função definida
    functions = [n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)]
    results.append(
        MetricResult(
            "has_function",
            float(len(functions)),
            len(functions) >= 1,
            f"{len(functions)} funções",
        )
    )

    # Tamanho: 15-80 linhas úteis
    lines = [
        ln for ln in code.split("\n")
        if ln.strip() and not ln.strip().startswith("#")
    ]
    results.append(
        MetricResult(
            "code_length",
            float(len(lines)),
            12 <= len(lines) <= 90,
            f"{len(lines)} linhas úteis (alvo 12-90)",
        )
    )

    # Densidade de comentários — o prompt pede comentários explicando o porquê
    comment_lines = [ln for ln in code.split("\n") if ln.strip().startswith("#")]
    docstrings = [
        n for n in ast.walk(tree)
        if isinstance(n, (ast.FunctionDef, ast.Module)) and ast.get_docstring(n)
    ]
    documented = len(comment_lines) + len(docstrings)
    ratio = documented / max(len(lines), 1)
    results.append(
        MetricResult(
            "comment_density",
            round(ratio, 3),
            ratio >= 0.12,
            f"{documented} comentários para {len(lines)} linhas",
        )
    )

    # Caveats específicos, não genéricos
    generic_caveats = [
        "simplified", "see the paper", "for details", "this is a simplified",
        "simplificado", "veja o paper",
    ]
    vague = [
        c for c in caveats
        if _words(c) < 6 or any(g in c.lower() and _words(c) < 12 for g in generic_caveats)
    ]
    results.append(
        MetricResult(
            "caveats_specific",
            float(len(vague)),
            not vague and len(caveats) >= 1,
            f"vagos: {vague}" if vague else f"{len(caveats)} caveats",
        )
    )

    # what_it_does existe
    results.append(
        MetricResult(
            "description_present",
            float(_words(what)),
            15 <= _words(what) <= 100,
            f"{_words(what)} palavras",
        )
    )

    return results


# ============================================================
# analogy
# ============================================================
AI_JARGON_IN_ANALOGY = {
    "neural network", "gradient", "embedding", "transformer",
    "attention mechanism", "backprop", "loss function", "ensemble",
    "fine-tuning", "training data", "parameters", "weights",
    "token", "logits", "inference", "dataset", "algorithm",
}

HEDGE_PHRASES = [
    "not exactly", "isn't perfect", "no analogy is perfect",
    "of course", "obviously", "it's not the same",
]


def eval_analogy_mode(content: dict) -> list[MetricResult]:
    results: list[MetricResult] = []
    analogies = content.get("analogies", []) or []

    results.append(
        MetricResult(
            "analogy_count",
            float(len(analogies)),
            2 <= len(analogies) <= 4,
            f"{len(analogies)} analogias (alvo 2-4)",
        )
    )

    if not analogies:
        return results

    # Domínios distintos — quatro analogias de cozinha é falha
    domains = [a.get("domain", "").lower().strip() for a in analogies]
    unique = len(set(domains))
    results.append(
        MetricResult(
            "domains_distinct",
            float(unique),
            unique == len(domains),
            f"{unique} domínios para {len(domains)} analogias",
        )
    )

    # Setup sem jargão de IA
    contaminated: list[str] = []
    for a in analogies:
        setup = (a.get("setup", "") or "").lower()
        hits = [j for j in AI_JARGON_IN_ANALOGY if j in setup]
        if hits:
            contaminated.append(f"{a.get('concept', '?')}: {hits[:2]}")
    results.append(
        MetricResult(
            "setups_jargon_free",
            float(len(contaminated)),
            not contaminated,
            "; ".join(contaminated[:2]) if contaminated else "ok",
        )
    )

    # Mapeamento não circular
    circular: list[str] = []
    for a in analogies:
        for line in a.get("mapping", []) or []:
            sep = "→" if "→" in line else "->"
            parts = [p.strip().lower() for p in line.split(sep, 1)]
            if len(parts) == 2:
                left = {w for w in parts[0].split() if len(w) > 3}
                right = {w for w in parts[1].split() if len(w) > 3}
                if left & right:
                    circular.append(f"{a.get('concept', '?')}: {line[:50]}")
    results.append(
        MetricResult(
            "mappings_not_circular",
            float(len(circular)),
            not circular,
            "; ".join(circular[:2]) if circular else "ok",
        )
    )

    # where_it_breaks ensina, não faz hedge
    weak: list[str] = []
    for a in analogies:
        breaks = (a.get("where_it_breaks", "") or "").lower()
        if _words(breaks) < 25 or any(h in breaks for h in HEDGE_PHRASES):
            weak.append(a.get("concept", "?"))
    results.append(
        MetricResult(
            "breaks_substantive",
            float(len(weak)),
            not weak,
            f"fracos: {weak}" if weak else "ok",
        )
    )

    return results


# ============================================================
# story
# ============================================================
GENERIC_HEADINGS = {
    "background", "prior work", "introduction", "the contribution",
    "related work", "the method", "results", "conclusion",
    "the setup", "the problem", "the solution",
}


def eval_story(content: dict) -> list[MetricResult]:
    results: list[MetricResult] = []

    beats = content.get("beats", []) or []
    ending = content.get("where_it_leaves_us", "") or ""

    results.append(
        MetricResult(
            "beat_count",
            float(len(beats)),
            4 <= len(beats) <= 7,
            f"{len(beats)} beats (alvo 4-7)",
        )
    )

    if not beats:
        return results

    # Headings específicos
    generic = [
        b.get("heading", "")
        for b in beats
        if b.get("heading", "").lower().strip() in GENERIC_HEADINGS
    ]
    results.append(
        MetricResult(
            "headings_specific",
            float(len(generic)),
            not generic,
            f"genéricos: {generic}" if generic else "ok",
        )
    )

    # Beats com substância
    thin = [
        b.get("heading", f"#{i}")
        for i, b in enumerate(beats)
        if _words(b.get("body", "")) < 30
    ]
    results.append(
        MetricResult(
            "beats_substantive",
            float(len(thin)),
            not thin,
            f"rasos: {thin}" if thin else "ok",
        )
    )

    # Anos plausíveis quando presentes — pega alucinação óbvia
    bad_years: list[str] = []
    for b in beats:
        year = b.get("year")
        if not year:
            continue
        found = re.findall(r"\b(19|20)\d{2}\b", str(year))
        if found:
            for prefix in found:
                full = re.search(rf"\b{prefix}\d{{2}}\b", str(year))
                if full and not (1950 <= int(full.group()) <= 2030):
                    bad_years.append(str(year))
    results.append(
        MetricResult(
            "years_plausible",
            float(len(bad_years)),
            not bad_years,
            f"implausíveis: {bad_years}" if bad_years else "ok",
        )
    )

    # Final olha pra frente, não resume
    summary_openers = ["in summary", "in conclusion", "this paper", "em resumo"]
    ending_lower = ending.lower()
    looks_forward = _words(ending) >= 30 and not any(
        ending_lower.startswith(s) for s in summary_openers
    )
    results.append(
        MetricResult(
            "ending_forward_looking",
            1.0 if looks_forward else 0.0,
            looks_forward,
            f"{_words(ending)} palavras" if looks_forward else "resume em vez de projetar",
        )
    )

    return results


MODE_EVALUATORS = {
    "math": eval_math,
    "analogy": eval_analogy_mode,
    "story": eval_story,
    "diagram": eval_diagram,
    "code": eval_code,
}