"""Python-native hooks that wrap every adapted OpenMontage tool call.

The hooks here are *not* OpenHarness shell hooks. OpenHarness's hook
system fires shell commands / HTTP / model prompts, which is great for
plugin authors but adds latency to every tool call and forces JSON
serialization. For the bridge we want full Python observability with
zero overhead in the common case, so we let
:class:`openharness.openmontage.bridge.tool_adapter.OMToolAdapter`
consult a session-scoped hook chain via a :class:`contextvars.ContextVar`.

Three hooks ship:

* :class:`TraceHook` — append a JSONL record per tool call to
  ``trace.jsonl`` under the run directory. The record carries the tool
  name, inputs (with secrets redacted), the structured OM result, the
  declared stage (if any), and timings. Replaying or grepping this
  file is the primary debugging mechanism the user asked for.
* :class:`CheckpointHook` — after each tool call, compute the delta
  between the previous and current artifact list and, when the agent
  declares a stage transition, write an OpenMontage checkpoint via
  :mod:`openharness.openmontage.lib.checkpoint`.
* :class:`CostHook` — accumulate the ``cost_usd`` field of every OM
  ToolResult into a single ``cost.csv``. Useful for budget reviews and
  for verifying that the cost tracker in OM is actually being charged.

The :class:`BridgeHookSession` owns the chain and the run directory.
Construct one with :func:`bind_session` (or via the ``oh montage agent``
command) and every adapter call in this asyncio task tree will see it.

This module deliberately avoids ``import asyncio`` so the hooks remain
usable from sync contexts too (the OM tools call into them via the
adapter, which is already async).
"""

from __future__ import annotations

import contextvars
import csv
import json
import logging
import os
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Optional, Protocol, Sequence

from openharness.openmontage.tools.base_tool import (
    BaseTool as OMBaseTool,
    ToolResult as OMToolResult,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Public types
# ---------------------------------------------------------------------------


class BridgeHook(Protocol):
    """Sync callback fired by the adapter around each OM tool call."""

    def before_tool(self, ctx: "ToolCallContext") -> None:
        ...

    def after_tool(self, ctx: "ToolCallContext", result: OMToolResult, elapsed_s: float) -> None:
        ...


@dataclass
class ToolCallContext:
    """Information passed to each hook for a single tool call."""

    tool: OMBaseTool
    inputs: dict[str, Any]
    cwd: Path
    stage: Optional[str] = None
    pipeline: Optional[str] = None
    extra: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Session — owns the chain + run directory
# ---------------------------------------------------------------------------


_REDACT_KEYS = ("api_key", "auth_token", "token", "secret", "password")


def _redact(value: Any) -> Any:
    """Return ``value`` with API-key-shaped fields scrubbed for trace files."""
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        for key, sub in value.items():
            lowered = key.lower()
            if any(needle in lowered for needle in _REDACT_KEYS):
                out[key] = "***redacted***"
            else:
                out[key] = _redact(sub)
        return out
    if isinstance(value, list):
        return [_redact(item) for item in value]
    return value


@dataclass
class BridgeHookSession:
    """Holds the run directory and the active hook chain for a pipeline run."""

    run_id: str
    run_dir: Path
    pipeline: Optional[str] = None
    hooks: list[BridgeHook] = field(default_factory=list)
    artifact_state: set[str] = field(default_factory=set)
    stage: Optional[str] = None

    @classmethod
    def for_pipeline(
        cls,
        pipeline: Optional[str],
        *,
        root: Optional[Path] = None,
        run_id: Optional[str] = None,
        hooks: Optional[Sequence[BridgeHook]] = None,
    ) -> "BridgeHookSession":
        """Create a session with a fresh run directory under ``.openharness/montage/runs/``."""
        run_id = run_id or _new_run_id()
        anchor = (root or Path.cwd()).resolve()
        run_dir = anchor / ".openharness" / "montage" / "runs" / run_id
        run_dir.mkdir(parents=True, exist_ok=True)
        session = cls(
            run_id=run_id,
            run_dir=run_dir,
            pipeline=pipeline,
            hooks=list(hooks or []),
        )
        session._write_metadata()
        return session

    def add_hook(self, hook: BridgeHook) -> None:
        """Append a hook to the chain."""
        self.hooks.append(hook)

    def set_stage(self, stage: Optional[str]) -> None:
        """Update the active stage. Called by orchestration hooks."""
        self.stage = stage

    def _write_metadata(self) -> None:
        (self.run_dir / "session.json").write_text(
            json.dumps(
                {
                    "run_id": self.run_id,
                    "pipeline": self.pipeline,
                    "started_at": time.time(),
                    "pid": os.getpid(),
                },
                indent=2,
            ),
            encoding="utf-8",
        )


_active_session: contextvars.ContextVar[Optional[BridgeHookSession]] = contextvars.ContextVar(
    "openmontage_bridge_session", default=None
)


def bind_session(session: BridgeHookSession) -> contextvars.Token:
    """Bind a session to the current async/thread context. Token must be reset."""
    return _active_session.set(session)


def current_session() -> Optional[BridgeHookSession]:
    """Return the session bound to this context (or None)."""
    return _active_session.get()


def reset_session(token: contextvars.Token) -> None:
    """Restore the previous session binding."""
    _active_session.reset(token)


# ---------------------------------------------------------------------------
# Trace hook
# ---------------------------------------------------------------------------


class TraceHook:
    """Append a JSONL trace record per tool call."""

    def __init__(self, session: BridgeHookSession) -> None:
        self._session = session
        self._path = session.run_dir / "trace.jsonl"

    def before_tool(self, ctx: ToolCallContext) -> None:
        ctx.extra["trace_started_at"] = time.time()

    def after_tool(self, ctx: ToolCallContext, result: OMToolResult, elapsed_s: float) -> None:
        record = {
            "ts": time.time(),
            "elapsed_s": round(elapsed_s, 4),
            "pipeline": ctx.pipeline or self._session.pipeline,
            "stage": ctx.stage or self._session.stage,
            "tool": ctx.tool.name,
            "provider": ctx.tool.provider,
            "tier": ctx.tool.tier.value if hasattr(ctx.tool.tier, "value") else str(ctx.tool.tier),
            "inputs": _redact(ctx.inputs),
            "result": {
                "success": result.success,
                "error": result.error,
                "artifacts": list(result.artifacts),
                "data_keys": sorted(result.data.keys()) if isinstance(result.data, dict) else None,
                "cost_usd": float(result.cost_usd or 0.0),
                "model": result.model,
                "seed": result.seed,
            },
        }
        with open(self._path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")


# ---------------------------------------------------------------------------
# Checkpoint hook
# ---------------------------------------------------------------------------


class CheckpointHook:
    """Diff the artifact set after each call; write a checkpoint when the stage changes."""

    def __init__(self, session: BridgeHookSession) -> None:
        self._session = session
        self._diff_path = session.run_dir / "artifact_diff.jsonl"
        self._checkpoint_root = session.run_dir / "checkpoints"
        self._checkpoint_root.mkdir(parents=True, exist_ok=True)

    def before_tool(self, ctx: ToolCallContext) -> None:
        pass

    def after_tool(self, ctx: ToolCallContext, result: OMToolResult, elapsed_s: float) -> None:
        before = set(self._session.artifact_state)
        produced = {str(a) for a in result.artifacts}
        if not produced and not before:
            return
        after = before | produced
        added = sorted(produced - before)
        removed = sorted(before - after)  # always empty given the union, kept for symmetry
        self._session.artifact_state = after
        with open(self._diff_path, "a", encoding="utf-8") as fh:
            fh.write(
                json.dumps(
                    {
                        "ts": time.time(),
                        "tool": ctx.tool.name,
                        "stage": ctx.stage or self._session.stage,
                        "added": added,
                        "removed": removed,
                        "total_after": len(after),
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )

        stage = ctx.stage or self._session.stage
        if not stage or not added:
            return

        # Best-effort handoff to the upstream checkpoint writer. Failures
        # are logged but don't abort the run — checkpointing is a debugging
        # aid, not a correctness gate.
        try:
            from openharness.openmontage.lib.checkpoint import write_checkpoint

            write_checkpoint(
                pipeline_dir=self._checkpoint_root,
                project_id=self._session.run_id,
                stage=stage,
                status="completed" if result.success else "failed",
                artifacts={name: name for name in produced},
                pipeline_type=ctx.pipeline or self._session.pipeline,
                error=result.error,
            )
        except Exception as exc:  # pragma: no cover - defensive
            logger.debug("checkpoint hook skipped for tool %s: %s", ctx.tool.name, exc)


# ---------------------------------------------------------------------------
# Cost hook
# ---------------------------------------------------------------------------


class CostHook:
    """Maintain a per-call ``cost.csv`` and an aggregated tally."""

    _CSV_HEADER = (
        "ts",
        "pipeline",
        "stage",
        "tool",
        "provider",
        "model",
        "cost_usd",
        "success",
    )

    def __init__(self, session: BridgeHookSession) -> None:
        self._session = session
        self._path = session.run_dir / "cost.csv"
        self._total = 0.0
        if not self._path.exists():
            with open(self._path, "w", encoding="utf-8", newline="") as fh:
                csv.writer(fh).writerow(self._CSV_HEADER)

    def before_tool(self, ctx: ToolCallContext) -> None:
        pass

    def after_tool(self, ctx: ToolCallContext, result: OMToolResult, elapsed_s: float) -> None:
        cost = float(result.cost_usd or 0.0)
        if cost <= 0.0 and result.model is None:
            return
        self._total += cost
        with open(self._path, "a", encoding="utf-8", newline="") as fh:
            csv.writer(fh).writerow(
                [
                    f"{time.time():.3f}",
                    ctx.pipeline or self._session.pipeline or "",
                    ctx.stage or self._session.stage or "",
                    ctx.tool.name,
                    ctx.tool.provider,
                    result.model or "",
                    f"{cost:.4f}",
                    "1" if result.success else "0",
                ]
            )

    @property
    def total_usd(self) -> float:
        """Running total spend across all calls in this session."""
        return self._total


# ---------------------------------------------------------------------------
# Utilities used by adapter + CLI
# ---------------------------------------------------------------------------


def install_default_hooks(session: BridgeHookSession) -> None:
    """Attach the default trace + checkpoint + cost trio to a session."""
    session.add_hook(TraceHook(session))
    session.add_hook(CheckpointHook(session))
    session.add_hook(CostHook(session))


def emit_before(ctx: ToolCallContext) -> None:
    """Fire every active hook's ``before_tool`` callback. Safe in sync code."""
    session = current_session()
    if session is None:
        return
    for hook in session.hooks:
        try:
            hook.before_tool(ctx)
        except Exception:  # pragma: no cover - defensive
            logger.exception("hook %r before_tool raised", hook)


def emit_after(ctx: ToolCallContext, result: OMToolResult, elapsed_s: float) -> None:
    """Fire every active hook's ``after_tool`` callback. Safe in sync code."""
    session = current_session()
    if session is None:
        return
    for hook in session.hooks:
        try:
            hook.after_tool(ctx, result, elapsed_s)
        except Exception:  # pragma: no cover - defensive
            logger.exception("hook %r after_tool raised", hook)


def _new_run_id() -> str:
    """Create a sortable run id (timestamp prefix + short uuid suffix)."""
    return f"{time.strftime('%Y%m%dT%H%M%S')}-{uuid.uuid4().hex[:8]}"


__all__ = [
    "BridgeHook",
    "BridgeHookSession",
    "CheckpointHook",
    "CostHook",
    "ToolCallContext",
    "TraceHook",
    "bind_session",
    "current_session",
    "emit_after",
    "emit_before",
    "install_default_hooks",
    "reset_session",
]
