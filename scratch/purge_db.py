#!/usr/bin/env python3
"""
Utility script to purge Neo4j and SQLite databases for a clean slate.
"""

import asyncio
import os
import sys
from pathlib import Path

# Add project root to python path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

def load_env() -> None:
    env_path = Path(__file__).resolve().parents[1] / "my-novel" / ".env"
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, val = line.split("=", 1)
                os.environ[key.strip()] = val.strip()

load_env()

from openharness.graphiti.client import GraphitiClient
from openharness.graphiti.config import GraphitiSettings


async def purge() -> None:
    settings = GraphitiSettings.from_env()
    client = GraphitiClient(settings)
    
    print("\033[36m1. 正在清理 Neo4j 图数据库...\033[0m")
    try:
        await client.connect()
        # Delete all nodes and relationships completely
        res = await client._graphiti.driver.execute_query("MATCH (n) DETACH DELETE n")
        print("\033[32m✅ Neo4j 清理成功！已删除所有节点和关系。\033[0m")
        await client.close()
    except Exception as e:
        print(f"\033[31m❌ Neo4j 清理失败: {e}\033[0m")

    print("\n\033[36m2. 正在清理本地 SQLite 索引库 (ingest.db)...\033[0m")
    # Search for ingest.db in my-novel/studio/
    db_paths = [
        Path(__file__).resolve().parents[1] / "my-novel" / "studio" / ".graphiti" / "ingest.db",
        Path(__file__).resolve().parents[1] / "studio" / ".graphiti" / "ingest.db"
    ]
    
    deleted_any = False
    for db_path in db_paths:
        if db_path.exists():
            try:
                db_path.unlink()
                print(f"\033[32m✅ 已成功删除本地索引文件: {db_path}\033[0m")
                deleted_any = True
            except Exception as e:
                print(f"\033[31m❌ 无法删除本地索引文件 {db_path}: {e}\033[0m")
                
    if not deleted_any:
        print("未检测到本地 SQLite 索引文件，无需清理。")


if __name__ == "__main__":
    asyncio.run(purge())
