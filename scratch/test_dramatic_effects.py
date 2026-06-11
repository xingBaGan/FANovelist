"""E2E Verification script to test Graphiti's dramatic narrative effects.

This script executes a two-chapter progression:
1. Ingests Chapter 1: Li Mo is panicked, holds the "forged letter" (Chekhov's Gun).
2. Ingests Chapter 2: Wang Tiger steals the "forged letter". Li Mo shifts to angry/desperate; Wang Tiger becomes arrogant.
3. Queries Neo4j to verify:
   - Dynamic Character State Updates (panicked -> angry/desperate)
   - Chekhov's Gun Relationship Shifts (Li Mo -> Wang Tiger)
   - Information Disparity/Beliefs (Wang Tiger believes Li Mo has evidence, which is a misconception)
   - Temporal order of events.
"""

from __future__ import annotations

import asyncio
import os
import sqlite3
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
from openharness.graphiti.ingest import ingest_submitted_document
from openharness.graphiti.ingest_store import IngestStateStore

TEST_GROUP_ID = "test-dramatic-effects"


async def main() -> None:
    workspace_root = Path(__file__).resolve().parents[1]
    studio_root = workspace_root / "my-novel" / "studio"
    db_path = studio_root / ".graphiti" / "ingest.db"

    # Setup directories
    chapters_dir = studio_root / "chapters"
    chapters_dir.mkdir(parents=True, exist_ok=True)
    ch1_path = chapters_dir / "chapter_test_01.md"
    ch2_path = chapters_dir / "chapter_test_02.md"

    # Write Chapter 1
    ch1_text = """# 第一章 绝地博弈
<!-- paragraph_uid: test-01-001 -->
李默此时满手是汗，他的气海破碎处于虚弱状态，心中极度渴望揭穿叛徒活下去。他感到很慌张，紧捏着怀里的伪造密信。这封信是他唯一的契诃夫之枪。
"""
    ch1_path.write_text(ch1_text, encoding="utf-8")

    # Write Chapter 2
    ch2_text = """# 第二章 密信易手
<!-- paragraph_uid: test-02-001 -->
王虎带人包围了后山，乘李默不备抢走了他怀里的伪造密信。那封作为物证的密信落入了王虎的手中。王虎坚信李默已经掌握了叛国通敌的铁证，所以他要抢走信件销毁证据。李默看着空空如也的双手，感到极度愤怒与绝望；而王虎则变得狂妄自大。
"""
    ch2_path.write_text(ch2_text, encoding="utf-8")

    # 1. Clean Group in Neo4j and SQLite
    if db_path.exists():
        db_path.unlink()
        print("Cleaned up SQLite database.")

    settings = GraphitiSettings.from_env(group_id=TEST_GROUP_ID)
    client = GraphitiClient(settings)
    store = IngestStateStore(db_path)

    if client.available:
        print("Cleaning up existing test group data in Neo4j...")
        await client.connect()
        await client._graphiti.driver.execute_query(
            "MATCH (n) WHERE n.group_id = $group_id DETACH DELETE n",
            params={"group_id": TEST_GROUP_ID}
        )

    print("\n--- INGESTING CHAPTER 1 ---")
    await ingest_submitted_document(
        source_path=ch1_path,
        source_kind="chapter",
        group_id=TEST_GROUP_ID,
        submit_gate="approve-chapter",
        submit_scope="chapter_all",
        studio_root=studio_root,
        graphiti=client,
        store=store,
        write_uids_to_markdown=False,
    )

    print("\n=== VERIFYING GRAPH STATE AFTER CHAPTER 1 ===")
    
    # Check Li Mo's state and item ownership
    res1 = await client._graphiti.driver.execute_query(
        "MATCH (c:MajorCharacter {name: '李默', group_id: $group_id}) RETURN c.emotional_state AS emotional_state, c.physical_status AS physical_status",
        params={"group_id": TEST_GROUP_ID}
    )
    if res1.records:
        r = res1.records[0]
        print(f"Li Mo's state: emotional_state='{r['emotional_state']}', physical_status='{r['physical_status']}'")
    else:
        print("Error: Li Mo node not found.")

    res_item1 = await client._graphiti.driver.execute_query(
        "MATCH (c:MajorCharacter {name: '李默', group_id: $group_id})-[r:RELATES_TO]->(g:ChekhovsGun {group_id: $group_id}) "
        "WHERE r.invalid_at IS NULL "
        "RETURN r.name AS rel_type, g.name AS gun_name",
        params={"group_id": TEST_GROUP_ID}
    )
    if res_item1.records:
        rec = res_item1.records[0]
        print(f"Li Mo holds Chekhov's Gun: '{rec['gun_name']}' via relationship '{rec['rel_type']}'")
    else:
        print("Li Mo holds no items.")

    print("\n--- INGESTING CHAPTER 2 ---")
    await ingest_submitted_document(
        source_path=ch2_path,
        source_kind="chapter",
        group_id=TEST_GROUP_ID,
        submit_gate="approve-chapter",
        submit_scope="chapter_all",
        studio_root=studio_root,
        graphiti=client,
        store=store,
        write_uids_to_markdown=False,
    )

    print("\n=== VERIFYING GRAPH STATE AFTER CHAPTER 2 ===")

    # Verify 1: Character State Shift
    res2 = await client._graphiti.driver.execute_query(
        "MATCH (c:MajorCharacter {name: '李默', group_id: $group_id}) RETURN c.emotional_state AS emotional_state, c.physical_status AS physical_status",
        params={"group_id": TEST_GROUP_ID}
    )
    if res2.records:
        r = res2.records[0]
        print(f"[Verification 1 - Character State] Li Mo's state updated:")
        print(f"  emotional_state: '{r['emotional_state']}' (Expected: shifted to angry / desperate / frustrated)")
        print(f"  physical_status: '{r['physical_status']}'")

    res_tiger = await client._graphiti.driver.execute_query(
        "MATCH (c:MajorCharacter {name: '王虎', group_id: $group_id}) RETURN c.emotional_state AS emotional_state",
        params={"group_id": TEST_GROUP_ID}
    )
    if res_tiger.records:
        print(f"[Verification 1 - Character State] Wang Tiger's state updated: emotional_state='{res_tiger.records[0]['emotional_state']}' (Expected: arrogant/confident)")

    # Verify 2: Chekhov's Gun Ownership Shift
    res_item2_limo = await client._graphiti.driver.execute_query(
        "MATCH (c:MajorCharacter {name: '李默', group_id: $group_id})-[r:RELATES_TO]->(g:ChekhovsGun {group_id: $group_id}) "
        "WHERE r.invalid_at IS NULL "
        "RETURN r.name AS rel_type, g.name AS gun_name",
        params={"group_id": TEST_GROUP_ID}
    )
    res_item2_tiger = await client._graphiti.driver.execute_query(
        "MATCH (c:MajorCharacter {name: '王虎', group_id: $group_id})-[r:RELATES_TO]->(g:ChekhovsGun {group_id: $group_id}) "
        "WHERE r.invalid_at IS NULL "
        "RETURN r.name AS rel_type, g.name AS gun_name",
        params={"group_id": TEST_GROUP_ID}
    )
    print(f"[Verification 2 - Item Ownership Shift]:")
    if res_item2_limo.records:
        print(f"  Does Li Mo still hold the letter? Yes (holds '{res_item2_limo.records[0]['gun_name']}' via '{res_item2_limo.records[0]['rel_type']}')")
    else:
        print("  Does Li Mo still hold the letter? No (Correctly disconnected)")

    if res_item2_tiger.records:
        print(f"  Does Wang Tiger now hold the letter? Yes (holds '{res_item2_tiger.records[0]['gun_name']}' via '{res_item2_tiger.records[0]['rel_type']}')")
    else:
        print("  Does Wang Tiger now hold the letter? No")

    # Verify 3: Information Asymmetry / Beliefs
    res_belief = await client._graphiti.driver.execute_query(
        "MATCH (c:MajorCharacter {group_id: $group_id})-[r:RELATES_TO {name: 'BELIEVES'}]->(b:Belief {group_id: $group_id}) "
        "WHERE r.invalid_at IS NULL "
        "RETURN c.name AS character, b.name AS belief_content, b.is_misconception AS is_misconception",
        params={"group_id": TEST_GROUP_ID}
    )
    print(f"[Verification 3 - Cognitive Asymmetry]:")
    for r in res_belief.records:
        print(f"  Character: '{r['character']}' believes '{r['belief_content']}' | is_misconception: {r['is_misconception']}")

    # Verify 4: Temporal Episode Sequence
    res_time = await client._graphiti.driver.execute_query(
        "MATCH (e:Episodic {group_id: $group_id}) RETURN e.name AS name, e.valid_at AS ref_time ORDER BY e.valid_at",
        params={"group_id": TEST_GROUP_ID}
    )
    print(f"[Verification 4 - Chronological Sequence]:")
    for idx, r in enumerate(res_time.records, 1):
        ref_time = r['ref_time']
        ref_time_str = ref_time.isoformat() if hasattr(ref_time, "isoformat") else str(ref_time)
        print(f"  Episode {idx}: Name='{r['name']}', Reference Time='{ref_time_str}'")

    # Clean up temp files
    if ch1_path.exists():
        ch1_path.unlink()
    if ch2_path.exists():
        ch2_path.unlink()
    await client.close()


if __name__ == "__main__":
    asyncio.run(main())
