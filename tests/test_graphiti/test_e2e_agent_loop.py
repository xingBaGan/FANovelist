"""End-to-End Test: Simulating an AI Agent Writing Loop."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from openharness.graphiti.client import GraphitiClient
from openharness.graphiti.config import GraphitiSettings
from openharness.graphiti.conflicts import check_submit_conflicts

# Mark all tests in this file as integration tests
pytestmark = pytest.mark.integration


def _load_env() -> None:
    """Load settings from my-novel/.env if present."""
    env_path = Path(__file__).resolve().parents[2] / "my-novel" / ".env"
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, val = line.split("=", 1)
                os.environ[key.strip()] = val.strip()


# Load the environment before checking configuration
_load_env()

NEO4J_CONFIGURED = (
    os.environ.get("NEO4J_URI") is not None
    and os.environ.get("OPENAI_API_KEY") is not None
)

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(not NEO4J_CONFIGURED, reason="Neo4j credentials or OpenAI API key missing"),
]

TEST_GROUP_ID = "test-e2e-agent-loop"


async def _purge_test_graph(client: GraphitiClient) -> None:
    """Ensure the test graph partition is completely empty to guarantee zero side effects."""
    await client.connect()
    # Delete all nodes matching the test group ID (and detach relationships)
    await client._graphiti.driver.execute_query(
        "MATCH (n) WHERE n.group_id = $group_id DETACH DELETE n",
        params={"group_id": TEST_GROUP_ID}
    )
    # Also delete any relationships that might not be bound to matched nodes
    await client._graphiti.driver.execute_query(
        "MATCH ()-[r]-() WHERE r.group_id = $group_id DELETE r",
        params={"group_id": TEST_GROUP_ID}
    )
    await client.close()


@pytest.fixture(autouse=True)
async def e2e_graphiti_test_lifecycle() -> None:
    """Setup and teardown hook for the E2E test."""
    client = GraphitiClient(GraphitiSettings.from_env(group_id=TEST_GROUP_ID))
    await _purge_test_graph(client)
    yield
    await _purge_test_graph(client)


@pytest.mark.asyncio
async def test_ai_writer_agent_loop() -> None:
    """Simulate an end-to-end writing loop with LLM and Neo4j memory."""
    import openai
    import json

    client = GraphitiClient(GraphitiSettings.from_env(group_id=TEST_GROUP_ID))
    await client.connect()

    print("\n\n--- [E2E STEP 1: BACKGROUND INGESTION] ---")
    background_text = "一年前，李默在神秘山谷中获得了一把锈迹斑斑的长生剑。他目前正在前往天机阁的路上。"
    await client.add_episode(
        name="ch00#background",
        episode_body=background_text,
        source_description="background-lore",
        group_id=TEST_GROUP_ID
    )
    print("Background ingested successfully.")

    print("\n--- [E2E STEP 2: CONTEXT RETRIEVAL] ---")
    # Fetch historical relationships to construct context
    context_data = await client.get_story_timeline(focus_entity="李默", group_id=TEST_GROUP_ID)
    
    # Format the context for the LLM
    context_str = json.dumps(context_data, ensure_ascii=False, indent=2)
    print(f"Retrieved Graph Context:\n{context_str}")

    print("\n--- [E2E STEP 3: LLM DRAFT GENERATION] ---")
    openai_client = openai.AsyncOpenAI()
    
    system_prompt = (
        "You are an expert fantasy novel writer. You will write the next paragraph of the story.\n"
        "Use the provided Knowledge Graph context to ensure accuracy. DO NOT invent contradicting facts.\n"
        "Instructions: Li Mo arrives at the gate of Tianjige. He meets a guard. Write a very short paragraph (max 50 words) describing this encounter."
    )
    
    user_prompt = f"### Knowledge Graph Context ###\n{context_str}\n\n### Task ###\nWrite the next paragraph in Chinese."
    
    response = await openai_client.chat.completions.create(
        model=os.environ.get("OPENAI_MODEL", "gpt-4o"),
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ],
        temperature=0.7,
    )
    generated_draft = response.choices[0].message.content.strip()
    print(f"Generated Draft:\n>>> {generated_draft} <<<")
    assert "天机阁" in generated_draft or "李默" in generated_draft

    print("\n--- [E2E STEP 4: CONFLICT VALIDATION] ---")
    # Feed the generated draft to the conflict engine to ensure no contradictions
    conflict_report = await check_submit_conflicts(
        client=client,
        draft_text=generated_draft,
        focus_character="李默",
        group_id=TEST_GROUP_ID
    )
    print(f"Conflict Blocked: {conflict_report.blocked}")
    for c in conflict_report.conflicts:
        print(f"  [{c.severity}] {c.category}: {c.message}")
        
    # The generated draft should be logical and NOT blocked!
    assert conflict_report.blocked is False, "LLM generated a contradicting fact that got blocked!"

    print("\n--- [E2E STEP 5: MEMORY UPDATE (INGESTION)] ---")
    # The draft is approved, ingest it back into the graph
    await client.add_episode(
        name="ch01#p1",
        episode_body=generated_draft,
        source_description="agent-generated",
        group_id=TEST_GROUP_ID
    )
    print("Agent draft ingested successfully.")

    print("\n--- [E2E STEP 6: GRAPH EVOLUTION ASSERTION] ---")
    # Verify the graph evolved to capture the new events.
    # We'll pull the story timeline again, expecting at least 2 episodes now.
    updated_timeline = await client.get_story_timeline(focus_entity="李默", group_id=TEST_GROUP_ID)
    
    print(f"Updated Timeline Episodes Count: {len(updated_timeline)}")
    assert len(updated_timeline) >= 2, "Failed to ingest the new episode!"
    
    # We should have relations connected to the new episode.
    # The new draft likely created a relationship (e.g. interacting with the guard, or LOCATED_AT Tianjige)
    new_episode_relations = []
    for ep in updated_timeline:
        if ep["episode_name"] == "ch01#p1":
            new_episode_relations.extend(ep["relations"])
            
    print(f"Extracted {len(new_episode_relations)} relationships from the AI draft.")
    for rel in new_episode_relations:
        print(f"  - {rel['source_name']} -[{rel['relation_name']}]-> {rel['target_name']} | Fact: {rel['fact']}")
        
    assert len(new_episode_relations) > 0, "The graphiti extraction failed to find any relations in the AI draft!"
    
    await client.close()
    print("\n--- [E2E TEST COMPLETE] ---")
