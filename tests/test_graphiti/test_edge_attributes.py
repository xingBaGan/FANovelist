"""Tests for custom edge schemas and attribute extraction."""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from graphiti_core.edges import EntityEdge
from graphiti_core.nodes import EpisodicNode, EpisodeType
from openharness.graphiti.client import GraphitiClient
from openharness.graphiti.ontology import (
    NOVEL_EDGE_TYPE_MAP,
    NOVEL_EDGE_TYPES,
    ActionRelation,
    EmotionalRelation,
    PhysicalRelation,
    SocialRelation,
)


def test_ontology_edge_definitions() -> None:
    """Verify that novel edge ontology definitions are correct."""
    assert "BELONGS_TO" in NOVEL_EDGE_TYPES
    assert "HATES" in NOVEL_EDGE_TYPES
    assert "KILLED" in NOVEL_EDGE_TYPES
    assert "OWNS" in NOVEL_EDGE_TYPES
    assert "PARTICIPATED_IN" in NOVEL_EDGE_TYPES
    assert "HAPPENED_AT" in NOVEL_EDGE_TYPES
    assert "CAUSED" in NOVEL_EDGE_TYPES
    assert "BECOMES" in NOVEL_EDGE_TYPES
    assert "EVOLVED_INTO" in NOVEL_EDGE_TYPES

    assert NOVEL_EDGE_TYPES["BELONGS_TO"] == SocialRelation
    assert NOVEL_EDGE_TYPES["HATES"] == EmotionalRelation
    assert NOVEL_EDGE_TYPES["KILLED"] == ActionRelation
    assert NOVEL_EDGE_TYPES["OWNS"] == PhysicalRelation
    assert NOVEL_EDGE_TYPES["PARTICIPATED_IN"] == ActionRelation
    assert NOVEL_EDGE_TYPES["HAPPENED_AT"] == PhysicalRelation
    assert NOVEL_EDGE_TYPES["CAUSED"] == ActionRelation
    assert NOVEL_EDGE_TYPES["BECOMES"] == ActionRelation
    assert NOVEL_EDGE_TYPES["EVOLVED_INTO"] == ActionRelation

    # RelatedPerson should act like a Character and have mappings
    assert ("RelatedPerson", "Organization") in NOVEL_EDGE_TYPE_MAP
    assert "BELONGS_TO" in NOVEL_EDGE_TYPE_MAP[("RelatedPerson", "Organization")]

    assert ("MajorCharacter", "Organization") in NOVEL_EDGE_TYPE_MAP
    assert "BELONGS_TO" in NOVEL_EDGE_TYPE_MAP[("MajorCharacter", "Organization")]

    assert ("MajorCharacter", "MajorCharacter") in NOVEL_EDGE_TYPE_MAP
    assert "HATES" in NOVEL_EDGE_TYPE_MAP[("MajorCharacter", "MajorCharacter")]
    assert "KILLED" in NOVEL_EDGE_TYPE_MAP[("MajorCharacter", "MajorCharacter")]
    assert "BECOMES" in NOVEL_EDGE_TYPE_MAP[("MajorCharacter", "MajorCharacter")]

    assert ("MajorCharacter", "NarrativeElement") in NOVEL_EDGE_TYPE_MAP
    assert "OWNS" in NOVEL_EDGE_TYPE_MAP[("MajorCharacter", "NarrativeElement")]
    assert "BECOMES" in NOVEL_EDGE_TYPE_MAP[("MajorCharacter", "NarrativeElement")]
    assert "EVOLVED_INTO" in NOVEL_EDGE_TYPE_MAP[("MajorCharacter", "NarrativeElement")]

    # Event, Location, Organization mapping relations
    assert ("MajorCharacter", "Event") in NOVEL_EDGE_TYPE_MAP
    assert "PARTICIPATED_IN" in NOVEL_EDGE_TYPE_MAP[("MajorCharacter", "Event")]

    assert ("Event", "Location") in NOVEL_EDGE_TYPE_MAP
    assert "HAPPENED_AT" in NOVEL_EDGE_TYPE_MAP[("Event", "Location")]
    assert "LOCATED_IN" in NOVEL_EDGE_TYPE_MAP[("Event", "Location")]

    assert ("Organization", "Location") in NOVEL_EDGE_TYPE_MAP
    assert "LOCATED_IN" in NOVEL_EDGE_TYPE_MAP[("Organization", "Location")]

    assert ("Location", "Location") in NOVEL_EDGE_TYPE_MAP
    assert "LOCATED_IN" in NOVEL_EDGE_TYPE_MAP[("Location", "Location")]

    # Event to Event causality
    assert ("Event", "Event") in NOVEL_EDGE_TYPE_MAP
    assert "CAUSED" in NOVEL_EDGE_TYPE_MAP[("Event", "Event")]
    assert "TRIGGERS" in NOVEL_EDGE_TYPE_MAP[("Event", "Event")]

    # Event to Character / NarrativeElement causality
    assert ("Event", "MajorCharacter") in NOVEL_EDGE_TYPE_MAP
    assert "CAUSED" in NOVEL_EDGE_TYPE_MAP[("Event", "MajorCharacter")]
    assert ("Event", "NarrativeElement") in NOVEL_EDGE_TYPE_MAP
    assert "CAUSED" in NOVEL_EDGE_TYPE_MAP[("Event", "NarrativeElement")]

    # Organization / NarrativeElement to Organization / NarrativeElement transformations
    assert ("Organization", "Organization") in NOVEL_EDGE_TYPE_MAP
    assert "EVOLVED_INTO" in NOVEL_EDGE_TYPE_MAP[("Organization", "Organization")]
    assert ("NarrativeElement", "NarrativeElement") in NOVEL_EDGE_TYPE_MAP
    assert "EVOLVED_INTO" in NOVEL_EDGE_TYPE_MAP[("NarrativeElement", "NarrativeElement")]




@pytest.mark.asyncio
async def test_client_passes_edge_types() -> None:
    """Verify client.add_episode forwards custom edge types/maps to the Graphiti object."""
    client = GraphitiClient()
    # Mocking graphiti core dependency
    client._graphiti = MagicMock()
    # Mocking the async add_episode response structure
    mock_result = MagicMock()
    mock_result.episode.uuid = "mock-episode-uuid"
    mock_result.edges = []
    client._graphiti.add_episode = AsyncMock(return_value=mock_result)

    with patch.object(client, "_ensure_connected", AsyncMock()):
        episode_uuid, edge_uuids = await client.add_episode(
            name="test-episode",
            episode_body="李默击杀了赤炼毒蛇。",
            source_description="test",
        )

        assert episode_uuid == "mock-episode-uuid"
        # Assert that client passed the correct edge_types and edge_type_map
        client._graphiti.add_episode.assert_called_once()
        kwargs = client._graphiti.add_episode.call_args[1]
        assert kwargs["edge_types"] == NOVEL_EDGE_TYPES
        assert kwargs["edge_type_map"] == NOVEL_EDGE_TYPE_MAP


@pytest.mark.asyncio
async def test_resolve_emotional_edge_attributes() -> None:
    """Verify that resolve_extracted_edge extracts properties for emotional relations."""
    from graphiti_core.utils.maintenance.edge_operations import resolve_extracted_edge

    mock_llm_client = AsyncMock()
    mock_llm_client.generate_response = AsyncMock(
        return_value={"emotion": "极度怨恨", "detail": "夺妻之妙/冲突"}
    )

    episode = EpisodicNode(
        name="test-episode",
        content="李默极度怨恨张三。",
        source_description="test",
        valid_at=datetime.now(timezone.utc),
        group_id="test-group",
        source=EpisodeType.text,
    )

    edge = EntityEdge(
        uuid="test-edge-uuid",
        group_id="test-group",
        source_node_uuid="char1-uuid",
        target_node_uuid="char2-uuid",
        name="HATES",
        fact="李默极度怨恨张三",
        episodes=["test-episode-uuid"],
        created_at=datetime.now(timezone.utc),
        valid_at=datetime.now(timezone.utc),
        attributes={},
    )

    resolved_edge, _, _ = await resolve_extracted_edge(
        llm_client=mock_llm_client,
        extracted_edge=edge,
        related_edges=[],
        existing_edges=[],
        episode=episode,
        edge_type_candidates={"HATES": EmotionalRelation},
    )

    assert resolved_edge.attributes == {"emotion": "极度怨恨", "detail": "夺妻之妙/冲突"}
    mock_llm_client.generate_response.assert_called_once()


@pytest.mark.asyncio
async def test_resolve_action_edge_attributes() -> None:
    """Verify that resolve_extracted_edge extracts properties for actions."""
    from graphiti_core.utils.maintenance.edge_operations import resolve_extracted_edge

    mock_llm_client = AsyncMock()
    mock_llm_client.generate_response = AsyncMock(
        return_value={"action_type": "杀死", "context": "大乾历100年在江城"}
    )

    episode = EpisodicNode(
        name="test-episode",
        content="李默于大乾历100年在江城杀死了赤炼毒蛇。",
        source_description="test",
        valid_at=datetime.now(timezone.utc),
        group_id="test-group",
        source=EpisodeType.text,
    )

    edge = EntityEdge(
        uuid="test-edge-uuid",
        group_id="test-group",
        source_node_uuid="char-uuid",
        target_node_uuid="snake-uuid",
        name="KILLED",
        fact="李默大乾历100年在江城杀死了赤炼毒蛇",
        episodes=["test-episode-uuid"],
        created_at=datetime.now(timezone.utc),
        valid_at=datetime.now(timezone.utc),
        attributes={},
    )

    resolved_edge, _, _ = await resolve_extracted_edge(
        llm_client=mock_llm_client,
        extracted_edge=edge,
        related_edges=[],
        existing_edges=[],
        episode=episode,
        edge_type_candidates={"KILLED": ActionRelation},
    )

    assert resolved_edge.attributes == {"action_type": "杀死", "context": "大乾历100年在江城"}
    mock_llm_client.generate_response.assert_called_once()


@pytest.mark.asyncio
async def test_resolve_causality_and_transformation_edge_attributes() -> None:
    """Verify that resolve_extracted_edge extracts properties for causality and transformation relations."""
    from graphiti_core.utils.maintenance.edge_operations import resolve_extracted_edge

    mock_llm_client = AsyncMock()
    mock_llm_client.generate_response = AsyncMock(
        return_value={"action_type": "导致/复仇", "context": "因为李默杀死了王虎"}
    )

    episode = EpisodicNode(
        name="test-episode",
        content="因为李默杀死了王虎，所以王虎之子前来复仇。",
        source_description="test",
        valid_at=datetime.now(timezone.utc),
        group_id="test-group",
        source=EpisodeType.text,
    )

    edge = EntityEdge(
        uuid="test-edge-uuid",
        group_id="test-group",
        source_node_uuid="event1-uuid",
        target_node_uuid="event2-uuid",
        name="CAUSED",
        fact="李默杀死王虎导致王虎之子前来复仇",
        episodes=["test-episode-uuid"],
        created_at=datetime.now(timezone.utc),
        valid_at=datetime.now(timezone.utc),
        attributes={},
    )

    resolved_edge, _, _ = await resolve_extracted_edge(
        llm_client=mock_llm_client,
        extracted_edge=edge,
        related_edges=[],
        existing_edges=[],
        episode=episode,
        edge_type_candidates={"CAUSED": ActionRelation},
    )

    assert resolved_edge.attributes == {"action_type": "导致/复仇", "context": "因为李默杀死了王虎"}
    mock_llm_client.generate_response.assert_called_once()

