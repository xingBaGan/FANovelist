"""Pre-processing pipeline to classify and aggregate paragraph summaries.

This script uses the newly extracted framework functions from openharness.graphiti.
"""

from __future__ import annotations

import asyncio
import os
from pathlib import Path

# Load env
_workspace_root = Path(__file__).resolve().parents[1]
_env_path = _workspace_root / ".env"
if _env_path.exists():
    for _line in _env_path.read_text(encoding="utf-8").splitlines():
        _line = _line.strip()
        if _line and not _line.startswith("#") and "=" in _line:
            _k, _, _v = _line.partition("=")
            os.environ.setdefault(_k.strip(), _v.strip())

from openharness.graphiti import (
    IngestStateStore,
    load_or_generate_aggregation_plan,
    ingest_aggregation_plan,
)
from openharness.graphiti.client import GraphitiClient
from openharness.graphiti.config import GraphitiSettings
from openharness.graphiti.summary_stage import parse_summary_file


async def main() -> None:
    workspace_root = Path(__file__).resolve().parents[1]
    studio_root = workspace_root / "my-novel" / "studio"
    db_path = studio_root / ".graphiti" / "ingest.db"
    summary_path = studio_root / "chapters" / "chapter_wuxia_01.summary.md"

    if not summary_path.exists():
        print(f"Error: Summary file {summary_path} not found.")
        return

    print("Step 1: Parsing summary buffer...")
    summary_content = summary_path.read_text(encoding="utf-8")
    parsed_summaries = parse_summary_file(summary_content)
    print(f"Loaded {len(parsed_summaries)} paragraph summaries.")

    # Convert to list of dicts for LLM processing
    paragraph_list = []
    for uid, (content_hash, text) in parsed_summaries.items():
        paragraph_list.append({
            "uid": uid,
            "hash": content_hash,
            "summary": text
        })

    # Prepare LLM client credentials
    api_key = (
        os.environ.get("XIAOMI_API_KEY") or
        os.environ.get("DEEPSEEK_API_KEY") or
        os.environ.get("OPENAI_API_KEY")
    )
    if not api_key:
        print("Error: No LLM API keys found in environment.")
        return

    base_url = None
    model = "mimo-v2-pro"
    if os.environ.get("XIAOMI_API_KEY"):
        base_url = "https://api.xiaomimimo.com/v1"
        model = os.environ.get("XIAOMI_MODEL", "mimo-v2-pro")
    elif os.environ.get("DEEPSEEK_API_KEY"):
        base_url = "https://api.deepseek.com"
        model = os.environ.get("DEEPSEEK_MODEL", "deepseek-chat")
    elif os.environ.get("OPENAI_API_KEY"):
        model = os.environ.get("OPENAI_MODEL", "gpt-4o")

    # Step 2: Load or Generate Plan using the framework function
    plan_output_path = studio_root / "chapters" / "chapter_wuxia_01.aggregation_plan.json"
    plan_data = await load_or_generate_aggregation_plan(
        plan_path=plan_output_path,
        paragraph_list=paragraph_list,
        api_key=api_key,
        base_url=base_url,
        model=model,
    )

    print(f"Classification Results:")
    print(f"  Static/Lore paragraphs: {len(plan_data.get('static_lore', []))}")
    print(f"  Aggregated dynamic scenes: {len(plan_data.get('dynamic_scenes', []))}")
    for idx, scene in enumerate(plan_data.get('dynamic_scenes', [])):
        print(f"    Scene {idx+1}: {scene['scene_title']} ({len(scene['paragraph_uids'])} paragraphs)")

    # Step 3: Execute plan ingestion using the framework function
    print("\nStep 3: Executing plan ingestion into SQLite and Neo4j...")
    settings = GraphitiSettings.from_env()
    client = GraphitiClient(settings)
    store = IngestStateStore(db_path)

    lore_file = studio_root / "chapters" / "chapter_wuxia_01.lore.json"

    await ingest_aggregation_plan(
        plan_data=plan_data,
        client=client,
        store=store,
        summary_path=summary_path,
        paragraph_list=paragraph_list,
        source_path_str="studio/chapters/chapter_wuxia_01.md",
        chapter_index_prefix="chapter_wuxia_01",
        submit_gate="approve-chapter",
        lore_output_path=lore_file,
    )


if __name__ == "__main__":
    asyncio.run(main())
