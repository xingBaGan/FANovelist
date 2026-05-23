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

def load_env() -> None:
    env_path = Path(__file__).resolve().parents[1] / "my-novel" / ".env"
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, val = line.split("=", 1)
                os.environ[key.strip()] = val.strip()

load_env()
TEST_GROUP_ID = "test-inspect"

async def inspect():
    client = GraphitiClient(GraphitiSettings.from_env(group_id=TEST_GROUP_ID))
    await client.connect()
    
    # Clean up test-inspect group
    await client._graphiti.driver.execute_query(
        "MATCH (n) WHERE n.group_id = $group_id DETACH DELETE n",
        params={"group_id": TEST_GROUP_ID}
    )
    
    t1 = datetime(2020, 1, 1, tzinfo=timezone.utc)
    print("Ingesting episode...")
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
    
    # Query all nodes
    print("--- NODES ---")
    nodes_res = await client._graphiti.driver.execute_query(
        "MATCH (n) WHERE n.group_id = $group_id RETURN n.name AS name, labels(n) AS labels, properties(n) AS props",
        params={"group_id": TEST_GROUP_ID}
    )
    for r in nodes_res.records:
        print(f"Node: {r['name']} | Labels: {r['labels']} | Props: {r['props']}")
        
    # Query all edges
    print("--- EDGES ---")
    edges_res = await client._graphiti.driver.execute_query(
        "MATCH (n)-[r]->(m) WHERE r.group_id = $group_id RETURN n.name AS src, type(r) AS rel_type, r.name AS r_name, m.name AS tgt, properties(r) AS props",
        params={"group_id": TEST_GROUP_ID}
    )
    for r in edges_res.records:
        clean_props = {k: v for k, v in r['props'].items() if k != 'fact_embedding'}
        print(f"Edge: {r['src']} -[{r['rel_type']}:{r['r_name']}]-> {r['tgt']} | Props: {clean_props}")

    await client.close()

if __name__ == "__main__":
    asyncio.run(inspect())
