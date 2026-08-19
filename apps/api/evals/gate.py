from __future__ import annotations

import json
import sys
from pathlib import Path

EVALS_DIR = Path(__file__).resolve().parent
RESULTS_DIR = EVALS_DIR / "results"
BASELINE_PATH = EVALS_DIR / "golden" / "baseline.json"

# Tolerância: quanto pode cair sem falhar
TOLERANCE = {
    "pass_rate": 0.05,        # 5 pontos percentuais
    "faithfulness": 0.05,
    "analogy_quality": 0.3,   # escala 1-5
    "heading_quality": 0.3,
}

# Pisos absolutos: abaixo disso falha independente do baseline
FLOORS = {
    "pass_rate": 0.70,
    "faithfulness": 0.80,
    "analogy_quality": 3.0,
    "heading_quality": 3.0,
}


def load_json(path: Path) -> dict | None:
    if not path.exists():
        return None
    with open(path) as f:
        return json.load(f)


def check(prompt_version: str = "v1") -> int:
    current = load_json(RESULTS_DIR / f"latest-{prompt_version}.json")
    if current is None:
        print(f"ERRO: não achei resultado para {prompt_version}. Rode evals/runner.py primeiro.")
        return 1

    baseline = load_json(BASELINE_PATH)
    failures: list[str] = []
    warnings: list[str] = []

    print(f"\n{'=' * 70}")
    print(f"EVAL GATE · prompt_version={prompt_version}")
    print(f"{'=' * 70}\n")

    for section, metrics in current["summary"].items():
        print(f"[{section}]")

        for metric_name, floor in FLOORS.items():
            value = metrics.get(metric_name)
            if value is None:
                continue

            # 1. Piso absoluto
            if value < floor:
                failures.append(
                    f"{section}.{metric_name} = {value} está abaixo do piso {floor}"
                )
                status = "FAIL"
            else:
                status = "ok"

            # 2. Regressão contra baseline
            delta_str = ""
            if baseline:
                base_value = baseline.get("summary", {}).get(section, {}).get(metric_name)
                if base_value is not None:
                    delta = value - base_value
                    delta_str = f"  (baseline {base_value}, delta {delta:+.3f})"
                    tol = TOLERANCE.get(metric_name, 0.05)
                    if delta < -tol:
                        failures.append(
                            f"{section}.{metric_name} caiu {abs(delta):.3f} "
                            f"(de {base_value} para {value}, tolerância {tol})"
                        )
                        status = "REGRESSION"
                    elif delta > tol:
                        warnings.append(f"{section}.{metric_name} melhorou {delta:+.3f}")

            print(f"  {metric_name:18} {value:>8}  [{status}]{delta_str}")

        print()

    print(f"{'=' * 70}")

    if warnings:
        print("\nMELHORIAS:")
        for w in warnings:
            print(f"  + {w}")

    if failures:
        print("\nFALHAS:")
        for f in failures:
            print(f"  - {f}")
        print(f"\n{len(failures)} falha(s). Gate BLOQUEADO.\n")
        return 1

    print("\nGate PASSOU.\n")
    return 0


def promote(prompt_version: str = "v1") -> int:
    """Promove o resultado atual a baseline."""
    current = load_json(RESULTS_DIR / f"latest-{prompt_version}.json")
    if current is None:
        print("Nenhum resultado para promover.")
        return 1

    with open(BASELINE_PATH, "w") as f:
        json.dump(current, f, indent=2)

    print(f"Baseline atualizado a partir de {prompt_version}.")
    print(json.dumps(current["summary"], indent=2))
    return 0


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--prompt-version", default="v1")
    parser.add_argument(
        "--promote",
        action="store_true",
        help="Salva o resultado atual como novo baseline",
    )
    args = parser.parse_args()

    if args.promote:
        sys.exit(promote(args.prompt_version))
    sys.exit(check(args.prompt_version))