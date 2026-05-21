"""Tests for paragraph splitting."""

from openharness.graphiti.paragraphs import content_hash, inject_paragraph_uids, split_paragraphs


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


def test_inject_paragraph_uids_roundtrip() -> None:
    raw = """# 章

李默生于江城，幼年丧父。母亲独自将他抚养长大，性格坚毅。

2020年，李默加入天机阁，成为外门弟子，修习基础剑法。他在外门比武中崭露头角，被长老看中。
"""
    blocks = split_paragraphs(raw)
    assert len(blocks) == 2
    injected = inject_paragraph_uids(raw, blocks)
    assert "<!-- paragraph_uid:" in injected
    roundtrip = split_paragraphs(injected)
    assert {b.paragraph_uid for b in roundtrip} == {b.paragraph_uid for b in blocks}


def test_inject_paragraph_uids_idempotent() -> None:
    text = """<!-- paragraph_uid: 11111111-1111-1111-1111-111111111101 -->

李默生于江城，幼年丧父。母亲独自将他抚养长大，性格坚毅，足够长度避免合并问题。
"""
    blocks = split_paragraphs(text)
    again = inject_paragraph_uids(text, blocks)
    assert again.count("paragraph_uid: 11111111") == 1
