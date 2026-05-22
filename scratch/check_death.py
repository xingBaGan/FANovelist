#!/usr/bin/env python3
import asyncio
import logging
import os
import sys
from pathlib import Path

# Try to load my-novel/.env to obtain real credentials
repo_root = Path("/Users/jzj/ai_writing/OpenHarness")
env_path = repo_root / "my-novel" / ".env"
if env_path.exists():
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ[k.strip()] = v.strip()

# Add src/ to sys.path
sys.path.insert(0, str(repo_root / "src"))

from openharness.graphiti.client import GraphitiClient
from openharness.graphiti.config import GraphitiSettings
from openharness.graphiti.conflicts import check_submit_conflicts

TEST_GROUP_ID = "test-death-scratch"

async def purge(client):
    await client._graphiti.driver.execute_query(
        "MATCH (n) WHERE n.group_id = $group_id DETACH DELETE n",
        params={"group_id": TEST_GROUP_ID}
    )

async def main():
    client = GraphitiClient(GraphitiSettings.from_env(group_id=TEST_GROUP_ID))
    await client.connect()
    try:
        await purge(client)
        print("Purged database partition.")

        # Ingest Li Zhan's death
        print("Ingesting: 李战在三年前战死。")
        await client.add_episode(
            name="ch01#p2",
            episode_body="李战在三年前战死。",
            source_description="test-source",
            group_id=TEST_GROUP_ID
        )

        # Query nodes
        nodes_res = await client._graphiti.driver.execute_query(
            "MATCH (n) WHERE n.group_id = $group_id RETURN n.name AS name, labels(n) AS labels, properties(n) AS props",
            params={"group_id": TEST_GROUP_ID}
        )
        print("\n--- NODES IN GRAPH ---")
        for r in nodes_res.records:
            print(f"Node: {r['name']} | Labels: {r['labels']} | Props: {r['props']}")

        # Query facts using search_facts
        print("\n--- SEARCH FACTS FOR '李战' ---")
        facts = await client.search_facts("李战", group_id=TEST_GROUP_ID)
        for f in facts:
            print(f"Fact type: {type(f)} | Content/Fact: {getattr(f, 'fact', f)}")

        # Run conflict check
        draft = "李战目前在江城修炼。"
        print(f"\nChecking conflicts for draft: {draft}")
        report = await check_submit_conflicts(
            client=client,
            draft_text=draft,
            focus_character="李战",
            group_id=TEST_GROUP_ID
        )

        print("\n--- CONFLICT REPORT ---")
        print(f"Blocked: {report.blocked}")
        print("Conflicts:")
        for c in report.conflicts:
            print(f"  Severity: {c.severity} | Category: {c.category} | Message: {c.message}")

    finally:
        await purge(client)
        await client.close()

if __name__ == "__main__":
    asyncio.run(main())
