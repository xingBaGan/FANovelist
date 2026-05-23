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

async def main():
    load_env()
    print("API Key:", os.environ.get("OPENAI_API_KEY"))
    client = AsyncOpenAI()
    try:
        print("Calling responses.parse...")
        response = await client.responses.parse(
            model="gpt-4o-mini",
            input=[{"role": "user", "content": "Return name='test' and value='hello'"}],
            text_format=TestModel,
        )
        print("Success! Parsed:", response)
    except Exception as e:
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(main())
