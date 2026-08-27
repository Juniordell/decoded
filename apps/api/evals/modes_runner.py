from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import structlog  # noqa: E402
from sqlalchemy import select  # noqa: E402
from sqlalchemy.orm import selectinload  # noqa: E402

from decoded.config import settings  # noqa: E402
from decoded.db.base import async_session_factory  # noqa: E402
from decoded.db.models import ModeStatus, Paper  # noqa: E402
from decoded.db.repositories.decoded_contents import DecodedContentsRepository  # noqa: E402
from decoded.db.repositories.explanation_modes import ExplanationModesRepository  # noqa: E402
from decoded.decoding.pipeline import _flatten_deep_dive  # noqa: E402
from decoded.decoding.prompts import VERSION as DECODE_VERSION  # noqa: E402
from decoded.logging import configure_logging  # noqa: E402
from decoded.observability.experiments import experiment_run  # noqa: E402

from metrics.judge import Judge  # noqa: E402
from metrics.modes import MODE_EVALUATORS  # noqa: E402

logger = structlog.get_logger()

EVALS_DIR = Path(__file__).resolve().parent
GOLDEN_PATH = EVALS_DIR / "golden" / "papers.json"
RESULTS_DIR = EVALS_DIR / "results"


def load_golden() -> list[dict]:
    with open(GOLDEN_PATH, encoding="utf-8") as f:
        return json.load(f)["papers"]


async def evaluate_paper_modes(
    paper: Paper,
    modes: dict,
    deep_dive_text: str,
    judge: Judge | None,
) -> dict:
    log = logger.bind(arxiv_id=paper.arxiv_id)
    out: dict = {
        "arxiv_id": paper.arxiv_id,
        "title": paper.title[:80],
        "modes": {},
    }

    for mode_name, row in modes.items():
        if row.status != ModeStatus.READY or not row.content:
            out["modes"][mode_name] = {"status": row.status.value, "skipped": True}
            continue

        entry: dict = {
            "status": "ready",
            "model": row.model,
            "cost_usd": row.cost_usd,
            "deterministic": [],
            "llm": {},
        }

        evaluator = MODE_EVALUATORS.get(mode_name)
        if evaluator:
            for m in evaluator(row.content):
                entry["deterministic"].append(
                    {
                        "name": m.name,
                        "value": m.value,
                        "passed": m.passed,
                        "detail": m.detail,
                    }
                )

        if judge is not None:
            try:
                if mode_name == "code" and deep_dive_text:
                    verdict = await judge.code_fidelity(
                        method_description=deep_dive_text,
                        code=row.content.get("code", ""),
                    )
                    entry["llm"]["code_fidelity"] = verdict.model_dump()

                elif mode_name == "story" and deep_dive_text:
                    beats = row.content.get("beats", []) or []
                    story_text = "\n\n".join(
                        f"{b.get('year') or ''} {b.get('heading', '')}\n{b.get('body', '')}"
                        for b in beats
                    )
                    story_text += f"\n\n{row.content.get('where_it_leaves_us', '')}"
                    verdict = await judge.story_grounding(
                        source_summary=deep_dive_text,
                        story_text=story_text,
                    )
                    entry["llm"]["story_grounding"] = verdict.model_dump()

            except Exception as e:
                log.warning("modes_eval.judge_failed", mode=mode_name, error=str(e))
                entry["llm"]["error"] = str(e)

        out["modes"][mode_name] = entry
        log.info("modes_eval.mode_done", mode=mode_name)

    return out


def aggregate(results: list[dict]) -> dict:
    by_mode: dict[str, dict] = {}

    for paper in results:
        for mode_name, entry in paper["modes"].items():
            agg = by_mode.setdefault(
                mode_name,
                {
                    "papers": 0,
                    "skipped": 0,
                    "checks_total": 0,
                    "checks_passed": 0,
                    "judge_scores": [],
                    "failing_checks": {},
                },
            )

            if entry.get("skipped"):
                agg["skipped"] += 1
                continue

            agg["papers"] += 1

            for m in entry["deterministic"]:
                agg["checks_total"] += 1
                if m["passed"]:
                    agg["checks_passed"] += 1
                else:
                    agg["failing_checks"][m["name"]] = (
                        agg["failing_checks"].get(m["name"], 0) + 1
                    )

            llm = entry.get("llm", {})
            for key in ("code_fidelity", "story_grounding"):
                if key in llm and isinstance(llm[key].get("score"), int):
                    agg["judge_scores"].append(llm[key]["score"])

    summary: dict = {}
    for mode_name, agg in by_mode.items():
        e = {
            "papers": agg["papers"],
            "skipped": agg["skipped"],
            "pass_rate": round(agg["checks_passed"] / agg["checks_total"], 3)
            if agg["checks_total"]
            else None,
            "checks": f"{agg['checks_passed']}/{agg['checks_total']}",
        }
        if agg["judge_scores"]:
            e["judge_mean"] = round(
                sum(agg["judge_scores"]) / len(agg["judge_scores"]), 2
            )
        if agg["failing_checks"]:
            e["top_failures"] = dict(
                sorted(agg["failing_checks"].items(), key=lambda x: -x[1])[:3]
            )
        summary[mode_name] = e

    return summary


async def run(prompt_version: str, run_llm: bool, run_name: str | None) -> dict:
    configure_logging("INFO")

    golden = load_golden()
    arxiv_ids = [p["arxiv_id"] for p in golden]
    logger.info("modes_eval.start", papers=len(arxiv_ids), llm=run_llm)

    judge = None
    if run_llm:
        if not settings.anthropic_api_key:
            logger.warning("modes_eval.no_key", hint="só métricas determinísticas")
            run_llm = False
        else:
            judge = Judge(api_key=settings.anthropic_api_key)

    results: list[dict] = []

    async with async_session_factory() as session:
        stmt = (
            select(Paper)
            .options(selectinload(Paper.parsed_content))
            .where(Paper.arxiv_id.in_(arxiv_ids))
        )
        papers = list((await session.execute(stmt)).scalars().all())

        modes_repo = ExplanationModesRepository(session)
        decoded_repo = DecodedContentsRepository(session)

        for paper in papers:
            modes = await modes_repo.list_for_paper(paper.id, prompt_version)
            if not modes:
                logger.warning("modes_eval.no_modes", arxiv_id=paper.arxiv_id)
                continue

            sections = await decoded_repo.get_all_sections(
                paper_id=paper.id, prompt_version=DECODE_VERSION
            )
            dd_row = sections.get("deep_dive")
            deep_dive_text = _flatten_deep_dive(dd_row.content) if dd_row else ""

            results.append(
                await evaluate_paper_modes(paper, modes, deep_dive_text, judge)
            )

    if judge:
        await judge.close()

    summary = aggregate(results)

    run_data = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "prompt_version": prompt_version,
        "llm_metrics": run_llm,
        "papers_evaluated": len(results),
        "summary": summary,
        "results": results,
    }

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    out_path = RESULTS_DIR / f"modes-{prompt_version}-{stamp}.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(run_data, f, indent=2)

    with open(RESULTS_DIR / f"modes-latest-{prompt_version}.json", "w", encoding="utf-8") as f:
        json.dump(run_data, f, indent=2)

    # MLflow
    name = run_name or f"modes-{prompt_version}-{datetime.now(timezone.utc):%m%d-%H%M}"
    with experiment_run(
        experiment="evals",
        run_name=name,
        params={
            "prompt_version": prompt_version,
            "llm_metrics": run_llm,
            "papers": len(results),
        },
        tags={"kind": "mode_eval"},
    ) as mlrun:
        for mode_name, metrics in summary.items():
            for key, value in metrics.items():
                if isinstance(value, (int, float)):
                    mlrun.log_metric(f"{mode_name}.{key}", float(value))

        rates = [
            m["pass_rate"]
            for m in summary.values()
            if isinstance(m.get("pass_rate"), (int, float))
        ]
        if rates:
            mlrun.log_metric("modes.overall_pass_rate", sum(rates) / len(rates))

        mlrun.log_artifact_dict("summary", summary)
        mlrun.log_artifact(out_path, subdir="raw")

    logger.info("modes_eval.done", output=str(out_path))
    print("\n" + "=" * 72)
    for mode_name, m in sorted(summary.items()):
        line = f"  {mode_name:10} pass {m['pass_rate']} ({m['checks']})"
        if "judge_mean" in m:
            line += f"  judge {m['judge_mean']}"
        if m["skipped"]:
            line += f"  [{m['skipped']} skipped]"
        print(line)
        if m.get("top_failures"):
            for check, count in m["top_failures"].items():
                print(f"             ✗ {check} × {count}")
    print("=" * 72 + "\n")

    return run_data


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--prompt-version", default="v1")
    parser.add_argument("--no-llm", action="store_true")
    parser.add_argument("--run-name", default=None)
    args = parser.parse_args()

    asyncio.run(run(args.prompt_version, not args.no_llm, args.run_name))