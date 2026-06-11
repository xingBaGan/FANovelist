"""Tests for aggregation module in graphiti."""

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from openharness.graphiti.aggregation import (
    classify_and_aggregate_summaries,
    load_or_generate_aggregation_plan,
    ingest_aggregation_plan,
)


@pytest.mark.asyncio
async def test_classify_and_aggregate_summaries_success() -> None:
    mock_response = AsyncMock()
    fake_plan = {
        "static_lore": [{"uid": "uid-1", "reason": "landscape"}],
        "dynamic_scenes": [
            {
                "scene_title": "Duel",
                "scene_summary": "Action duel scene",
                "paragraph_uids": ["uid-2"],
                "key_dramatic_elements": "survival",
            }
        ],
    }
    mock_response.choices = [
        AsyncMock(message=AsyncMock(content=json.dumps(fake_plan)))
    ]

    with patch("openharness.graphiti.aggregation.AsyncOpenAI") as mock_openai_cls:
        mock_client = AsyncMock()
        mock_openai_cls.return_value.__aenter__.return_value = mock_client
        mock_client.chat.completions.create.return_value = mock_response

        paragraph_list = [
            {"uid": "uid-1", "hash": "hash1", "summary": "Landscape info"},
            {"uid": "uid-2", "hash": "hash2", "summary": "Fight scene info"},
        ]

        result = await classify_and_aggregate_summaries(
            paragraph_list=paragraph_list,
            api_key="test-key",
            model="gpt-4o",
        )

        assert result == fake_plan
        mock_openai_cls.assert_called_once_with(api_key="test-key", base_url=None)
        mock_client.chat.completions.create.assert_called_once()


@pytest.mark.asyncio
async def test_load_or_generate_aggregation_plan(tmp_path: Path) -> None:
    plan_path = tmp_path / "plan.json"
    fake_plan = {
        "static_lore": [],
        "dynamic_scenes": [],
    }

    # 1. Test when plan doesn't exist (calls LLM and saves)
    with patch(
        "openharness.graphiti.aggregation.classify_and_aggregate_summaries",
        new_callable=AsyncMock,
    ) as mock_classify:
        mock_classify.return_value = fake_plan

        res = await load_or_generate_aggregation_plan(
            plan_path=plan_path,
            paragraph_list=[],
            api_key="test-key",
        )
        assert res == fake_plan
        assert plan_path.exists()
        mock_classify.assert_called_once()

    # 2. Test when plan already exists (loads from disk without LLM call)
    with patch(
        "openharness.graphiti.aggregation.classify_and_aggregate_summaries",
        new_callable=AsyncMock,
    ) as mock_classify_2:
        res2 = await load_or_generate_aggregation_plan(
            plan_path=plan_path,
            paragraph_list=[],
            api_key="test-key",
        )
        assert res2 == fake_plan
        mock_classify_2.assert_not_called()


@pytest.mark.asyncio
async def test_ingest_aggregation_plan(tmp_path: Path) -> None:
    fake_plan = {
        "static_lore": [{"uid": "uid-1", "reason": "landscape"}],
        "dynamic_scenes": [
            {
                "scene_title": "Duel",
                "scene_summary": "Action duel scene",
                "paragraph_uids": ["uid-2"],
                "key_dramatic_elements": "survival",
            }
        ],
    }

    paragraph_list = [
        {"uid": "uid-1", "hash": "hash1", "summary": "Landscape info"},
        {"uid": "uid-2", "hash": "hash2", "summary": "Fight scene info"},
    ]

    # Mock GraphitiClient
    mock_client = MagicMock()
    mock_client.available = True
    # Return (None, [], None) from get_episode_by_name to force add_episode
    mock_client.get_episode_by_name = AsyncMock(return_value=(None, [], None))
    mock_client.add_episode = AsyncMock(return_value=("episode-uuid-xyz", ["edge-1"]))

    # Mock IngestStateStore
    mock_store = MagicMock()
    mock_store.start_submit_run.return_value = 42
    mock_store.get_paragraph.return_value = None  # Force save_paragraph_links

    summary_path = tmp_path / "summary.md"
    lore_output_path = tmp_path / "lore.json"

    run_id = await ingest_aggregation_plan(
        plan_data=fake_plan,
        client=mock_client,
        store=mock_store,
        summary_path=summary_path,
        paragraph_list=paragraph_list,
        source_path_str="studio/chapters/ch1.md",
        chapter_index_prefix="ch1",
        submit_gate="approve-chapter",
        lore_output_path=lore_output_path,
    )

    assert run_id == 42
    assert lore_output_path.exists()

    # Verify Neo4j was queried and added
    mock_client.get_episode_by_name.assert_called_once_with("ch1#Duel")
    mock_client.add_episode.assert_called_once()

    # Verify SQLite mappings were logged
    mock_store.start_submit_run.assert_called_once()
    assert mock_store.save_paragraph_links.call_count == 2
    mock_store.finish_submit_run.assert_called_once_with(42, {"dynamic_scenes_ingested": 1})
