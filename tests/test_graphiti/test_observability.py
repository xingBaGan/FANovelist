from __future__ import annotations

import json
from pathlib import Path
import sys
import types

from openharness.graphiti.observability import (
    env_value,
    log_artifacts,
    log_llm_call,
    log_metrics,
    log_params,
    mlflow_tracking_uri,
    start_graphiti_run,
    usage_from_completion,
)


def test_env_value_strips_inline_comment(monkeypatch) -> None:
    monkeypatch.setenv("MLFLOW_TRACKING_URI", "http://localhost:5000  # comment")
    assert mlflow_tracking_uri() == "http://localhost:5000"
    assert env_value("GRAPHITI_MLFLOW_EXPERIMENT", "graphiti") == "graphiti"


class _FakeRunCtx:
    def __enter__(self) -> object:
        return object()

    def __exit__(self, exc_type, exc, tb) -> None:
        return None


def test_start_graphiti_run_and_logging(monkeypatch, tmp_path: Path) -> None:
    calls: dict[str, object] = {}

    fake_mlflow = types.SimpleNamespace(
        set_tracking_uri=lambda v: calls.setdefault("tracking_uri", v),
        set_experiment=lambda v: calls.setdefault("experiment", v),
        start_run=lambda run_name: _FakeRunCtx(),
        set_tags=lambda tags: calls.setdefault("tags", tags),
        log_params=lambda params: calls.setdefault("params", params),
        log_metrics=lambda metrics: calls.setdefault("metrics", metrics),
        log_artifact=lambda path, artifact_path=None: calls.setdefault("artifact", (path, artifact_path)),
    )

    monkeypatch.setitem(sys.modules, "mlflow", fake_mlflow)
    monkeypatch.setenv("GRAPHITI_MLFLOW_ENABLED", "1")
    monkeypatch.setenv("GRAPHITI_MLFLOW_EXPERIMENT", "graphiti-test")
    monkeypatch.setenv("MLFLOW_TRACKING_URI", "file:///tmp/mlruns")

    artifact = tmp_path / "x.txt"
    artifact.write_text("ok", encoding="utf-8")

    with start_graphiti_run(run_name="unit_test", tags={"k": "v"}) as run:
        assert run is not None
        log_params(run, {"a": 1})
        log_metrics(run, {"m": 2.0})
        log_artifacts(run, [artifact], artifact_path="g")

    assert calls["tracking_uri"] == "file:///tmp/mlruns"
    assert calls["experiment"] == "graphiti-test"
    assert calls["tags"] == {"k": "v"}
    assert calls["params"] == {"a": "1"}
    assert calls["metrics"] == {"m": 2.0}
    assert calls["artifact"] == (str(artifact), "g")


def test_start_graphiti_run_disabled(monkeypatch) -> None:
    monkeypatch.setenv("GRAPHITI_MLFLOW_ENABLED", "0")
    with start_graphiti_run(run_name="disabled") as run:
        assert run is None


def test_usage_from_completion() -> None:
    usage = types.SimpleNamespace(prompt_tokens=10, completion_tokens=5, total_tokens=15)
    assert usage_from_completion(usage) == {
        "llm_prompt_tokens": 10,
        "llm_completion_tokens": 5,
        "llm_total_tokens": 15,
    }


class _FakeSpan:
    def set_inputs(self, payload: object) -> None:
        self.inputs = payload

    def set_outputs(self, payload: object) -> None:
        self.outputs = payload

    def set_attribute(self, key: str, value: object) -> None:
        self.attributes = {key: value}


class _FakeSpanCtx:
    def __enter__(self) -> _FakeSpan:
        return _FakeSpan()

    def __exit__(self, exc_type, exc, tb) -> None:
        return None


def test_log_llm_call_records_metrics_and_artifact(monkeypatch, tmp_path: Path) -> None:
    calls: dict[str, object] = {}
    fake_run = object()

    def _start_span(name: str, span_type: str = "UNKNOWN") -> _FakeSpanCtx:
        calls["span"] = (name, span_type)
        return _FakeSpanCtx()

    fake_mlflow = types.SimpleNamespace(
        active_run=lambda: fake_run,
        log_metrics=lambda metrics: calls.setdefault("metrics", metrics),
        log_artifact=lambda path, artifact_path=None: calls.setdefault(
            "artifact", (path, artifact_path)
        ),
        start_span=_start_span,
    )
    monkeypatch.setitem(sys.modules, "mlflow", fake_mlflow)
    monkeypatch.setenv("GRAPHITI_MLFLOW_ENABLED", "1")

    log_llm_call(
        fake_run,
        name="unit_llm",
        model="test-model",
        messages=[{"role": "user", "content": "hello"}],
        response_content="world",
        usage=types.SimpleNamespace(prompt_tokens=3, completion_tokens=2, total_tokens=5),
    )

    assert calls["metrics"] == {
        "unit_llm/llm_prompt_tokens": 3,
        "unit_llm/llm_completion_tokens": 2,
        "unit_llm/llm_total_tokens": 5,
    }
    artifact_path, artifact_dir = calls["artifact"]
    assert artifact_dir == "llm_calls/unit_llm"
    payload = json.loads(Path(artifact_path).read_text(encoding="utf-8"))
    assert payload["model"] == "test-model"
    assert payload["response"] == "world"
    assert calls["span"] == ("unit_llm", "CHAT_MODEL")
