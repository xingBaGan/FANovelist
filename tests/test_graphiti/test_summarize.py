"""Tests for openai_summarizer in graphiti."""

import os
from unittest.mock import AsyncMock, patch
import pytest

from openharness.graphiti.summarize import openai_summarizer


@pytest.mark.asyncio
async def test_openai_summarizer_success() -> None:
    # Set the key temporarily in the test
    with patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}, clear=True):
        mock_response = AsyncMock()
        mock_response.choices = [
            AsyncMock(message=AsyncMock(content="李默决定离开门派，下山历练。"))
        ]

        with patch("openharness.graphiti.summarize.AsyncOpenAI") as mock_openai_cls:
            mock_client = AsyncMock()
            mock_openai_cls.return_value.__aenter__.return_value = mock_client
            mock_client.chat.completions.create.return_value = mock_response

            paragraph = "李默收拾好包袱，看了一眼居住了十年的破旧木屋，拂袖而去，踏上了下山的小路。"
            result = await openai_summarizer(paragraph)

            assert result == "李默决定离开门派，下山历练。"
            mock_openai_cls.assert_called_once_with(api_key="test-key")
            mock_client.chat.completions.create.assert_called_once()

            # Check system prompt and model
            call_kwargs = mock_client.chat.completions.create.call_args.kwargs
            assert call_kwargs["model"] == "gpt-4o"
            assert call_kwargs["messages"][0]["role"] == "system"
            assert "same language" in call_kwargs["messages"][0]["content"]
            assert call_kwargs["messages"][1]["content"] == paragraph


@pytest.mark.asyncio
async def test_openai_summarizer_custom_model() -> None:
    with patch.dict(os.environ, {"OPENAI_API_KEY": "test-key", "OPENAI_MODEL": "gpt-4o-mini"}, clear=True):
        mock_response = AsyncMock()
        mock_response.choices = [
            AsyncMock(message=AsyncMock(content="Summary content."))
        ]

        with patch("openharness.graphiti.summarize.AsyncOpenAI") as mock_openai_cls:
            mock_client = AsyncMock()
            mock_openai_cls.return_value.__aenter__.return_value = mock_client
            mock_client.chat.completions.create.return_value = mock_response

            result = await openai_summarizer("Some paragraph")
            assert result == "Summary content."

            call_kwargs = mock_client.chat.completions.create.call_args.kwargs
            assert call_kwargs["model"] == "gpt-4o-mini"


@pytest.mark.asyncio
async def test_openai_summarizer_missing_key() -> None:
    with patch.dict(os.environ, {}, clear=True):
        if "OPENAI_API_KEY" in os.environ:
            del os.environ["OPENAI_API_KEY"]
        with pytest.raises(ValueError, match="DEEPSEEK_API_KEY environment variable is not set"):
            await openai_summarizer("Some paragraph")


@pytest.mark.asyncio
async def test_openai_batch_summarizer_success() -> None:
    from openharness.graphiti.summarize import openai_batch_summarizer
    import json

    with patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}, clear=True):
        mock_response = AsyncMock()
        mock_response.choices = [
            AsyncMock(message=AsyncMock(content=json.dumps({"summaries": ["Summary A", "Summary B"]})))
        ]

        with patch("openharness.graphiti.summarize.AsyncOpenAI") as mock_openai_cls:
            mock_client = AsyncMock()
            mock_openai_cls.return_value.__aenter__.return_value = mock_client
            mock_client.chat.completions.create.return_value = mock_response

            paragraphs = ["Paragraph A", "Paragraph B"]
            result = await openai_batch_summarizer(paragraphs)

            assert result == ["Summary A", "Summary B"]
            mock_openai_cls.assert_called_once_with(api_key="test-key")
            mock_client.chat.completions.create.assert_called_once()


@pytest.mark.asyncio
async def test_openai_batch_summarizer_mismatch_fallback() -> None:
    from openharness.graphiti.summarize import openai_batch_summarizer
    import json

    with patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}, clear=True):
        mock_response = AsyncMock()
        # Return only one summary instead of two (mismatch)
        mock_response.choices = [
            AsyncMock(message=AsyncMock(content=json.dumps({"summaries": ["Summary AOnly"]})))
        ]

        mock_seq_response = AsyncMock()
        mock_seq_response.choices = [
            AsyncMock(message=AsyncMock(content="Fallback Summary"))
        ]

        with patch("openharness.graphiti.summarize.AsyncOpenAI") as mock_openai_cls:
            mock_client = AsyncMock()
            mock_openai_cls.return_value.__aenter__.return_value = mock_client
            # First call is batch, subsequent calls are sequential fallback
            mock_client.chat.completions.create.side_effect = [
                mock_response,
                mock_seq_response,
                mock_seq_response,
            ]

            paragraphs = ["Paragraph A", "Paragraph B"]
            result = await openai_batch_summarizer(paragraphs)

            assert result == ["Fallback Summary", "Fallback Summary"]
            assert mock_client.chat.completions.create.call_count == 3


@pytest.mark.asyncio
async def test_xiaomi_summarizer_priority() -> None:
    from openharness.graphiti.summarize import openai_summarizer, openai_batch_summarizer
    import json

    # Test single summarizer priority
    with patch.dict(os.environ, {
        "XIAOMI_API_KEY": "xm-key",
        "DEEPSEEK_API_KEY": "ds-key",
        "OPENAI_API_KEY": "oa-key"
    }, clear=True):
        mock_response = AsyncMock()
        mock_response.choices = [
            AsyncMock(message=AsyncMock(content="Xiaomi Summary"))
        ]

        with patch("openharness.graphiti.summarize.AsyncOpenAI") as mock_openai_cls:
            mock_client = AsyncMock()
            mock_openai_cls.return_value.__aenter__.return_value = mock_client
            mock_client.chat.completions.create.return_value = mock_response

            res = await openai_summarizer("Paragraph")
            assert res == "Xiaomi Summary"
            # Verify client was initialized with Xiaomi key and base_url
            mock_openai_cls.assert_called_once_with(api_key="xm-key", base_url="https://api.xiaomimimo.com/v1")
            call_kwargs = mock_client.chat.completions.create.call_args.kwargs
            assert call_kwargs["model"] == "mimo-v2-pro"

    # Test batch summarizer priority
    with patch.dict(os.environ, {
        "XIAOMI_API_KEY": "xm-key",
        "DEEPSEEK_API_KEY": "ds-key",
        "OPENAI_API_KEY": "oa-key"
    }, clear=True):
        mock_response = AsyncMock()
        mock_response.choices = [
            AsyncMock(message=AsyncMock(content=json.dumps({"summaries": ["Xiaomi Batch"]})))
        ]

        with patch("openharness.graphiti.summarize.AsyncOpenAI") as mock_openai_cls:
            mock_client = AsyncMock()
            mock_openai_cls.return_value.__aenter__.return_value = mock_client
            mock_client.chat.completions.create.return_value = mock_response

            res = await openai_batch_summarizer(["Paragraph"])
            assert res == ["Xiaomi Batch"]
            mock_openai_cls.assert_called_once_with(api_key="xm-key", base_url="https://api.xiaomimimo.com/v1")
            call_kwargs = mock_client.chat.completions.create.call_args.kwargs
            assert call_kwargs["model"] == "mimo-v2-pro"


