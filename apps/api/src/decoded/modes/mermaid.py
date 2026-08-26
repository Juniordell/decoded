"""Validação leve de sintaxe Mermaid.

Não é um parser completo — é uma checagem dos erros que o LLM comete
na prática: parênteses em labels, nós órfãos, cabeçalho faltando.
"""

from __future__ import annotations

import re

VALID_HEADERS = (
    "flowchart",
    "graph",
    "sequenceDiagram",
    "stateDiagram",
    "stateDiagram-v2",
    "classDiagram",
    "erDiagram",
)

# Caracteres que quebram o parser dentro de labels [..] {..} (..)
PROBLEM_CHARS = re.compile(r'[(){}"\':]')


class MermaidValidationError(Exception):
    pass


def validate(source: str) -> list[str]:
    """Retorna lista de problemas. Lista vazia significa provavelmente válido."""
    problems: list[str] = []
    lines = [ln.rstrip() for ln in source.strip().split("\n") if ln.strip()]

    if not lines:
        return ["diagrama vazio"]

    header = lines[0].strip()
    if not header.startswith(VALID_HEADERS):
        problems.append(f"cabeçalho inválido: {header[:40]!r}")

    # Labels com caracteres problemáticos
    label_pattern = re.compile(r"\[([^\]]*)\]")
    for i, line in enumerate(lines[1:], start=2):
        for label in label_pattern.findall(line):
            if PROBLEM_CHARS.search(label):
                problems.append(
                    f"linha {i}: label contém caractere problemático: {label[:40]!r}"
                )

    # Conta nós e arestas
    edge_count = len(re.findall(r"-{1,3}[.>|]|={2,3}>", source))
    if edge_count == 0 and header.startswith(("flowchart", "graph")):
        problems.append("nenhuma aresta encontrada")

    node_ids = set(re.findall(r"\b([A-Za-z][A-Za-z0-9_]*)\s*[\[\({]", source))
    if len(node_ids) < 3 and header.startswith(("flowchart", "graph")):
        problems.append(f"apenas {len(node_ids)} nós — pouco para um diagrama")

    return problems


def sanitize(source: str) -> str:
    """
    Conserta os problemas mais comuns automaticamente.
    Remove parênteses e dois-pontos de dentro de labels.
    """
    def clean_label(match: re.Match) -> str:
        label = match.group(1)
        cleaned = PROBLEM_CHARS.sub("", label).strip()
        cleaned = re.sub(r"\s+", " ", cleaned)
        return f"[{cleaned}]"

    return re.sub(r"\[([^\]]*)\]", clean_label, source)