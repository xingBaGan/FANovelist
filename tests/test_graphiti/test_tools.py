"""Tests for Graphiti agent tools."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from openharness.graphiti.tools import (
    DeleteEntityEdgeTool,
    GetCanonStateTool,
    GetFactionsOutlineTool,
    GetStoryTimelineTool,
    RemoveEpisodeTool,
    SearchFactsTool,
    TraceEntityOriginsTool,
)
from openharness.tools.base import ToolExecutionContext


@pytest.mark.asyncio
async def test_search_facts_tool() -> None:
    tool = SearchFactsTool()
    ctx = ToolExecutionContext(cwd=Path("."), metadata={"graphiti_group_id": "test-group"})

    mock_edge = MagicMock()
    mock_edge.dict.return_value = {
        "uuid": "rel-456",
        "fact": "李默加入天机阁",
        "fact_embedding": [0.1],
        "valid_at": "2020-01-01T00:00:00Z",
    }

    mock_client = MagicMock()
    mock_client.available = True
    mock_client.connect = AsyncMock()
    mock_client.search_facts = AsyncMock(return_value=[mock_edge])
    mock_client.close = AsyncMock()

    with patch("openharness.graphiti.tools.GraphitiClient", return_value=mock_client):
        args = tool.input_model(query="李默", group_id="test-group")
        res = await tool.execute(args, ctx)

        assert not res.is_error
        assert "rel-456" in res.output
        assert "fact_embedding" not in res.output

        mock_client.search_facts.assert_called_once_with("李默", group_id="test-group")


@pytest.mark.asyncio
async def test_remove_episode_tool() -> None:
    tool = RemoveEpisodeTool()
    ctx = ToolExecutionContext(cwd=Path("."), metadata={})

    mock_client = MagicMock()
    mock_client.available = True
    mock_client.connect = AsyncMock()
    mock_client.remove_episode = AsyncMock()
    mock_client.close = AsyncMock()

    with patch("openharness.graphiti.tools.GraphitiClient", return_value=mock_client):
        args = tool.input_model(episode_uuid="ep-123")
        res = await tool.execute(args, ctx)

        assert not res.is_error
        assert "success" in res.output

        mock_client.remove_episode.assert_called_once_with("ep-123")


@pytest.mark.asyncio
async def test_delete_entity_edge_tool() -> None:
    tool = DeleteEntityEdgeTool()
    ctx = ToolExecutionContext(cwd=Path("."), metadata={})

    mock_client = MagicMock()
    mock_client.available = True
    mock_client.connect = AsyncMock()
    mock_client.delete_entity_edge = AsyncMock()
    mock_client.close = AsyncMock()

    with patch("openharness.graphiti.tools.GraphitiClient", return_value=mock_client):
        args = tool.input_model(edge_uuid="edge-789")
        res = await tool.execute(args, ctx)

        assert not res.is_error
        assert "success" in res.output

        mock_client.delete_entity_edge.assert_called_once_with("edge-789")


@pytest.mark.asyncio
async def test_trace_entity_origins_tool() -> None:
    tool = TraceEntityOriginsTool()
    ctx = ToolExecutionContext(cwd=Path("."), metadata={})

    mock_client = MagicMock()
    mock_client.available = True
    mock_client.connect = AsyncMock()
    mock_client.trace_entity_origins = AsyncMock(return_value=[{"episode_uuid": "ep-123"}])
    mock_client.close = AsyncMock()

    with patch("openharness.graphiti.tools.GraphitiClient", return_value=mock_client):
        args = tool.input_model(entity_name="李默", group_id="test-group")
        res = await tool.execute(args, ctx)

        assert not res.is_error
        assert "ep-123" in res.output

        mock_client.trace_entity_origins.assert_called_once_with("李默", group_id="test-group")


@pytest.mark.asyncio
async def test_get_story_timeline_tool() -> None:
    tool = GetStoryTimelineTool()
    ctx = ToolExecutionContext(cwd=Path("."), metadata={})

    mock_client = MagicMock()
    mock_client.available = True
    mock_client.connect = AsyncMock()
    mock_client.get_story_timeline = AsyncMock(return_value=[{"episode_uuid": "ep-123"}])
    mock_client.close = AsyncMock()

    with patch("openharness.graphiti.tools.GraphitiClient", return_value=mock_client):
        args = tool.input_model(focus_entity="李默", group_id="test-group")
        res = await tool.execute(args, ctx)

        assert not res.is_error
        assert "ep-123" in res.output

        mock_client.get_story_timeline.assert_called_once_with(focus_entity="李默", group_id="test-group")


@pytest.mark.asyncio
async def test_get_factions_outline_tool() -> None:
    tool = GetFactionsOutlineTool()
    ctx = ToolExecutionContext(cwd=Path("."), metadata={})

    mock_client = MagicMock()
    mock_client.available = True
    mock_client.connect = AsyncMock()
    mock_client.get_factions_outline = AsyncMock(return_value=[{"community_uuid": "comm-123"}])
    mock_client.close = AsyncMock()

    with patch("openharness.graphiti.tools.GraphitiClient", return_value=mock_client):
        args = tool.input_model(group_id="test-group")
        res = await tool.execute(args, ctx)

        assert not res.is_error
        assert "comm-123" in res.output

        mock_client.get_factions_outline.assert_called_once_with(group_id="test-group")


@pytest.mark.asyncio
async def test_get_canon_state_tool() -> None:
    tool = GetCanonStateTool()
    ctx = ToolExecutionContext(cwd=Path("."), metadata={})

    mock_client = MagicMock()
    mock_client.available = True
    mock_client.connect = AsyncMock()
    mock_client.get_historical_relationships = AsyncMock(return_value=[{"edge_uuid": "edge-123"}])
    mock_client.close = AsyncMock()

    with patch("openharness.graphiti.tools.GraphitiClient", return_value=mock_client):
        args = tool.input_model(target_time="2020-01-01T00:00:00Z", focus_entity="李默", group_id="test-group")
        res = await tool.execute(args, ctx)

        assert not res.is_error
        assert "edge-123" in res.output

        mock_client.get_historical_relationships.assert_called_once_with(
            target_time="2020-01-01T00:00:00Z",
            focus_entity="李默",
            group_id="test-group",
        )
