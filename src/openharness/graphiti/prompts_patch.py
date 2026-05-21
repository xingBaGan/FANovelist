"""Patch graphiti-core prompts so summaries/facts match source language."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

_PATCHED = False

_LANG_RULE = (
    "\n\nLANGUAGE: Use the same language as the source text in MESSAGES/CURRENT_MESSAGE. "
    "Chinese input → Chinese output only; do not use English."
)


def _wrap_user_suffix(fn: Callable[[dict[str, Any]], list[Any]]) -> Callable[[dict[str, Any]], list[Any]]:
    def wrapped(context: dict[str, Any]) -> list[Any]:
        messages = fn(context)
        out: list[Any] = []
        for msg in messages:
            if getattr(msg, "role", None) == "user":
                out.append(type(msg)(role=msg.role, content=msg.content + _LANG_RULE))
            else:
                out.append(msg)
        return out

    return wrapped


def apply_novel_language_prompt_patches() -> None:
    """Idempotent: extend Graphiti summary prompts for novel Chinese canon."""
    global _PATCHED
    if _PATCHED:
        return
    from graphiti_core.prompts.lib import prompt_library

    prompt_library.extract_nodes.extract_summary = _wrap_user_suffix(
        prompt_library.extract_nodes.extract_summary
    )
    prompt_library.extract_nodes.extract_summaries_batch = _wrap_user_suffix(
        prompt_library.extract_nodes.extract_summaries_batch
    )
    _PATCHED = True
