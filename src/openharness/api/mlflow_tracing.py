"""MLflow tracing wrapper for the main agent ``stream_message`` path."""

from __future__ import annotations

import os
from contextlib import contextmanager
from dataclasses import dataclass
from typing import AsyncIterator, Iterator

from openharness.api.client import (
    ApiMessageCompleteEvent,
    ApiMessageRequest,
    ApiStreamEvent,
    ApiTextDeltaEvent,
    SupportsStreamingMessages,
)
from openharness.engine.messages import ConversationMessage, ImageBlock, TextBlock
from openharness.graphiti.observability import env_value, log_llm_call, mlflow_tracking_uri


def agent_mlflow_enabled() -> bool:
    """Whether MLflow logging is enabled for OpenHarness agent calls."""
    explicit = os.environ.get("OPENHARNESS_MLFLOW_ENABLED")
    if explicit is not None:
        return explicit.lower() not in {"0", "false", "no"}
    return os.environ.get("GRAPHITI_MLFLOW_ENABLED", "1").lower() not in {"0", "false", "no"}


def mlflow_agent_active() -> bool:
    """True when agent tracing is enabled and the mlflow package is importable."""
    if not agent_mlflow_enabled():
        return False
    try:
        import mlflow  # noqa: F401
    except Exception:
        return False
    return True


def describe_mlflow_agent_status() -> str:
    """Human-readable MLflow status for UI and /doctor."""
    if not agent_mlflow_enabled():
        return "off"
    if not mlflow_agent_active():
        return "on (mlflow not installed)"
    experiment = env_value("OPENHARNESS_MLFLOW_EXPERIMENT", "openharness")
    uri = mlflow_tracking_uri()
    if uri:
        return f"on · {experiment} → {uri}"
    return f"on · {experiment}"


def wrap_api_client_if_enabled(client: SupportsStreamingMessages) -> SupportsStreamingMessages:
    """Return *client* wrapped for MLflow when agent tracing is enabled."""
    if not agent_mlflow_enabled():
        return client
    return MlflowTracingClient(client)


@dataclass(frozen=True)
class MlflowTracingClient:
    """Delegates streaming to *inner* and logs each completed model call to MLflow."""

    inner: SupportsStreamingMessages

    async def stream_message(self, request: ApiMessageRequest) -> AsyncIterator[ApiStreamEvent]:
        collected: list[str] = []
        final: ApiMessageCompleteEvent | None = None
        try:
            async for event in self.inner.stream_message(request):
                if isinstance(event, ApiTextDeltaEvent):
                    collected.append(event.text)
                elif isinstance(event, ApiMessageCompleteEvent):
                    final = event
                yield event
        finally:
            if final is None and not collected:
                return
            response = (final.message.text if final is not None else "") or "".join(collected)
            usage = final.usage if final is not None else None
            _record_agent_llm_call(
                name=_call_name(request),
                model=request.model,
                messages=_messages_for_log(request),
                response_content=response,
                usage=usage,
            )


@contextmanager
def _agent_mlflow_run(run_name: str) -> Iterator[object | None]:
    if not agent_mlflow_enabled():
        yield None
        return
    try:
        import mlflow
    except Exception:
        yield None
        return

    experiment = env_value("OPENHARNESS_MLFLOW_EXPERIMENT", "openharness")
    tracking_uri = mlflow_tracking_uri()
    try:
        if tracking_uri:
            mlflow.set_tracking_uri(tracking_uri)
        mlflow.set_experiment(experiment)
        nested = mlflow.active_run() is not None
        with mlflow.start_run(run_name=run_name, nested=nested) as run:
            yield run
    except Exception:
        yield None


def _record_agent_llm_call(
    *,
    name: str,
    model: str,
    messages: list[dict[str, object]],
    response_content: str,
    usage: object | None,
) -> None:
    with _agent_mlflow_run(f"{name}:{model}"):
        log_llm_call(
            None,
            name=name,
            model=model,
            messages=messages,
            response_content=response_content,
            usage=usage,
        )


def _call_name(request: ApiMessageRequest) -> str:
    return "agent_tool_turn" if request.tools else "agent_chat_turn"


def _messages_for_log(request: ApiMessageRequest) -> list[dict[str, object]]:
    logged: list[dict[str, object]] = []
    if request.system_prompt:
        logged.append({"role": "system", "content": request.system_prompt})
    for message in request.messages:
        logged.append({"role": message.role, "content": _message_content(message)})
    return logged


def _message_content(message: ConversationMessage) -> str:
    parts: list[str] = []
    for block in message.content:
        if isinstance(block, TextBlock):
            parts.append(block.text)
        elif isinstance(block, ImageBlock):
            parts.append(f"[image:{block.media_type}]")
        else:
            parts.append(f"[{block.type}]")
    return "\n".join(parts)
