"""Tests for GraphitiClient novel-studio query features."""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from openharness.graphiti.client import GraphitiClient


@pytest.mark.asyncio
async def test_trace_entity_origins() -> None:
    client = GraphitiClient()
    client._graphiti = MagicMock()

    mock_record = MagicMock()
    mock_record.get.side_effect = lambda key: {
        "episode_uuid": "ep-123",
        "episode_name": "chapter-1",
        "content": "李默出生在江城",
        "valid_at": "2020-01-01T00:00:00Z"
    }.get(key)

    mock_result = MagicMock()
    mock_result.records = [mock_record]

    client._graphiti.driver.execute_query = AsyncMock(return_value=mock_result)

    with patch.object(client, "_ensure_connected", AsyncMock()):
        res = await client.trace_entity_origins("李默", group_id="test-group")

        assert len(res) == 1
        assert res[0]["episode_name"] == "chapter-1"
        assert res[0]["content"] == "李默出生在江城"
        assert res[0]["valid_at"] == "2020-01-01T00:00:00Z"

        client._graphiti.driver.execute_query.assert_called_once()
        args, kwargs = client._graphiti.driver.execute_query.call_args
        assert "WHERE n.name = $entity_name AND e.group_id = $group_id" in args[0]
        assert kwargs["params"] == {"entity_name": "李默", "group_id": "test-group"}


@pytest.mark.asyncio
async def test_get_story_timeline_without_focus() -> None:
    client = GraphitiClient()
    client._graphiti = MagicMock()

    mock_episode_record = MagicMock()
    mock_episode_record.get.side_effect = lambda key: {
        "episode_uuid": "ep-123",
        "episode_name": "chapter-1",
        "content": "李默出生在江城",
        "valid_at": "2020-01-01T00:00:00Z"
    }.get(key)

    mock_ep_result = MagicMock()
    mock_ep_result.records = [mock_episode_record]

    mock_rel_record = MagicMock()
    mock_rel_record.get.side_effect = lambda key: {
        "edge_uuid": "rel-456",
        "relation_name": "LOCATED_IN",
        "fact": "李默出生在江城",
        "source_name": "李默",
        "target_name": "江城",
        "valid_at": "2020-01-01T00:00:00Z",
        "invalid_at": None,
        "episodes": ["ep-123"]
    }.get(key)

    mock_rel_result = MagicMock()
    mock_rel_result.records = [mock_rel_record]

    # Handle multiple sequential queries
    client._graphiti.driver.execute_query = AsyncMock()
    client._graphiti.driver.execute_query.side_effect = [mock_ep_result, mock_rel_result]

    with patch.object(client, "_ensure_connected", AsyncMock()):
        res = await client.get_story_timeline(group_id="test-group")

        assert len(res) == 1
        assert res[0]["episode_uuid"] == "ep-123"
        assert len(res[0]["relations"]) == 1
        assert res[0]["relations"][0]["edge_uuid"] == "rel-456"
        assert res[0]["relations"][0]["relation_name"] == "LOCATED_IN"

        assert client._graphiti.driver.execute_query.call_count == 2


@pytest.mark.asyncio
async def test_get_factions_outline() -> None:
    client = GraphitiClient()
    client._graphiti = MagicMock()

    mock_record = MagicMock()
    mock_record.get.side_effect = lambda key: {
        "community_uuid": "comm-123",
        "summary": "天机阁弟子核心圈子",
        "members": [{"name": "李默", "labels": ["MajorCharacter"]}]
    }.get(key)

    mock_result = MagicMock()
    mock_result.records = [mock_record]

    client._graphiti.driver.execute_query = AsyncMock(return_value=mock_result)

    with patch.object(client, "_ensure_connected", AsyncMock()):
        res = await client.get_factions_outline(group_id="test-group")

        assert len(res) == 1
        assert res[0]["community_uuid"] == "comm-123"
        assert res[0]["summary"] == "天机阁弟子核心圈子"
        assert res[0]["members"][0]["name"] == "李默"


@pytest.mark.asyncio
async def test_get_historical_relationships() -> None:
    client = GraphitiClient()
    client._graphiti = MagicMock()

    mock_record = MagicMock()
    mock_record.get.side_effect = lambda key: {
        "source_name": "李默",
        "source_labels": ["MajorCharacter"],
        "target_name": "天机阁",
        "target_labels": ["Organization"],
        "edge_uuid": "edge-789",
        "relation_name": "MEMBER_OF",
        "fact": "李默是外门弟子",
        "valid_at": "2020-01-01T00:00:00Z",
        "invalid_at": None,
        "all_props": {
            "name": "MEMBER_OF",
            "uuid": "edge-789",
            "fact_embedding": [0.1],
            "role": "外门弟子",
            "detail": "新入门"
        }
    }.get(key)

    mock_result = MagicMock()
    mock_result.records = [mock_record]

    client._graphiti.driver.execute_query = AsyncMock(return_value=mock_result)

    with patch.object(client, "_ensure_connected", AsyncMock()):
        res = await client.get_historical_relationships(
            target_time="2020-06-01T00:00:00Z",
            group_id="test-group"
        )

        assert len(res) == 1
        assert res[0]["source_name"] == "李默"
        assert res[0]["relation_name"] == "MEMBER_OF"
        # System keys must be filtered out of attributes
        assert "role" in res[0]["attributes"]
        assert "detail" in res[0]["attributes"]
        assert "uuid" not in res[0]["attributes"]
        assert "fact_embedding" not in res[0]["attributes"]
