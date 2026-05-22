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
    
    nodes_res = await client._graphiti.driver.execute_query(
        "MATCH (n:Entity {name: '李战'}) WHERE n.group_id = $group_id RETURN properties(n) AS props, labels(n) AS labels",
        params={"group_id": TEST_GROUP_ID}
    )
    for r in nodes_res.records:
        print("Labels:", r['labels'])
        print("Props:", {k: v for k, v in r['props'].items() if k != 'summary_embedding'})
        
    await client.close()

if __name__ == "__main__":
    asyncio.run(main())
