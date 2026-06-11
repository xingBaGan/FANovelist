"""Paragraph summarization for Graphiti episodes."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
import logging
import os
from openai import AsyncOpenAI

from openharness.graphiti.observability import log_llm_call

logger = logging.getLogger(__name__)

Summarizer = Callable[[str], Awaitable[str]]


async def passthrough_summarizer(text: str) -> str:
    """Use normalized paragraph text as episode body (tests / fallback)."""
    return " ".join(text.split()).strip()[:2000]


async def openai_summarizer(text: str) -> str:
    """Summarize paragraph using DeepSeek or fallback OpenAI endpoint, preserving input language."""
    api_key = os.environ.get("XIAOMI_API_KEY")
    base_url = None
    model = os.environ.get("XIAOMI_MODEL", "mimo-v2-pro")

    if api_key:
        base_url = "https://api.xiaomimimo.com/v1"
    else:
        api_key = os.environ.get("DEEPSEEK_API_KEY")
        if api_key:
            base_url = "https://api.deepseek.com"
            model = os.environ.get("DEEPSEEK_MODEL", "deepseek-v4-flash")
        else:
            api_key = os.environ.get("OPENAI_API_KEY")
            if api_key:
                model = os.environ.get("OPENAI_MODEL", "gpt-4o")
            else:
                raise ValueError("DEEPSEEK_API_KEY environment variable is not set (and OPENAI_API_KEY and XIAOMI_API_KEY are not set)")

    client_kwargs = {"api_key": api_key}
    if base_url:
        client_kwargs["base_url"] = base_url

    async with AsyncOpenAI(**client_kwargs) as client:
        system_prompt = (
            "You are a professional novel editor.\n"
            "Summarize the following paragraph of a novel concisely, focusing on characters, actions, events, settings, and key plot developments.\n"
            "CRITICAL: The summary MUST be in the exact same language as the input text. If the input is in English, summarize in English. If the input is in Chinese, summarize in Chinese. Do NOT translate the text.\n"
            "Output ONLY the summary itself, without any introductory or concluding text, prefix, or markdown formatting."
        )

        logger.debug("Summarizing paragraph of length %d using model %s...", len(text), model)

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": text},
        ]
        try:
            response = await client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=0.3,
            )
        except Exception as exc:
            logger.exception("Failed to summarize paragraph via OpenAI API: %s", exc)
            raise

    summary = response.choices[0].message.content or ""
    log_llm_call(
        None,
        name="summarize_paragraph",
        model=model,
        messages=messages,
        response_content=summary,
        usage=response.usage,
    )
    if summary is None:
        logger.warning("OpenAI API returned an empty completion content.")
        return ""
    
    summary = summary.strip()
    logger.debug("Generated summary of length %d: %s", len(summary), summary)
    return summary


async def openai_batch_summarizer(texts: list[str]) -> list[str]:
    """Summarize a list of paragraphs in a single batch LLM call."""
    if not texts:
        return []

    import json

    api_key = os.environ.get("XIAOMI_API_KEY")
    base_url = None
    model = os.environ.get("XIAOMI_MODEL", "mimo-v2-pro")

    if api_key:
        base_url = "https://api.xiaomimimo.com/v1"
    else:
        api_key = os.environ.get("DEEPSEEK_API_KEY")
        if api_key:
            base_url = "https://api.deepseek.com"
            model = os.environ.get("DEEPSEEK_MODEL", "deepseek-chat")
        else:
            api_key = os.environ.get("OPENAI_API_KEY")
            if api_key:
                model = os.environ.get("OPENAI_MODEL", "gpt-4o")
            else:
                raise ValueError("Neither XIAOMI_API_KEY, DEEPSEEK_API_KEY, nor OPENAI_API_KEY environment variable is set")

    system_prompt = (
        "You are a professional novel editor.\n"
        f"You will be given exactly {len(texts)} paragraphs from a novel. Summarize each paragraph concisely and independently, focusing on characters, actions, events, settings, and key plot developments.\n"
        "CRITICAL:\n"
        f"1. You MUST return exactly {len(texts)} summaries in the 'summaries' list. Do not combine, skip, or merge any paragraphs. Every input paragraph must have a corresponding summary.\n"
        "2. The summary for each paragraph MUST be in the exact same language as the input text (e.g. Chinese paragraphs must have Chinese summaries).\n"
        "3. Keep the summaries in the exact same order as the input list.\n"
        "4. Return the summaries as a JSON object matching this schema:\n"
        "{\n"
        "  \"summaries\": [\n"
        "    \"concise summary of paragraph 1\",\n"
        "    \"concise summary of paragraph 2\",\n"
        "    ...\n"
        "  ]\n"
        "}"
    )

    user_content = json.dumps({"paragraphs": texts}, ensure_ascii=False)
    client_kwargs = {"api_key": api_key}
    if base_url:
        client_kwargs["base_url"] = base_url

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_content},
    ]
    try:
        async with AsyncOpenAI(**client_kwargs) as client:
            response = await client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=0.3,
                response_format={"type": "json_object"},
            )
            result_str = response.choices[0].message.content or "{}"
            log_llm_call(
                None,
                name="summarize_batch",
                model=model,
                messages=messages,
                response_content=result_str,
                usage=response.usage,
            )
            result_json = json.loads(result_str)
            summaries = result_json.get("summaries", [])

            if len(summaries) != len(texts):
                logger.warning(
                    "Batch summarizer returned mismatched count: expected %d, got %d. Falling back to sequential.",
                    len(texts),
                    len(summaries)
                )
                return [await openai_summarizer(t) for t in texts]
            return [s.strip() for s in summaries]

    except Exception as exc:
        logger.warning("Failed to batch summarize paragraphs: %s. Falling back to sequential.", exc)
        return [await openai_summarizer(t) for t in texts]


