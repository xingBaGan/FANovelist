"""Generate or edit raster images with configurable image generation providers."""

from __future__ import annotations

import base64
import json
import logging
from pathlib import Path
from typing import Any, Literal

import httpx
from openai import AsyncOpenAI
from pydantic import BaseModel, Field

from openharness.api.codex_client import _build_codex_headers, _resolve_codex_url
from openharness.api.openai_client import _normalize_openai_base_url
from openharness.tools.base import BaseTool, ToolExecutionContext, ToolResult

log = logging.getLogger(__name__)

_DEFAULT_PROMPT = (
    "Create a high-quality raster image that satisfies the user's request. "
    "Avoid watermarks, unintended text, and unrelated logos."
)
_DEFAULT_MODEL = "gpt-image-2"
_DEFAULT_OUTPUT_DIR = "generated_images"
ImageGenerationProvider = Literal["auto", "openai", "codex", "comfyui"]


class ImageGenerationToolInput(BaseModel):
    """Arguments for image generation or editing."""

    prompt: str = Field(default=_DEFAULT_PROMPT, description="Image generation or edit prompt.")
    provider: ImageGenerationProvider = Field(
        default="auto",
        description="Image generation provider: auto, openai, codex, or comfyui.",
    )
    image_paths: list[str] = Field(
        default_factory=list,
        description="Local image paths to edit or use as references. OpenAI provider uses image edit mode. Codex hosted generation currently treats these as visual context.",
    )
    mask_path: str | None = Field(default=None, description="Optional PNG mask path for OpenAI edit mode.")
    output_path: str | None = Field(
        default=None,
        description="Optional output path. For multiple images, numeric suffixes are added.",
    )
    output_dir: str = Field(
        default=_DEFAULT_OUTPUT_DIR,
        description="Output directory used when output_path is not provided.",
    )
    model: str | None = Field(default=None, description="OpenAI image model override.")
    n: int = Field(default=1, ge=1, le=10, description="Number of images to generate.")
    size: str = Field(default="auto", description="OpenAI image size, e.g. auto, 1024x1024, 1536x1024.")
    quality: str = Field(default="medium", description="OpenAI image quality, e.g. low, medium, high, auto.")
    background: Literal["transparent", "opaque", "auto"] | None = Field(
        default=None,
        description="Optional OpenAI background mode when supported by the provider.",
    )
    output_format: Literal["png", "jpeg", "webp"] = Field(default="png", description="Output image format.")
    output_compression: int | None = Field(
        default=None,
        ge=0,
        le=100,
        description="Optional OpenAI compression level for lossy output formats when supported.",
    )
    input_fidelity: Literal["low", "high"] | None = Field(
        default=None,
        description="Optional OpenAI edit input fidelity when supported by the provider.",
    )
    moderation: str | None = Field(default=None, description="Optional OpenAI moderation setting.")
    overwrite: bool = Field(default=False, description="Whether to overwrite existing output files.")
    negative_prompt: str = Field(default="", description="Negative prompt for ComfyUI provider.")
    steps: int = Field(default=6, description="Sampling steps for ComfyUI provider.")
    cfg: float = Field(default=1.0, description="CFG scale for ComfyUI provider.")
    seed: int = Field(default=-1, description="Random seed for ComfyUI provider (use -1 for random).")
    filename_prefix: str = Field(default="LAN_Flux2", description="Filename prefix for generated image in ComfyUI.")


class ImageGenerationTool(BaseTool):
    """Generate or edit raster images and save them to local files."""

    name = "image_generation"
    description = (
        "Generate or edit raster images using a configurable image generation provider. "
        "Use this for bitmap assets such as photos, illustrations, sprites, mockups, "
        "transparent cutouts, or edited local images. Supports provider='codex' for "
        "Codex hosted image_generation with Codex subscription auth, and provider='openai' "
        "for OpenAI-compatible key/base_url image APIs."
    )
    input_model = ImageGenerationToolInput

    async def execute(self, arguments: ImageGenerationToolInput, context: ToolExecutionContext) -> ToolResult:
        config = context.metadata.get("image_generation_config", {})
        if not isinstance(config, dict):
            config = {}
        provider = _resolve_provider(arguments.provider, config)

        mode = "edit" if arguments.image_paths else "generate"
        model = (arguments.model or str(config.get("model") or _DEFAULT_MODEL)).strip()

        try:
            output_paths = self._resolve_output_paths(arguments, context.cwd)
            if provider == "codex":
                image_b64, revised_prompt = await self._generate_with_codex(arguments, config)
                written = self._write_images(image_b64, output_paths, overwrite=arguments.overwrite)
                self._log_to_mlflow(written, arguments.prompt, model)
                extra = f"\nRevised prompt: {revised_prompt}" if revised_prompt else ""
                return ToolResult(
                    output=(
                        "[Image generation via Codex hosted image_generation]\n"
                        + "\n".join(f"Wrote {path}" for path in written)
                        + extra
                    ),
                    metadata={
                        "paths": [str(path) for path in written],
                        "provider": "codex",
                        "revised_prompt": revised_prompt,
                    },
                )
            elif provider == "comfyui":
                image_b64 = await self._generate_with_comfyui(arguments, config)
                written = self._write_images(image_b64, output_paths, overwrite=arguments.overwrite)
                self._log_to_mlflow(written, arguments.prompt, "comfyui")
                return ToolResult(
                    output=(
                        f"[Image generation via ComfyUI ({mode})]\n"
                        + "\n".join(f"Wrote {path}" for path in written)
                    ),
                    metadata={
                        "paths": [str(path) for path in written],
                        "provider": "comfyui",
                        "model": "comfyui",
                    },
                )

            image_b64 = await self._generate_with_openai(arguments, config)
            written = self._write_images(image_b64, output_paths, overwrite=arguments.overwrite)
            self._log_to_mlflow(written, arguments.prompt, model)
        except Exception as exc:
            log.exception("image_generation failed")
            return ToolResult(output=f"image_generation failed: {exc}", is_error=True)

        return ToolResult(
            output=(
                f"[Image generation via {model} ({mode}, openai)]\n"
                + "\n".join(f"Wrote {path}" for path in written)
            ),
            metadata={"paths": [str(path) for path in written], "model": model, "mode": mode, "provider": "openai"},
        )

    def _log_to_mlflow(self, paths: list[Path], prompt: str, model: str) -> None:
        try:
            import mlflow
            import os
            
            # Setup experiment
            experiment = os.environ.get("OPENHARNESS_MLFLOW_EXPERIMENT", "openharness")
            mlflow.set_experiment(experiment)
            
            active_run = mlflow.active_run()
            nested = active_run is not None
            
            # Start run (nested if a run is already active) to log parameters and artifacts
            with mlflow.start_run(run_name=f"image_generation:{model}", nested=nested) as run:
                mlflow.log_param("prompt", prompt)
                mlflow.log_param("model", model)
                
                # Log generated images as artifacts (Method 1)
                for path in paths:
                    if path.exists():
                        mlflow.log_artifact(str(path), artifact_path="generated_images")
                
                # Write a span trace to show in the MLflow Traces UI (and display the image as inline HTML / base64)
                # Check if mlflow telemetry/tracing support is active (mlflow 2.14+)
                if hasattr(mlflow, "start_span"):
                    span_name = f"image_generation:{model}"
                    with mlflow.start_span(name=span_name, span_type="TOOL") as span:
                        span.set_inputs({
                            "prompt": prompt,
                            "model": model,
                        })
                        outputs = []
                        for path in paths:
                            if path.exists():
                                data = base64.b64encode(path.read_bytes()).decode("ascii")
                                # Embed HTML img inside the trace outputs so it displays directly in the UI
                                outputs.append({
                                    "file_path": str(path),
                                    "image_html": f'<img src="data:image/png;base64,{data}" width="300" style="border-radius: 8px;" />'
                                })
                        span.set_outputs({"images": outputs})
        except Exception:
            pass

    async def _generate_with_openai(self, arguments: ImageGenerationToolInput, config: dict[str, object]) -> list[str]:
        model = (arguments.model or str(config.get("model") or _DEFAULT_MODEL)).strip()
        api_key = str(config.get("api_key") or "").strip()
        base_url = str(config.get("base_url") or "").strip()
        if not api_key:
            raise RuntimeError(
                "OpenAI image generation API key is not configured. Set image_generation.api_key "
                "or OPENHARNESS_IMAGE_GENERATION_API_KEY, or choose provider='codex'."
            )
        if arguments.image_paths:
            return await self._edit_images(arguments, model, api_key, base_url)
        return await self._generate_images(arguments, model, api_key, base_url)

    async def _generate_with_codex(
        self,
        arguments: ImageGenerationToolInput,
        config: dict[str, object],
    ) -> tuple[list[str], str | None]:
        auth_token = str(config.get("codex_auth_token") or "").strip()
        if not auth_token:
            raise RuntimeError(
                "Codex image generation auth is not configured. Run 'oh auth codex-login' "
                "or use provider='openai' with OPENHARNESS_IMAGE_GENERATION_API_KEY."
            )
        model = str(config.get("codex_model") or "gpt-5.4").strip() or "gpt-5.4"
        base_url = str(config.get("codex_base_url") or "").strip()
        prompt = _codex_prompt(arguments)
        body: dict[str, Any] = {
            "model": model,
            "store": False,
            "stream": True,
            "instructions": "Generate the requested image using the hosted image_generation tool.",
            "input": [{"role": "user", "content": _codex_user_content(arguments, prompt)}],
            "text": {"verbosity": "medium"},
            "tools": [{"type": "image_generation", "output_format": arguments.output_format}],
            "tool_choice": "auto",
            "parallel_tool_calls": False,
        }
        headers = _build_codex_headers(auth_token)
        url = _resolve_codex_url(base_url)

        image_results: list[str] = []
        revised_prompt: str | None = None
        async with httpx.AsyncClient(timeout=180.0, follow_redirects=True) as client:
            async with client.stream("POST", url, headers=headers, json=body) as response:
                if response.status_code >= 400:
                    payload = await response.aread()
                    raise RuntimeError(payload.decode("utf-8", "replace") or f"Codex request failed: {response.status_code}")
                async for event in _iter_sse_events(response):
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

    async def _generate_with_comfyui(
        self,
        arguments: ImageGenerationToolInput,
        config: dict[str, object],
    ) -> list[str]:
        import os
        comfy_url = (
            str(config.get("comfyui_base_url") or "").strip()
            or os.environ.get("COMFYUI_BACKEND_URL", "").strip()
            or os.environ.get("COMFYUI_URL", "").strip()
            or "http://127.0.0.1:8190"
        )
        if comfy_url.endswith("/"):
            comfy_url = comfy_url[:-1]

        # Parse size parameter (e.g. "720x1280", "1024x1024")
        width = 720
        height = 1280
        if arguments.size and arguments.size != "auto":
            parts = arguments.size.split("x")
            if len(parts) == 2:
                try:
                    width = int(parts[0])
                    height = int(parts[1])
                except ValueError:
                    pass

        payload = {
            "prompt": arguments.prompt,
            "negative_prompt": arguments.negative_prompt or "",
            "width": width,
            "height": height,
            "steps": arguments.steps,
            "cfg": arguments.cfg,
            "seed": arguments.seed,
            "filename_prefix": arguments.filename_prefix or "LAN_Flux2",
            "wait": True,
        }

        async with httpx.AsyncClient(timeout=600.0) as client:
            resp = await client.post(f"{comfy_url}/generate", json=payload)
            resp.raise_for_status()
            data = resp.json()

            images_info = data.get("images", [])
            b64_results: list[str] = []
            for img in images_info:
                filename = img.get("filename")
                subfolder = img.get("subfolder", "")
                type_ = img.get("type", "output")

                img_url = f"{comfy_url}/image?filename={filename}&subfolder={subfolder}&type={type_}"
                img_resp = await client.get(img_url)
                img_resp.raise_for_status()

                b64_data = base64.b64encode(img_resp.content).decode("utf-8")
                b64_results.append(b64_data)

            return b64_results

    @staticmethod
    async def _generate_images(arguments: ImageGenerationToolInput, model: str, api_key: str, base_url: str) -> list[str]:
        client = AsyncOpenAI(
            api_key=api_key,
            base_url=_normalize_openai_base_url(base_url),
            default_headers={"Authorization": f"Bearer {api_key}"},
        )
        result = await client.images.generate(**_image_payload(arguments, model, base_url))
        return await _extract_b64_images(result)

    @staticmethod
    async def _edit_images(arguments: ImageGenerationToolInput, model: str, api_key: str, base_url: str) -> list[str]:
        client = AsyncOpenAI(
            api_key=api_key,
            base_url=_normalize_openai_base_url(base_url),
            default_headers={"Authorization": f"Bearer {api_key}"},
        )
        image_handles = [Path(path).expanduser().resolve().open("rb") for path in arguments.image_paths]
        mask_handle = Path(arguments.mask_path).expanduser().resolve().open("rb") if arguments.mask_path else None
        try:
            payload = _image_payload(arguments, model, base_url)
            payload["image"] = image_handles if len(image_handles) > 1 else image_handles[0]
            if mask_handle is not None:
                payload["mask"] = mask_handle
            result = await client.images.edit(**payload)
        finally:
            for handle in image_handles:
                handle.close()
            if mask_handle is not None:
                mask_handle.close()
        return await _extract_b64_images(result)

    @staticmethod
    def _resolve_output_paths(arguments: ImageGenerationToolInput, cwd: Path) -> list[Path]:
        suffix = f".{arguments.output_format}"
        if arguments.output_path:
            base = Path(arguments.output_path)
            if not base.is_absolute():
                base = cwd / base
            base = base.expanduser().resolve()
        else:
            out_dir = Path(arguments.output_dir)
            if not out_dir.is_absolute():
                out_dir = cwd / out_dir
            out_dir = out_dir.expanduser().resolve()
            base = out_dir / f"image{suffix}"
        if base.suffix.lower() != suffix:
            base = base.with_suffix(suffix)
        if arguments.n == 1:
            return [base]
        return [base.with_name(f"{base.stem}-{idx}{base.suffix}") for idx in range(1, arguments.n + 1)]

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


def _resolve_provider(requested: str, config: dict[str, object]) -> Literal["openai", "codex", "comfyui"]:
    if requested in {"openai", "codex", "comfyui"}:
        return requested  # type: ignore[return-value]
    configured = str(config.get("provider") or "auto").strip().lower()
    if configured in {"openai", "codex", "comfyui"}:
        return configured  # type: ignore[return-value]
    if str(config.get("codex_auth_token") or "").strip():
        return "codex"
    if str(config.get("comfyui_base_url") or "").strip():
        return "comfyui"
    return "openai"


def _image_payload(arguments: ImageGenerationToolInput, model: str, base_url: str = "") -> dict[str, Any]:
    is_siliconflow = "siliconflow" in base_url.lower() or model.startswith(("Kwai-", "black-forest-labs/", "stabilityai/"))
    
    size = arguments.size
    if is_siliconflow and size == "auto":
        size = "1024x1024"

    payload: dict[str, Any] = {
        "model": model,
        "prompt": arguments.prompt,
        "n": arguments.n,
        "size": size,
    }

    if not is_siliconflow:
        payload.update({
            "quality": arguments.quality,
            "background": arguments.background,
            "output_format": arguments.output_format,
            "output_compression": arguments.output_compression,
            "input_fidelity": arguments.input_fidelity,
            "moderation": arguments.moderation,
        })

    return {key: value for key, value in payload.items() if value is not None}


def _codex_prompt(arguments: ImageGenerationToolInput) -> str:
    lines = [arguments.prompt]
    if arguments.n > 1:
        lines.append(f"Generate {arguments.n} distinct variants.")
    if arguments.image_paths:
        lines.append("Use the attached image(s) as visual context/reference for the generation or edit.")
    return "\n".join(line for line in lines if line.strip())


def _codex_user_content(arguments: ImageGenerationToolInput, prompt: str) -> list[dict[str, str]]:
    content = [{"type": "input_text", "text": prompt}]
    for path_str in arguments.image_paths:
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


async def _iter_sse_events(response: httpx.Response):
    data_lines: list[str] = []
    async for line in response.aiter_lines():
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


async def _extract_b64_images(result: Any) -> list[str]:
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
                async with httpx.AsyncClient(timeout=30.0) as client:
                    resp = await client.get(url)
                    resp.raise_for_status()
                    images.append(base64.b64encode(resp.content).decode("utf-8"))
    return images
