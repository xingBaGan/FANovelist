"""CLI commands for novel Graphiti canon ingest."""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

import typer

graphiti_app = typer.Typer(name="graphiti", help="Novel canon graph (Graphiti + Neo4j)")


@graphiti_app.command("ingest")
def graphiti_ingest(
    studio_root: Path = typer.Option(..., "--studio-root", help="Path to studio/ directory"),
    source: Path = typer.Option(..., "--source", help="Submitted markdown file"),
    gate: str = typer.Option("approve-chapter", "--gate", help="Submit gate name"),
    kind: str = typer.Option("chapter", "--kind", help="source_kind for ingest index"),
    group_id: str | None = typer.Option(None, "--group-id", help="Neo4j partition id"),
    scope: str = typer.Option(
        "changed_paragraphs",
        "--scope",
        help="changed_paragraphs | chapter_all",
    ),
    write_uids: bool = typer.Option(True, "--write-uids/--no-write-uids"),
) -> None:
    """Run ingest_submitted_document after human approve."""
    from openharness.graphiti.client import GraphitiClient
    from openharness.graphiti.config import GraphitiSettings
    from openharness.graphiti.ingest import ingest_submitted_document

    gid = group_id or GraphitiSettings.from_env().group_id

    async def _run() -> dict[str, object]:
        client = GraphitiClient(GraphitiSettings.from_env(group_id=gid))
        report = await ingest_submitted_document(
            source_path=source.resolve(),
            source_kind=kind,
            group_id=gid,
            submit_gate=gate,
            submit_scope=scope,
            studio_root=studio_root.resolve(),
            graphiti=client,
            write_uids_to_markdown=write_uids,
        )
        await client.close()
        return {
            "paragraphs_ingested": report.paragraphs_ingested,
            "paragraphs_skipped": report.paragraphs_skipped,
            "paragraphs_superseded": report.paragraphs_superseded,
            "entities_promoted": report.entities_promoted,
            "promotion_notes": report.promotion_notes,
            "errors": report.errors,
            "submit_run_id": report.submit_run_id,
        }

    typer.echo(json.dumps(asyncio.run(_run()), ensure_ascii=False, indent=2))


@graphiti_app.command("check-conflicts")
def graphiti_check_conflicts(
    source: Path = typer.Option(..., "--source", help="Draft or final markdown to check"),
    focus: str | typer.Option(None, "--focus", help="Focus character, e.g. 李默"),
    group_id: str | None = typer.Option(None, "--group-id"),
) -> None:
    """Pre-approve conflict gate. Exit code 1 if critical conflicts found."""
    from openharness.graphiti.client import GraphitiClient
    from openharness.graphiti.config import GraphitiSettings
    from openharness.graphiti.conflicts import check_submit_conflicts

    gid = group_id or GraphitiSettings.from_env().group_id
    text = source.read_text(encoding="utf-8")

    async def _run() -> dict[str, object]:
        client = GraphitiClient(GraphitiSettings.from_env(group_id=gid))
        report = await check_submit_conflicts(
            client, text, focus_character=focus, group_id=gid
        )
        await client.close()
        return {
            "blocked": report.blocked,
            "critical": [
                {"category": c.category, "message": c.message} for c in report.critical
            ],
            "warnings": [
                {"category": c.category, "message": c.message} for c in report.warnings
            ],
        }

    payload = asyncio.run(_run())
    typer.echo(json.dumps(payload, ensure_ascii=False, indent=2))
    if payload.get("blocked"):
        raise typer.Exit(code=1)
