import asyncio
import os
from pathlib import Path

# Load env
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

async def clear_all():
    settings = GraphitiSettings.from_env()
    client = GraphitiClient(settings)
    
    print(f"Group ID: {settings.group_id}")
    
    # 1. Purge Neo4j database for this group
    if client.available:
        print("Purging Neo4j database for group...")
        await client.connect()
        # Delete all nodes and relationships matching the group ID
        await client._graphiti.driver.execute_query(
            "MATCH (n) WHERE n.group_id = $group_id DETACH DELETE n",
            params={"group_id": settings.group_id}
        )
        print("Purged Neo4j nodes.")
        
        # Also clean up relationships just in case
        await client._graphiti.driver.execute_query(
            "MATCH ()-[r]-() WHERE r.group_id = $group_id DELETE r",
            params={"group_id": settings.group_id}
        )
        print("Purged Neo4j relationships.")
        await client.close()
    else:
        print("Neo4j client not available, skipping Neo4j purge.")
        
    # 2. Delete SQLite database
    db_path = _workspace_root / "my-novel" / "studio" / ".graphiti" / "ingest.db"
    if db_path.exists():
        print(f"Deleting SQLite database at {db_path}...")
        db_path.unlink()
        print("Deleted SQLite database.")
    else:
        print(f"SQLite database at {db_path} does not exist, skipping.")

    print("\nClear completed successfully!")

if __name__ == "__main__":
    asyncio.run(clear_all())
