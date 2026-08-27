"""Compila o programa de analogia com DSPy.

Uso:
    poetry run python optimization/compile_analogy.py
    poetry run python optimization/compile_analogy.py --max-demos 6
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import dspy  # noqa: E402
import structlog  # noqa: E402

from decoded.config import settings  # noqa: E402
from decoded.logging import configure_logging  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))

from analogy_metric import analogy_metric, deterministic_score  # noqa: E402
from analogy_program import (  # noqa: E402
    COMPILED_DIR,
    AnalogyProgram,
    load_examples,
    split_examples,
)

logger = structlog.get_logger()


def evaluate(program, examples: list[dspy.Example], label: str) -> dict:
    """Roda o programa no conjunto e agrega scores."""
    scores: list[float] = []
    all_problems: list[str] = []
    latencies: list[float] = []

    for ex in examples:
        start = time.perf_counter()
        try:
            pred = program(concept=ex.concept, context=ex.context)
            latencies.append(time.perf_counter() - start)

            score = analogy_metric(ex, pred)
            scores.append(score)

            _, problems = deterministic_score(pred)
            all_problems.extend(problems)

        except Exception as e:
            logger.warning("eval.example_failed", concept=ex.concept, error=str(e))
            scores.append(0.0)

    mean = sum(scores) / len(scores) if scores else 0.0
    mean_latency = sum(latencies) / len(latencies) if latencies else 0.0

    logger.info(
        f"eval.{label}",
        mean_score=round(mean, 4),
        n=len(scores),
        mean_latency_s=round(mean_latency, 2),
        problem_count=len(all_problems),
    )

    return {
        "label": label,
        "mean_score": round(mean, 4),
        "scores": [round(s, 4) for s in scores],
        "n": len(scores),
        "mean_latency_s": round(mean_latency, 2),
        "problems": all_problems[:20],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--max-demos", type=int, default=4)
    parser.add_argument("--max-rounds", type=int, default=1)
    parser.add_argument("--model", default=None)
    args = parser.parse_args()

    configure_logging("INFO")

    if not settings.anthropic_api_key:
        logger.error("compile.failed", reason="ANTHROPIC_API_KEY não definida")
        return 1

    model = args.model or settings.dspy_generator_model

    lm = dspy.LM(
        model,
        api_key=settings.openai_api_key,
        max_tokens=2000,
    )
    dspy.configure(lm=lm)

    examples = load_examples()
    if len(examples) < 8:
        logger.error(
            "compile.failed",
            reason=f"apenas {len(examples)} exemplos, mínimo 8",
        )
        return 1

    train, val = split_examples(examples)
    logger.info("compile.start", train=len(train), val=len(val), model=model)

    # ---------- Baseline ----------
    baseline = AnalogyProgram()
    logger.info("compile.evaluating_baseline")
    baseline_result = evaluate(baseline, val, "baseline")

    # ---------- Compilação ----------
    logger.info("compile.optimizing", max_demos=args.max_demos)

    optimizer = dspy.BootstrapFewShot(
        metric=analogy_metric,
        max_bootstrapped_demos=args.max_demos,
        max_labeled_demos=args.max_demos,
        max_rounds=args.max_rounds,
    )

    start = time.perf_counter()
    compiled = optimizer.compile(AnalogyProgram(), trainset=train)
    compile_seconds = round(time.perf_counter() - start, 1)

    # optimizer = dspy.MIPROv2(
    #     metric=analogy_metric,
    #     auto="light",
    #     num_threads=4,
    # )

    # start = time.perf_counter()
    # compiled = optimizer.compile(
    #     AnalogyProgram(),
    #     trainset=train,
    #     max_bootstrapped_demos=args.max_demos,
    #     max_labeled_demos=args.max_demos,
    #     requires_permission_to_run=False,
    # )
    # compile_seconds = round(time.perf_counter() - start, 1)

    logger.info("compile.optimized", seconds=compile_seconds)

    # ---------- Avaliação ----------
    logger.info("compile.evaluating_compiled")
    compiled_result = evaluate(compiled, val, "compiled")

    # ---------- Salvar ----------
    COMPILED_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")

    program_path = COMPILED_DIR / f"analogy-{stamp}.json"
    compiled.save(str(program_path))

    latest_path = COMPILED_DIR / "analogy-latest.json"
    compiled.save(str(latest_path))

    delta = compiled_result["mean_score"] - baseline_result["mean_score"]
    pct = (delta / baseline_result["mean_score"] * 100) if baseline_result["mean_score"] else 0

    report = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "model": model,
        "train_size": len(train),
        "val_size": len(val),
        "max_demos": args.max_demos,
        "compile_seconds": compile_seconds,
        "baseline": baseline_result,
        "compiled": compiled_result,
        "delta": round(delta, 4),
        "delta_pct": round(pct, 1),
        "program_path": str(program_path),
    }

    report_path = COMPILED_DIR / f"report-{stamp}.json"
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)

    print("\n" + "=" * 62)
    print(f"  BASELINE   {baseline_result['mean_score']:.4f}")
    print(f"  COMPILED   {compiled_result['mean_score']:.4f}")
    print(f"  DELTA      {delta:+.4f}  ({pct:+.1f}%)")
    print("=" * 62)
    print(f"\n  program  {program_path}")
    print(f"  report   {report_path}\n")

    return 0


if __name__ == "__main__":
    sys.exit(main())