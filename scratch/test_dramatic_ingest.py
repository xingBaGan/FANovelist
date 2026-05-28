"""Manual end-to-end validation script for dramatic narrative ingestion.

This script:
1. Sets up a temporary sample chapter markdown file with high-dramatic tension.
2. Ingests it using ingest_submitted_document (automatically parsing title/indexing and scene value shifts).
3. Queries and prints SQLite records (chapters, paragraphs, scene_value_shifts, paragraph_graph_links).
4. Verifies database consistency and logs the results.
"""

from __future__ import annotations

import asyncio
import os
import sqlite3
from pathlib import Path

# Load .env manually
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
from openharness.graphiti.ingest_store import IngestStateStore


async def main() -> None:
    workspace_root = Path(__file__).resolve().parents[1]
    studio_root = workspace_root / "my-novel" / "studio"
    db_path = studio_root / ".graphiti" / "ingest.db"

    # Ensure clean state
    if db_path.exists():
        try:
            db_path.unlink()
            print("Cleaned up existing local SQLite database.")
        except Exception as exc:
            print(f"Could not delete database: {exc}")

    # Create dummy directory structure
    chapters_dir = studio_root / "chapters"
    chapters_dir.mkdir(parents=True, exist_ok=True)
    temp_chapter = chapters_dir / "chapter_dramatic_01.md"

    # Write a highly dramatic text
    # It contains clear character emotional shifts, desires, fears, a Chekhov's gun, and a belief
    sample_text = """# 第一章 绝地反击

<!-- paragraph_uid: 00000000-0000-0000-0000-000000000001 -->
李默此时满手是汗，他的气海接近破碎，身体处于极度虚弱的状态。他的欲望非常强烈：他必须要在这场对决中活下去，以便揭穿天机阁的叛徒。但他内心深处最深的恐惧是如果他失败了，他的亲人将会被天机阁彻底抹杀。他极力掩饰着自己的慌张。

<!-- paragraph_uid: 00000000-0000-0000-0000-000000000002 -->
王虎正用冰冷的目光看着李默。李默从怀中缓缓掏出了那封伪造的密信。这封信就是关键的契诃夫之枪，它是天机阁勾结魔宗的铁证。李默出示了伪造的密信，直接引爆了王虎的慌乱。王虎坚信李默已经掌握了一切证据，他原本嚣张的气焰瞬间萎缩。
"""
    temp_chapter.write_text(sample_text, encoding="utf-8")
    print(f"Created temporary chapter markdown file at: {temp_chapter}")

    # Load settings
    settings = GraphitiSettings.from_env()
    print(f"Loaded Group ID: {settings.group_id}")

    # Initialize client
    client = GraphitiClient(settings)
    store = IngestStateStore(db_path)

    print("\nRunning ingestion pipeline...")
    report = await ingest_submitted_document(
        source_path=temp_chapter,
        source_kind="chapter",
        group_id=settings.group_id,
        submit_gate="approve-chapter",
        submit_scope="chapter_all",
        studio_root=studio_root,
        graphiti=client,
        store=store,
        write_uids_to_markdown=False,
    )

    print(f"\nIngestion Pipeline Report:")
    print(f"  Paragraphs Ingested: {report.paragraphs_ingested}")
    print(f"  Paragraphs Skipped: {report.paragraphs_skipped}")
    print(f"  Submit Run ID: {report.submit_run_id}")
    if report.errors:
        print(f"  Errors encountered: {report.errors}")

    print("\n=== VERIFYING SQLITE DATABASE RECORDS ===")
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row

        # 1. Verify Chapters table
        ch_rows = conn.execute("SELECT * FROM chapters").fetchall()
        print(f"\n[Chapters Table] Total: {len(ch_rows)}")
        for r in ch_rows:
            print(f"  Path: {r['chapter_path']}, Title: '{r['title']}', Index: {r['chapter_index']}, Status: {r['approval_status']}")

        # 2. Verify Paragraphs table (including chapter_path column)
        p_rows = conn.execute("SELECT * FROM paragraphs").fetchall()
        print(f"\n[Paragraphs Table] Total: {len(p_rows)}")
        for r in p_rows:
            print(f"  UID: {r['paragraph_uid']}, Section: {r['section_heading']}, Hash: {r['content_hash'][:8]}, Chapter Foreign Key: {r['chapter_path']}")

        # 3. Verify Paragraph Graph Links mapping
        link_rows = conn.execute("SELECT * FROM paragraph_graph_links").fetchall()
        print(f"\n[Paragraph Graph Links Table] Total: {len(link_rows)}")
        for r in link_rows:
            print(f"  Paragraph UID: {r['paragraph_uid']} -> Episode UUID: {r['episode_uuid']}")

        # 4. Verify Scene Value Shifts
        shift_rows = conn.execute("SELECT * FROM scene_value_shifts").fetchall()
        print(f"\n[Scene Value Shifts Table] Total: {len(shift_rows)}")
        for r in shift_rows:
            print(f"  Paragraph UID: {r['paragraph_uid']}")
            print(f"    Conflict Focus: {r['conflict_focus']}")
            print(f"    Value Dimension: {r['value_dimension']}")
            print(f"    Initial Value: {r['initial_value']} -> Target Value: {r['target_value']}")

    # Clean up temp file
    if temp_chapter.exists():
        temp_chapter.unlink()
        print("\nCleaned up temporary chapter markdown file.")


if __name__ == "__main__":
    asyncio.run(main())
