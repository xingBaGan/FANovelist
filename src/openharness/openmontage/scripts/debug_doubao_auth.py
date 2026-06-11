#!/usr/bin/env python3
"""
Local Doubao auth/payload probe (safe logging).

Usage:
  uv run python scripts/debug_doubao_auth.py

What it does:
1) Loads .env (override=True)
2) Prints key formatting diagnostics (redacted)
3) Sends a few minimal payload variants to /api/v3/tts/submit
4) Prints status + response JSON (with key redacted)
"""

from __future__ import annotations

import json
import os
import uuid
from pathlib import Path
from typing import Any

import requests
from dotenv import load_dotenv


SUBMIT_URL = "https://openspeech.bytedance.com/api/v3/tts/submit"
RESOURCE_ID = "seed-tts-2.0"


def redact(text: str, secret: str | None) -> str:
    if not secret:
        return text
    return text.replace(secret, "[redacted]")


def print_key_diagnostics(api_key: str, voice: str) -> None:
    print("== Env diagnostics ==")
    print(f"DOUBAO_SPEECH_API_KEY set: {bool(api_key)}")
    print(f"DOUBAO_SPEECH_API_KEY length: {len(api_key) if api_key else 0}")
    starts_quote = api_key.startswith(('"', "'")) if api_key else False
    ends_quote = api_key.endswith(('"', "'")) if api_key else False
    print(f"DOUBAO key starts with quote: {starts_quote}")
    print(f"DOUBAO key ends with quote: {ends_quote}")
    print(f"DOUBAO key has whitespace: {any(c.isspace() for c in api_key) if api_key else False}")
    if api_key:
        print(f"DOUBAO key prefix/suffix: {api_key[:4]}*** / ***{api_key[-4:]}")
        if api_key.startswith("ark-"):
            print("hint: key looks like ModelArk/LLM key (ark-*), not always valid for openspeech TTS")
    print(f"DOUBAO_SPEECH_VOICE_TYPE set: {bool(voice)}")
    print(f"DOUBAO_SPEECH_VOICE_TYPE length: {len(voice) if voice else 0}")
    print()


def post_variant(api_key: str, body: dict[str, Any]) -> tuple[int, dict[str, Any] | str]:
    headers = {
        "X-Api-Key": api_key,
        "X-Api-Resource-Id": RESOURCE_ID,
        "X-Api-Request-Id": str(uuid.uuid4()),
        "Content-Type": "application/json",
    }
    response = requests.post(SUBMIT_URL, headers=headers, json=body, timeout=20)
    try:
        return response.status_code, response.json()
    except ValueError:
        return response.status_code, response.text[:1000]


def main() -> None:
    load_dotenv(Path(".env"), override=True)

    api_key = os.getenv("DOUBAO_SPEECH_API_KEY", "")
    voice = os.getenv("DOUBAO_SPEECH_VOICE_TYPE", "")

    print_key_diagnostics(api_key, voice)

    if not api_key:
        print("Missing DOUBAO_SPEECH_API_KEY in .env")
        return
    if not voice:
        print("Missing DOUBAO_SPEECH_VOICE_TYPE in .env")
        return

    variants: dict[str, dict[str, Any]] = {
        "v1_tool_shape": {
            "user": {"uid": "openmontage"},
            "unique_id": str(uuid.uuid4()),
            "req_params": {
                "text": "测试",
                "speaker": voice,
                "audio_params": {
                    "format": "mp3",
                    "sample_rate": 24000,
                    "speech_rate": 0,
                    "enable_timestamp": True,
                },
                "additions": json.dumps({"disable_markdown_filter": False}, ensure_ascii=False),
            },
        },
        "v2_flat_minimal": {
            "input": "测试",
            "voice_type": voice,
        },
        "v3_flat_with_audio_config": {
            "input": "测试",
            "voice_type": voice,
            "audio_config": {"format": "mp3", "sample_rate": 24000},
        },
    }

    print("== Submit probes ==")
    for name, body in variants.items():
        status, payload = post_variant(api_key, body)
        if isinstance(payload, dict):
            out = json.dumps(payload, ensure_ascii=False)
        else:
            out = payload
        print(f"\n--- {name} ---")
        print(f"status: {status}")
        print(redact(out, api_key))


if __name__ == "__main__":
    main()
