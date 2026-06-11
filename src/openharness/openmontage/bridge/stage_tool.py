"""Native OpenHarness tool: om_enter_stage.

Tells the BridgeHookSession which pipeline stage the agent is entering so that
:class:`CheckpointHook` can attribute artifacts and write stage checkpoints.

Usage (model calls):
    om_enter_stage({"stage": "idea", "pipeline": "cinematic"})

This is deliberately thin — it only mutates the session context var and
returns a confirmation string. The heavy lifting (writing the checkpoint JSON)
stays inside CheckpointHook, which fires automatically after every om_* tool
call when stage is set.
"""

from __future__ import annotations

import json

from pydantic import BaseModel, Field

from openharness.tools.base import BaseTool, ToolExecutionContext, ToolResult


class OmEnterStageToolInput(BaseModel):
    """Arguments for ``om_enter_stage``."""

    stage: str = Field(
        ...,
        description="Pipeline stage you are entering, e.g. 'idea', 'research', 'script'.",
    )
    pipeline: str | None = Field(
        default=None,
        description="Pipeline name this stage belongs to, e.g. 'cinematic'. Optional.",
    )


class OmEnterStageTool(BaseTool):
    """Signal the current pipeline stage so CheckpointHook can track progress."""

    name = "om_enter_stage"
    description = (
        "Signal which pipeline stage you are entering. "
        "Call this once at the start of each stage so checkpoint and cost hooks "
        "can attribute artifacts and costs to the correct stage. "
        "Required: `stage` (string, e.g. 'idea'). "
        "Optional: `pipeline` (string, e.g. 'cinematic')."
    )
    input_model = OmEnterStageToolInput

    def is_read_only(self, arguments: OmEnterStageToolInput) -> bool:
        del arguments
        return True  # read-only: mutates in-process state only, no disk writes

    async def execute(
        self, arguments: OmEnterStageToolInput, context: ToolExecutionContext
    ) -> ToolResult:
        del context

        stage = arguments.stage.strip()
        pipeline = (arguments.pipeline or "").strip()

        if not stage:
            return ToolResult(
                output=json.dumps({"ok": False, "error": "stage is required"}),
                is_error=True,
            )

        try:
            from openharness.openmontage.bridge.tool_adapter import current_session

            session = current_session()
            if session is None:
                return ToolResult(
                    output=json.dumps(
                        {
                            "ok": False,
                            "error": "No active BridgeHookSession — is the openmontage plugin enabled?",
                        }
                    ),
                    is_error=True,
                )
            session.stage = stage
            if pipeline:
                session.pipeline = pipeline
        except Exception as exc:  # pragma: no cover
            return ToolResult(
                output=json.dumps({"ok": False, "error": str(exc)}),
                is_error=True,
            )

        return ToolResult(
            output=json.dumps({"ok": True, "stage": stage, "pipeline": pipeline or None})
        )
