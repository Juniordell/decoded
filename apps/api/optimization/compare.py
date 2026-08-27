from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import dspy  # noqa: E402

from decoded.config import settings  # noqa: E402
from analogy_program import COMPILED_DIR, AnalogyProgram  # noqa: E402
from analogy_metric import deterministic_score  # noqa: E402


def show(label: str, pred) -> None:
    print(f"\n{'=' * 62}")
    print(f"  {label}")
    print("=" * 62)
    print(f"\nDOMAIN: {pred.domain}\n")
    print(f"SETUP:\n{pred.setup}\n")
    print(f"MAPPING:\n{pred.mapping}\n")
    print(f"WHERE IT BREAKS:\n{pred.where_it_breaks}\n")

    score, problems = deterministic_score(pred)
    print(f"deterministic score: {score:.3f}")
    if problems:
        for p in problems:
            print(f"  - {p}")


def main() -> None:
    concept = sys.argv[1] if len(sys.argv) > 1 else "speculative decoding"
    context = (
        sys.argv[2]
        if len(sys.argv) > 2
        else "A small draft model proposes several tokens ahead. The large model "
             "verifies all of them in a single forward pass and accepts the longest "
             "matching prefix. Rejected tokens are discarded and the process repeats."
    )

    lm = dspy.LM(
        f"anthropic/{settings.decoder_model_fast}",
        api_key=settings.anthropic_api_key,
        max_tokens=2000,
        temperature=0.7,
    )
    dspy.configure(lm=lm)

    baseline = AnalogyProgram()
    show("BASELINE", baseline(concept=concept, context=context))

    compiled = AnalogyProgram()
    compiled.load(str(COMPILED_DIR / "analogy-latest.json"))
    show("COMPILED", compiled(concept=concept, context=context))


if __name__ == "__main__":
    main()