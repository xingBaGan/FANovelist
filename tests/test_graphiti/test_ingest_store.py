"""Tests for SQLite ingest store."""

from pathlib import Path

from openharness.graphiti.ingest_store import IngestStateStore


def test_submit_audit_log(tmp_path: Path) -> None:
    db = tmp_path / "ingest.db"
    store = IngestStateStore(db)
    run_id = store.start_submit_run(
        submit_gate="approve-chapter",
        source_path="studio/chapters/ch01.md",
        source_kind="chapter",
        submit_scope="chapter_all",
    )
    store.log_paragraph_event(
        submit_run_id=run_id,
        paragraph_uid="uid-1",
        action="added",
        new_hash="abc",
        episode_created="ep-1",
    )
    store.finish_submit_run(run_id, {"paragraphs_ingested": 1})
    store.save_paragraph_links(
        paragraph_uid="uid-1",
        source_path="studio/chapters/ch01.md",
        paragraph_index=0,
        section_heading=None,
        content_hash="abc",
        paragraph_text="sample text",
        episode_uuids=["ep-1"],
        edge_uuids=["edge-1"],
    )
    loaded = store.get_paragraph("uid-1")
    assert loaded is not None
    assert loaded.episode_uuids == ("ep-1",)
    assert loaded.paragraph_text == "sample text"


def test_new_store_tables(tmp_path: Path) -> None:
    db = tmp_path / "ingest.db"
    store = IngestStateStore(db)

    # 1. Test Chapter tracking
    store.upsert_chapter(
        chapter_path="studio/chapters/ch01.md",
        title="第一章 觉醒",
        chapter_index=1,
        approval_status="approved",
    )
    ch = store.get_chapter("studio/chapters/ch01.md")
    assert ch is not None
    assert ch["title"] == "第一章 觉醒"
    assert ch["chapter_index"] == 1
    assert ch["approval_status"] == "approved"

    chapters = store.list_chapters()
    assert len(chapters) == 1
    assert chapters[0]["chapter_path"] == "studio/chapters/ch01.md"

    # 2. Test Scene value shifts
    store.save_scene_value_shift(
        chapter_path="studio/chapters/ch01.md",
        paragraph_uid="uid-1",
        conflict_focus="发现叛徒",
        value_dimension="Safety",
        initial_value=5,
        target_value=-8,
    )
    shifts = store.list_scene_value_shifts("studio/chapters/ch01.md")
    assert len(shifts) == 1
    assert shifts[0]["conflict_focus"] == "发现叛徒"
    assert shifts[0]["value_dimension"] == "Safety"
    assert shifts[0]["initial_value"] == 5
    assert shifts[0]["target_value"] == -8

    # 3. Test Paragraph graph links
    store.save_paragraph_links(
        paragraph_uid="uid-1",
        source_path="studio/chapters/ch01.md",
        paragraph_index=0,
        section_heading=None,
        content_hash="abc",
        paragraph_text="sample",
        episode_uuids=["neo4j-ep-123"],
        edge_uuids=[],
    )
    links = store.get_paragraph_graph_links("uid-1")
    assert links == ["neo4j-ep-123"]
