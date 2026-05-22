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

async def main():
    client = GraphitiClient(GraphitiSettings.from_env(group_id="test-inspect"))
    await client.connect()
    res = await client.search_facts("李默", group_id="test-inspect")
    print("TYPE OF RES:", type(res))
    if res:
        print("TYPE OF ITEM:", type(res[0]))
        print("DIR OF ITEM:", dir(res[0]))
        try:
            print("ITEM DICT:", res[0].__dict__)
        except Exception as e:
            print("COULD NOT GET __dict__:", e)
        print("ITEM STRING:", str(res[0]))
    await client.close()

if __name__ == "__main__":
    asyncio.run(main())
