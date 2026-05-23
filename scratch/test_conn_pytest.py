import os
import pytest
from pathlib import Path
from openai import AsyncOpenAI

def load_env():
    env_path = Path("/Users/jzj/ai_writing/OpenHarness/my-novel/.env")
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, val = line.split("=", 1)
                os.environ[key.strip()] = val.strip()

@pytest.mark.asyncio
async def test_openai_conn():
    load_env()
    print("API Key:", os.environ.get("OPENAI_API_KEY"))
    client = AsyncOpenAI()
    res = await client.embeddings.create(
        input=["test"],
        model="text-embedding-3-small"
    )
    print("Success!", len(res.data[0].embedding))
