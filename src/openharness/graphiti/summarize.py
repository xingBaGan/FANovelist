"""Paragraph summarization for Graphiti episodes."""

from __future__ import annotations

from collections.abc import Awaitable, Callable

Summarizer = Callable[[str], Awaitable[str]]


async def passthrough_summarizer(text: str) -> str:
    """Use normalized paragraph text as episode body (tests / fallback)."""
    return " ".join(text.split()).strip()[:2000]
