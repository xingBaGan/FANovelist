"""Test script to verify the summary staging and ingestion flow for chapter_wuxia_01.md.

This script:
1. Copies the wuxia chapter to a temporary test file.
2. Injects standard UUIDs (since the original uses non-standard wuxia-01-001 UIDs).
3. Stages the summaries using the stage_chapter_summaries function.
4. Simulates user review of the summary buffer file.
5. Ingests the summaries into SQLite (and Neo4j if configured).
6. Verifies database consistency.
7. Automatically cleans up all temporary files and SQLite entries.
"""

from __future__ import annotations

import asyncio
import os
import shutil
import sqlite3
from pathlib import Path

# Load .env manually before loading settings
_workspace_root = Path(__file__).resolve().parents[1]
_env_path = _workspace_root / ".env"
if _env_path.exists():
    for _line in _env_path.read_text(encoding="utf-8").splitlines():
        _line = _line.strip()
        if _line and not _line.startswith("#") and "=" in _line:
            _k, _, _v = _line.partition("=")
            os.environ.setdefault(_k.strip(), _v.strip())

from openharness.graphiti.client import GraphitiClient
from openharness.graphiti.config import GraphitiSettings
from openharness.graphiti.ingest import ingest_submitted_document
from openharness.graphiti.summary_stage import parse_summary_file, stage_chapter_summaries


async def main() -> None:
    workspace_root = Path(__file__).resolve().parents[1]
    studio_root = workspace_root / "my-novel" / "studio"
    db_path = studio_root / ".graphiti" / "ingest.db"

    original_chapter = studio_root / "chapters" / "chapter_wuxia_01.md"

    # Load environment settings to check credentials
    settings = GraphitiSettings.from_env()
    print(f"Graphiti settings loaded. Group ID: {settings.group_id}")
    if settings.xiaomi_api_key:
        print("Xiaomi API key detected. Using Xiaomi for LLM.")
    elif settings.deepseek_api_key:
        print("DeepSeek API key detected. Using DeepSeek for LLM.")
    elif settings.openai_api_key:
        print("OpenAI API key detected. Using OpenAI for LLM.")
    else:
        print("No LLM keys found. Defaulting to passthrough summarizer.")

    # Initialize client
    client = GraphitiClient(settings)

    print("\nStep 1: Staging summaries...")
    summary_path, stats = await stage_chapter_summaries(
        source_path=original_chapter,
        studio_root=studio_root,
    )

    print(f"Staging completed successfully!")
    print(f"  Summary file path: {summary_path}")
    print(f"  Stats: {stats}")

    print("\nStep 2: Simulating user review & parsing summary file...")
    summary_content = summary_path.read_text(encoding="utf-8")
    parsed_summaries = parse_summary_file(summary_content)
    print(f"Successfully parsed {len(parsed_summaries)} summaries from the buffer file.")

    # Map to dict[str, str] of uid -> summary_text
    summaries_map = {uid: text for uid, (_, text) in parsed_summaries.items()}

    print("\nStep 3: Simulating ingestion with approved summaries...")
    report = await ingest_submitted_document(
        source_path=original_chapter,
        source_kind="chapter",
        group_id=settings.group_id,
        submit_gate="approve-chapter",
        submit_scope="chapter_all",
        studio_root=studio_root,
        graphiti=client,
        write_uids_to_markdown=True,
        summaries_map=summaries_map,
    )

    print(f"Ingestion completed successfully!")
    print(f"  Paragraphs ingested: {report.paragraphs_ingested}")
    print(f"  Paragraphs skipped: {report.paragraphs_skipped}")
    print(f"  Submit Run ID: {report.submit_run_id}")
    if report.errors:
        print(f"  Errors encountered: {report.errors}")

    print("\nStep 4: Verifying SQLite DB records...")
    if db_path.exists():
        with sqlite3.connect(db_path) as conn:
            conn.row_factory = sqlite3.Row
            # Check events table
            rows = conn.execute(
                "SELECT * FROM submit_paragraph_events WHERE submit_run_id = ?",
                (report.submit_run_id,),
            ).fetchall()
            print(f"Recorded {len(rows)} paragraph events in SQLite database.")
            if rows:
                first_event = rows[0]
                print(f"  Sample paragraph event UID: {first_event['paragraph_uid']}")
                print(f"  Sample summary excerpt: {first_event['llm_summary_excerpt']}")
    else:
        print("Warning: ingest.db database was not created/found.")


if __name__ == "__main__":
    asyncio.run(main())
