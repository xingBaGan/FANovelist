"""Offline E2E ingest scenarios (TC-SS-03..07, no Neo4j)."""

from pathlib import Path

import pytest

from openharness.graphiti.client import GraphitiClient
from openharness.graphiti.config import GraphitiSettings
from openharness.graphiti.ingest import ingest_submitted_document
from openharness.graphiti.ingest_store import IngestStateStore
from openharness.graphiti.paragraphs import inject_paragraph_uids, split_paragraphs


def _offline_client() -> GraphitiClient:
    return GraphitiClient(
        GraphitiSettings(
            neo4j_uri="",
            neo4j_user="",
            neo4j_password="",
            neo4j_database="neo4j",
            group_id="e2e-test",
            openai_api_key=None,
        )
    )


def _fixture(name: str) -> Path:
    return Path(__file__).resolve().parents[1] / "fixtures" / "short_story" / name


async def _ingest(tmp_path: Path, fixture: str, *, scope: str = "chapter_all") -> object:
    root = tmp_path / "studio"
    target = root / "chapters" / "ch01.md"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(_fixture(fixture).read_text(encoding="utf-8"), encoding="utf-8")
    return await ingest_submitted_document(
        source_path=target,
        source_kind="chapter",
        group_id="e2e-test",
        submit_gate="test",
        submit_scope=scope,
        studio_root=root,
        graphiti=_offline_client(),
        write_uids_to_markdown=False,
    )


@pytest.mark.asyncio
async def test_tc_ss_03_add_paragraph(tmp_path: Path) -> None:
    await _ingest(tmp_path, "story.v1.md")
    report = await _ingest(tmp_path, "story.v2-add.md", scope="changed_paragraphs")
    assert report.paragraphs_ingested == 1
    assert report.paragraphs_skipped == 3


@pytest.mark.asyncio
async def test_tc_ss_05_delete_paragraph(tmp_path: Path) -> None:
    await _ingest(tmp_path, "story.v1.md")
    report = await _ingest(tmp_path, "story.v3-delete.md", scope="changed_paragraphs")
    assert report.paragraphs_superseded >= 1


@pytest.mark.asyncio
async def test_tc_ss_06_edit_paragraph(tmp_path: Path) -> None:
    await _ingest(tmp_path, "story.v1.md")
    report = await _ingest(tmp_path, "story.v4-edit.md", scope="changed_paragraphs")
    assert report.paragraphs_superseded >= 1
    assert report.paragraphs_ingested >= 1


@pytest.mark.asyncio
async def test_tc_ss_07_inject_uids(tmp_path: Path) -> None:
    root = tmp_path / "studio"
    target = root / "chapters" / "ch01.md"
    target.parent.mkdir(parents=True, exist_ok=True)
    raw = "李默生于江城，幼年丧父。母亲独自将他抚养长大，性格坚毅，后入江湖。"
    target.write_text(raw, encoding="utf-8")
    client = _offline_client()
    report = await ingest_submitted_document(
        source_path=target,
        source_kind="chapter",
        group_id="e2e-test",
        submit_gate="test",
        submit_scope="chapter_all",
        studio_root=root,
        graphiti=client,
        write_uids_to_markdown=True,
    )
    assert report.paragraphs_ingested == 1
    text = target.read_text(encoding="utf-8")
    assert "paragraph_uid:" in text
    blocks = split_paragraphs(text)
    assert len(blocks) == 1
