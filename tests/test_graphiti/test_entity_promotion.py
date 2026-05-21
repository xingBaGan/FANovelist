"""Tests for entity promotion rules."""

from openharness.graphiti.entity_promotion import EntitySnapshot, suggest_promotion


def _snap(**kwargs: object) -> EntitySnapshot:
    defaults = {
        "uuid": "u1",
        "name": "长老",
        "primary_label": "NarrativeElement",
        "summary": "",
        "episode_mentions": 0,
        "background": None,
        "scene_note": None,
        "element_note": None,
    }
    defaults.update(kwargs)
    return EntitySnapshot(**defaults)  # type: ignore[arg-type]


def test_narrative_promotes_after_two_episodes() -> None:
    d = suggest_promotion(_snap(episode_mentions=2))
    assert d is not None
    assert d.to_label == "MinorCharacter"


def test_minor_promotes_with_background() -> None:
    d = suggest_promotion(
        _snap(
            name="张长老",
            primary_label="MinorCharacter",
            background="天机阁执法长老",
            episode_mentions=1,
        )
    )
    assert d is not None
    assert d.to_label == "MajorCharacter"


def test_narrative_stays_with_one_mention() -> None:
    assert suggest_promotion(_snap(episode_mentions=1, summary="长老看了一眼")) is None
