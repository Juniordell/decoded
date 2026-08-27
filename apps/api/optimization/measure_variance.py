"""Mede a variância do baseline.

Sem isso você não sabe se um delta de -3% é regressão ou ruído.
"""

from __future__ import annotations

import argparse
import statistics
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import dspy  # noqa: E402
import structlog  # noqa: E402

from decoded.config import settings  # noqa: E402
from decoded.logging import configure_logging  # noqa: E402
from decoded.observability.experiments import experiment_run  # noqa: E402

from analogy_metric import analogy_metric  # noqa: E402
from analogy_program import (  # noqa: E402
    COMPILED_DIR,
    AnalogyProgram,
    load_examples,
    split_examples,
)

logger = structlog.get_logger()


def run_once(program, val) -> float:
    scores = []
    for ex in val:
        try:
            pred = program(concept=ex.concept, context=ex.context)
            scores.append(analogy_metric(ex, pred))
        except Exception as e:
            logger.warning("variance.example_failed", error=str(e))
            scores.append(0.0)
    return sum(scores) / len(scores) if scores else 0.0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runs", type=int, default=5)
    parser.add_argument(
        "--program",
        default="baseline",
        choices=["baseline", "compiled"],
    )
    args = parser.parse_args()

    configure_logging("INFO")

    lm = dspy.LM(
        settings.dspy_generator_model,
        api_key=settings.openai_api_key,
        max_tokens=2000,
        cache=False,
    )
    dspy.configure(lm=lm)

    _, val = split_examples(load_examples())

    program = AnalogyProgram()
    if args.program == "compiled":
        program.load(str(COMPILED_DIR / "analogy-latest.json"))

    run_name = f"variance-{args.program}-{datetime.now(timezone.utc):%m%d-%H%M}"

    with experiment_run(
        experiment="dspy",
        run_name=run_name,
        params={
            "program": args.program,
            "runs": args.runs,
            "model": settings.dspy_generator_model,
            "val_size": len(val),
        },
        tags={"kind": "variance_measurement", "target": "analogy"},
    ) as mlrun:

        scores: list[float] = []
        for i in range(args.runs):
            score = run_once(program, val)
            scores.append(score)
            mlrun.log_metric("run_score", score, step=i)
            logger.info("variance.run", run=i + 1, score=round(score, 4))

        mean = statistics.mean(scores)
        stdev = statistics.stdev(scores) if len(scores) > 1 else 0.0
        spread = max(scores) - min(scores)

        mlrun.log_metric("mean", mean)
        mlrun.log_metric("stdev", stdev)
        mlrun.log_metric("spread", spread)
        mlrun.log_metric("noise_floor_2sigma", 2 * stdev)

    print("\n" + "=" * 62)
    print(f"  PROGRAM        {args.program}")
    print(f"  RUNS           {args.runs}")
    print(f"  SCORES         {[round(s, 4) for s in scores]}")
    print(f"  MEAN           {mean:.4f}")
    print(f"  STDEV          {stdev:.4f}")
    print(f"  SPREAD         {spread:.4f}")
    print(f"  NOISE FLOOR    ±{2 * stdev:.4f}  (2 sigma)")
    print("=" * 62)
    print(
        f"\n  Qualquer delta menor que {2 * stdev:.4f} é ruído, não sinal.\n"
    )

    return 0


if __name__ == "__main__":
    sys.exit(main())