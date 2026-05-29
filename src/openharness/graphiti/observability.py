"""Observability helpers for Graphiti pipelines."""

from __future__ import annotations

import json
import os
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator


def env_value(name: str, default: str = "") -> str:
    """Read an env var and strip inline ``#`` comments (common in ``.env`` files)."""
    raw = os.environ.get(name, default)
    if not raw:
        return default
    return raw.split("#", 1)[0].strip() or default


def mlflow_tracking_uri() -> str:
    return env_value("MLFLOW_TRACKING_URI")


def mlflow_enabled() -> bool:
    """Whether MLflow logging is enabled."""
    return os.environ.get("GRAPHITI_MLFLOW_ENABLED", "1").lower() not in {"0", "false", "no"}


@contextmanager
def start_graphiti_run(
    *,
    run_name: str,
    tags: dict[str, str] | None = None,
) -> Iterator[object | None]:
    """Start an MLflow run if available; yield None otherwise."""
    if not mlflow_enabled():
        yield None
        return

    try:
        import mlflow
    except Exception:
        yield None
        return

    experiment = env_value("GRAPHITI_MLFLOW_EXPERIMENT", "graphiti")
    tracking_uri = mlflow_tracking_uri()

    try:
        if tracking_uri:
            mlflow.set_tracking_uri(tracking_uri)
        mlflow.set_experiment(experiment)
        with mlflow.start_run(run_name=run_name) as run:
            if tags:
                mlflow.set_tags(tags)
            yield run
    except Exception:
        # Observability must never break the main pipeline.
        yield None


def log_params(run: object | None, params: dict[str, object]) -> None:
    if run is None:
        return
    import mlflow

    safe_params = {k: str(v) for k, v in params.items() if v is not None}
    if safe_params:
        mlflow.log_params(safe_params)


def log_metrics(run: object | None, metrics: dict[str, int | float]) -> None:
    if run is None:
        return
    import mlflow

    if metrics:
        mlflow.log_metrics(metrics)


def log_artifacts(run: object | None, paths: list[Path], artifact_path: str = "graphiti") -> None:
    if run is None:
        return
    import mlflow

    for p in paths:
        if p.exists():
            mlflow.log_artifact(str(p), artifact_path=artifact_path)


def usage_from_completion(usage: object | None) -> dict[str, int]:
    """Normalize OpenAI-style usage objects to token metrics."""
    if usage is None:
        return {}
    prompt = getattr(usage, "prompt_tokens", None) or getattr(usage, "input_tokens", None)
    completion = getattr(usage, "completion_tokens", None) or getattr(usage, "output_tokens", None)
    total = getattr(usage, "total_tokens", None)
    metrics: dict[str, int] = {}
    if prompt is not None:
        metrics["llm_prompt_tokens"] = int(prompt)
    if completion is not None:
        metrics["llm_completion_tokens"] = int(completion)
    if total is not None:
        metrics["llm_total_tokens"] = int(total)
    elif metrics:
        metrics["llm_total_tokens"] = metrics.get("llm_prompt_tokens", 0) + metrics.get(
            "llm_completion_tokens", 0
        )
    return metrics


def log_llm_trace(
    *,
    name: str,
    model: str,
    messages: list[dict[str, Any]],
    response_content: str,
    usage: object | None = None,
) -> None:
    """Emit a GenAI trace span (Observability / Evaluation run traces UI)."""
    if not mlflow_enabled():
        return
    try:
        import mlflow
    except Exception:
        return
    if mlflow.active_run() is None:
        return

    metrics = usage_from_completion(usage)
    logged_messages = [{**m, "content": str(m.get("content", ""))} for m in messages]
    try:
        with mlflow.start_span(name=name, span_type="CHAT_MODEL") as span:
            span.set_inputs({"model": model, "messages": logged_messages})
            span.set_outputs(
                {
                    "choices": [
                        {
                            "message": {
                                "role": "assistant",
                                "content": response_content,
                            }
                        }
                    ]
                }
            )
            if metrics:
                span.set_attribute(
                    "mlflow.chat.tokenUsage",
                    {
                        "input_tokens": metrics.get("llm_prompt_tokens", 0),
                        "output_tokens": metrics.get("llm_completion_tokens", 0),
                        "total_tokens": metrics.get("llm_total_tokens", 0),
                    },
                )
    except Exception:
        pass


def log_llm_call(
    run: object | None,
    *,
    name: str,
    model: str,
    messages: list[dict[str, Any]],
    response_content: str,
    usage: object | None = None,
) -> None:
    """Log one chat completion: tokens as metrics, I/O as a JSON artifact."""
    if not mlflow_enabled():
        return
    try:
        import mlflow
    except Exception:
        return

    active = run if run is not None else mlflow.active_run()
    if active is None:
        return

    metrics = usage_from_completion(usage)
    if metrics:
        mlflow.log_metrics({f"{name}/{k}": v for k, v in metrics.items()})

    payload = {
        "name": name,
        "model": model,
        "messages": [{**m, "content": str(m.get("content", ""))} for m in messages],
        "response": response_content,
        "usage": metrics,
    }
    temp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            suffix=".json",
            delete=False,
            encoding="utf-8",
        ) as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            temp_path = Path(handle.name)
        mlflow.log_artifact(str(temp_path), artifact_path=f"llm_calls/{name}")
    except Exception:
        pass
    finally:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)

    log_llm_trace(
        name=name,
        model=model,
        messages=messages,
        response_content=response_content,
        usage=usage,
    )
