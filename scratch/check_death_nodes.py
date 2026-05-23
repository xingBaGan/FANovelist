import asyncio
import os
from pathlib import Path
from openharness.graphiti.client import GraphitiClient
from openharness.graphiti.config import GraphitiSettings

def load_env():
    env_path = Path(__file__).resolve().parents[1] / "my-novel" / ".env"
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, val = line.split("=", 1)
                os.environ[key.strip()] = val.strip()

load_env()
TEST_GROUP_ID = "test-death"

async def main():
    client = GraphitiClient(GraphitiSettings.from_env(group_id=TEST_GROUP_ID))
    await client.connect()
    
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
    asyncio.run(main())
