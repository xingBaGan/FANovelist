"""Tests for canon snippet classification."""

from openharness.graphiti.canon_classify import classify_snippet


def test_background_not_entity() -> None:
    items = classify_snippet("幼年丧父，母亲独自抚养", focus_character="李默")
    kinds = {i.kind for i in items}
    assert "background" in kinds


def test_narrative_element_for_role() -> None:
    items = classify_snippet("成为外门弟子，修习基础剑法", focus_character="李默")
    assert any(i.kind == "narrative_element" for i in items)


def test_organization_hint() -> None:
    items = classify_snippet("李默加入天机阁", focus_character="李默")
    assert any(i.entity_type == "Organization" for i in items)
