from __future__ import annotations

import sys
import types
from typing import AsyncIterator

import pytest

from openharness.api.client import (
    ApiMessageCompleteEvent,
    ApiMessageRequest,
    ApiStreamEvent,
    ApiTextDeltaEvent,
    SupportsStreamingMessages,
)
from openharness.api.mlflow_tracing import MlflowTracingClient, wrap_api_client_if_enabled
from openharness.api.usage import UsageSnapshot
from openharness.engine.messages import ConversationMessage, TextBlock


class _StubClient:
    def __init__(self, events: list[ApiStreamEvent]) -> None:
        self._events = events

    async def stream_message(self, request: ApiMessageRequest) -> AsyncIterator[ApiStreamEvent]:
        for event in self._events:
            yield event


@pytest.mark.asyncio
async def test_wrap_logs_completed_stream(monkeypatch) -> None:
    calls: dict[str, object] = {}

    class _FakeRunCtx:
        def __enter__(self) -> object:
            return object()

        def __exit__(self, exc_type, exc, tb) -> None:
            return None

    fake_mlflow = types.SimpleNamespace(
        set_tracking_uri=lambda v: calls.setdefault("tracking_uri", v),
        set_experiment=lambda v: calls.setdefault("experiment", v),
        active_run=lambda: None,
        start_run=lambda run_name, nested=False: _FakeRunCtx(),
    )
    monkeypatch.setitem(sys.modules, "mlflow", fake_mlflow)
    monkeypatch.setenv("OPENHARNESS_MLFLOW_ENABLED", "1")
    monkeypatch.setenv("OPENHARNESS_MLFLOW_EXPERIMENT", "openharness-test")
    monkeypatch.setenv("MLFLOW_TRACKING_URI", "file:///tmp/mlruns")

    logged: list[dict[str, object]] = []

    def _fake_log_llm_call(run, **kwargs) -> None:
        logged.append(kwargs)

    monkeypatch.setattr(
        "openharness.graphiti.observability.log_llm_call",
        _fake_log_llm_call,
    )

    message = ConversationMessage(role="assistant", content=[TextBlock(text="hello back")])
    events = [
        ApiTextDeltaEvent(text="hello "),
        ApiMessageCompleteEvent(
            message=message,
            usage=UsageSnapshot(input_tokens=3, output_tokens=2),
            stop_reason="end_turn",
        ),
    ]
    wrapped = wrap_api_client_if_enabled(_StubClient(events))
    assert isinstance(wrapped, MlflowTracingClient)

    collected: list[ApiStreamEvent] = []
    async for event in wrapped.stream_message(
        ApiMessageRequest(model="test-model", messages=[ConversationMessage.from_user_text("hi")])
    ):
        collected.append(event)

    assert len(collected) == 2
    assert calls["experiment"] == "openharness-test"
    assert logged[0]["name"] == "agent_chat_turn"
    assert logged[0]["model"] == "test-model"
    assert logged[0]["response_content"] == "hello back"


def test_wrap_disabled_returns_same_client(monkeypatch) -> None:
    monkeypatch.setenv("OPENHARNESS_MLFLOW_ENABLED", "0")
    stub = _StubClient([])
    assert wrap_api_client_if_enabled(stub) is stub
