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
