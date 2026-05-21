"""Apply entity promotions against Neo4j after ingest."""

from __future__ import annotations

from openharness.graphiti.client import GraphitiClient
from openharness.graphiti.entity_promotion import EntitySnapshot, PromotionDecision, suggest_promotion


async def fetch_entity_snapshots(client: GraphitiClient, group_id: str) -> list[EntitySnapshot]:
    await client._ensure_connected()
    driver = client._graphiti.driver
    query = """
    MATCH (n:Entity {group_id: $gid})
    OPTIONAL MATCH (ep:Episodic)-[:MENTIONS]->(n)
    WITH n, count(DISTINCT ep) AS mentions
    RETURN n.uuid AS uuid, n.name AS name, n.summary AS summary,
           n.background AS background, n.scene_note AS scene_note,
           n.element_note AS element_note, mentions,
           [l IN labels(n) WHERE l <> 'Entity'][0] AS primary_label
    """
    records, _, _ = await driver.execute_query(query, gid=group_id)
    out: list[EntitySnapshot] = []
    for r in records:
        label = r.get("primary_label") or "Entity"
        out.append(
            EntitySnapshot(
                uuid=r["uuid"],
                name=r["name"],
                primary_label=label,
                summary=r.get("summary") or "",
                episode_mentions=int(r.get("mentions") or 0),
                background=r.get("background"),
                scene_note=r.get("scene_note"),
                element_note=r.get("element_note"),
            )
        )
    return out


_ALLOWED = frozenset({"MinorCharacter", "MajorCharacter", "NarrativeElement"})


async def relabel_entity(
    client: GraphitiClient,
    *,
    uuid: str,
    from_label: str,
    to_label: str,
    group_id: str,
) -> None:
    if from_label not in _ALLOWED or to_label not in _ALLOWED:
        raise ValueError(f"invalid label transition {from_label!r} -> {to_label!r}")
    await client._ensure_connected()
    driver = client._graphiti.driver
    # Neo4j does not allow parameterized labels; names are from our ontology only.
    query = (
        f"MATCH (n:Entity {{uuid: $uuid, group_id: $gid}}) "
        f"REMOVE n:{from_label} SET n:{to_label} SET n.labels = ['Entity', '{to_label}']"
    )
    await driver.execute_query(query, uuid=uuid, gid=group_id)


async def run_entity_promotions(
    client: GraphitiClient,
    group_id: str,
) -> list[PromotionDecision]:
    """Evaluate and apply label promotions for a graph partition."""
    applied: list[PromotionDecision] = []
    for entity in await fetch_entity_snapshots(client, group_id):
        decision = suggest_promotion(entity)
        if decision is None:
            continue
        await relabel_entity(
            client,
            uuid=decision.uuid,
            from_label=decision.from_label,
            to_label=decision.to_label,
            group_id=group_id,
        )
        applied.append(decision)
    return applied
