"""Tests for the image_generation tool."""

from __future__ import annotations

import base64
import json
import sys
from io import BytesIO
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[3] / "src" / "openharness" / "openmontage"
sys.path.insert(0, str(PROJECT_ROOT))

from openharness.openmontage.tools.graphics.image_generation import ImageGeneration, _resolve_config


def _b64url(data: dict[str, object]) -> str:
    raw = json.dumps(data, separators=(",", ":")).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _fake_codex_token() -> str:
    payload = {"https://api.openai.com/auth": {"chatgpt_account_id": "acct_test"}}
    return f"{_b64url({'alg': 'none', 'typ': 'JWT'})}.{_b64url(payload)}.sig"


class TestImageGenerationContracts:
    def test_identity(self):
        tool = ImageGeneration()
        info = tool.get_info()
        assert info["name"] == "image_generation"
        assert info["capability"] == "image_generation"

    def test_discoverable(self):
        from openharness.openmontage.tools.tool_registry import ToolRegistry

        reg = ToolRegistry()
        reg.discover("openharness.openmontage.tools")
        assert reg.get("image_generation") is not None


class TestResolveConfig:
    def test_openai_env(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("IMAGE_GENERATION_PROVIDER", "openai")
        monkeypatch.setenv("IMAGE_GENERATION_MODEL", "gpt-image-1")
        monkeypatch.setenv("IMAGE_GENERATION_API_KEY", "sk-test")
        monkeypatch.setenv("IMAGE_GENERATION_BASE_URL", "https://example.test/v1")

        cfg = _resolve_config()
        assert cfg["provider"] == "openai"
        assert cfg["model"] == "gpt-image-1"
        assert cfg["api_key"] == "sk-test"
        assert cfg["base_url"] == "https://example.test/v1"

    def test_siliconflow_fallback(self, monkeypatch: pytest.MonkeyPatch):
        for var in (
            "IMAGE_GENERATION_API_KEY",
            "OPENAI_API_KEY",
            "OPENMONTAGE_IMAGE_GENERATION_API_KEY",
            "OPENHARNESS_IMAGE_GENERATION_API_KEY",
        ):
            monkeypatch.delenv(var, raising=False)
        monkeypatch.setenv("SILICONFLOW_API_KEY", "sk-silicon")

        cfg = _resolve_config()
        assert cfg["api_key"] == "sk-silicon"
        assert cfg["base_url"] == "https://api.siliconflow.cn/v1"

    def test_comfyui_env(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("COMFYUI_BACKEND_URL", "http://remote-comfy:8190")
        cfg = _resolve_config()
        assert cfg["comfyui_base_url"] == "http://remote-comfy:8190"


class TestExecute:
    def test_requires_api_key_for_openai(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
        monkeypatch.chdir(tmp_path)
        for key in (
            "IMAGE_GENERATION_API_KEY",
            "OPENAI_API_KEY",
            "OPENMONTAGE_IMAGE_GENERATION_API_KEY",
            "OPENHARNESS_IMAGE_GENERATION_API_KEY",
            "SILICONFLOW_API_KEY",
            "CODEX_AUTH_TOKEN",
            "COMFYUI_BACKEND_URL",
            "COMFYUI_URL",
        ):
            monkeypatch.delenv(key, raising=False)

        tool = ImageGeneration()
        result = tool.execute({"prompt": "a cat", "provider": "openai"})
        assert not result.success
        assert "API key is not configured" in (result.error or "")

    def test_generate_writes_file(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
        image_bytes = b"fake-png"
        image_b64 = base64.b64encode(image_bytes).decode("ascii")

        def fake_generate_with_openai(self, inputs, config, prompt, image_paths):
            assert prompt == "a cat"
            assert config["api_key"] == "test-key"
            return [image_b64]

        monkeypatch.setattr(ImageGeneration, "_generate_with_openai", fake_generate_with_openai)
        monkeypatch.setenv("IMAGE_GENERATION_API_KEY", "test-key")
        monkeypatch.setenv("IMAGE_GENERATION_MODEL", "gpt-image-2")

        tool = ImageGeneration()
        result = tool.execute(
            {
                "prompt": "a cat",
                "output_path": "assets/cat.png",
                "provider": "openai",
                "cwd": str(tmp_path),
            }
        )

        out = tmp_path / "assets" / "cat.png"
        assert result.success
        assert out.read_bytes() == image_bytes
        assert result.artifacts == [str(out)]

    def test_codex_provider(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
        image_bytes = b"codex-png"
        image_b64 = base64.b64encode(image_bytes).decode("ascii")

        def fake_generate_with_codex(self, inputs, config, prompt):
            return [image_b64], "blue icon"

        monkeypatch.setattr(ImageGeneration, "_generate_with_codex", fake_generate_with_codex)
        monkeypatch.setenv("CODEX_AUTH_TOKEN", _fake_codex_token())

        tool = ImageGeneration()
        result = tool.execute(
            {
                "prompt": "a blue icon",
                "provider": "codex",
                "output_path": "codex.png",
                "cwd": str(tmp_path),
            }
        )

        assert result.success
        assert (tmp_path / "codex.png").read_bytes() == image_bytes
        assert result.data["revised_prompt"] == "blue icon"

    def test_comfyui_provider(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
        image_bytes = b"comfyui-png"
        image_b64 = base64.b64encode(image_bytes).decode("ascii")

        def fake_generate_with_comfyui(self, inputs, config, prompt):
            assert prompt == "a cat"
            assert config["comfyui_base_url"] == "http://remote-comfy:8190"
            return [image_b64]

        monkeypatch.setattr(ImageGeneration, "_generate_with_comfyui", fake_generate_with_comfyui)
        monkeypatch.setenv("COMFYUI_BACKEND_URL", "http://remote-comfy:8190")

        tool = ImageGeneration()
        result = tool.execute(
            {
                "prompt": "a cat",
                "negative_prompt": "dogs",
                "steps": 10,
                "cfg": 2.5,
                "seed": 42,
                "filename_prefix": "test_prefix",
                "output_path": "comfy.png",
                "provider": "comfyui",
                "cwd": str(tmp_path),
            }
        )

        assert result.success
        assert (tmp_path / "comfy.png").read_bytes() == image_bytes
        assert result.data["provider"] == "comfyui"

    def test_overwrite_guard(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
        out = tmp_path / "hero.png"
        out.write_bytes(b"existing")

        def fake_generate_with_openai(self, inputs, config, prompt, image_paths):
            return [base64.b64encode(b"new").decode("ascii")]

        monkeypatch.setattr(ImageGeneration, "_generate_with_openai", fake_generate_with_openai)
        monkeypatch.setenv("IMAGE_GENERATION_API_KEY", "test")

        tool = ImageGeneration()
        result = tool.execute(
            {
                "prompt": "a cat",
                "output_path": str(out),
                "provider": "openai",
                "cwd": str(tmp_path),
            }
        )

        assert not result.success
        assert "output already exists" in (result.error or "")
        assert out.read_bytes() == b"existing"


def test_resolve_output_paths_multiple(tmp_path: Path):
    paths = ImageGeneration._resolve_output_paths(
        {"output_path": "hero.png", "n": 2},
        tmp_path,
        "png",
    )
    assert paths == [tmp_path / "hero-1.png", tmp_path / "hero-2.png"]
