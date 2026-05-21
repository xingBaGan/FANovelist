"""Ingest pipeline tests without live Neo4j."""

from pathlib import Path

import pytest

from openharness.graphiti.client import GraphitiClient
from openharness.graphiti.config import GraphitiSettings
from openharness.graphiti.ingest import ingest_submitted_document


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


@pytest.mark.asyncio
async def test_ingest_story_v1_without_graphiti(tmp_path: Path) -> None:
    fixture = Path(__file__).resolve().parents[1] / "fixtures" / "short_story" / "story.v1.md"
    target = tmp_path / "studio" / "chapters" / "ch01.md"
    target.parent.mkdir(parents=True)
    target.write_text(fixture.read_text(encoding="utf-8"), encoding="utf-8")

    client = _offline_client()
    report = await ingest_submitted_document(
        source_path=target,
        source_kind="chapter",
        group_id="test-novel",
        submit_gate="approve-chapter",
        submit_scope="chapter_all",
        studio_root=tmp_path / "studio",
        graphiti=client,
        write_uids_to_markdown=False,
    )
    assert report.paragraphs_ingested == 3
    assert report.paragraphs_skipped == 0

    report2 = await ingest_submitted_document(
        source_path=target,
        source_kind="chapter",
        group_id="test-novel",
        submit_gate="approve-chapter",
        submit_scope="changed_paragraphs",
        studio_root=tmp_path / "studio",
        graphiti=client,
        write_uids_to_markdown=False,
    )
    assert report2.paragraphs_ingested == 0
    assert report2.paragraphs_skipped == 3
