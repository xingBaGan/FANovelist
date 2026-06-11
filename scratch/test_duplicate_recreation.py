import asyncio
import os
import sqlite3
import shutil
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
from openharness.graphiti.ingest import ingest_submitted_document

async def main():
    settings = GraphitiSettings.from_env()
    client = GraphitiClient(settings)
    
    test_root = _workspace_root / "scratch" / "test_dup_run"
    if test_root.exists():
        shutil.rmtree(test_root)
    test_root.mkdir(parents=True)
    
    test_chapter = test_root / "chapters" / "test_chapter.md"
    test_chapter.parent.mkdir(parents=True)
    
    test_chapter.write_text(
        "# Test Chapter\n\n"
        "<!-- paragraph_uid: test-custom-uid-xyz -->\n\n"
        "This is a test paragraph that is long enough to stand alone and be processed by the ingestion engine without merging.\n",
        encoding="utf-8"
    )
    
    print("--- FIRST INGESTION (creating node in Neo4j and SQLite) ---")
    report = await ingest_submitted_document(
        source_path=test_chapter,
        source_kind="chapter",
        group_id=settings.group_id,
        submit_gate="test-dup",
        submit_scope="chapter_all",
        studio_root=test_root,
        graphiti=client,
        write_uids_to_markdown=False,
    )
    print(f"First ingestion done. Ingested: {report.paragraphs_ingested}")
    
    await client.connect()
    episode_name = f"{test_chapter}#test-custom-uid-xyz"
    existing_uuid, existing_edges, existing_content = await client.get_episode_by_name(episode_name)
    print(f"Neo4j check: uuid={existing_uuid}, content={existing_content}")
    assert existing_uuid is not None, "Episode should have been created in Neo4j!"
    
    db_path = test_root / ".graphiti" / "ingest.db"
    print(f"Wiping SQLite database at: {db_path}")
    db_path.unlink()
    
    print("\n--- SECOND INGESTION (SQLite is empty, should REUSE from Neo4j) ---")
    report2 = await ingest_submitted_document(
        source_path=test_chapter,
        source_kind="chapter",
        group_id=settings.group_id,
        submit_gate="test-dup",
        submit_scope="chapter_all",
        studio_root=test_root,
        graphiti=client,
        write_uids_to_markdown=False,
    )
    print(f"Second ingestion done. Ingested: {report2.paragraphs_ingested}")
    
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        ep_rows = conn.execute("SELECT episode_uuid FROM paragraph_episodes WHERE paragraph_uid = 'test-custom-uid-xyz'").fetchall()
        print(f"SQLite recovery check: found episode_uuid in DB: {ep_rows[0]['episode_uuid'] if ep_rows else None}")
        assert len(ep_rows) == 1
        assert ep_rows[0]["episode_uuid"] == existing_uuid, "Reused UUID should match first run's UUID!"

    res = await client._graphiti.driver.execute_query(
        "MATCH (e:Episodic) WHERE e.name = $name AND e.group_id = $group_id RETURN e.uuid as uuid",
        name=episode_name, group_id=settings.group_id
    )
    print(f"Neo4j duplicate check: found {len(res.records)} nodes with name '{episode_name}'")
    assert len(res.records) == 1, "There should be exactly one episodic node in Neo4j!"
    
    await client.remove_episode(existing_uuid)
    print("Cleaned up Neo4j test episode.")
    await client.close()
    
    shutil.rmtree(test_root)
    print("Cleaned up local files.")
    print("SUCCESS: End-to-end duplicate recreation and self-healing test passed!")

if __name__ == "__main__":
    asyncio.run(main())
