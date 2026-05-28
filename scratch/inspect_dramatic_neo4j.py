import asyncio
import os
from pathlib import Path

# Load .env manually
_workspace_root = Path(__file__).resolve().parents[1]
_env_path = _workspace_root / ".env"
if _env_path.exists():
    for _line in _env_path.read_text(encoding="utf-8").splitlines():
        _line = _line.strip()
        if _line and not _line.startswith("#") and "=" in _line:
            _k, _, _v = _line.partition("=")
            os.environ.setdefault(_k.strip(), _v.strip())

from openharness.graphiti.client import GraphitiClient
from openharness.graphiti.config import GraphitiSettings


async def main() -> None:
    settings = GraphitiSettings.from_env()
    client = GraphitiClient(settings)
    await client.connect()

    print(f"=== NEO4J DRAMATIC NODES (Group: {settings.group_id}) ===")
    nodes_res = await client._graphiti.driver.execute_query(
        "MATCH (n) WHERE n.group_id = $group_id RETURN n.name AS name, labels(n) AS labels, properties(n) AS props",
        params={"group_id": settings.group_id}
    )
    for r in nodes_res.records:
        print(f"Node: '{r['name']}' | Labels: {r['labels']}")
        # Print non-empty properties
        for k, v in r['props'].items():
            if v and k not in ('summary_embedding', 'name_embedding'):
                print(f"  {k}: {v}")

    print(f"\n=== NEO4J DRAMATIC EDGES (Group: {settings.group_id}) ===")
    edges_res = await client._graphiti.driver.execute_query(
        "MATCH (n)-[r]->(m) WHERE r.group_id = $group_id RETURN n.name AS src, type(r) AS rel_type, r.name AS r_name, m.name AS tgt, properties(r) AS props",
        params={"group_id": settings.group_id}
    )
    for r in edges_res.records:
        clean_props = {k: v for k, v in r['props'].items() if k != 'fact_embedding'}
        print(f"Edge: '{r['src']}' -[{r['rel_type']}:{r['r_name']}]-> '{r['tgt']}'")
        for k, v in clean_props.items():
            if v:
                print(f"  {k}: {v}")

    await client.close()


if __name__ == "__main__":
    asyncio.run(main())
