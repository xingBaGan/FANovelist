"""Integration tests against a live Neo4j database."""

from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path
import pytest

from openharness.graphiti.client import GraphitiClient
from openharness.graphiti.config import GraphitiSettings
from openharness.graphiti.conflicts import check_submit_conflicts

# Mark all tests in this file as integration tests
pytestmark = pytest.mark.integration


def _load_env() -> None:
    """Load settings from my-novel/.env if present."""
    env_path = Path(__file__).resolve().parents[2] / "my-novel" / ".env"
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, val = line.split("=", 1)
                os.environ[key.strip()] = val.strip()


# Load the environment before checking configuration
_load_env()

NEO4J_CONFIGURED = (
    os.environ.get("NEO4J_URI") is not None
    and os.environ.get("OPENAI_API_KEY") is not None
)

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(not NEO4J_CONFIGURED, reason="Neo4j credentials or OpenAI API key missing"),
]

TEST_GROUP_ID = "test-integration"


async def _purge_test_graph(client: GraphitiClient) -> None:
    """Ensure the test graph partition is completely empty."""
    await client.connect()
    # Delete all nodes matching the test group ID (and detach relationships)
    await client._graphiti.driver.execute_query(
        "MATCH (n) WHERE n.group_id = $group_id DETACH DELETE n",
        params={"group_id": TEST_GROUP_ID}
    )
    # Also delete any relationships that might not be bound to matched nodes
    await client._graphiti.driver.execute_query(
        "MATCH ()-[r]-() WHERE r.group_id = $group_id DELETE r",
        params={"group_id": TEST_GROUP_ID}
    )
    await client.close()


@pytest.fixture(autouse=True)
async def graphiti_test_lifecycle() -> None:
    """Setup and teardown hook for each integration test."""
    client = GraphitiClient(GraphitiSettings.from_env(group_id=TEST_GROUP_ID))
    await _purge_test_graph(client)
    yield
    await _purge_test_graph(client)


@pytest.mark.asyncio
async def test_integration_origin_tracing() -> None:
    """Goal 1: Ingest a paragraph and verify we can trace the origin back to the source text."""
    client = GraphitiClient(GraphitiSettings.from_env(group_id=TEST_GROUP_ID))
    await client.connect()

    # Ingest a simple fact about Li Mo
    episode_uuid, _ = await client.add_episode(
        name="ch01#p1",
        episode_body="李默出生在江城，自幼跟随母亲生活。",
        source_description="test-source",
        group_id=TEST_GROUP_ID
    )

    assert episode_uuid is not None

    # Retrieve origins
    origins = await client.trace_entity_origins("李默", group_id=TEST_GROUP_ID)
    assert len(origins) >= 1
    assert any(o["episode_name"] == "ch01#p1" for o in origins)
    assert any("李默出生在江城" in o["content"] for o in origins)
    assert all(o["valid_at"] is not None for o in origins)

    await client.close()


@pytest.mark.asyncio
async def test_integration_contradiction_detection() -> None:
    """Goal 2: Ingest facts and verify that check_submit_conflicts blocks contradicting facts."""
    client = GraphitiClient(GraphitiSettings.from_env(group_id=TEST_GROUP_ID))
    await client.connect()

    # Step 1: Ingest birthplace "江城"
    await client.add_episode(
        name="ch01#p1",
        episode_body="李默生于江城。",
        source_description="test-source",
        group_id=TEST_GROUP_ID
    )

    # Step 2: Test birthplace conflict detection (Li Mo born in Yecheng)
    draft_birthplace = "李默生于邺城。"
    
    # Debug nodes
    nodes_res = await client._graphiti.driver.execute_query(
        "MATCH (n) WHERE n.group_id = $group_id RETURN n.name AS name, labels(n) AS labels, properties(n) AS props",
        params={"group_id": TEST_GROUP_ID}
    )
    print("\n--- DEBUG NODES ---")
    for r in nodes_res.records:
        print(f"Node: {r['name']} | Labels: {r['labels']} | Props: {r['props']}")

    report = await check_submit_conflicts(
        client=client,
        draft_text=draft_birthplace,
        focus_character="李默",
        group_id=TEST_GROUP_ID
    )
    print("--- DEBUG REPORT ---")
    print(f"Blocked: {report.blocked}")
    for c in report.conflicts:
        print(f"  Conflict: {c.severity} | {c.category} | {c.message}")
        
    assert report.blocked is True
    assert any("邺城" in c.message or "江城" in c.message for c in report.critical)

    # Step 3: Ingest Li Zhan's death
    await client.add_episode(
        name="ch01#p2",
        episode_body="李战在三年前战死。",
        source_description="test-source",
        group_id=TEST_GROUP_ID
    )

    # Step 4: Test timeline life-death conflict (Li Zhan active)
    draft_death_active = "李战目前在江城修炼。"
    report2 = await check_submit_conflicts(
        client=client,
        draft_text=draft_death_active,
        focus_character="李战",
        group_id=TEST_GROUP_ID
    )
    print("--- DEBUG REPORT 2 ---")
    print(f"Blocked: {report2.blocked}")
    for c in report2.conflicts:
        print(f"  Conflict: {c.severity} | {c.category} | {c.message}")
        
    assert report2.blocked is True
    assert any("生死" in c.message or "战死" in c.message or "修炼" in c.message for c in report2.critical)

    await client.close()


@pytest.mark.asyncio
async def test_integration_temporal_state_queries() -> None:
    """Goal 3: Verify temporal validity of relationships over time using historical queries."""
    client = GraphitiClient(GraphitiSettings.from_env(group_id=TEST_GROUP_ID))
    await client.connect()

    # T1: 2020-01-01 -> Li Mo joins Tianjige as an outer disciple
    # We use reference_time manually via client._graphiti.add_episode to control the timestamps
    t1 = datetime(2020, 1, 1, tzinfo=timezone.utc)
    t2 = datetime(2020, 12, 1, tzinfo=timezone.utc)

    from graphiti_core.nodes import EpisodeType
    from openharness.graphiti.ontology import (
        NOVEL_EDGE_TYPE_MAP,
        NOVEL_EDGE_TYPES,
        NOVEL_ENTITY_TYPES,
        NOVEL_EXTRACTION_INSTRUCTIONS,
    )

    # Add T1 episode
    await client._graphiti.add_episode(
        name="ch01#p3",
        episode_body="2020年，李默加入天机阁成为外门弟子。",
        source_description="test-source",
        reference_time=t1,
        source=EpisodeType.text,
        group_id=TEST_GROUP_ID,
        entity_types=NOVEL_ENTITY_TYPES,
        excluded_entity_types=["Entity"],
        edge_types=NOVEL_EDGE_TYPES,
        edge_type_map=NOVEL_EDGE_TYPE_MAP,
        custom_extraction_instructions=NOVEL_EXTRACTION_INSTRUCTIONS,
    )
    
    # Add T2 episode (role transition / expulsion)
    await client._graphiti.add_episode(
        name="ch01#p4",
        episode_body="2020年底，李默从天机阁毕业，并被逐出天机阁，师门关系就此断绝，他不再是天机阁弟子。",
        source_description="test-source",
        reference_time=t2,
        source=EpisodeType.text,
        group_id=TEST_GROUP_ID,
        entity_types=NOVEL_ENTITY_TYPES,
        excluded_entity_types=["Entity"],
        edge_types=NOVEL_EDGE_TYPES,
        edge_type_map=NOVEL_EDGE_TYPE_MAP,
        custom_extraction_instructions=NOVEL_EXTRACTION_INSTRUCTIONS,
    )

    # Query mid-year T_mid (2020-06-01): Li Mo is still an outer disciple of Tianjige
    rels_mid = await client.get_historical_relationships(
        target_time="2020-06-01T00:00:00Z",
        focus_entity="李默",
        group_id=TEST_GROUP_ID
    )
    
    # Filter for MEMBER_OF relations
    member_relations = [r for r in rels_mid if r["relation_name"] == "MEMBER_OF"]
    assert len(member_relations) >= 1
    assert any("外门弟子" in r.get("fact", "") or r["attributes"].get("role") == "外门弟子" for r in member_relations)

    # Query next year T_after (2021-01-01): Li Mo has been expelled
    rels_after = await client.get_historical_relationships(
        target_time="2021-01-01T00:00:00Z",
        focus_entity="李默",
        group_id=TEST_GROUP_ID
    )
    
    # Assert that MEMBER_OF relation is no longer active
    member_after = [r for r in rels_after if r["relation_name"] == "MEMBER_OF"]
    assert len(member_after) == 0

    await client.close()
