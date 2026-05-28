"""CLI commands for novel Graphiti canon ingest."""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from typing import Any

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
    approved: bool = typer.Option(False, "--approved", help="Approve ingestion of the staged summaries"),
    direct: bool = typer.Option(False, "--direct", help="Bypass the summary buffer and ingest directly"),
) -> None:
    """Run ingest_submitted_document after human approve."""
    from openharness.graphiti.client import GraphitiClient
    from openharness.graphiti.config import GraphitiSettings
    from openharness.graphiti.ingest import ingest_submitted_document
    from openharness.graphiti.paragraphs import split_paragraphs
    from openharness.graphiti.summary_stage import parse_summary_file

    gid = group_id or GraphitiSettings.from_env().group_id

    summaries_map = None
    if not direct:
        summary_path = source.resolve().with_suffix(".summary.md")
        if not summary_path.exists():
            typer.echo(
                f"Error: Summary buffer file not found at {summary_path}.\n"
                f"Please run the stage-summary command first:\n"
                f"  uv run openharness graphiti stage-summary --studio-root {studio_root} --source {source}",
                err=True,
            )
            sys.exit(1)

        try:
            summary_content = summary_path.read_text(encoding="utf-8")
            parsed_summaries = parse_summary_file(summary_content)
        except Exception as e:
            typer.echo(f"Error: Failed to parse summary buffer file: {e}", err=True)
            sys.exit(1)

        try:
            source_content = source.read_text(encoding="utf-8")
            source_blocks = split_paragraphs(source_content)
        except Exception as e:
            typer.echo(f"Error: Failed to read/parse source file: {e}", err=True)
            sys.exit(1)

        mismatched = []
        for block in source_blocks:
            existing = parsed_summaries.get(block.paragraph_uid)
            if not existing or existing[0] != block.content_hash:
                mismatched.append(block.paragraph_uid)

        if mismatched:
            typer.echo(
                f"Error: Summary buffer is out of date. The following paragraph UIDs are missing or have mismatched hashes: {mismatched}.\n"
                f"Please run stage-summary first to update the summary buffer:\n"
                f"  uv run openharness graphiti stage-summary --studio-root {studio_root} --source {source}",
                err=True,
            )
            sys.exit(1)

        if not approved:
            typer.echo(
                f"Summary buffer file found and validated at {summary_path}.\n"
                f"Please review it, make sure the summaries are correct, and run the ingest command with the --approved flag:\n"
                f"  uv run openharness graphiti ingest --studio-root {studio_root} --source {source} --gate {gate} --kind {kind} --approved",
                err=True,
            )
            sys.exit(1)

        summaries_map = {uid: text for uid, (_, text) in parsed_summaries.items()}

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
            summaries_map=summaries_map,
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


@graphiti_app.command("stage-summary")
def graphiti_stage_summary(
    studio_root: Path = typer.Option(..., "--studio-root", help="Path to studio/ directory"),
    source: Path = typer.Option(..., "--source", help="Chapter markdown file"),
) -> None:
    """Generate or update the intermediate summary buffer file."""
    from openharness.graphiti.summary_stage import stage_chapter_summaries

    async def _run() -> dict[str, object]:
        summary_path, stats = await stage_chapter_summaries(
            source_path=source.resolve(),
            studio_root=studio_root.resolve(),
        )
        return {
            "summary_path": str(summary_path),
            "stats": stats,
        }

    try:
        res = asyncio.run(_run())
        typer.echo(json.dumps(res, ensure_ascii=False, indent=2))
    except Exception as e:
        typer.echo(f"Error: {e}", err=True)
        sys.exit(1)


@graphiti_app.command("check-conflicts")
def graphiti_check_conflicts(
    source: Path = typer.Option(..., "--source", help="Draft or final markdown to check"),
    focus: str | None = typer.Option(None, "--focus", help="Focus character, e.g. 李默"),
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


@graphiti_app.command("trace-origins")
def graphiti_trace_origins(
    entity: str = typer.Option(..., "--entity", help="Entity name to trace, e.g. 李默"),
    group_id: str | None = typer.Option(None, "--group-id"),
) -> None:
    """Find all episodic source paragraphs mentioning the given entity."""
    from openharness.graphiti.client import GraphitiClient
    from openharness.graphiti.config import GraphitiSettings

    gid = group_id or GraphitiSettings.from_env().group_id

    async def _run() -> list[dict[str, Any]]:
        client = GraphitiClient(GraphitiSettings.from_env(group_id=gid))
        res = await client.trace_entity_origins(entity, group_id=gid)
        await client.close()
        return res

    typer.echo(json.dumps(asyncio.run(_run()), ensure_ascii=False, indent=2))


@graphiti_app.command("story-timeline")
def graphiti_story_timeline(
    focus: str | None = typer.Option(None, "--focus", help="Focus character or entity name"),
    group_id: str | None = typer.Option(None, "--group-id"),
) -> None:
    """Get a chronological story timeline, optionally filtered by a focus entity."""
    from openharness.graphiti.client import GraphitiClient
    from openharness.graphiti.config import GraphitiSettings

    gid = group_id or GraphitiSettings.from_env().group_id

    async def _run() -> list[dict[str, Any]]:
        client = GraphitiClient(GraphitiSettings.from_env(group_id=gid))
        res = await client.get_story_timeline(focus_entity=focus, group_id=gid)
        await client.close()
        return res

    typer.echo(json.dumps(asyncio.run(_run()), ensure_ascii=False, indent=2))


@graphiti_app.command("factions-outline")
def graphiti_factions_outline(
    group_id: str | None = typer.Option(None, "--group-id"),
) -> None:
    """Get an outline of factions/communities and their member entities."""
    from openharness.graphiti.client import GraphitiClient
    from openharness.graphiti.config import GraphitiSettings

    gid = group_id or GraphitiSettings.from_env().group_id

    async def _run() -> list[dict[str, Any]]:
        client = GraphitiClient(GraphitiSettings.from_env(group_id=gid))
        res = await client.get_factions_outline(group_id=gid)
        await client.close()
        return res

    typer.echo(json.dumps(asyncio.run(_run()), ensure_ascii=False, indent=2))


@graphiti_app.command("historical-relationships")
def graphiti_historical_relationships(
    time: str = typer.Option(..., "--time", help="Target ISO-8601 time string, e.g. '2020-12-01T00:00:00Z'"),
    focus: str | None = typer.Option(None, "--focus", help="Focus character or entity name"),
    group_id: str | None = typer.Option(None, "--group-id"),
) -> None:
    """Get active semantic relationships at a specific point in time."""
    from openharness.graphiti.client import GraphitiClient
    from openharness.graphiti.config import GraphitiSettings

    gid = group_id or GraphitiSettings.from_env().group_id

    async def _run() -> list[dict[str, Any]]:
        client = GraphitiClient(GraphitiSettings.from_env(group_id=gid))
        res = await client.get_historical_relationships(time, focus_entity=focus, group_id=gid)
        await client.close()
        return res

    typer.echo(json.dumps(asyncio.run(_run()), ensure_ascii=False, indent=2))

