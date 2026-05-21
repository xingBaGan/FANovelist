"""Tests for paragraph splitting."""

from openharness.graphiti.paragraphs import content_hash, split_paragraphs


def test_split_paragraphs_respects_uids() -> None:
    text = """# Title

<!-- paragraph_uid: 11111111-1111-1111-1111-111111111101 -->

First paragraph with enough characters to avoid merge into the next block for testing.

<!-- paragraph_uid: 11111111-1111-1111-1111-111111111102 -->

Second paragraph also long enough to stand alone under the eighty character threshold rule.
"""
    blocks = split_paragraphs(text)
    uids = {b.paragraph_uid for b in blocks}
    assert "11111111-1111-1111-1111-111111111101" in uids
    assert "11111111-1111-1111-1111-111111111102" in uids
    assert len(blocks) == 2


def test_content_hash_stable() -> None:
    a = content_hash("Hello   world")
    b = content_hash("Hello world")
    assert a == b
