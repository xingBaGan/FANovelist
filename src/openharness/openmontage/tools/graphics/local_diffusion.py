"""Local FLUX image generation via a ComfyUI HTTP backend.

Replaces the previous in-process Stable Diffusion/diffusers path. Point
COMFYUI_BACKEND_URL at a LAN or local ComfyUI server running the FLUX workflow.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from openharness.openmontage.tools.base_tool import (
    BaseTool,
    Determinism,
    ExecutionMode,
    ResourceProfile,
    RetryPolicy,
    ToolResult,
    ToolRuntime,
    ToolStability,
    ToolStatus,
    ToolTier,
)
from openharness.openmontage.tools.graphics._comfyui_client import (
    generate_images_bytes,
    is_comfyui_configured,
    resolve_comfyui_base_url,
)


class LocalDiffusion(BaseTool):
    name = "local_diffusion"
    version = "0.2.0"
    tier = ToolTier.GENERATE
    capability = "image_generation"
    provider = "local_diffusion"
    stability = ToolStability.BETA
    execution_mode = ExecutionMode.SYNC
    determinism = Determinism.SEEDED
    runtime = ToolRuntime.HYBRID

    dependencies = []
    install_instructions = (
        "Run a ComfyUI FLUX backend and set its URL:\n"
        "  COMFYUI_BACKEND_URL=http://<host>:8190\n"
        "  # or COMFYUI_URL=http://<host>:8190\n"
        "The backend must expose POST /generate and GET /image endpoints."
    )
    agent_skills = ["flux-best-practices"]

    capabilities = ["generate_image", "generate_illustration", "text_to_image"]
    supports = {
        "negative_prompt": True,
        "seed": True,
        "custom_size": True,
        "comfyui_backend": True,
    }
    best_for = [
        "local or LAN FLUX generation via ComfyUI (no cloud API cost)",
        "free image generation when a ComfyUI GPU server is available",
        "privacy-sensitive workflows using your own hardware",
    ]
    not_good_for = [
        "machines without a reachable ComfyUI backend",
        "environments with no COMFYUI_BACKEND_URL configured",
    ]

    input_schema = {
        "type": "object",
        "required": ["prompt"],
        "properties": {
            "prompt": {"type": "string"},
            "negative_prompt": {"type": "string", "default": ""},
            "width": {"type": "integer", "default": 1024},
            "height": {"type": "integer", "default": 1024},
            "size": {"type": "string", "description": "Alternative to width/height, e.g. 1024x1024"},
            "seed": {"type": "integer", "default": -1},
            "steps": {"type": "integer", "default": 6},
            "num_inference_steps": {"type": "integer", "description": "Alias for steps"},
            "cfg": {"type": "number", "default": 1.0},
            "guidance_scale": {"type": "number", "description": "Alias for cfg"},
            "filename_prefix": {"type": "string", "default": "OpenMontage_Flux2"},
            "output_path": {"type": "string"},
            "comfyui_base_url": {"type": "string", "description": "Override COMFYUI_BACKEND_URL"},
        },
    }

    resource_profile = ResourceProfile(
        cpu_cores=1, ram_mb=512, vram_mb=0, disk_mb=200, network_required=True
    )
    retry_policy = RetryPolicy(max_retries=1, retryable_errors=["timeout", "connection"])
    idempotency_key_fields = ["prompt", "width", "height", "seed"]
    side_effects = ["writes image file to output_path", "calls ComfyUI HTTP backend"]
    user_visible_verification = ["Inspect generated image for relevance and quality"]

    def get_status(self) -> ToolStatus:
        if is_comfyui_configured():
            return ToolStatus.AVAILABLE
        return ToolStatus.UNAVAILABLE

    def estimate_cost(self, inputs: dict[str, Any]) -> float:
        return 0.0

    def estimate_runtime(self, inputs: dict[str, Any]) -> float:
        steps = inputs.get("steps") or inputs.get("num_inference_steps", 6)
        return max(10.0, float(steps) * 2.0)

    def execute(self, inputs: dict[str, Any]) -> ToolResult:
        if not is_comfyui_configured():
            return ToolResult(
                success=False,
                error="ComfyUI backend is not configured. " + self.install_instructions,
            )

        start = time.time()
        prompt = inputs["prompt"]
        base_url = resolve_comfyui_base_url(inputs.get("comfyui_base_url"))

        try:
            image_bytes_list = generate_images_bytes(base_url, inputs, prompt)
            output_path = Path(inputs.get("output_path", "generated_image.png"))
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_bytes(image_bytes_list[0])
        except Exception as exc:
            return ToolResult(success=False, error=f"ComfyUI FLUX generation failed: {exc}")

        seed = inputs.get("seed")
        return ToolResult(
            success=True,
            data={
                "provider": "comfyui",
                "backend": base_url,
                "model": "flux-comfyui",
                "prompt": prompt,
                "output": str(output_path),
            },
            artifacts=[str(output_path)],
            cost_usd=0.0,
            duration_seconds=round(time.time() - start, 2),
            seed=seed if isinstance(seed, int) and seed >= 0 else None,
            model="flux-comfyui",
        )
