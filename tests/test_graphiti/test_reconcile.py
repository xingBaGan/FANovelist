"""Tests for paragraph reconcile."""

from openharness.graphiti.ingest_store import StoredParagraph
from openharness.graphiti.paragraphs import ParagraphBlock, split_paragraphs
from openharness.graphiti.reconcile import reconcile_paragraphs


def _stored(uid: str, text: str, h: str) -> StoredParagraph:
    return StoredParagraph(
        paragraph_uid=uid,
        source_path="story.md",
        content_hash=h,
        paragraph_text=text,
        paragraph_index=0,
        section_heading=None,
        tombstone=False,
        episode_uuids=(),
        edge_uuids=(),
    )


def test_reconcile_detects_edit_and_delete() -> None:
    uid1 = "11111111-1111-1111-1111-111111111101"
    uid2 = "11111111-1111-1111-1111-111111111102"
    uid3 = "11111111-1111-1111-1111-111111111103"
    old = [
        _stored(uid1, "alpha paragraph one with enough text for reconcile testing here.", "h1"),
        _stored(uid2, "beta paragraph two with enough text for reconcile testing here.", "h2"),
    ]
    new = split_paragraphs(
        f"<!-- paragraph_uid: {uid1} -->\nalpha paragraph ONE with enough text for reconcile testing here.\n\n"
        f"<!-- paragraph_uid: {uid3} -->\nnew paragraph three added here with enough length for the threshold."
    )
    recon = reconcile_paragraphs(old, new)
    assert len(recon.deleted) == 1
    assert recon.deleted[0].paragraph_uid == uid2
    assert len(recon.added) == 1
    assert recon.added[0].paragraph_uid == uid3
    assert len(recon.edited) == 1
