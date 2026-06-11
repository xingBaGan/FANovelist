"""Sync OpenMontage BaseTool -> async OpenHarness BaseTool adapter.

The two frameworks have intentionally different tool contracts:

- OpenMontage (sync, dict-in/result-out, cost+artifacts in the result)
- OpenHarness (async, Pydantic-in, single-string output + metadata, hookable)

Rewriting the 80+ OpenMontage tools to async/Pydantic would freeze
iteration for weeks. Instead, this adapter wraps each OM tool so that:

* ``execute()`` runs on a worker thread via :func:`asyncio.to_thread`
* OM ``ToolResult`` is serialized to a JSON envelope as ``output``, with
  ``artifacts``/``cost_usd``/``model``/``seed``/``duration_seconds``
  preserved in ``metadata``
* ``is_read_only`` defaults to ``False`` since OM tools often write files;
  callers can override per tool via ``OMToolAdapter.read_only=True``
* Permission gating and PreToolUse/PostToolUse hooks fire naturally
  because the wrapper is a first-class OpenHarness ``BaseTool``

Input model
-----------

Most OpenMontage tools declare ``input_schema = {}`` and accept an
ad-hoc dict whose shape varies per tool. To stay universal in v1 we
expose a single permissive ``inputs`` dict on the adapter input model.
The agent constructs the OM-flavored dict; the adapter forwards it.

Subsequent versions can introspect richer ``input_schema`` declarations
and generate per-tool Pydantic models that surface field-level docs to
the LLM. For now the OM ``best_for``/``not_good_for``/``capabilities``
arrays are folded into the OpenHarness description so the agent can
still choose well.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from openharness.openmontage.bridge.hooks import (
    ToolCallContext as BridgeToolCallContext,
    current_session,
    emit_after,
    emit_before,
)
from openharness.openmontage.tools.base_tool import (
    BaseTool as OMBaseTool,
    ToolResult as OMToolResult,
)
from openharness.openmontage.tools.tool_registry import registry as om_registry
from openharness.tools.base import BaseTool, ToolExecutionContext, ToolResult

logger = logging.getLogger(__name__)


class _OMAdapterInput(BaseModel):
    """Permissive input model passed to every adapted OpenMontage tool.

    The ``inputs`` dict is forwarded verbatim to the underlying tool's
    sync ``execute()`` method. ``extra="allow"`` lets the agent pass
    flat keyword arguments too; we merge those into ``inputs``.
    """

    model_config = ConfigDict(extra="allow")
    inputs: dict[str, Any] = Field(
        default_factory=dict,
        description=(
            "Tool-specific arguments as a JSON object. Refer to the tool's "
            "description and any referenced agent_skills for the expected keys."
        ),
    )


def _build_description(tool: OMBaseTool) -> str:
    """Compose a model-friendly description from OM tool metadata."""
    doc = (tool.__class__.__doc__ or "").strip().splitlines()
    head = doc[0].strip() if doc else f"{tool.capability} ({tool.provider})"

    parts: list[str] = [head]
    if tool.best_for:
        parts.append("Best for: " + ", ".join(tool.best_for) + ".")
    if tool.not_good_for:
        parts.append("Not good for: " + ", ".join(tool.not_good_for) + ".")
    if tool.agent_skills:
        parts.append(
            "Layer-3 skills: " + ", ".join(tool.agent_skills) + " "
            "(load via the `skill` tool before calling for prompting guidance)."
        )
    parts.append(
        "Inputs: pass an `inputs` JSON object. See agent_skills or the tool's "
        "registered input_schema for keys."
    )
    return " ".join(parts)


def _serialize_om_result(result: OMToolResult) -> ToolResult:
    """Translate an OpenMontage ToolResult to an OpenHarness ToolResult.

    The OM result carries structured ``data`` plus typed sidecar fields.
    We render the human-facing summary as ``output`` and put everything
    else in ``metadata`` so downstream hooks/observers can use it.
    """
    body: dict[str, Any] = {
        "success": result.success,
        "data": result.data,
        "artifacts": result.artifacts,
    }
    if result.error:
        body["error"] = result.error
    if result.model:
        body["model"] = result.model
    if result.seed is not None:
        body["seed"] = result.seed
    if result.cost_usd:
        body["cost_usd"] = result.cost_usd
    if result.duration_seconds:
        body["duration_seconds"] = result.duration_seconds

    try:
        output = json.dumps(body, ensure_ascii=False, indent=2, default=str)
    except (TypeError, ValueError):
        output = json.dumps(
            {"success": result.success, "error": "result not JSON-serializable"},
            ensure_ascii=False,
        )

    metadata: dict[str, Any] = {
        "om_tool": True,
        "artifacts": list(result.artifacts),
        "cost_usd": float(result.cost_usd or 0.0),
        "duration_seconds": float(result.duration_seconds or 0.0),
    }
    if result.model:
        metadata["model"] = result.model
    if result.seed is not None:
        metadata["seed"] = result.seed

    return ToolResult(output=output, is_error=not result.success, metadata=metadata)


class OMToolAdapter(BaseTool):
    """Expose a single sync OpenMontage tool as an async OpenHarness tool."""

    input_model = _OMAdapterInput

    def __init__(self, om_tool: OMBaseTool, *, read_only: bool = False) -> None:
        self._om_tool = om_tool
        # Prefix to avoid collisions with native OpenHarness tools sharing a
        # generic name (e.g. ``image_generation`` exists on both sides).
        self.name = f"om_{om_tool.name}"
        self.description = _build_description(om_tool)
        self._read_only = read_only

    @property
    def om_tool(self) -> OMBaseTool:
        """Return the wrapped OpenMontage tool (handy for introspection)."""
        return self._om_tool

    def is_read_only(self, arguments: BaseModel) -> bool:
        del arguments
        return self._read_only

    async def execute(
        self,
        arguments: _OMAdapterInput,
        context: ToolExecutionContext,
    ) -> ToolResult:
        payload: dict[str, Any] = dict(arguments.inputs or {})
        extras = arguments.model_dump(exclude={"inputs"})
        # ``extras`` only carries fields the agent set via ``extra="allow"``;
        # keep the explicit ``inputs`` keys as the source of truth and add
        # the rest only when they don't collide.
        for key, value in extras.items():
            payload.setdefault(key, value)

        payload.setdefault("cwd", str(context.cwd))

        session = current_session()
        bridge_ctx = BridgeToolCallContext(
            tool=self._om_tool,
            inputs=payload,
            cwd=context.cwd,
            pipeline=session.pipeline if session else None,
            stage=session.stage if session else None,
        )
        emit_before(bridge_ctx)
        started = time.monotonic()
        try:
            om_result: OMToolResult = await asyncio.to_thread(
                self._om_tool.execute, payload
            )
        except Exception as exc:  # pragma: no cover - defensive
            logger.exception("OM tool %s raised", self._om_tool.name)
            failure = OMToolResult(success=False, error=repr(exc))
            emit_after(bridge_ctx, failure, time.monotonic() - started)
            return ToolResult(
                output=json.dumps({"success": False, "error": repr(exc)}),
                is_error=True,
                metadata={"om_tool": True, "exception": True},
            )
        emit_after(bridge_ctx, om_result, time.monotonic() - started)
        return _serialize_om_result(om_result)


def adapt_tool(om_tool: OMBaseTool, *, read_only: bool = False) -> OMToolAdapter:
    """Adapt a single concrete OpenMontage tool."""
    return OMToolAdapter(om_tool, read_only=read_only)


def adapt_all_tools(
    *,
    discover: bool = True,
    only: set[str] | None = None,
    read_only_names: set[str] | None = None,
) -> list[OMToolAdapter]:
    """Return adapters for every (or a subset of) discovered OM tool.

    Args:
        discover: If True, call the OM registry's ``discover()`` so every
            ``tools/`` subpackage is imported and registered. Pass False
            if you already populated the registry yourself.
        only: Optional set of OM tool names to keep. Useful for early
            phases where you want to bridge only the talking-head subset.
        read_only_names: Subset that should be treated as read-only by the
            permission checker (analysis tools, dry-runs, info queries).
    """
    if discover:
        om_registry.ensure_discovered()
    read_only_names = read_only_names or set()
    adapters: list[OMToolAdapter] = []
    for name, tool in om_registry._tools.items():  # noqa: SLF001 — internal but stable
        if only is not None and name not in only:
            continue
        adapters.append(OMToolAdapter(tool, read_only=name in read_only_names))
    return adapters
