from __future__ import annotations

import asyncio
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import structlog  # noqa: E402
from sqlalchemy import select  # noqa: E402
from sqlalchemy.orm import selectinload  # noqa: E402

from decoded.config import settings  # noqa: E402
from decoded.db.base import async_session_factory  # noqa: E402
from decoded.db.models import Paper  # noqa: E402
from decoded.db.repositories.decoded_contents import DecodedContentsRepository  # noqa: E402
from decoded.logging import configure_logging  # noqa: E402
from decoded.observability.experiments import experiment_run  # noqa: E402

from metrics.deterministic import EVALUATORS  # noqa: E402
from metrics.judge import Judge  # noqa: E402

logger = structlog.get_logger()

EVALS_DIR = Path(__file__).resolve().parent
GOLDEN_PATH = EVALS_DIR / "golden" / "papers.json"
RESULTS_DIR = EVALS_DIR / "results"


def load_golden() -> list[dict]:
    with open(GOLDEN_PATH) as f:
        data = json.load(f)
    return data["papers"]


async def evaluate_paper(
    paper: Paper,
    sections: dict,
    judge: Judge | None,
    run_llm_metrics: bool,
) -> dict:
    """Avalia todas as seções decodificadas de um paper."""
    log = logger.bind(arxiv_id=paper.arxiv_id)
    paper_result: dict = {
        "arxiv_id": paper.arxiv_id,
        "title": paper.title[:100],
        "sections": {},
    }

    source_text = ""
    if paper.parsed_content and paper.parsed_content.markdown:
        source_text = paper.parsed_content.markdown

    for section_name, row in sections.items():
        content = row.content
        section_result: dict = {
            "model": row.model,
            "prompt_version": row.prompt_version,
            "cost_usd": row.cost_usd,
            "deterministic": [],
            "llm": {},
        }

        # --- Métricas determinísticas ---
        evaluator = EVALUATORS.get(section_name)
        if evaluator:
            for m in evaluator(content):
                section_result["deterministic"].append(
                    {
                        "name": m.name,
                        "value": m.value,
                        "passed": m.passed,
                        "detail": m.detail,
                    }
                )

        # --- Métricas com LLM ---
        if run_llm_metrics and judge is not None:
            try:
                if section_name == "deep_dive" and source_text:
                    flat = " ".join(
                        (content.get(k) or {}).get("body", "")
                        for k in ["setup", "idea", "method", "results", "implications"]
                    )
                    faith = await judge.faithfulness(source_text, flat)
                    section_result["llm"]["faithfulness"] = faith.model_dump()

                    headings = [
                        (content.get(k) or {}).get("heading", "")
                        for k in ["setup", "idea", "method", "results", "implications"]
                    ]
                    hq = await judge.heading_quality([h for h in headings if h])
                    section_result["llm"]["heading_quality"] = hq.model_dump()

                elif section_name == "sixty_second" and source_text:
                    flat = " ".join(
                        content.get(k, "") for k in ["problem", "approach", "result"]
                    )
                    faith = await judge.faithfulness(source_text, flat)
                    section_result["llm"]["faithfulness"] = faith.model_dump()

                elif section_name == "analogies":
                    scores = []
                    for item in content.get("items", []):
                        aq = await judge.analogy_quality(
                            item.get("concept", ""), item.get("analogy", "")
                        )
                        scores.append(aq.model_dump())
                    section_result["llm"]["analogy_quality"] = scores
                    if scores:
                        section_result["llm"]["analogy_mean_score"] = sum(
                            s["score"] for s in scores
                        ) / len(scores)

            except Exception as e:
                log.warning("eval.llm_metric_failed", section=section_name, error=str(e))
                section_result["llm"]["error"] = str(e)

        paper_result["sections"][section_name] = section_result
        log.info("eval.section_done", section=section_name)

    return paper_result


async def run_evals(
    prompt_version: str = "v1",
    run_llm_metrics: bool = True,
    run_name: str | None = None,
) -> dict:
    configure_logging("INFO")
    golden = load_golden()
    arxiv_ids = [p["arxiv_id"] for p in golden]

    logger.info("eval.start", papers=len(arxiv_ids), llm_metrics=run_llm_metrics)

    judge = None
    if run_llm_metrics:
        if not settings.anthropic_api_key:
            logger.warning("eval.no_api_key", hint="rodando só métricas determinísticas")
            run_llm_metrics = False
        else:
            judge = Judge(api_key=settings.anthropic_api_key)

    results = []

    async with async_session_factory() as session:
        stmt = (
            select(Paper)
            .options(selectinload(Paper.parsed_content))
            .where(Paper.arxiv_id.in_(arxiv_ids))
        )
        db_result = await session.execute(stmt)
        papers = list(db_result.scalars().all())

        repo = DecodedContentsRepository(session)

        for paper in papers:
            sections = await repo.get_all_sections(
                paper_id=paper.id, prompt_version=prompt_version
            )
            if not sections:
                logger.warning("eval.no_decoded_content", arxiv_id=paper.arxiv_id)
                continue

            paper_result = await evaluate_paper(paper, sections, judge, run_llm_metrics)
            results.append(paper_result)

    if judge:
        await judge.close()

    summary = aggregate(results)

    run = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "prompt_version": prompt_version,
        "llm_metrics_enabled": run_llm_metrics,
        "papers_evaluated": len(results),
        "summary": summary,
        "results": results,
    }

    # --- Persistência local (mantida) ---
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    out_path = RESULTS_DIR / f"eval-{prompt_version}-{stamp}.json"
    with open(out_path, "w") as f:
        json.dump(run, f, indent=2)

    with open(RESULTS_DIR / f"latest-{prompt_version}.json", "w") as f:
        json.dump(run, f, indent=2)

    # --- MLflow ---
    _log_to_mlflow(run, summary, prompt_version, run_llm_metrics, run_name, out_path)

    logger.info("eval.done", output=str(out_path), **summary)
    return run


def _log_to_mlflow(
    run: dict,
    summary: dict,
    prompt_version: str,
    llm_metrics: bool,
    run_name: str | None,
    results_path: Path,
) -> None:
    """Registra o resultado do eval como um run do MLflow."""
    name = run_name or f"eval-{prompt_version}-{datetime.now(timezone.utc):%m%d-%H%M}"

    with experiment_run(
        experiment="evals",
        run_name=name,
        params={
            "prompt_version": prompt_version,
            "llm_metrics": llm_metrics,
            "papers": run["papers_evaluated"],
            "decoder_fast": settings.decoder_model_fast,
            "decoder_deep": settings.decoder_model_deep,
        },
        tags={"kind": "section_eval"},
    ) as mlrun:
        # Métricas achatadas: secao.metrica
        for section, metrics in summary.items():
            for key, value in metrics.items():
                if isinstance(value, (int, float)):
                    mlrun.log_metric(f"{section}.{key}", float(value))

        # Agregado geral — o número que você olha primeiro
        pass_rates = [
            m["pass_rate"]
            for m in summary.values()
            if isinstance(m.get("pass_rate"), (int, float))
        ]
        if pass_rates:
            mlrun.log_metric("overall.pass_rate", sum(pass_rates) / len(pass_rates))

        faithfulness = [
            m["faithfulness"]
            for m in summary.values()
            if isinstance(m.get("faithfulness"), (int, float))
        ]
        if faithfulness:
            mlrun.log_metric(
                "overall.faithfulness", sum(faithfulness) / len(faithfulness)
            )

        mlrun.log_artifact_dict("summary", summary)
        mlrun.log_artifact(results_path, subdir="raw")


def aggregate(results: list[dict]) -> dict:
    """Agrega métricas em números únicos por seção."""
    by_section: dict[str, dict] = {}

    for paper in results:
        for section_name, section in paper["sections"].items():
            agg = by_section.setdefault(
                section_name,
                {"papers": 0, "checks_total": 0, "checks_passed": 0, "faithfulness": [], "analogy_scores": [], "heading_scores": []},
            )
            agg["papers"] += 1

            for m in section["deterministic"]:
                agg["checks_total"] += 1
                if m["passed"]:
                    agg["checks_passed"] += 1

            llm = section.get("llm", {})
            if "faithfulness" in llm:
                agg["faithfulness"].append(llm["faithfulness"]["score"])
            if "analogy_mean_score" in llm:
                agg["analogy_scores"].append(llm["analogy_mean_score"])
            if "heading_quality" in llm:
                agg["heading_scores"].append(llm["heading_quality"]["score"])

    summary: dict = {}
    for section_name, agg in by_section.items():
        entry = {
            "papers": agg["papers"],
            "pass_rate": round(agg["checks_passed"] / agg["checks_total"], 3)
            if agg["checks_total"]
            else None,
            "checks": f"{agg['checks_passed']}/{agg['checks_total']}",
        }
        if agg["faithfulness"]:
            entry["faithfulness"] = round(sum(agg["faithfulness"]) / len(agg["faithfulness"]), 3)
        if agg["analogy_scores"]:
            entry["analogy_quality"] = round(sum(agg["analogy_scores"]) / len(agg["analogy_scores"]), 2)
        if agg["heading_scores"]:
            entry["heading_quality"] = round(sum(agg["heading_scores"]) / len(agg["heading_scores"]), 2)
        summary[section_name] = entry

    return summary


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--prompt-version", default="v1")
    parser.add_argument(
        "--no-llm",
        action="store_true",
        help="Roda só métricas determinísticas (grátis)",
    )
    parser.add_argument("--run-name", default=None, help="Nome do run no MLflow")
    args = parser.parse_args()

    asyncio.run(
        run_evals(
            prompt_version=args.prompt_version,
            run_llm_metrics=not args.no_llm,
            run_name=args.run_name,
        )
    )