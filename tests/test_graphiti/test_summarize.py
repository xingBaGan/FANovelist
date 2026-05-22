"""Tests for openai_summarizer in graphiti."""

import os
from unittest.mock import AsyncMock, patch
import pytest

from openharness.graphiti.summarize import openai_summarizer


@pytest.mark.asyncio
async def test_openai_summarizer_success() -> None:
    # Set the key temporarily in the test
    with patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}):
        mock_response = AsyncMock()
        mock_response.choices = [
            AsyncMock(message=AsyncMock(content="李默决定离开门派，下山历练。"))
        ]

        with patch("openharness.graphiti.summarize.AsyncOpenAI") as mock_openai_cls:
            mock_client = AsyncMock()
            mock_openai_cls.return_value = mock_client
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
    with patch.dict(os.environ, {"OPENAI_API_KEY": "test-key", "OPENAI_MODEL": "gpt-4o-mini"}):
        mock_response = AsyncMock()
        mock_response.choices = [
            AsyncMock(message=AsyncMock(content="Summary content."))
        ]

        with patch("openharness.graphiti.summarize.AsyncOpenAI") as mock_openai_cls:
            mock_client = AsyncMock()
            mock_openai_cls.return_value = mock_client
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
        with pytest.raises(ValueError, match="OPENAI_API_KEY environment variable is not set"):
            await openai_summarizer("Some paragraph")
