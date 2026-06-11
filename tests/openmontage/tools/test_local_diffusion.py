"""Tests for ComfyUI-backed local_diffusion tool."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[3] / "src" / "openharness" / "openmontage"
sys.path.insert(0, str(PROJECT_ROOT))

from openharness.openmontage.tools.graphics.local_diffusion import LocalDiffusion


class TestLocalDiffusion:
    def test_unavailable_without_env(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.delenv("COMFYUI_BACKEND_URL", raising=False)
        monkeypatch.delenv("COMFYUI_URL", raising=False)
        tool = LocalDiffusion()
        assert tool.get_status().value == "unavailable"

    def test_available_with_backend_url(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("COMFYUI_BACKEND_URL", "http://192.168.0.112:8190")
        tool = LocalDiffusion()
        assert tool.get_status().value == "available"

    def test_execute_requires_backend(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.delenv("COMFYUI_BACKEND_URL", raising=False)
        monkeypatch.delenv("COMFYUI_URL", raising=False)
        tool = LocalDiffusion()
        result = tool.execute({"prompt": "a classroom"})
        assert not result.success
        assert "ComfyUI backend is not configured" in (result.error or "")

    def test_execute_writes_image(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
        monkeypatch.setenv("COMFYUI_BACKEND_URL", "http://192.168.0.112:8190")

        def fake_generate(base_url, inputs, prompt, **kwargs):
            assert base_url == "http://192.168.0.112:8190"
            assert prompt == "a cozy classroom"
            assert inputs["width"] == 1280
            assert inputs["height"] == 720
            return [b"fake-png"]

        with patch("openharness.openmontage.tools.graphics.local_diffusion.generate_images_bytes", fake_generate):
            tool = LocalDiffusion()
            result = tool.execute(
                {
                    "prompt": "a cozy classroom",
                    "width": 1280,
                    "height": 720,
                    "output_path": str(tmp_path / "scene.png"),
                }
            )

        assert result.success
        assert (tmp_path / "scene.png").read_bytes() == b"fake-png"
        assert result.data["provider"] == "comfyui"
        assert result.data["backend"] == "http://192.168.0.112:8190"
