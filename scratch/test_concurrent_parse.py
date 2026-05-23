import asyncio
import os
from pathlib import Path
from openai import AsyncOpenAI
from pydantic import BaseModel

def load_env():
    env_path = Path("/Users/jzj/ai_writing/OpenHarness/my-novel/.env")
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, val = line.split("=", 1)
                os.environ[key.strip()] = val.strip()

class TestModel(BaseModel):
    name: str
    value: str

async def make_call(client, i):
    try:
        print(f"Starting call {i}...")
        response = await client.responses.parse(
            model="gpt-4o-mini",
            input=[{"role": "user", "content": f"Return name='test{i}' and value='hello{i}'"}],
            text_format=TestModel,
        )
        print(f"Call {i} success!")
        return response
    except Exception as e:
        print(f"Call {i} failed: {e}")
        import traceback
        traceback.print_exc()
        raise

async def main():
    load_env()
    client = AsyncOpenAI()
    tasks = [make_call(client, i) for i in range(10)]
    await asyncio.gather(*tasks)

if __name__ == "__main__":
    asyncio.run(main())
