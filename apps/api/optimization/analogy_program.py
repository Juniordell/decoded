from __future__ import annotations

import json
from pathlib import Path

import dspy

DATA_DIR = Path(__file__).resolve().parent / "data"
COMPILED_DIR = Path(__file__).resolve().parent / "compiled"


# ============================================================
# Assinatura — o QUE, não o COMO
# ============================================================
class GenerateAnalogy(dspy.Signature):
    """Explain a technical AI concept through a concrete everyday analogy.

    The analogy must map relationships, not just objects. It must use a
    domain the reader knows viscerally. It must name where it breaks down.
    """

    concept: str = dspy.InputField(
        desc="The technical concept to explain"
    )
    context: str = dspy.InputField(
        desc="What the paper says about this concept"
    )

    domain: str = dspy.OutputField(
        desc="The everyday domain borrowed from, one or two words"
    )
    setup: str = dspy.OutputField(
        desc="The everyday scenario described on its own terms, before any "
             "connection to the technical concept is made. 3-5 sentences."
    )
    mapping: str = dspy.OutputField(
        desc="Explicit correspondences, one per line, format "
             "'everyday thing → technical thing'. 4-5 lines."
    )
    where_it_breaks: str = dspy.OutputField(
        desc="Where the analogy stops being accurate, and what that reveals "
             "about the technical concept. 2-3 sentences."
    )


class AnalogyProgram(dspy.Module):
    """ChainOfThought porque a escolha do domínio se beneficia de raciocínio explícito."""

    def __init__(self) -> None:
        super().__init__()
        self.generate = dspy.ChainOfThought(GenerateAnalogy)

    def forward(self, concept: str, context: str) -> dspy.Prediction:
        return self.generate(concept=concept, context=context)


# ============================================================
# Dados
# ============================================================
def load_examples(path: Path | None = None) -> list[dspy.Example]:
    path = path or (DATA_DIR / "analogies.jsonl")

    examples: list[dspy.Example] = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            examples.append(
                dspy.Example(
                    concept=row["concept"],
                    context=row["context"],
                    domain=row["domain"],
                    setup=row["setup"],
                    mapping="\n".join(row["mapping"]),
                    where_it_breaks=row["where_it_breaks"],
                ).with_inputs("concept", "context")
            )

    return examples


def split_examples(
    examples: list[dspy.Example],
    train_frac: float = 0.6,
) -> tuple[list[dspy.Example], list[dspy.Example]]:
    """Divide em treino e validação. Ordem preservada para reprodutibilidade."""
    cut = int(len(examples) * train_frac)
    return examples[:cut], examples[cut:]