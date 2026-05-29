"""Submit-triggered paragraph ingest pipeline."""

from __future__ import annotations

import asyncio

from dataclasses import dataclass, field
from pathlib import Path

from openharness.graphiti.client import GraphitiClient
from openharness.graphiti.config import GraphitiSettings
from openharness.graphiti.ingest_store import IngestStateStore
from openharness.graphiti.paragraphs import ParagraphBlock, split_paragraphs
from openharness.graphiti.reconcile import reconcile_paragraphs
from openharness.graphiti.observability import log_llm_call
from openharness.graphiti.summarize import Summarizer, passthrough_summarizer


@dataclass
class IngestReport:
    paragraphs_superseded: int = 0
    paragraphs_ingested: int = 0
    paragraphs_skipped: int = 0
    submit_run_id: int = 0
    entities_promoted: int = 0
    promotion_notes: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


async def ingest_submitted_document(
    *,
    source_path: Path,
    source_kind: str,
    group_id: str,
    submit_gate: str,
    submit_scope: str = "changed_paragraphs",
    studio_root: Path,
    graphiti: GraphitiClient | None = None,
    store: IngestStateStore | None = None,
    summarizer: Summarizer | None = None,
    write_uids_to_markdown: bool = True,
    summaries_map: dict[str, str] | None = None,
) -> IngestReport:
    """Ingest submitted markdown after reconcile and optional supersede."""
    report = IngestReport()
    db_path = studio_root / ".graphiti" / "ingest.db"
    state = store or IngestStateStore(db_path)
    client = graphiti or GraphitiClient(GraphitiSettings.from_env(group_id=group_id))

    if summarizer is not None:
        summarize = summarizer
    elif client.available and getattr(client._settings, "openai_api_key", None):
        from openharness.graphiti.summarize import openai_summarizer
        summarize = openai_summarizer
    else:
        summarize = passthrough_summarizer

    rel_path = str(source_path)
    markdown = source_path.read_text(encoding="utf-8")
    new_blocks = split_paragraphs(markdown)
    old_blocks = state.list_paragraphs(rel_path)
    recon = reconcile_paragraphs(old_blocks, new_blocks)

    if client.available:
        from openharness.graphiti.reconcile import ReconcileResult

        skipped_list = list(recon.skipped)
        added_list = list(recon.added)
        edited_list = list(recon.edited)
        old_map = {p.paragraph_uid: p for p in old_blocks}
        new_skipped = []
        for block in skipped_list:
            old_stored = old_map.get(block.paragraph_uid)
            if old_stored and not old_stored.episode_uuids:
                edited_list.append((block, old_stored))
            else:
                new_skipped.append(block)
        recon = ReconcileResult(
            edited=tuple(edited_list),
            added=recon.added,
            deleted=recon.deleted,
            skipped=tuple(new_skipped),
            ambiguous=recon.ambiguous,
        )

    run_id = state.start_submit_run(
        submit_gate=submit_gate,
        source_path=rel_path,
        source_kind=source_kind,
        submit_scope=submit_scope,
    )
    report.submit_run_id = run_id
    state.upsert_document(rel_path, source_kind, group_id)

    # Extract chapter index and title for SQLite chapter tracking
    import re
    match = re.search(r"(?:ch|chapter|chap)_*(?:\w*_)*(\d+)", source_path.name, re.IGNORECASE)
    if match:
        chapter_index = int(match.group(1))
    else:
        digits = re.findall(r"\d+", source_path.name)
        chapter_index = int(digits[-1]) if digits else 0
    title = None
    for line in markdown.splitlines():
        if line.startswith("# "):
            title = line[2:].strip()
            break
    if not title:
        title = source_path.stem
    state.upsert_chapter(
        chapter_path=rel_path,
        title=title,
        chapter_index=chapter_index,
        approval_status="submitted",
    )

    if submit_scope == "chapter_all":
        to_process = list(new_blocks)
    else:
        to_process = [
            b
            for b in new_blocks
            if any(b.paragraph_uid == n.paragraph_uid for n in recon.added)
            or any(b.paragraph_uid == e[0].paragraph_uid for e in recon.edited)
        ]

    # Concurrently process deletes, edits, and additions
    sem = asyncio.Semaphore(5)

    # Process all deletions concurrently first
    deleted_tasks = [
        _supersede_paragraph(state, client, old.paragraph_uid, run_id)
        for old in recon.deleted
    ]
    if deleted_tasks:
        await asyncio.gather(*deleted_tasks)
    report.paragraphs_superseded += len(recon.deleted)

    edited_to_process = [
        (new, old) for new, old in recon.edited
        if new.paragraph_uid in {p.paragraph_uid for p in to_process}
    ]
    added_to_process = [
        new for new in recon.added
        if new.paragraph_uid in {p.paragraph_uid for p in to_process}
    ]
    total_to_process = len(edited_to_process) + len(added_to_process)

    async def process_edited(new, old, idx):
        async with sem:
            await _supersede_paragraph(state, client, old.paragraph_uid, run_id)
            report.paragraphs_superseded += 1
            print(f"[Ingest] Ingesting edited paragraph {idx}/{total_to_process} ({new.paragraph_uid})...", flush=True)
            if await _ingest_one(
                state, client, summarize, new, rel_path, source_kind, submit_gate, run_id, "edited", summaries_map
            ):
                report.paragraphs_ingested += 1

    async def process_added(new, idx):
        async with sem:
            print(f"[Ingest] Ingesting added paragraph {idx}/{total_to_process} ({new.paragraph_uid})...", flush=True)
            if await _ingest_one(
                state, client, summarize, new, rel_path, source_kind, submit_gate, run_id, "added", summaries_map
            ):
                report.paragraphs_ingested += 1

    tasks = []
    idx = 1
    for new, old in edited_to_process:
        tasks.append(process_edited(new, old, idx))
        idx += 1
    for new in added_to_process:
        tasks.append(process_added(new, idx))
        idx += 1

    if tasks:
        await asyncio.gather(*tasks)

    for skipped in recon.skipped:
        state.log_paragraph_event(
            submit_run_id=run_id,
            paragraph_uid=skipped.paragraph_uid,
            action="skipped",
            new_hash=skipped.content_hash,
        )
        report.paragraphs_skipped += 1

    if write_uids_to_markdown and to_process:
        from openharness.graphiti.paragraphs import inject_paragraph_uids

        updated = inject_paragraph_uids(markdown, new_blocks)
        source_path.write_text(updated, encoding="utf-8")

    if client.available and report.paragraphs_ingested > 0:
        try:
            from openharness.graphiti.promotion_runner import run_entity_promotions

            promotions = await run_entity_promotions(client, group_id)
            report.entities_promoted = len(promotions)
            report.promotion_notes = [
                f"{p.name}: {p.from_label} → {p.to_label} ({p.reason})" for p in promotions
            ]
        except Exception as exc:  # noqa: BLE001
            report.errors.append(f"promotion: {exc}")

    state.finish_submit_run(
        run_id,
        {
            "paragraphs_superseded": report.paragraphs_superseded,
            "paragraphs_ingested": report.paragraphs_ingested,
            "paragraphs_skipped": report.paragraphs_skipped,
            "entities_promoted": report.entities_promoted,
        },
    )
    return report


async def _supersede_paragraph(
    store: IngestStateStore,
    client: GraphitiClient,
    paragraph_uid: str,
    run_id: int,
) -> None:
    stored = store.get_paragraph(paragraph_uid)
    if stored is None:
        return
    episodes = list(stored.episode_uuids)
    edges = list(stored.edge_uuids)
    if client.available:
        for ep in episodes:
            try:
                await client.remove_episode(ep)
            except Exception:  # noqa: BLE001
                pass
        for edge in edges:
            try:
                await client.delete_entity_edge(edge)
            except Exception:  # noqa: BLE001
                pass
    store.tombstone_paragraph(paragraph_uid)
    store.log_paragraph_event(
        submit_run_id=run_id,
        paragraph_uid=paragraph_uid,
        action="deleted",
        old_hash=stored.content_hash,
        episodes_removed=episodes,
        edges_removed=edges,
    )


async def _ingest_one(
    store: IngestStateStore,
    client: GraphitiClient,
    summarize: Summarizer,
    block: ParagraphBlock,
    source_path: str,
    source_kind: str,
    submit_gate: str,
    run_id: int,
    action: str,
    summaries_map: dict[str, str] | None = None,
) -> bool:
    # 1. Run summarization and value shift extraction concurrently to optimize performance
    if summaries_map is not None and block.paragraph_uid in summaries_map:
        async def get_summary():
            return summaries_map[block.paragraph_uid]
        summary_task = get_summary()
    else:
        summary_task = summarize(block.text)

    summary, _ = await asyncio.gather(
        summary_task,
        _extract_and_save_value_shifts(
            store=store,
            client_available=client.available,
            chapter_path=source_path,
            paragraph_uid=block.paragraph_uid,
            paragraph_text=block.text,
        )
    )

    episode_uuid = ""
    edge_uuids: list[str] = []
    if client.available:
        try:
            episode_name = f"{source_path}#{block.paragraph_uid}"
            existing_uuid, existing_edges, existing_content = await client.get_episode_by_name(episode_name)

            if existing_uuid is not None:
                if existing_content == summary:
                    episode_uuid = existing_uuid
                    edge_uuids = existing_edges
                    print(f"[Ingest] Reusing existing episode from Neo4j for {episode_name}", flush=True)
                else:
                    print(f"[Ingest] Episode content changed. Removing old episode {existing_uuid}...", flush=True)
                    await client.remove_episode(existing_uuid)

            if not episode_uuid:
                episode_uuid, edge_uuids = await client.add_episode(
                    name=episode_name,
                    episode_body=summary,
                    source_description=(
                        f"{submit_gate}|{source_kind}|{block.section_heading or ''}|{block.paragraph_uid}"
                    ),
                )
        except Exception as exc:  # noqa: BLE001
            store.log_paragraph_event(
                submit_run_id=run_id,
                paragraph_uid=block.paragraph_uid,
                action=f"{action}_error",
                new_hash=block.content_hash,
                llm_summary_excerpt=str(exc),
            )
            return False

    # 2. SQLite persistence with transaction rollback safety (prevents SQLite/Neo4j state fork)
    try:
        store.save_paragraph_links(
            paragraph_uid=block.paragraph_uid,
            source_path=source_path,
            paragraph_index=block.paragraph_index,
            section_heading=block.section_heading,
            content_hash=block.content_hash,
            paragraph_text=block.text,
            episode_uuids=[episode_uuid] if episode_uuid else [],
            edge_uuids=edge_uuids,
        )
    except Exception as exc:
        if episode_uuid and client.available:
            try:
                print(f"[Ingest] SQLite link persistence failed for {block.paragraph_uid}. Rolling back Neo4j episode {episode_uuid}...", flush=True)
                await client.remove_episode(episode_uuid)
            except Exception:
                pass
        raise exc

    store.log_paragraph_event(
        submit_run_id=run_id,
        paragraph_uid=block.paragraph_uid,
        action=action,
        new_hash=block.content_hash,
        episode_created=episode_uuid or None,
        llm_summary_excerpt=summary[:200],
    )
    return True


async def _extract_and_save_value_shifts(
    store: IngestStateStore,
    client_available: bool,
    chapter_path: str,
    paragraph_uid: str,
    paragraph_text: str,
) -> None:
    if not client_available:
        return

    import os
    api_key = (
        os.environ.get("XIAOMI_API_KEY") or
        os.environ.get("DEEPSEEK_API_KEY") or
        os.environ.get("OPENAI_API_KEY")
    )
    if not api_key:
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

    from openai import AsyncOpenAI
    import json

    client_kwargs = {"api_key": api_key}
    if base_url:
        client_kwargs["base_url"] = base_url

    system_prompt = (
        "You are a professional novel editor.\n"
        "Analyze the following paragraph and identify if there is any 'scene value shift' (场景价值转移).\n"
        "A scene value shift occurs when a value dimension of a character or situation changes (e.g. safety -> danger, power -> weakness, trust -> suspicion).\n"
        "Format your output as a JSON object with the following fields:\n"
        "- conflict_focus: A brief description of the dramatic conflict in this paragraph (str or null).\n"
        "- value_dimension: The value dimension that shifted, e.g. 'Safety', 'Power', 'Trust', 'Life/Death' (str or null).\n"
        "- initial_value: The starting value of this dimension on a scale of -10 to 10 (int or null).\n"
        "- target_value: The ending value of this dimension on a scale of -10 to 10 (int or null).\n"
        "Return ONLY valid JSON, no markdown formatting, no explanation."
    )

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": paragraph_text},
    ]
    try:
        async with AsyncOpenAI(**client_kwargs) as openai_client:
            response = await openai_client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=0.1,
                response_format={"type": "json_object"} if "gpt-4" in model or "mimo" in model or "deepseek" in model else None,
            )
            content = response.choices[0].message.content or ""
            log_llm_call(
                None,
                name=f"scene_value_shift/{paragraph_uid}",
                model=model,
                messages=messages,
                response_content=content,
                usage=response.usage,
            )
            if content:
                data = json.loads(content)
                conflict_focus = data.get("conflict_focus")
                value_dim = data.get("value_dimension")
                init_val = data.get("initial_value")
                targ_val = data.get("target_value")
                if conflict_focus or value_dim:
                    store.save_scene_value_shift(
                        chapter_path=chapter_path,
                        paragraph_uid=paragraph_uid,
                        conflict_focus=conflict_focus or "",
                        value_dimension=value_dim or "",
                        initial_value=int(init_val) if init_val is not None else 0,
                        target_value=int(targ_val) if targ_val is not None else 0,
                    )
    except Exception as exc:
        import logging
        logger = logging.getLogger(__name__)
        logger.debug("Failed to extract scene value shift: %s", exc)
