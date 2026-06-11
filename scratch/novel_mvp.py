#!/usr/bin/env python3
"""
MVP: Interactive Novel Conflict Check & Ingestion Sandbox (Neo4j Connected)
Uses the project's actual GraphitiClient, conflicts checker, and ingest pipelines.
"""

import asyncio
import os
import sys
from pathlib import Path
from typing import Any

# Add project root to python path to allow importing openharness
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# Load my-novel/.env automatically
def load_env() -> None:
    env_path = Path(__file__).resolve().parents[1] / "my-novel" / ".env"
    if env_path.exists():
        print(f"\033[36m已检测到环境配置文件: {env_path}，正在加载环境变量...\033[0m")
        for line in env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, val = line.split("=", 1)
                os.environ[key.strip()] = val.strip()
    else:
        print("\033[33m警告: 未找到 my-novel/.env 文件。将直接从系统当前环境变量中读取。\033[0m")

load_env()

from openharness.graphiti.client import GraphitiClient
from openharness.graphiti.config import GraphitiSettings
from openharness.graphiti.conflicts import check_submit_conflicts
from openharness.graphiti.promotion_runner import run_entity_promotions


def print_header(title: str, color: str = "36") -> None:
    print(f"\n\033[1;{color}m" + "=" * 55)
    print(f" {title} ".center(55, "="))
    print("=" * 55 + "\033[0m")


async def show_character_canon(client: GraphitiClient, focus: str, group_id: str) -> None:
    """Helper to retrieve and display current state of a character from Neo4j."""
    print(f"\n\033[1;33m--- Neo4j 中 [{focus}] 的当前关联设定 ---\033[0m")
    
    # 1. Fetch episodic origin paragraphs
    try:
        origins = await client.trace_entity_origins(focus, group_id=group_id)
        if origins:
            print("\033[1;35m[出处段落]:\033[0m")
            for o in origins:
                print(f"  - ({o['episode_name']}): \"{o['content']}\"")
        else:
            print("  - [出处段落]: 无记录")
    except Exception as e:
        print(f"  - 无法获取出处段落: {e}")

    # 2. Fetch semantic facts (Relationships/Edges)
    try:
        facts = await client.search_facts(focus, group_id=group_id)
        if facts:
            print("\033[1;35m[提取的关系事实 (Facts)]:\033[0m")
            seen = set()
            for f in facts:
                fact_text = getattr(f, "fact", str(f)).strip()
                if fact_text and fact_text not in seen:
                    print(f"  - {fact_text}")
                    seen.add(fact_text)
        else:
            print("  - [关系事实]: 无记录")
    except Exception as e:
        print(f"  - 无法获取关系事实: {e}")
        
    print("-" * 55)


async def main() -> None:
    settings = GraphitiSettings.from_env()
    group_id = settings.group_id or "integration-test"

    print_header("小说 Ingest 与矛盾检测实机 MVP", "35")
    print(f"当前配置：")
    print(f"  - Neo4j URI: {settings.neo4j_uri}")
    print(f"  - Group ID: {group_id}")
    
    # 1. Verify connection
    client = GraphitiClient(settings)
    print("\n\033[36m正在建立 Neo4j 连接并构筑图谱索引...\033[0m")
    try:
        await client.connect()
        print("\033[32m✅ Neo4j 连接成功！\033[0m")
    except Exception as e:
        print_header(" 连接失败 ", "31")
        print(f"\033[1;31m错误详情: {e}\033[0m\n")
        print("请检查：")
        print("  1. Docker 容器是否正常运行 (在 my-novel 下运行 `docker compose up -d`)")
        print("  2. my-novel/.env 文件中的端口/密码是否正确")
        sys.exit(1)

    # 2. Define focus character
    focus_char = input("\n请输入你要关注的主角姓名 (默认: 李默): ").strip()
    if not focus_char:
        focus_char = "李默"

    # Display initial state
    await show_character_canon(client, focus_char, group_id)

    episode_counter = 1

    # 3. Main Loop
    while True:
        try:
            print("\n" + "=" * 55)
            draft = input("\033[1;34m请输入准备合并的新剧情/设定草稿 (输入 'q' 退出):\033[0m\n> ").strip()
            if not draft:
                continue
            if draft.lower() == 'q':
                break

            print("\n\033[36m正在调用 check_submit_conflicts 进行 Neo4j 实机冲突扫描...\033[0m")
            report = await check_submit_conflicts(
                client=client,
                draft_text=draft,
                focus_character=focus_char,
                group_id=group_id
            )

            if report.blocked:
                print_header(" 阻断：检测到设定冲突 (BLOCKED) ", "31")
                for c in report.critical:
                    print(f"\033[1;31m❌ [{c.category.upper()}] {c.message}\033[0m")
                print("\033[33m该草稿包含矛盾，拒绝写入数据库，请先修改。\033[0m")
            else:
                print_header(" 通过：设定一致 (APPROVED) ", "32")
                print("\033[1;32m✅ 未检测到冲突！可以安全写入 Neo4j。\033[0m")
                
                # Ask user if they want to merge
                choice = input("是否将该段 Ingest (合并写入) 到 Neo4j 数据库？(y/n): ").strip().lower()
                if choice == 'y':
                    ep_name = f"mvp#ch01#p{episode_counter}"
                    episode_counter += 1
                    
                    print(f"\033[36m正在写入 Episode '{ep_name}' 并提取事实...\033[0m")
                    ep_uuid, edges = await client.add_episode(
                        name=ep_name,
                        episode_body=draft,
                        source_description="mvp-runner",
                        group_id=group_id
                    )
                    print(f"\033[32m成功写入！Episode UUID: {ep_uuid}, 新增边数量: {len(edges)}\033[0m")
                    
                    # Run promotion
                    print("\033[36m正在评估实体是否需要升级等级标签 (Entity Promotion)...\033[0m")
                    promotions = await run_entity_promotions(client, group_id)
                    if promotions:
                        for p in promotions:
                            print(f"  - 实体 [{p.name}] 标签由 {p.from_label} 升级为 {p.to_label} ({p.reason})")
                    else:
                        print("  - 无实体达到升级阈值。")
                    
                    # Show latest state
                    await show_character_canon(client, focus_char, group_id)
                else:
                    print("\033[33m已取消合并写入。\033[0m")

        except (KeyboardInterrupt, EOFError):
            break

    await client.close()
    print("\n沙盒会话结束。")


if __name__ == "__main__":
    asyncio.run(main())
