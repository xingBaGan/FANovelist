"""Native OpenHarness port of ``tts_selector``.

Educational target: show how a legacy sync OpenMontage tool gets a
typed, async, Pydantic-backed OpenHarness face without surrendering
the underlying OM provider tools. The same template applies to the
other selectors (image, video, music).

Comparison to the legacy sync version (
``openharness.openmontage.tools.audio.tts_selector``):

* **Input**: ``TtsSelectorInput`` Pydantic model with field
  descriptions surfaces to the LLM as a real JSON schema. The OM
  version declares ``input_schema: dict``, which OpenHarness can't
  validate.
* **Output**: ``ToolResult(output=..., metadata=...)`` returns a
  short, model-friendly string plus structured metadata. The OM
  version returns a custom ``ToolResult`` dataclass with the model,
  cost, artifacts, and data dict — useful for OM but opaque to OH.
* **Lifecycle**: pure ``async`` with ``asyncio.to_thread`` for the
  provider call. Cancellable and observable via OH hooks.
* **Skills**: ``required_skills`` lists agent_skills so OpenHarness
  can hint the model towards loading them first.

Internally we still call into the OM provider tools — the porting
pattern is "rewrite the outside, keep the inside" until you're ready
to replace the provider implementations too.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from openharness.tools.base import BaseTool, ToolExecutionContext, ToolResult

logger = logging.getLogger(__name__)


class TtsSelectorInput(BaseModel):
    """Inputs for the TTS selector. Mirrors the legacy schema but typed."""

    model_config = ConfigDict(extra="forbid")

    text: str = Field(description="Text to synthesize.")
    voice_id: str | None = Field(
        default=None,
        description="Provider-specific voice ID (passed through to the chosen provider).",
    )
    model_id: str | None = Field(
        default=None,
        description="Provider TTS model (e.g. `eleven_multilingual_v2`).",
    )
    stability: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="ElevenLabs voice stability. Lower = more expressive.",
    )
    similarity_boost: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="ElevenLabs similarity boost.",
    )
    style: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="ElevenLabs style exaggeration.",
    )
    output_format: str | None = Field(
        default=None,
        description="Audio output format (e.g. `mp3_44100_128`).",
    )
    preferred_provider: str = Field(
        default="auto",
        description="Provider name or `auto`. Available names depend on env credentials.",
    )
    allowed_providers: list[str] | None = Field(
        default=None,
        description="Whitelist of provider names to consider.",
    )
    operation: Literal["generate", "rank"] = Field(
        default="generate",
        description="`generate` to synthesize; `rank` to return scored provider rankings only.",
    )
    output_path: str | None = Field(
        default=None,
        description="Where to write the audio file (when `operation` is `generate`).",
    )


class TtsSelectorNativeTool(BaseTool):
    """Native OpenHarness tool that selects + invokes a TTS provider."""

    name = "tts_native"
    description = (
        "Synthesize speech from text via the best-available TTS provider. "
        "Auto-discovers OpenMontage TTS providers from the bridge registry, "
        "ranks them for the task context, and delegates execution. "
        "Returns the audio path plus the selection reasoning."
    )
    input_model = TtsSelectorInput
    required_skills = ("text-to-speech",)

    def is_read_only(self, arguments: TtsSelectorInput) -> bool:
        # `rank` mode is pure compute; `generate` writes a file.
        return arguments.operation == "rank"

    async def execute(
        self,
        arguments: TtsSelectorInput,
        context: ToolExecutionContext,
    ) -> ToolResult:
        try:
            from openharness.openmontage.tools.audio.tts_selector import TTSSelector
        except ImportError as exc:  # pragma: no cover - subpackage missing
            return ToolResult(
                output=f"OpenMontage TTS selector unavailable: {exc}",
                is_error=True,
            )

        payload = arguments.model_dump(exclude_none=True)
        payload.setdefault("cwd", str(context.cwd))

        try:
            om_result = await asyncio.to_thread(TTSSelector().execute, payload)
        except Exception as exc:  # pragma: no cover - defensive
            logger.exception("native TTS selector failed")
            return ToolResult(
                output=f"TTS selector raised: {exc!r}",
                is_error=True,
            )

        if not om_result.success:
            return ToolResult(
                output=om_result.error or "TTS provider returned an error.",
                is_error=True,
                metadata={
                    "om_native": True,
                    "operation": arguments.operation,
                    "cost_usd": float(om_result.cost_usd or 0.0),
                },
            )

        data = dict(om_result.data or {})
        if arguments.operation == "rank":
            output_lines = [
                "Top-ranked TTS providers:",
                data.get("explanation") or "(no explanation)",
            ]
            return ToolResult(
                output="\n".join(output_lines),
                metadata={
                    "om_native": True,
                    "operation": "rank",
                    "rankings": data.get("rankings"),
                    "task_context": data.get("normalized_task_context"),
                    "artifacts": list(om_result.artifacts),
                    "cost_usd": float(om_result.cost_usd or 0.0),
                },
            )

        selected_tool = data.get("selected_tool") or "(unknown)"
        selected_provider = data.get("selected_provider") or "(unknown)"
        selection_reason = data.get("selection_reason") or ""
        artifacts = list(om_result.artifacts)
        head = (
            f"Synthesized with `{selected_tool}` (provider={selected_provider}). "
            f"{selection_reason}"
        ).strip()
        if artifacts:
            head += f"\nAudio file: {artifacts[0]}"
        return ToolResult(
            output=head,
            metadata={
                "om_native": True,
                "operation": "generate",
                "selected_tool": selected_tool,
                "selected_provider": selected_provider,
                "alternatives_considered": data.get("alternatives_considered", []),
                "required_agent_skills": data.get("required_agent_skills", []),
                "artifacts": artifacts,
                "cost_usd": float(om_result.cost_usd or 0.0),
                "model": om_result.model,
                "seed": om_result.seed,
                "raw_data": _safe_json(data),
            },
        )


def _safe_json(payload: Any) -> Any:
    """Return ``payload`` if it round-trips through JSON; otherwise a stringified view."""
    try:
        return json.loads(json.dumps(payload, default=str))
    except (TypeError, ValueError):
        return str(payload)
