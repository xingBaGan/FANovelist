"""Shared HTTP client for ComfyUI image generation backends."""

from __future__ import annotations

import base64
import os
from typing import Any

import requests

_DEFAULT_BASE_URL = "http://127.0.0.1:8190"


def resolve_comfyui_base_url(override: str | None = None) -> str:
    """Resolve the ComfyUI backend URL from override or environment."""
    url = (
        (override or "").strip()
        or os.environ.get("COMFYUI_BACKEND_URL", "").strip()
        or os.environ.get("COMFYUI_URL", "").strip()
        or _DEFAULT_BASE_URL
    )
    return url.rstrip("/")


def is_comfyui_configured() -> bool:
    """Return True when a ComfyUI backend URL is explicitly configured."""
    return bool(
        os.environ.get("COMFYUI_BACKEND_URL", "").strip()
        or os.environ.get("COMFYUI_URL", "").strip()
    )


def parse_dimensions(
    inputs: dict[str, Any],
    *,
    default_width: int = 1024,
    default_height: int = 1024,
) -> tuple[int, int]:
    """Parse width/height from tool inputs, including WxH size strings."""
    width = inputs.get("width")
    height = inputs.get("height")
    if width is not None and height is not None:
        return int(width), int(height)

    size = inputs.get("size", "auto")
    if size and size != "auto":
        parts = str(size).split("x")
        if len(parts) == 2:
            try:
                return int(parts[0]), int(parts[1])
            except ValueError:
                pass
    return default_width, default_height


def build_generate_payload(
    inputs: dict[str, Any],
    prompt: str,
    *,
    default_width: int = 1024,
    default_height: int = 1024,
) -> dict[str, Any]:
    """Build the JSON body for ComfyUI /generate."""
    width, height = parse_dimensions(
        inputs,
        default_width=default_width,
        default_height=default_height,
    )
    return {
        "prompt": prompt,
        "negative_prompt": inputs.get("negative_prompt") or "",
        "width": width,
        "height": height,
        "steps": inputs.get("steps") or inputs.get("num_inference_steps", 6),
        "cfg": inputs.get("cfg") or inputs.get("guidance_scale", 1.0),
        "seed": inputs.get("seed", -1),
        "filename_prefix": inputs.get("filename_prefix") or "OpenMontage_Flux2",
        "wait": True,
    }


def generate_images_b64(
    base_url: str,
    inputs: dict[str, Any],
    prompt: str,
    *,
    default_width: int = 1024,
    default_height: int = 1024,
    timeout_seconds: int = 600,
) -> list[str]:
    """Generate images via ComfyUI and return base64-encoded PNG/JPEG bytes."""
    return [
        base64.b64encode(image_bytes).decode("utf-8")
        for image_bytes in generate_images_bytes(
            base_url,
            inputs,
            prompt,
            default_width=default_width,
            default_height=default_height,
            timeout_seconds=timeout_seconds,
        )
    ]


def generate_images_bytes(
    base_url: str,
    inputs: dict[str, Any],
    prompt: str,
    *,
    default_width: int = 1024,
    default_height: int = 1024,
    timeout_seconds: int = 600,
) -> list[bytes]:
    """Generate images via ComfyUI and return raw image bytes."""
    comfy_url = base_url.rstrip("/")
    payload = build_generate_payload(
        inputs,
        prompt,
        default_width=default_width,
        default_height=default_height,
    )

    response = requests.post(f"{comfy_url}/generate", json=payload, timeout=timeout_seconds)
    response.raise_for_status()
    data = response.json()

    images: list[bytes] = []
    for img in data.get("images", []):
        filename = img.get("filename")
        subfolder = img.get("subfolder", "")
        type_ = img.get("type", "output")
        img_url = f"{comfy_url}/image?filename={filename}&subfolder={subfolder}&type={type_}"
        img_resp = requests.get(img_url, timeout=60)
        img_resp.raise_for_status()
        images.append(img_resp.content)
    if not images:
        raise RuntimeError("ComfyUI backend returned no images")
    return images
