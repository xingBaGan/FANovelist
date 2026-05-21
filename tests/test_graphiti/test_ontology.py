"""Tests for novel prescribed ontology."""

from graphiti_core.utils.ontology_utils.entity_types_utils import validate_entity_types

from openharness.graphiti.ontology import NOVEL_ENTITY_TYPES, MajorCharacter, MinorCharacter


def test_novel_entity_types_validate() -> None:
    assert validate_entity_types(NOVEL_ENTITY_TYPES) is True


def test_major_character_consolidated_background() -> None:
    c = MajorCharacter(
        personality="坚毅",
        background="生于江城，幼年丧父，由母亲独自抚养长大",
    )
    assert c.personality == "坚毅"
    assert "丧父" in (c.background or "")


def test_minor_character_has_no_background_field() -> None:
    assert "background" not in MinorCharacter.model_fields
    assert "scene_note" in MinorCharacter.model_fields
