from __future__ import annotations

import json
import sys
from pathlib import Path

EVALS_DIR = Path(__file__).resolve().parent
RESULTS_DIR = EVALS_DIR / "results"
BASELINE_PATH = EVALS_DIR / "golden" / "baseline.json"

# Tolerância: quanto pode cair sem falhar
TOLERANCE = {
    "pass_rate": 0.05,
    "faithfulness": 0.05,
    "analogy_quality": 0.3,
    "heading_quality": 0.3,
    "judge_mean": 0.3,
}

# Pisos absolutos: abaixo disso falha independente do baseline
FLOORS = {
    "pass_rate": 0.70,
    "faithfulness": 0.80,
    "analogy_quality": 3.0,
    "heading_quality": 3.0,
    "judge_mean": 3.0,
}


def load_json(path: Path) -> dict | None:
    if not path.exists():
        return None
    with open(path) as f:
        return json.load(f)


def _load_latest(kind: str, prompt_version: str) -> dict | None:
    if kind == "sections":
        return load_json(RESULTS_DIR / f"latest-{prompt_version}.json")
    return load_json(RESULTS_DIR / f"modes-latest-{prompt_version}.json")


def _baseline_path(kind: str) -> Path:
    if kind == "sections":
        return EVALS_DIR / "golden" / "baseline.json"
    return EVALS_DIR / "golden" / "baseline-modes.json"


def check_one(kind: str, prompt_version: str) -> tuple[list[str], list[str]]:
    current = _load_latest(kind, prompt_version)
    if current is None:
        return ([f"{kind}: nenhum resultado — rode o runner primeiro"], [])

    baseline = load_json(_baseline_path(kind))
    failures: list[str] = []
    warnings: list[str] = []

    print(f"\n{'=' * 72}")
    print(f"  {kind.upper()} · prompt_version={prompt_version}")
    print("=" * 72)

    for name, metrics in sorted(current["summary"].items()):
        print(f"\n[{name}]")

        for metric_name, floor in FLOORS.items():
            value = metrics.get(metric_name)
            if value is None:
                continue

            status = "ok"
            if value < floor:
                failures.append(
                    f"{kind}.{name}.{metric_name} = {value} abaixo do piso {floor}"
                )
                status = "FAIL"

            delta_str = ""
            if baseline:
                base = baseline.get("summary", {}).get(name, {}).get(metric_name)
                if base is not None:
                    delta = value - base
                    delta_str = f"  (base {base}, Δ {delta:+.3f})"
                    tol = TOLERANCE.get(metric_name, 0.05)
                    if delta < -tol:
                        failures.append(
                            f"{kind}.{name}.{metric_name} caiu {abs(delta):.3f} "
                            f"(de {base} para {value})"
                        )
                        status = "REGRESSION"
                    elif delta > tol:
                        warnings.append(f"{kind}.{name}.{metric_name} +{delta:.3f}")

            print(f"  {metric_name:18} {value:>8}  [{status}]{delta_str}")

        # Mostra as checagens que mais falham — diagnóstico, não gate
        if metrics.get("top_failures"):
            for check_name, count in metrics["top_failures"].items():
                print(f"    ✗ {check_name} × {count}")

    return failures, warnings


def check(prompt_version: str = "v1", kinds: list[str] | None = None) -> int:
    kinds = kinds or ["sections", "modes"]

    all_failures: list[str] = []
    all_warnings: list[str] = []

    for kind in kinds:
        f, w = check_one(kind, prompt_version)
        all_failures.extend(f)
        all_warnings.extend(w)

    print(f"\n{'=' * 72}")

    if all_warnings:
        print("\nMELHORIAS:")
        for w in all_warnings:
            print(f"  + {w}")

    if all_failures:
        print("\nFALHAS:")
        for f in all_failures:
            print(f"  - {f}")
        print(f"\n{len(all_failures)} falha(s). Gate BLOQUEADO.\n")
        return 1

    print("\nGate PASSOU.\n")
    return 0


def promote(prompt_version: str = "v1", kinds: list[str] | None = None) -> int:
    kinds = kinds or ["sections", "modes"]

    for kind in kinds:
        current = _load_latest(kind, prompt_version)
        if current is None:
            print(f"{kind}: nada para promover")
            continue

        path = _baseline_path(kind)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(current, f, indent=2)
        print(f"{kind}: baseline atualizado → {path.name}")
        print(json.dumps(current["summary"], indent=2))

    return 0


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--prompt-version", default="v1")
    parser.add_argument("--promote", action="store_true")
    parser.add_argument(
        "--kinds",
        default="sections,modes",
        help="Quais avaliar: sections, modes, ou ambos",
    )
    args = parser.parse_args()

    kinds = [k.strip() for k in args.kinds.split(",") if k.strip()]

    if args.promote:
        sys.exit(promote(args.prompt_version, kinds))
    sys.exit(check(args.prompt_version, kinds))