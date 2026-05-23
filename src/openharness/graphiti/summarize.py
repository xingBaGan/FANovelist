"""Paragraph summarization for Graphiti episodes."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
import logging
import os
from openai import AsyncOpenAI

logger = logging.getLogger(__name__)

Summarizer = Callable[[str], Awaitable[str]]


async def passthrough_summarizer(text: str) -> str:
    """Use normalized paragraph text as episode body (tests / fallback)."""
    return " ".join(text.split()).strip()[:2000]


async def openai_summarizer(text: str) -> str:
    """Summarize paragraph using OpenAI, preserving input language."""
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise ValueError("OPENAI_API_KEY environment variable is not set")

    model = os.environ.get("OPENAI_MODEL", "gpt-4o")
    async with AsyncOpenAI(api_key=api_key) as client:
        system_prompt = (
            "You are a professional novel editor.\n"
            "Summarize the following paragraph of a novel concisely, focusing on characters, actions, events, settings, and key plot developments.\n"
            "CRITICAL: The summary MUST be in the exact same language as the input text. If the input is in English, summarize in English. If the input is in Chinese, summarize in Chinese. Do NOT translate the text.\n"
            "Output ONLY the summary itself, without any introductory or concluding text, prefix, or markdown formatting."
        )

        logger.debug("Summarizing paragraph of length %d using model %s...", len(text), model)

        try:
            response = await client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": text},
                ],
                temperature=0.3,
            )
        except Exception as exc:
            logger.exception("Failed to summarize paragraph via OpenAI API: %s", exc)
            raise

    summary = response.choices[0].message.content
    if summary is None:
        logger.warning("OpenAI API returned an empty completion content.")
        return ""
    
    summary = summary.strip()
    logger.debug("Generated summary of length %d: %s", len(summary), summary)
    return summary


