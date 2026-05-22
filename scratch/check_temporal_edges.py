import asyncio
import os
from datetime import datetime, timezone
from pathlib import Path
from openharness.graphiti.client import GraphitiClient
from openharness.graphiti.config import GraphitiSettings
from graphiti_core.nodes import EpisodeType
from openharness.graphiti.ontology import (
    NOVEL_EDGE_TYPE_MAP,
    NOVEL_EDGE_TYPES,
    NOVEL_ENTITY_TYPES,
    NOVEL_EXTRACTION_INSTRUCTIONS,
)

def load_env():
    env_path = Path(__file__).resolve().parents[1] / "my-novel" / ".env"
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, val = line.split("=", 1)
                os.environ[key.strip()] = val.strip()

load_env()
TEST_GROUP_ID = "test-temporal-inspect"

async def main():
    client = GraphitiClient(GraphitiSettings.from_env(group_id=TEST_GROUP_ID))
    await client.connect()
    
    # Purge
    await client._graphiti.driver.execute_query(
        "MATCH (n) WHERE n.group_id = $group_id DETACH DELETE n",
        params={"group_id": TEST_GROUP_ID}
    )
    
    t1 = datetime(2020, 1, 1, tzinfo=timezone.utc)
    t2 = datetime(2020, 12, 1, tzinfo=timezone.utc)
    
    print("Ingesting T1...")
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
    
    print("Ingesting T2...")
    await client._graphiti.add_episode(
        name="ch01#p4",
        episode_body="2020年底，李默从天机阁毕业，并被逐出天机阁，师门关系就此断绝。",
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
    
    # Query all nodes
    print("--- NODES ---")
    nodes_res = await client._graphiti.driver.execute_query(
        "MATCH (n) WHERE n.group_id = $group_id RETURN n.name AS name, labels(n) AS labels, properties(n) AS props",
        params={"group_id": TEST_GROUP_ID}
    )
    for r in nodes_res.records:
        print(f"Node: {r['name']} | Labels: {r['labels']}")
        
    # Query all edges
    print("--- EDGES ---")
    edges_res = await client._graphiti.driver.execute_query(
        "MATCH (n)-[r]->(m) WHERE r.group_id = $group_id RETURN n.name AS src, type(r) AS rel_type, r.name AS r_name, m.name AS tgt, r.fact AS fact, r.valid_at AS valid_at, r.invalid_at AS invalid_at",
        params={"group_id": TEST_GROUP_ID}
    )
    for r in edges_res.records:
        print(f"Edge: {r['src']} -[{r['rel_type']}:{r['r_name']}]-> {r['tgt']} | Fact: {r['fact']} | valid_at: {r['valid_at']} | invalid_at: {r['invalid_at']}")

    print("--- historical relationships at 2020-06-01 ---")
    rels_mid = await client.get_historical_relationships(
        target_time="2020-06-01T00:00:00Z",
        focus_entity="李默",
        group_id=TEST_GROUP_ID
    )
    for r in rels_mid:
        print(f"Mid: {r['source_name']} -[{r['relation_name']}]-> {r['target_name']} | Fact: {r['fact']} | valid_at: {r['valid_at']} | invalid_at: {r['invalid_at']}")

    print("--- historical relationships at 2021-01-01 ---")
    rels_after = await client.get_historical_relationships(
        target_time="2021-01-01T00:00:00Z",
        focus_entity="李默",
        group_id=TEST_GROUP_ID
    )
    for r in rels_after:
        print(f"After: {r['source_name']} -[{r['relation_name']}]-> {r['target_name']} | Fact: {r['fact']} | valid_at: {r['valid_at']} | invalid_at: {r['invalid_at']}")

    await client.close()

if __name__ == "__main__":
    asyncio.run(main())
