from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from openai import AsyncOpenAI

from openharness.graphiti.client import GraphitiClient
from openharness.graphiti.ingest_store import IngestStateStore


async def classify_and_aggregate_summaries(
    paragraph_list: list[dict[str, Any]],
    api_key: str,
    base_url: str | None = None,
    model: str = "gpt-4o",
) -> dict[str, Any]:
    """Uses the LLM to classify paragraph summaries into static_lore and dynamic_scenes.

    Adjacent dynamic paragraphs are aggregated into single major scenes.
    """
    system_prompt = (
        "You are an expert novel editor and narrative architect.\n"
        "Your task is to analyze a list of paragraph summaries of a chapter and classify them to optimize a knowledge graph.\n"
        "We want to split the information into two parts:\n"
        "1. Static/Lore (landscape, minor character descriptions, minor interactions, daily routines) - this belongs in markdown/JSON and should NOT go to the Neo4j graph database.\n"
        "2. Dynamic/Dramatic (core conflicts, value shifts, beliefs, secrets/misconceptions, Chekhov's guns, major character decisions) - these will go to Neo4j.\n"
        "\n"
        "To save tokens and prevent noisy graphs, adjacent dynamic paragraphs belonging to the same dramatic scene/sequence MUST be aggregated into a single major scene (episode).\n"
        "\n"
        "Format your output as a JSON object with the following fields:\n"
        "- static_lore: List of objects, each containing:\n"
        "    - uid: The paragraph uid.\n"
        "    - reason: Why this paragraph is static lore.\n"
        "- dynamic_scenes: List of aggregated scenes, each containing:\n"
        "    - scene_title: A concise title for the aggregated episode (in Chinese).\n"
        "    - scene_summary: A consolidated, dramatic summary of what happens in this scene, combining the source paragraphs (in Chinese).\n"
        "    - paragraph_uids: List of the source paragraph uids that are merged into this scene.\n"
        "    - key_dramatic_elements: A brief description of the desire, fear, secret, or value shift in this scene.\n"
        "\n"
        "Output ONLY valid JSON, no markdown formatting."
    )

    async with AsyncOpenAI(api_key=api_key, base_url=base_url) as openai_client:
        response = await openai_client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": json.dumps(paragraph_list, ensure_ascii=False)},
            ],
            temperature=0.2,
            response_format={"type": "json_object"} if "gpt-4" in model or "mimo" in model or "deepseek" in model else None,
        )
        plan_content = response.choices[0].message.content

    if not plan_content:
        raise RuntimeError("Empty response from LLM during aggregation.")

    return json.loads(plan_content.strip())


async def load_or_generate_aggregation_plan(
    plan_path: Path,
    paragraph_list: list[dict[str, Any]],
    api_key: str,
    base_url: str | None = None,
    model: str = "gpt-4o",
) -> dict[str, Any]:
    """Loads aggregation plan from cache if it exists, otherwise calls LLM and saves it."""
    if plan_path.exists():
        print(f"Loading existing aggregation plan from cache: {plan_path}")
        return json.loads(plan_path.read_text(encoding="utf-8"))

    print(f"Aggregating paragraph summaries using LLM model: {model}...")
    plan_data = await classify_and_aggregate_summaries(
        paragraph_list=paragraph_list,
        api_key=api_key,
        base_url=base_url,
        model=model,
    )
    plan_path.parent.mkdir(parents=True, exist_ok=True)
    plan_path.write_text(json.dumps(plan_data, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Aggregation plan saved to: {plan_path}")
    return plan_data


async def ingest_aggregation_plan(
    *,
    plan_data: dict[str, Any],
    client: GraphitiClient,
    store: IngestStateStore,
    summary_path: Path,
    paragraph_list: list[dict[str, Any]],
    source_path_str: str,  # e.g. "studio/chapters/chapter_wuxia_01.md"
    chapter_index_prefix: str,  # e.g. "chapter_wuxia_01"
    submit_gate: str = "approve-chapter",
    lore_output_path: Path | None = None,
) -> int:
    """Executes the ingestion of the aggregation plan.

    Ingests aggregated scenes into Neo4j and SQLite sequentially, and handles static lore.
    Returns the submit_run_id.
    """
    # 1. Save static lore locally if requested
    static_lore_list = plan_data.get("static_lore", [])
    static_lore_map = {
        item["uid"]: next(p for p in paragraph_list if p["uid"] == item["uid"])
        for item in static_lore_list
    }
    if lore_output_path:
        lore_output_path.parent.mkdir(parents=True, exist_ok=True)
        lore_output_path.write_text(json.dumps(static_lore_map, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"Saved local static lore to: {lore_output_path}")

    # 2. Ingest dynamic scenes to Neo4j and SQLite sequentially to ensure correct temporal state updates
    submit_run_id = store.start_submit_run(
        submit_gate=submit_gate,
        source_path=str(summary_path),
        source_kind="chapter",
        submit_scope="chapter_all"
    )

    base_time = datetime.now(timezone.utc)

    for idx, scene in enumerate(plan_data.get("dynamic_scenes", [])):
        episode_name = f"{chapter_index_prefix}#{scene['scene_title']}"
        print(f"Ingesting aggregated scene: '{scene['scene_title']}'...")

        episode_uuid = ""
        edge_uuids = []
        ref_time = base_time + timedelta(minutes=idx)
        if client.available:
            try:
                # Deduplication/reuse check: query existing episode by name
                existing_uuid, existing_edges, existing_content = await client.get_episode_by_name(episode_name)
                if existing_uuid:
                    if existing_content == scene["scene_summary"]:
                        print(f"  [Reuse] Found matching existing episode in Neo4j: {existing_uuid}")
                        episode_uuid = existing_uuid
                        edge_uuids = existing_edges
                    else:
                        print(f"  [Update] Content changed for '{scene['scene_title']}'. Removing old episode: {existing_uuid}")
                        await client.remove_episode(existing_uuid)
                        # Add new episode
                        episode_uuid, edge_uuids = await client.add_episode(
                            name=episode_name,
                            episode_body=scene["scene_summary"],
                            source_description=f"aggregated-scene|{scene['key_dramatic_elements']}",
                            reference_time=ref_time
                        )
                        print(f"  Ingested updated scene to Neo4j. Episode UUID: {episode_uuid}")
                else:
                    # Add new episode
                    episode_uuid, edge_uuids = await client.add_episode(
                        name=episode_name,
                        episode_body=scene["scene_summary"],
                        source_description=f"aggregated-scene|{scene['key_dramatic_elements']}",
                        reference_time=ref_time
                    )
                    print(f"  Ingested new scene to Neo4j. Episode UUID: {episode_uuid}")
            except Exception as exc:
                print(f"  Error ingesting to Neo4j: {exc}")

        # Save SQLite mappings for each source paragraph
        for p_uid in scene["paragraph_uids"]:
            orig_p = next(p for p in paragraph_list if p["uid"] == p_uid)
            # Check if this paragraph is already linked to this episode in SQLite
            existing_p = store.get_paragraph(p_uid)
            if existing_p and existing_p.content_hash == orig_p["hash"] and (episode_uuid in existing_p.episode_uuids):
                print(f"  [SQLite] Paragraph {p_uid} already linked. Skipping.")
                continue

            store.save_paragraph_links(
                paragraph_uid=p_uid,
                source_path=source_path_str,
                paragraph_index=paragraph_list.index(orig_p),
                section_heading=scene["scene_title"],
                content_hash=orig_p["hash"],
                paragraph_text=orig_p["summary"],
                episode_uuids=[episode_uuid] if episode_uuid else [],
                edge_uuids=edge_uuids
            )
            store.log_paragraph_event(
                submit_run_id=submit_run_id,
                paragraph_uid=p_uid,
                action="ingested_aggregated",
                new_hash=orig_p["hash"],
                episode_created=episode_uuid or None,
                llm_summary_excerpt=scene["scene_summary"][:100]
            )

    # For static lore, we also save links with empty episode_uuids to mark them processed in SQLite
    for p_uid, orig_p in static_lore_map.items():
        existing_p = store.get_paragraph(p_uid)
        if existing_p and existing_p.content_hash == orig_p["hash"] and len(existing_p.episode_uuids) == 0:
            print(f"  [SQLite] Lore Paragraph {p_uid} already stored. Skipping.")
            continue

        store.save_paragraph_links(
            paragraph_uid=p_uid,
            source_path=source_path_str,
            paragraph_index=paragraph_list.index(orig_p),
            section_heading="Static Lore",
            content_hash=orig_p["hash"],
            paragraph_text=orig_p["summary"],
            episode_uuids=[],
            edge_uuids=[]
        )
        store.log_paragraph_event(
            submit_run_id=submit_run_id,
            paragraph_uid=p_uid,
            action="skipped_lore",
            new_hash=orig_p["hash"]
        )

    store.finish_submit_run(submit_run_id, {"dynamic_scenes_ingested": len(plan_data.get("dynamic_scenes", []))})
    print("\nIngestion plan execution completed successfully!")
    return submit_run_id
