"""Unit tests for summary buffer staging and parsing."""

from __future__ import annotations

import sqlite3
from pathlib import Path
import pytest

from openharness.graphiti.client import GraphitiClient
from openharness.graphiti.config import GraphitiSettings
from openharness.graphiti.ingest import ingest_submitted_document
from openharness.graphiti.summary_stage import (
    parse_summary_file,
    serialize_summary_file,
    stage_chapter_summaries,
)

UUID1 = "11111111-1111-1111-1111-111111111101"
UUID2 = "11111111-1111-1111-1111-111111111102"
UUID3 = "11111111-1111-1111-1111-111111111103"

HASH1 = "a1b2c3d4e5f67890a1b2c3d4e5f67890a1b2c3d4e5f67890a1b2c3d4e5f67890"
HASH2 = "0987654321fedcba0987654321fedcba0987654321fedcba0987654321fedcba"


def _offline_client() -> GraphitiClient:
    return GraphitiClient(
        GraphitiSettings(
            neo4j_uri="",
            neo4j_user="",
            neo4j_password="",
            neo4j_database="neo4j",
            group_id="test-novel",
            openai_api_key=None,
        )
    )


def test_parse_and_serialize_summaries() -> None:
    summaries = [
        (UUID1, HASH1, "This is summary one."),
        (UUID2, HASH2, "This is summary two.\nIt has multiple lines."),
    ]
    serialized = serialize_summary_file(summaries)
    assert f"paragraph_uid: {UUID1} hash: {HASH1}" in serialized
    assert "This is summary one." in serialized
    assert f"paragraph_uid: {UUID2} hash: {HASH2}" in serialized
    assert "This is summary two.\nIt has multiple lines." in serialized

    parsed = parse_summary_file(serialized)
    assert len(parsed) == 2
    assert parsed[UUID1] == (HASH1, "This is summary one.")
    assert parsed[UUID2] == (HASH2, "This is summary two.\nIt has multiple lines.")


@pytest.mark.asyncio
async def test_stage_chapter_summaries_lifecycle(tmp_path: Path) -> None:
    source_file = tmp_path / "chapter.md"
    # Create a simple story with paragraph comments
    source_file.write_text(
        "# Title\n\n"
        f"<!-- paragraph_uid: {UUID1} -->\n\n"
        "This is paragraph one content, which is long enough to avoid being merged.\n\n"
        f"<!-- paragraph_uid: {UUID2} -->\n\n"
        "This is paragraph two content, which is also long enough to avoid being merged.\n",
        encoding="utf-8",
    )

    summarized_count = 0

    async def mock_summarizer(text: str) -> str:
        nonlocal summarized_count
        summarized_count += 1
        return f"Summary of: {text[:20]}"

    # 1. Run staging for the first time
    summary_file, stats = await stage_chapter_summaries(
        source_path=source_file,
        studio_root=tmp_path,
        summarizer=mock_summarizer,
    )

    assert summary_file.exists()
    assert stats["created"] == 2
    assert stats["reused"] == 0
    assert stats["updated"] == 0
    assert summarized_count == 2

    # Check generated summary contents
    parsed = parse_summary_file(summary_file.read_text(encoding="utf-8"))
    assert UUID1 in parsed
    assert parsed[UUID1][1] == "Summary of: This is paragraph on"
    assert UUID2 in parsed
    assert parsed[UUID2][1] == "Summary of: This is paragraph tw"

    # 2. Run staging again without modifying the source file (all should be reused)
    summarized_count = 0
    summary_file, stats = await stage_chapter_summaries(
        source_path=source_file,
        studio_root=tmp_path,
        summarizer=mock_summarizer,
    )
    assert stats["created"] == 0
    assert stats["reused"] == 2
    assert stats["updated"] == 0
    assert summarized_count == 0

    # 3. Edit one paragraph and run staging again (one should update, one reuse)
    source_file.write_text(
        "# Title\n\n"
        f"<!-- paragraph_uid: {UUID1} -->\n\n"
        "This is paragraph one content, which is long enough to avoid being merged.\n\n"
        f"<!-- paragraph_uid: {UUID2} -->\n\n"
        "This is paragraph two content has been edited and modified.\n",
        encoding="utf-8",
    )

    summarized_count = 0
    summary_file, stats = await stage_chapter_summaries(
        source_path=source_file,
        studio_root=tmp_path,
        summarizer=mock_summarizer,
    )
    assert stats["created"] == 0
    assert stats["reused"] == 1
    assert stats["updated"] == 1
    assert summarized_count == 1

    parsed = parse_summary_file(summary_file.read_text(encoding="utf-8"))
    assert parsed[UUID2][1] == "Summary of: This is paragraph tw"


@pytest.mark.asyncio
async def test_ingest_with_summaries_map(tmp_path: Path) -> None:
    source_file = tmp_path / "chapter.md"
    source_file.write_text(
        "# Title\n\n"
        f"<!-- paragraph_uid: {UUID1} -->\n\n"
        "This is paragraph one content, which is long enough to avoid being merged.\n\n"
        f"<!-- paragraph_uid: {UUID2} -->\n\n"
        "This is paragraph two content, which is also long enough to avoid being merged.\n",
        encoding="utf-8",
    )

    client = _offline_client()
    summaries_map = {
        UUID1: "Staged summary one.",
        UUID2: "Staged summary two.",
    }

    report = await ingest_submitted_document(
        source_path=source_file,
        source_kind="chapter",
        group_id="test-novel",
        submit_gate="approve-chapter",
        submit_scope="chapter_all",
        studio_root=tmp_path,
        graphiti=client,
        write_uids_to_markdown=False,
        summaries_map=summaries_map,
    )

    assert report.paragraphs_ingested == 2
    # Verify events logged to state db use summaries_map values
    db_path = tmp_path / ".graphiti" / "ingest.db"
    assert db_path.exists()

    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT * FROM submit_paragraph_events WHERE submit_run_id = ? AND paragraph_uid = ?",
            (report.submit_run_id, UUID1),
        ).fetchone()
        assert row is not None
        assert row["llm_summary_excerpt"] == "Staged summary one."


@pytest.mark.asyncio
async def test_custom_model_configuration_connect() -> None:
    from unittest.mock import MagicMock, patch

    settings = GraphitiSettings(
        neo4j_uri="bolt://localhost:7687",
        neo4j_user="neo4j",
        neo4j_password="password",
        neo4j_database="neo4j",
        group_id="custom-group",
        openai_api_key=None,
        deepseek_api_key="ds-key",
        siliconflow_api_key="sf-key",
    )
    client = GraphitiClient(settings)

    mock_driver = MagicMock()
    mock_graphiti = MagicMock()
    from unittest.mock import AsyncMock
    mock_graphiti.build_indices_and_constraints = AsyncMock()

    with patch("openharness.graphiti.client.Neo4jDriver", return_value=mock_driver), \
         patch("openharness.graphiti.client.Graphiti", return_value=mock_graphiti) as mock_graphiti_class, \
         patch("openharness.graphiti.client.DeepSeekLLMClient") as mock_ds_client, \
         patch("openharness.graphiti.client.OpenAIEmbedder") as mock_embedder:

        await client.connect()

        # Verify that DeepSeekLLMClient and OpenAIEmbedder were instantiated and passed
        mock_ds_client.assert_called_once()
        mock_embedder.assert_called_once()

        # Verify arguments passed to Graphiti
        call_args = mock_graphiti_class.call_args
        assert call_args is not None
        kwargs = call_args.kwargs
        assert kwargs["graph_driver"] == mock_driver
        assert kwargs["llm_client"] == mock_ds_client.return_value
        assert kwargs["embedder"] == mock_embedder.return_value
        assert kwargs["cross_encoder"] is not None


@pytest.mark.asyncio
async def test_stage_chapter_summaries_batching(tmp_path: Path) -> None:
    from unittest.mock import AsyncMock, patch
    import os

    source_file = tmp_path / "chapter_batch.md"
    paragraphs_content = []
    for i in range(12):
        uid = f"11111111-1111-1111-1111-1111111112{i:02d}"
        paragraphs_content.append(
            f"<!-- paragraph_uid: {uid} -->\n\n"
            f"This is paragraph number {i} content. It is long enough to avoid being merged."
        )
    source_file.write_text("\n\n".join(paragraphs_content), encoding="utf-8")

    mock_batch_summarizer = AsyncMock()
    mock_batch_summarizer.side_effect = [
        [f"Summary of {i}" for i in range(10)],
        [f"Summary of {i}" for i in range(10, 12)],
    ]

    with patch.dict(os.environ, {"DEEPSEEK_API_KEY": "ds-key"}, clear=True), \
         patch("openharness.graphiti.summarize.openai_batch_summarizer", mock_batch_summarizer):

        summary_file, stats = await stage_chapter_summaries(
            source_path=source_file,
            studio_root=tmp_path,
        )

        assert stats["created"] == 12
        assert mock_batch_summarizer.call_count == 2

        # Verify first call had 10 texts
        first_call_args = mock_batch_summarizer.call_args_list[0][0][0]
        assert len(first_call_args) == 10
        assert "paragraph number 0" in first_call_args[0]

        # Verify second call had 2 texts
        second_call_args = mock_batch_summarizer.call_args_list[1][0][0]
        assert len(second_call_args) == 2
        assert "paragraph number 10" in second_call_args[0]

        # Verify parsing
        parsed = parse_summary_file(summary_file.read_text(encoding="utf-8"))
        assert len(parsed) == 12
        for i in range(12):
            uid = f"11111111-1111-1111-1111-1111111112{i:02d}"
            assert parsed[uid][1] == f"Summary of {i}"


@pytest.mark.asyncio
async def test_xiaomi_model_configuration_connect() -> None:
    from unittest.mock import MagicMock, patch, AsyncMock

    settings = GraphitiSettings(
        neo4j_uri="bolt://localhost:7687",
        neo4j_user="neo4j",
        neo4j_password="password",
        neo4j_database="neo4j",
        group_id="custom-group",
        openai_api_key=None,
        deepseek_api_key="ds-key",
        siliconflow_api_key="sf-key",
        xiaomi_api_key="xm-key",
    )
    client = GraphitiClient(settings)

    mock_driver = MagicMock()
    mock_graphiti = MagicMock()
    mock_graphiti.build_indices_and_constraints = AsyncMock()

    with patch("openharness.graphiti.client.Neo4jDriver", return_value=mock_driver), \
         patch("openharness.graphiti.client.Graphiti", return_value=mock_graphiti) as mock_graphiti_class, \
         patch("openharness.graphiti.client.DeepSeekLLMClient") as mock_ds_client, \
         patch("openharness.graphiti.client.OpenAIEmbedder") as mock_embedder:

        await client.connect()

        # Verify that DeepSeekLLMClient was initialized with the Xiaomi config since xiaomi_api_key is set
        mock_ds_client.assert_called_once()
        call_kwargs = mock_ds_client.call_args.kwargs
        assert call_kwargs["config"].api_key == "xm-key"
        assert call_kwargs["config"].model == "mimo-v2-pro"
        assert call_kwargs["config"].base_url == "https://api.xiaomimimo.com/v1"


@pytest.mark.asyncio
async def test_ingest_reuses_neo4j_episode_matching_content(tmp_path: Path) -> None:
    from unittest.mock import AsyncMock, PropertyMock, patch
    from openharness.graphiti.ingest import ingest_submitted_document

    source_file = tmp_path / "chapter.md"
    source_file.write_text(
        "# Chapter 1\n\n<!-- paragraph_uid: custom-uid-123 -->\n\n"
        "This is paragraph one with enough text length to stand alone.\n",
        encoding="utf-8"
    )

    client = _offline_client()
    with patch("openharness.graphiti.client.GraphitiClient.available", new_callable=PropertyMock, return_value=True):
        client.get_episode_by_name = AsyncMock(
            return_value=("existing-episode-uuid-999", ["existing-edge-1", "existing-edge-2"], "Summary excerpt")
        )
        client.add_episode = AsyncMock()
        client.remove_episode = AsyncMock()

        summaries_map = {"custom-uid-123": "Summary excerpt"}

        report = await ingest_submitted_document(
            source_path=source_file,
            source_kind="chapter",
            group_id="test-novel",
            submit_gate="test",
            submit_scope="chapter_all",
            studio_root=tmp_path,
            graphiti=client,
            write_uids_to_markdown=False,
            summaries_map=summaries_map,
        )

        assert report.paragraphs_ingested == 1
        client.add_episode.assert_not_called()
        client.remove_episode.assert_not_called()
        client.get_episode_by_name.assert_called_once_with(f"{source_file}#custom-uid-123")

        db_path = tmp_path / ".graphiti" / "ingest.db"
        assert db_path.exists()
        with sqlite3.connect(db_path) as conn:
            conn.row_factory = sqlite3.Row
            p_row = conn.execute("SELECT * FROM paragraphs WHERE paragraph_uid = 'custom-uid-123'").fetchone()
            assert p_row is not None
            assert p_row["content_hash"] is not None

            ep_rows = conn.execute("SELECT episode_uuid FROM paragraph_episodes WHERE paragraph_uid = 'custom-uid-123'").fetchall()
            assert len(ep_rows) == 1
            assert ep_rows[0]["episode_uuid"] == "existing-episode-uuid-999"

            edge_rows = conn.execute("SELECT edge_uuid FROM paragraph_edges WHERE paragraph_uid = 'custom-uid-123'").fetchall()
            assert len(edge_rows) == 2
            assert {r["edge_uuid"] for r in edge_rows} == {"existing-edge-1", "existing-edge-2"}


@pytest.mark.asyncio
async def test_ingest_removes_old_neo4j_episode_if_content_changed(tmp_path: Path) -> None:
    from unittest.mock import AsyncMock, PropertyMock, patch
    from openharness.graphiti.ingest import ingest_submitted_document

    source_file = tmp_path / "chapter.md"
    source_file.write_text(
        "# Chapter 1\n\n<!-- paragraph_uid: custom-uid-123 -->\n\n"
        "This is paragraph one with enough text length to stand alone.\n",
        encoding="utf-8"
    )

    client = _offline_client()
    with patch("openharness.graphiti.client.GraphitiClient.available", new_callable=PropertyMock, return_value=True):
        client.get_episode_by_name = AsyncMock(
            return_value=("existing-episode-uuid-999", ["existing-edge-1", "existing-edge-2"], "Old Summary")
        )
        client.add_episode = AsyncMock(
            return_value=("new-episode-uuid-888", ["new-edge-1"])
        )
        client.remove_episode = AsyncMock()

        summaries_map = {"custom-uid-123": "New Summary"}

        report = await ingest_submitted_document(
            source_path=source_file,
            source_kind="chapter",
            group_id="test-novel",
            submit_gate="test",
            submit_scope="chapter_all",
            studio_root=tmp_path,
            graphiti=client,
            write_uids_to_markdown=False,
            summaries_map=summaries_map,
        )

        assert report.paragraphs_ingested == 1
        client.remove_episode.assert_called_once_with("existing-episode-uuid-999")
        client.add_episode.assert_called_once()
        client.get_episode_by_name.assert_called_once_with(f"{source_file}#custom-uid-123")

        db_path = tmp_path / ".graphiti" / "ingest.db"
        with sqlite3.connect(db_path) as conn:
            conn.row_factory = sqlite3.Row
            ep_rows = conn.execute("SELECT episode_uuid FROM paragraph_episodes WHERE paragraph_uid = 'custom-uid-123'").fetchall()
            assert len(ep_rows) == 1
            assert ep_rows[0]["episode_uuid"] == "new-episode-uuid-888"


@pytest.mark.asyncio
async def test_client_get_episode_by_name_handles_duplicates() -> None:
    from unittest.mock import AsyncMock, MagicMock, PropertyMock, patch

    client = _offline_client()
    with patch("openharness.graphiti.client.GraphitiClient.available", new_callable=PropertyMock, return_value=True):
        mock_driver = MagicMock()

        class MockRecord:
            def __init__(self, data: dict):
                self.data = data
            def get(self, key):
                return self.data.get(key)

        mock_result = MagicMock()
        mock_result.records = [
            MockRecord({"episode_uuid": "dup-uuid-1", "edge_uuids": ["edge-1"], "content": "Summary text"}),
            MockRecord({"episode_uuid": "dup-uuid-2", "edge_uuids": ["edge-2"], "content": "Summary text"}),
        ]

        mock_driver.execute_query = AsyncMock(return_value=mock_result)
        client._graphiti = MagicMock()
        client._graphiti.driver = mock_driver
        client._ensure_connected = AsyncMock()
        client.remove_episode = AsyncMock()

        episode_uuid, edge_uuids, content = await client.get_episode_by_name("test-episode-name")

        assert episode_uuid is None
        assert edge_uuids == []
        assert content is None

        assert client.remove_episode.call_count == 2
        client.remove_episode.assert_any_call("dup-uuid-1")
        client.remove_episode.assert_any_call("dup-uuid-2")




