"""Multi-provider raster image generation and editing.

Ported from OpenHarness image_generation_tool. Supports:
- OpenAI-compatible image APIs (OpenAI, SiliconFlow, custom base_url)
- Codex subscription hosted image_generation
- ComfyUI HTTP backend (local or remote)
"""

from __future__ import annotations

import base64
import json
import logging
import os
import platform
import time
from pathlib import Path
from typing import Any, Iterator, Literal
from urllib.parse import urlsplit, urlunsplit

import requests

from openharness.openmontage.tools.graphics._comfyui_client import generate_images_b64, resolve_comfyui_base_url
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

log = logging.getLogger(__name__)

_DEFAULT_PROMPT = (
    "Create a high-quality raster image that satisfies the user's request. "
    "Avoid watermarks, unintended text, and unrelated logos."
)
_DEFAULT_MODEL = "gpt-image-2"
_DEFAULT_OUTPUT_DIR = "generated_images"
_DEFAULT_CODEX_BASE_URL = "https://chatgpt.com/backend-api"
_JWT_CLAIM_PATH = "https://api.openai.com/auth"

ImageGenerationProvider = Literal["auto", "openai", "codex", "comfyui"]


def _env(name: str, *fallback_names: str) -> str:
    for key in (name, *fallback_names):
        value = os.environ.get(key, "").strip()
        if value:
            return value
    return ""


def _resolve_config(inputs: dict[str, Any] | None = None) -> dict[str, str]:
    """Resolve provider credentials from env vars and optional input overrides."""
    inputs = inputs or {}
    api_key = (
        str(inputs.get("api_key") or "").strip()
        or _env(
            "IMAGE_GENERATION_API_KEY",
            "OPENMONTAGE_IMAGE_GENERATION_API_KEY",
            "OPENHARNESS_IMAGE_GENERATION_API_KEY",
            "OPENAI_API_KEY",
        )
    )
    base_url = (
        str(inputs.get("base_url") or "").strip()
        or _env(
            "IMAGE_GENERATION_BASE_URL",
            "OPENMONTAGE_IMAGE_GENERATION_BASE_URL",
            "OPENHARNESS_IMAGE_GENERATION_BASE_URL",
        )
    )
    model = (
        str(inputs.get("model") or "").strip()
        or _env(
            "IMAGE_GENERATION_MODEL",
            "OPENMONTAGE_IMAGE_GENERATION_MODEL",
            "OPENHARNESS_IMAGE_GENERATION_MODEL",
        )
        or _DEFAULT_MODEL
    )
    provider = (
        str(inputs.get("provider") or "").strip()
        or _env(
            "IMAGE_GENERATION_PROVIDER",
            "OPENMONTAGE_IMAGE_GENERATION_PROVIDER",
            "OPENHARNESS_IMAGE_GENERATION_PROVIDER",
        )
        or "auto"
    )
    codex_auth_token = (
        str(inputs.get("codex_auth_token") or "").strip()
        or _env(
            "IMAGE_GENERATION_CODEX_AUTH_TOKEN",
            "CODEX_AUTH_TOKEN",
            "OPENHARNESS_IMAGE_GENERATION_CODEX_AUTH_TOKEN",
        )
    )
    codex_model = (
        str(inputs.get("codex_model") or "").strip()
        or _env(
            "IMAGE_GENERATION_CODEX_MODEL",
            "OPENMONTAGE_IMAGE_GENERATION_CODEX_MODEL",
            "OPENHARNESS_IMAGE_GENERATION_CODEX_MODEL",
        )
        or "gpt-5.4"
    )
    codex_base_url = (
        str(inputs.get("codex_base_url") or "").strip()
        or _env(
            "IMAGE_GENERATION_CODEX_BASE_URL",
            "OPENMONTAGE_IMAGE_GENERATION_CODEX_BASE_URL",
            "OPENHARNESS_IMAGE_GENERATION_CODEX_BASE_URL",
        )
    )
    comfyui_base_url = (
        str(inputs.get("comfyui_base_url") or "").strip()
        or _env("COMFYUI_BACKEND_URL", "COMFYUI_URL")
    )

    silicon_key = _env("SILICONFLOW_API_KEY")
    if silicon_key and not api_key:
        api_key = silicon_key
        if not base_url:
            base_url = "https://api.siliconflow.cn/v1"

    return {
        "provider": provider,
        "model": model,
        "api_key": api_key,
        "base_url": base_url,
        "codex_auth_token": codex_auth_token,
        "codex_model": codex_model,
        "codex_base_url": codex_base_url,
        "comfyui_base_url": comfyui_base_url,
    }


class ImageGeneration(BaseTool):
    """Generate or edit raster images across OpenAI-compatible, Codex, and ComfyUI providers."""

    name = "image_generation"
    version = "0.1.0"
    tier = ToolTier.GENERATE
    capability = "image_generation"
    provider = "multi"
    stability = ToolStability.BETA
    execution_mode = ExecutionMode.SYNC
    determinism = Determinism.STOCHASTIC
    runtime = ToolRuntime.HYBRID

    dependencies = []
    install_instructions = (
        "Configure at least one provider:\n"
        "  OpenAI-compatible: set OPENAI_API_KEY or IMAGE_GENERATION_API_KEY "
        "(optional IMAGE_GENERATION_BASE_URL for custom gateways like SiliconFlow)\n"
        "  Codex subscription: set CODEX_AUTH_TOKEN or IMAGE_GENERATION_CODEX_AUTH_TOKEN\n"
        "  ComfyUI: set COMFYUI_BACKEND_URL or COMFYUI_URL (defaults to http://127.0.0.1:8190)\n"
        "  pip install openai  # required for OpenAI-compatible providers"
    )
    agent_skills = ["flux-best-practices"]

    capabilities = [
        "generate_image",
        "edit_image",
        "text_to_image",
        "image_to_image",
        "transparent_cutout",
    ]
    supports = {
        "openai_compatible_api": True,
        "codex_subscription": True,
        "comfyui_backend": True,
        "image_edit": True,
        "mask_edit": True,
        "multiple_outputs": True,
        "siliconflow_gateway": True,
    }
    best_for = [
        "OpenAI-compatible gateways (OpenAI, SiliconFlow, custom base_url)",
        "Codex subscription hosted image_generation",
        "local or remote ComfyUI FLUX workflows",
        "editing existing local images with masks",
    ]
    not_good_for = [
        "stock image search (use pexels_image or pixabay_image)",
        "provider-agnostic routing (use image_selector)",
    ]

    input_schema = {
        "type": "object",
        "required": ["prompt"],
        "properties": {
            "prompt": {"type": "string", "default": _DEFAULT_PROMPT},
            "provider": {
                "type": "string",
                "enum": ["auto", "openai", "codex", "comfyui"],
                "default": "auto",
            },
            "image_paths": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Local image paths for edit/reference mode.",
            },
            "mask_path": {"type": "string", "description": "Optional PNG mask for OpenAI edit mode."},
            "output_path": {"type": "string"},
            "output_dir": {"type": "string", "default": _DEFAULT_OUTPUT_DIR},
            "model": {"type": "string"},
            "n": {"type": "integer", "default": 1, "minimum": 1, "maximum": 10},
            "size": {"type": "string", "default": "auto"},
            "quality": {"type": "string", "default": "medium"},
            "background": {"type": "string", "enum": ["transparent", "opaque", "auto"]},
            "output_format": {"type": "string", "enum": ["png", "jpeg", "webp"], "default": "png"},
            "output_compression": {"type": "integer", "minimum": 0, "maximum": 100},
            "input_fidelity": {"type": "string", "enum": ["low", "high"]},
            "moderation": {"type": "string"},
            "overwrite": {"type": "boolean", "default": False},
            "negative_prompt": {"type": "string", "default": ""},
            "steps": {"type": "integer", "default": 6},
            "cfg": {"type": "number", "default": 1.0},
            "seed": {"type": "integer", "default": -1},
            "filename_prefix": {"type": "string", "default": "LAN_Flux2"},
            "cwd": {"type": "string", "description": "Working directory for relative output paths."},
        },
    }

    resource_profile = ResourceProfile(
        cpu_cores=1, ram_mb=512, vram_mb=0, disk_mb=200, network_required=True
    )
    retry_policy = RetryPolicy(max_retries=2, retryable_errors=["rate_limit", "timeout"])
    idempotency_key_fields = ["prompt", "provider", "size", "model", "output_path"]
    side_effects = ["writes image files", "calls external image generation APIs"]
    user_visible_verification = ["Inspect generated image for relevance, composition, and artifacts"]

    def get_status(self) -> ToolStatus:
        config = _resolve_config()
        if config["api_key"] or config["codex_auth_token"] or config["comfyui_base_url"]:
            return ToolStatus.AVAILABLE
        if _env("COMFYUI_BACKEND_URL", "COMFYUI_URL"):
            return ToolStatus.AVAILABLE
        return ToolStatus.UNAVAILABLE

    def estimate_cost(self, inputs: dict[str, Any]) -> float:
        provider = _resolve_provider(inputs.get("provider", "auto"), _resolve_config(inputs))
        if provider == "comfyui":
            return 0.0
        quality = inputs.get("quality", "medium")
        n = inputs.get("n", 1)
        cost_map = {"low": 0.011, "medium": 0.042, "high": 0.167, "auto": 0.042}
        return cost_map.get(quality, 0.042) * n

    def execute(self, inputs: dict[str, Any]) -> ToolResult:
        start = time.time()
        config = _resolve_config(inputs)
        provider = _resolve_provider(inputs.get("provider", "auto"), config)
        cwd = Path(inputs.get("cwd") or Path.cwd()).expanduser().resolve()
        prompt = inputs.get("prompt") or _DEFAULT_PROMPT
        image_paths = list(inputs.get("image_paths") or [])
        mode = "edit" if image_paths else "generate"
        model = (inputs.get("model") or config.get("model") or _DEFAULT_MODEL).strip()
        output_format = inputs.get("output_format", "png")

        try:
            output_paths = self._resolve_output_paths(inputs, cwd, output_format)
            if provider == "codex":
                images_b64, revised_prompt = self._generate_with_codex(inputs, config, prompt)
                written = self._write_images(images_b64, output_paths, overwrite=bool(inputs.get("overwrite")))
                data = {
                    "provider": "codex",
                    "mode": mode,
                    "prompt": prompt,
                    "outputs": [str(path) for path in written],
                    "revised_prompt": revised_prompt,
                }
                model_used = config.get("codex_model") or "gpt-5.4"
            elif provider == "comfyui":
                images_b64 = self._generate_with_comfyui(inputs, config, prompt)
                written = self._write_images(images_b64, output_paths, overwrite=bool(inputs.get("overwrite")))
                data = {
                    "provider": "comfyui",
                    "mode": mode,
                    "prompt": prompt,
                    "outputs": [str(path) for path in written],
                }
                model_used = "comfyui"
            else:
                images_b64 = self._generate_with_openai(inputs, config, prompt, image_paths)
                written = self._write_images(images_b64, output_paths, overwrite=bool(inputs.get("overwrite")))
                data = {
                    "provider": "openai",
                    "mode": mode,
                    "prompt": prompt,
                    "outputs": [str(path) for path in written],
                }
                model_used = model
        except Exception as exc:
            log.exception("image_generation failed")
            return ToolResult(success=False, error=f"image_generation failed: {exc}")

        return ToolResult(
            success=True,
            data=data,
            artifacts=[str(path) for path in written],
            cost_usd=self.estimate_cost(inputs),
            duration_seconds=round(time.time() - start, 2),
            model=model_used,
        )

    def _generate_with_openai(
        self,
        inputs: dict[str, Any],
        config: dict[str, str],
        prompt: str,
        image_paths: list[str],
    ) -> list[str]:
        model = (inputs.get("model") or config.get("model") or _DEFAULT_MODEL).strip()
        api_key = config.get("api_key", "")
        base_url = config.get("base_url", "")
        if not api_key:
            raise RuntimeError(
                "OpenAI image generation API key is not configured. Set IMAGE_GENERATION_API_KEY "
                "or OPENAI_API_KEY, or choose provider='codex' or provider='comfyui'."
            )

        from openai import OpenAI

        client_kwargs: dict[str, Any] = {
            "api_key": api_key,
            "default_headers": {"Authorization": f"Bearer {api_key}"},
        }
        normalized_base_url = _normalize_openai_base_url(base_url)
        if normalized_base_url:
            client_kwargs["base_url"] = normalized_base_url
        client = OpenAI(**client_kwargs)

        if image_paths:
            image_handles = [Path(path).expanduser().resolve().open("rb") for path in image_paths]
            mask_handle = None
            mask_path = inputs.get("mask_path")
            if mask_path:
                mask_handle = Path(mask_path).expanduser().resolve().open("rb")
            try:
                payload = _image_payload(inputs, model, base_url, prompt)
                payload["image"] = image_handles if len(image_handles) > 1 else image_handles[0]
                if mask_handle is not None:
                    payload["mask"] = mask_handle
                result = client.images.edit(**payload)
            finally:
                for handle in image_handles:
                    handle.close()
                if mask_handle is not None:
                    mask_handle.close()
        else:
            payload = _image_payload(inputs, model, base_url, prompt)
            result = client.images.generate(**payload)

        return _extract_b64_images(result)

    def _generate_with_codex(
        self,
        inputs: dict[str, Any],
        config: dict[str, str],
        prompt: str,
    ) -> tuple[list[str], str | None]:
        auth_token = config.get("codex_auth_token", "")
        if not auth_token:
            raise RuntimeError(
                "Codex image generation auth is not configured. Set CODEX_AUTH_TOKEN "
                "or IMAGE_GENERATION_CODEX_AUTH_TOKEN, or use provider='openai'."
            )

        model = config.get("codex_model") or "gpt-5.4"
        codex_prompt = _codex_prompt(inputs, prompt)
        body: dict[str, Any] = {
            "model": model,
            "store": False,
            "stream": True,
            "instructions": "Generate the requested image using the hosted image_generation tool.",
            "input": [{"role": "user", "content": _codex_user_content(inputs, codex_prompt)}],
            "text": {"verbosity": "medium"},
            "tools": [{"type": "image_generation", "output_format": inputs.get("output_format", "png")}],
            "tool_choice": "auto",
            "parallel_tool_calls": False,
        }
        headers = _build_codex_headers(auth_token)
        url = _resolve_codex_url(config.get("codex_base_url", ""))

        image_results: list[str] = []
        revised_prompt: str | None = None
        with requests.post(url, headers=headers, json=body, stream=True, timeout=180) as response:
            if response.status_code >= 400:
                raise RuntimeError(response.text or f"Codex request failed: {response.status_code}")
            for event in _iter_sse_events(response):
                if event.get("type") != "response.output_item.done":
                    if event.get("type") == "response.failed":
                        raise RuntimeError(json.dumps(event.get("response") or event, ensure_ascii=False))
                    if event.get("type") == "error":
                        raise RuntimeError(json.dumps(event, ensure_ascii=False))
                    continue
                item = event.get("item")
                if not isinstance(item, dict) or item.get("type") != "image_generation_call":
                    continue
                result = item.get("result")
                if isinstance(result, str) and result:
                    image_results.append(result)
                candidate = item.get("revised_prompt")
                if isinstance(candidate, str) and candidate:
                    revised_prompt = candidate

        if not image_results:
            raise RuntimeError("Codex hosted image_generation returned no image result")
        return image_results, revised_prompt

    def _generate_with_comfyui(
        self,
        inputs: dict[str, Any],
        config: dict[str, str],
        prompt: str,
    ) -> list[str]:
        comfy_url = resolve_comfyui_base_url(config.get("comfyui_base_url"))
        return generate_images_b64(
            comfy_url,
            inputs,
            prompt,
            default_width=720,
            default_height=1280,
        )

    @staticmethod
    def _resolve_output_paths(inputs: dict[str, Any], cwd: Path, output_format: str) -> list[Path]:
        suffix = f".{output_format}"
        output_path = inputs.get("output_path")
        n = int(inputs.get("n", 1))
        if output_path:
            base = Path(output_path)
            if not base.is_absolute():
                base = cwd / base
            base = base.expanduser().resolve()
        else:
            out_dir = Path(inputs.get("output_dir", _DEFAULT_OUTPUT_DIR))
            if not out_dir.is_absolute():
                out_dir = cwd / out_dir
            out_dir = out_dir.expanduser().resolve()
            base = out_dir / f"image{suffix}"
        if base.suffix.lower() != suffix:
            base = base.with_suffix(suffix)
        if n == 1:
            return [base]
        return [base.with_name(f"{base.stem}-{idx}{base.suffix}") for idx in range(1, n + 1)]

    @staticmethod
    def _write_images(images: list[str], output_paths: list[Path], *, overwrite: bool) -> list[Path]:
        written: list[Path] = []
        for image_b64, output_path in zip(images, output_paths, strict=False):
            if output_path.exists() and not overwrite:
                raise FileExistsError(f"output already exists: {output_path} (set overwrite=true)")
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_bytes(base64.b64decode(image_b64))
            written.append(output_path)
        if not written:
            raise RuntimeError("provider returned no image data")
        return written


def _resolve_provider(requested: str, config: dict[str, str]) -> Literal["openai", "codex", "comfyui"]:
    if requested in {"openai", "codex", "comfyui"}:
        return requested  # type: ignore[return-value]
    configured = str(config.get("provider") or "auto").strip().lower()
    if configured in {"openai", "codex", "comfyui"}:
        return configured  # type: ignore[return-value]
    if config.get("codex_auth_token"):
        return "codex"
    if config.get("comfyui_base_url"):
        return "comfyui"
    return "openai"


def _normalize_openai_base_url(base_url: str | None) -> str | None:
    if not base_url:
        return None
    trimmed = base_url.strip()
    if not trimmed:
        return None
    parts = urlsplit(trimmed)
    if not parts.scheme or not parts.netloc:
        return trimmed.rstrip("/")
    path = parts.path.rstrip("/")
    if not path:
        path = "/v1"
    return urlunsplit((parts.scheme, parts.netloc, path, parts.query, parts.fragment))


def _image_payload(
    inputs: dict[str, Any],
    model: str,
    base_url: str,
    prompt: str,
) -> dict[str, Any]:
    is_siliconflow = "siliconflow" in base_url.lower() or model.startswith(
        ("Kwai-", "black-forest-labs/", "stabilityai/")
    )
    size = inputs.get("size", "auto")
    if is_siliconflow and size == "auto":
        size = "1024x1024"

    payload: dict[str, Any] = {
        "model": model,
        "prompt": prompt,
        "n": inputs.get("n", 1),
        "size": size,
    }
    if not is_siliconflow:
        payload.update(
            {
                "quality": inputs.get("quality", "medium"),
                "background": inputs.get("background"),
                "output_format": inputs.get("output_format", "png"),
                "output_compression": inputs.get("output_compression"),
                "input_fidelity": inputs.get("input_fidelity"),
                "moderation": inputs.get("moderation"),
            }
        )
    return {key: value for key, value in payload.items() if value is not None}


def _codex_prompt(inputs: dict[str, Any], prompt: str) -> str:
    lines = [prompt]
    n = int(inputs.get("n", 1))
    if n > 1:
        lines.append(f"Generate {n} distinct variants.")
    if inputs.get("image_paths"):
        lines.append("Use the attached image(s) as visual context/reference for the generation or edit.")
    return "\n".join(line for line in lines if line.strip())


def _codex_user_content(inputs: dict[str, Any], prompt: str) -> list[dict[str, str]]:
    content: list[dict[str, str]] = [{"type": "input_text", "text": prompt}]
    for path_str in inputs.get("image_paths") or []:
        path = Path(path_str).expanduser().resolve()
        media_type = _media_type_for_path(path)
        data = base64.b64encode(path.read_bytes()).decode("ascii")
        content.append({"type": "input_image", "image_url": f"data:{media_type};base64,{data}"})
    return content


def _media_type_for_path(path: Path) -> str:
    return {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".webp": "image/webp",
        ".gif": "image/gif",
    }.get(path.suffix.lower(), "image/png")


def _extract_account_id(token: str) -> str:
    parts = token.split(".")
    if len(parts) != 3:
        raise RuntimeError("Codex access token is not a valid JWT.")
    try:
        payload = json.loads(
            base64.urlsafe_b64decode(parts[1] + "=" * (-len(parts[1]) % 4)).decode("utf-8")
        )
    except Exception as exc:
        raise RuntimeError("Could not decode Codex access token payload.") from exc
    auth_claim = payload.get(_JWT_CLAIM_PATH)
    if not isinstance(auth_claim, dict):
        raise RuntimeError("Codex access token is missing account metadata.")
    account_id = auth_claim.get("chatgpt_account_id")
    if not isinstance(account_id, str) or not account_id:
        raise RuntimeError("Codex access token is missing chatgpt_account_id.")
    return account_id


def _resolve_codex_url(base_url: str | None) -> str:
    trimmed = (base_url or "").strip()
    if trimmed and "chatgpt.com/backend-api" not in trimmed:
        trimmed = ""
    raw = (trimmed or _DEFAULT_CODEX_BASE_URL).rstrip("/")
    if raw.endswith("/codex/responses"):
        return raw
    if raw.endswith("/codex"):
        return f"{raw}/responses"
    return f"{raw}/codex/responses"


def _build_codex_headers(token: str) -> dict[str, str]:
    account_id = _extract_account_id(token)
    return {
        "Authorization": f"Bearer {token}",
        "chatgpt-account-id": account_id,
        "originator": "openmontage",
        "User-Agent": f"openmontage ({platform.system().lower()} {platform.machine() or 'unknown'})",
        "OpenAI-Beta": "responses=experimental",
        "accept": "text/event-stream",
        "content-type": "application/json",
    }


def _iter_sse_events(response: requests.Response) -> Iterator[dict[str, Any]]:
    data_lines: list[str] = []
    for raw_line in response.iter_lines(decode_unicode=True):
        line = raw_line or ""
        if line == "":
            if data_lines:
                payload = "\n".join(data_lines).strip()
                data_lines = []
                if payload and payload != "[DONE]":
                    try:
                        event = json.loads(payload)
                    except json.JSONDecodeError:
                        continue
                    if isinstance(event, dict):
                        yield event
            continue
        if line.startswith("data:"):
            data_lines.append(line[5:].strip())
    if data_lines:
        payload = "\n".join(data_lines).strip()
        if payload and payload != "[DONE]":
            try:
                event = json.loads(payload)
            except json.JSONDecodeError:
                return
            if isinstance(event, dict):
                yield event


def _extract_b64_images(result: Any) -> list[str]:
    images: list[str] = []
    for item in getattr(result, "data", []) or []:
        b64 = getattr(item, "b64_json", None)
        if isinstance(b64, str) and b64:
            images.append(b64)
            continue
        url = getattr(item, "url", None)
        if isinstance(url, str):
            if url.startswith("data:image/") and ";base64," in url:
                images.append(url.split(";base64,", 1)[1])
            elif url.startswith(("http://", "https://")):
                resp = requests.get(url, timeout=30)
                resp.raise_for_status()
                images.append(base64.b64encode(resp.content).decode("utf-8"))
    return images
