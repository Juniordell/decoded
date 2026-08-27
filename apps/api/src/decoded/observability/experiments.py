"""Registro de experimentos com MLflow.

Wrapper fino sobre o SDK. Se o MLflow não estiver instalado ou falhar,
o experimento roda igual — tracking nunca é dependência de um resultado.
"""

from __future__ import annotations

import json
import subprocess
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

import structlog

from decoded.config import settings

logger = structlog.get_logger()

_enabled: bool | None = None


def _check() -> bool:
    global _enabled
    if _enabled is not None:
        return _enabled

    try:
        import mlflow  # noqa: F401

        _enabled = True
    except ImportError:
        logger.info("experiments.disabled", reason="mlflow não instalado")
        _enabled = False

    return _enabled


def git_sha() -> str | None:
    """Commit atual, para reprodutibilidade."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except Exception:
        pass
    return None


def git_dirty() -> bool:
    """Há mudanças não commitadas? Um run sujo não é reproduzível."""
    try:
        result = subprocess.run(
            ["git", "status", "--porcelain"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        return bool(result.stdout.strip())
    except Exception:
        return False


@contextmanager
def experiment_run(
    experiment: str,
    run_name: str,
    params: dict[str, Any] | None = None,
    tags: dict[str, str] | None = None,
) -> Iterator["_Run"]:
    """
    Contexto de um run.

        with experiment_run("evals", "prompt-v2", params={"model": "haiku"}) as run:
            run.log_metric("faithfulness", 0.87)
            run.log_artifact_dict("results", data)
    """
    if not _check():
        yield _NoOpRun()
        return

    import mlflow

    try:
        mlflow.set_tracking_uri(settings.mlflow_tracking_uri)
        mlflow.set_experiment(f"{settings.mlflow_experiment_prefix}-{experiment}")

        with mlflow.start_run(run_name=run_name):
            sha = git_sha()
            base_tags = {
                "git_sha": sha or "unknown",
                "git_dirty": str(git_dirty()).lower(),
                **(tags or {}),
            }
            mlflow.set_tags(base_tags)

            if params:
                mlflow.log_params(_flatten(params))

            yield _Run(mlflow)

    except Exception as e:
        logger.warning("experiments.run_failed", error=str(e))
        yield _NoOpRun()


def _flatten(d: dict, prefix: str = "") -> dict[str, Any]:
    """MLflow não aceita params aninhados. Achata com pontos."""
    out: dict[str, Any] = {}
    for k, v in d.items():
        key = f"{prefix}{k}"
        if isinstance(v, dict):
            out.update(_flatten(v, f"{key}."))
        elif isinstance(v, (list, tuple)):
            out[key] = json.dumps(v)[:250]
        else:
            out[key] = v
    return out


class _Run:
    def __init__(self, mlflow_module: Any) -> None:
        self._mlflow = mlflow_module

    def log_metric(self, key: str, value: float, step: int | None = None) -> None:
        try:
            self._mlflow.log_metric(key, value, step=step)
        except Exception:
            pass

    def log_metrics(self, metrics: dict[str, float], step: int | None = None) -> None:
        try:
            self._mlflow.log_metrics(metrics, step=step)
        except Exception:
            pass

    def log_param(self, key: str, value: Any) -> None:
        try:
            self._mlflow.log_param(key, value)
        except Exception:
            pass

    def log_artifact(self, path: str | Path, subdir: str | None = None) -> None:
        try:
            self._mlflow.log_artifact(str(path), artifact_path=subdir)
        except Exception:
            pass

    def log_artifact_dict(self, name: str, data: dict) -> None:
        """Salva um dict como JSON anexado ao run."""
        try:
            self._mlflow.log_dict(data, f"{name}.json")
        except Exception:
            pass

    def log_text(self, name: str, text: str) -> None:
        try:
            self._mlflow.log_text(text, f"{name}.txt")
        except Exception:
            pass

    def set_tag(self, key: str, value: str) -> None:
        try:
            self._mlflow.set_tag(key, value)
        except Exception:
            pass


class _NoOpRun:
    def log_metric(self, *a, **k) -> None: ...
    def log_metrics(self, *a, **k) -> None: ...
    def log_param(self, *a, **k) -> None: ...
    def log_artifact(self, *a, **k) -> None: ...
    def log_artifact_dict(self, *a, **k) -> None: ...
    def log_text(self, *a, **k) -> None: ...
    def set_tag(self, *a, **k) -> None: ...