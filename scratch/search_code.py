import os
from pathlib import Path

site_packages = Path("/Users/jzj/ai_writing/OpenHarness/.venv/lib/python3.12/site-packages")
graphiti_core = site_packages / "graphiti_core"

print("Searching for 'invalid_at' in graphiti_core:")
for path in graphiti_core.glob("**/*.py"):
    content = path.read_text(encoding="utf-8")
    if "invalid_at" in content:
        print(f"Found in {path.relative_to(graphiti_core)}")
        for i, line in enumerate(content.splitlines(), 1):
            if "invalid_at" in line:
                print(f"  Line {i}: {line.strip()}")
