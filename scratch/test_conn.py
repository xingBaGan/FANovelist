import asyncio
import os
from pathlib import Path
from openai import AsyncOpenAI
from pydantic import BaseModel

class TestModel(BaseModel):
    summary: str

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
    print("API Key:", os.environ.get("OPENAI_API_KEY"))
    client = AsyncOpenAI()
    
    # We try client.responses.parse
    request_kwargs = {
        'model': 'gpt-4o-mini',
        'input': [{'role': 'user', 'content': 'Hello, output a summary in JSON.'}],
        'max_output_tokens': 1000,
        'text_format': TestModel,
        'temperature': 0.7,
    }
    
    try:
        print("Calling client.responses.parse...")
        response = await client.responses.parse(**request_kwargs)
        print("Success! Response:", response)
    except Exception as e:
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(main())
