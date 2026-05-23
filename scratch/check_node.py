import asyncio
from openharness.graphiti.client import GraphitiClient

async def main():
    client = GraphitiClient()
    await client.connect()
    
    res = await client._graphiti.driver.execute_query(
        "MATCH (n) WHERE n.group_id = 'test-e2e-agent-loop' RETURN n.name AS name, labels(n) AS labels"
    )
    for record in res.records:
        print(f"Node: {record['name']} | Labels: {record['labels']}")
        
    await client.close()

asyncio.run(main())
