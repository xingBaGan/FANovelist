import asyncio
import os
from pathlib import Path
from openharness.graphiti.client import GraphitiClient
from openharness.graphiti.config import GraphitiSettings

def load_env():
    env_path = Path("/Users/jzj/ai_writing/OpenHarness/my-novel/.env")
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, val = line.split("=", 1)
                os.environ[key.strip()] = val.strip()

async def main():
    load_env()
    print("OPENAI_API_KEY:", os.environ.get("OPENAI_API_KEY"))
    print("NEO4J_URI:", os.environ.get("NEO4J_URI"))
    
    # Check proxies
    import urllib.request
    print("Urllib proxies:", urllib.request.getproxies())
    
    TEST_GROUP_ID = "test-add-episode-scratch"
    client = GraphitiClient(GraphitiSettings.from_env(group_id=TEST_GROUP_ID))
    await client.connect()
    
    text = "李默拔出长生剑，施展雷影步，一剑斩杀了赤炼毒蛇。"
    hints = (
        "- 长生剑: narrative_element (Weapon/Item, NarrativeElement)\n"
        "- 雷影步: narrative_element (Skill, NarrativeElement)\n"
        "- 赤炼毒蛇: MinorCharacter (Monster/Creature, MinorCharacter)"
    )
    body = f"{text}\n\n[canon-hints]\n{hints}"
    
    try:
        print("Running add_episode...")
        res = await client.add_episode(name="combat_01", episode_body=body, source_description="test", group_id=TEST_GROUP_ID)
        print("add_episode success! Result:", res)
    except Exception as e:
        import traceback
        traceback.print_exc()
        if hasattr(e, "__cause__") and e.__cause__:
            print("Underlying cause:")
            traceback.print_exception(type(e.__cause__), e.__cause__, e.__cause__.__traceback__)
    finally:
        await client.close()

if __name__ == "__main__":
    asyncio.run(main())
