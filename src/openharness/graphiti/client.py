"""Thin async wrapper around graphiti-core."""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from openharness.graphiti.config import GraphitiSettings
from openharness.graphiti.ontology import (
    NOVEL_EDGE_TYPE_MAP,
    NOVEL_EDGE_TYPES,
    NOVEL_ENTITY_TYPES,
    NOVEL_EXTRACTION_INSTRUCTIONS,
)
from openharness.graphiti.prompts_patch import apply_novel_language_prompt_patches
from openharness.graphiti.save_patch import apply_graphiti_save_patches

try:
    from graphiti_core import Graphiti
    from graphiti_core.driver.neo4j_driver import Neo4jDriver
    from graphiti_core.edges import EntityEdge
    from graphiti_core.graphiti import AddEpisodeResults
    from graphiti_core.nodes import EpisodeType

    # Extra imports for custom models
    import json
    import re
    import typing
    from pydantic import BaseModel
    from graphiti_core.cross_encoder.client import CrossEncoderClient
    from graphiti_core.embedder.openai import OpenAIEmbedder, OpenAIEmbedderConfig
    from graphiti_core.llm_client.config import LLMConfig, ModelSize
    from graphiti_core.llm_client.openai_generic_client import OpenAIGenericClient
    from graphiti_core.prompts.models import Message

    _GRAPHITI_AVAILABLE = True
except ImportError:
    Graphiti = None  # type: ignore[misc, assignment]
    Neo4jDriver = None  # type: ignore[misc, assignment]
    EntityEdge = None  # type: ignore[misc, assignment]
    AddEpisodeResults = None  # type: ignore[misc, assignment]
    EpisodeType = None  # type: ignore[misc, assignment]
    _GRAPHITI_AVAILABLE = False


if _GRAPHITI_AVAILABLE:
    class DeepSeekLLMClient(OpenAIGenericClient):
        """DeepSeek workaround for json_schema format."""

        async def _generate_response(
            self,
            messages: list[Message],
            response_model: type[BaseModel] | None = None,
            max_tokens: int = 4096,
            model_size: ModelSize = ModelSize.medium,
        ) -> dict[str, typing.Any]:
            import openai

            openai_messages: list[dict] = []
            for m in messages:
                content = self._clean_input(m.content)
                if response_model is not None and m.role == "system":
                    schema_str = json.dumps(
                        response_model.model_json_schema(), ensure_ascii=False, indent=2
                    )
                    content = (
                        content
                        + "\n\nRespond with valid JSON that matches this schema:\n"
                        + schema_str
                    )
                if m.role == "user":
                    openai_messages.append({"role": "user", "content": content})
                elif m.role == "system":
                    openai_messages.append({"role": "system", "content": content})

            try:
                response = await self.client.chat.completions.create(
                    model=self.model,
                    messages=openai_messages,
                    temperature=self.temperature,
                    max_tokens=self.max_tokens,
                    response_format={"type": "json_object"},
                )
                result = response.choices[0].message.content or "{}"
                return json.loads(result)
            except Exception:
                raise

    class LocalRerankerClient(CrossEncoderClient):
        """Lightweight lexical reranker."""

        @staticmethod
        def _score(query: str, passage: str) -> float:
            query_terms = {
                term
                for term in re.findall(r"[\u4e00-\u9fff]{2,}|[A-Za-z0-9_/-]+", query)
                if term
            }
            if not query_terms:
                query_terms = {ch for ch in query if not ch.isspace()}
            if not passage:
                return 0.0
            hits = sum(1 for term in query_terms if term in passage)
            return float(hits)

        async def rank(self, query: str, passages: list[str]) -> list[tuple[str, float]]:
            ranked = [(passage, self._score(query, passage)) for passage in passages]
            ranked.sort(key=lambda item: item[1], reverse=True)
            return ranked


@dataclass(frozen=True)
class GraphitiStatus:
    connected: bool
    message: str


class GraphitiClient:
    """Lazy Graphiti connection with hard-delete helpers."""

    def __init__(self, settings: GraphitiSettings | None = None) -> None:
        self._settings = settings or GraphitiSettings.from_env()
        self._graphiti: Any = None

    @property
    def available(self) -> bool:
        return _GRAPHITI_AVAILABLE and self._settings.is_configured

    async def connect(self) -> None:
        if not self.available:
            raise RuntimeError("graphiti-core is not installed or Neo4j env is incomplete")
        driver = Neo4jDriver(
            uri=self._settings.neo4j_uri,
            user=self._settings.neo4j_user,
            password=self._settings.neo4j_password,
            database=self._settings.neo4j_database,
        )
        apply_novel_language_prompt_patches()
        apply_graphiti_save_patches()

        llm_client = None
        embedder = None
        cross_encoder = None

        if self._settings.xiaomi_api_key:
            llm_client = DeepSeekLLMClient(
                config=LLMConfig(
                    api_key=self._settings.xiaomi_api_key,
                    model=os.environ.get("XIAOMI_MODEL", "mimo-v2-pro"),
                    base_url="https://api.xiaomimimo.com/v1",
                ),
                max_tokens=4096,
            )
            cross_encoder = LocalRerankerClient()
        elif self._settings.deepseek_api_key:
            llm_client = DeepSeekLLMClient(
                config=LLMConfig(
                    api_key=self._settings.deepseek_api_key,
                    model=os.environ.get("DEEPSEEK_MODEL", "deepseek-v4-flash"),
                    base_url="https://api.deepseek.com",
                ),
                max_tokens=4096,
            )
            cross_encoder = LocalRerankerClient()

        if self._settings.siliconflow_api_key:
            embedder = OpenAIEmbedder(
                config=OpenAIEmbedderConfig(
                    api_key=self._settings.siliconflow_api_key,
                    base_url="https://api.siliconflow.cn/v1",
                    embedding_model="BAAI/bge-m3",
                    embedding_dim=1024,
                )
            )

        self._graphiti = Graphiti(
            graph_driver=driver,
            llm_client=llm_client,
            embedder=embedder,
            cross_encoder=cross_encoder,
        )
        await self._graphiti.build_indices_and_constraints()

    async def close(self) -> None:
        if self._graphiti is not None:
            await self._graphiti.close()
            self._graphiti = None

    async def get_status(self) -> GraphitiStatus:
        if not self.available:
            return GraphitiStatus(False, "graphiti-core or Neo4j configuration missing")
        try:
            await self.connect()
            return GraphitiStatus(True, "Neo4j connected")
        except Exception as exc:  # noqa: BLE001
            return GraphitiStatus(False, str(exc))

    async def add_episode(
        self,
        *,
        name: str,
        episode_body: str,
        source_description: str,
        reference_time: datetime | None = None,
        group_id: str | None = None,
        entity_types: dict[str, type[Any]] | None = None,
        custom_extraction_instructions: str | None = None,
        excluded_entity_types: list[str] | None = None,
        edge_types: dict[str, type[Any]] | None = None,
        edge_type_map: dict[tuple[str, str], list[str]] | None = None,
    ) -> tuple[str, list[str]]:
        """Return (episode_uuid, edge_uuids)."""
        await self._ensure_connected()
        types = entity_types if entity_types is not None else NOVEL_ENTITY_TYPES
        etypes = edge_types if edge_types is not None else NOVEL_EDGE_TYPES
        emap = edge_type_map if edge_type_map is not None else NOVEL_EDGE_TYPE_MAP
        instructions = (
            custom_extraction_instructions
            if custom_extraction_instructions is not None
            else NOVEL_EXTRACTION_INSTRUCTIONS
        )
        excluded = (
            excluded_entity_types
            if excluded_entity_types is not None
            else ["Entity"]
        )
        result: AddEpisodeResults = await self._graphiti.add_episode(
            name=name,
            episode_body=episode_body,
            source_description=source_description,
            reference_time=reference_time if reference_time is not None else datetime.now(timezone.utc),
            source=EpisodeType.text,
            group_id=group_id or self._settings.group_id,
            entity_types=types,
            excluded_entity_types=excluded,
            edge_types=etypes,
            edge_type_map=emap,
            custom_extraction_instructions=instructions,
        )
        episode_uuid = result.episode.uuid
        edge_uuids = [edge.uuid for edge in result.edges]
        return episode_uuid, edge_uuids

    async def get_episode_by_name(
        self,
        name: str,
        group_id: str | None = None,
    ) -> tuple[str | None, list[str], str | None]:
        """Query Neo4j for an existing episodic node by name.

        Returns (episode_uuid, edge_uuids, content) or (None, [], None) if not found.
        If duplicates exist, deletes all of them (self-healing duplicate cleanup) and returns (None, [], None).
        """
        if not self.available:
            return None, [], None
        await self._ensure_connected()
        gid = group_id or self._settings.group_id

        query = (
            "MATCH (e:Episodic) "
            "WHERE e.name = $name AND e.group_id = $group_id "
            "RETURN e.uuid AS episode_uuid, e.entity_edges AS edge_uuids, e.content AS content"
        )

        result = await self._graphiti.driver.execute_query(
            query,
            params={"name": name, "group_id": gid}
        )

        if not result.records:
            return None, [], None

        if len(result.records) > 1:
            for record in result.records:
                uuid_to_del = record.get("episode_uuid")
                if uuid_to_del:
                    try:
                        await self.remove_episode(uuid_to_del)
                    except Exception:  # noqa: BLE001
                        pass
            return None, [], None

        record = result.records[0]
        episode_uuid = record.get("episode_uuid")
        edge_uuids = record.get("edge_uuids") or []
        content = record.get("content")
        return episode_uuid, edge_uuids, content

    async def remove_episode(self, episode_uuid: str) -> None:
        await self._ensure_connected()
        await self._graphiti.remove_episode(episode_uuid)

    async def delete_entity_edge(self, edge_uuid: str) -> None:
        await self._ensure_connected()
        edge = await EntityEdge.get_by_uuid(self._graphiti.driver, edge_uuid)
        await edge.delete(self._graphiti.driver)

    async def search_facts(self, query: str, *, group_id: str | None = None) -> list[Any]:
        await self._ensure_connected()
        gid = group_id or self._settings.group_id
        return await self._graphiti.search(query, group_ids=[gid])

    async def search_nodes(self, query: str, *, group_id: str | None = None) -> Any:
        await self._ensure_connected()
        gid = group_id or self._settings.group_id
        return await self._graphiti.search_(query, group_ids=[gid])

    async def trace_entity_origins(
        self,
        entity_name: str,
        *,
        group_id: str | None = None,
    ) -> list[dict[str, Any]]:
        """Find all episodic source paragraphs mentioning the given entity."""
        await self._ensure_connected()
        gid = group_id or self._settings.group_id
        
        query = (
            "MATCH (e:Episodic)-[:MENTIONS]->(n:Entity) "
            "WHERE n.name = $entity_name AND e.group_id = $group_id "
            "RETURN e.uuid AS episode_uuid, e.name AS episode_name, "
            "       e.content AS content, e.valid_at AS valid_at "
            "ORDER BY e.valid_at ASC"
        )
        
        result = await self._graphiti.driver.execute_query(
            query,
            params={"entity_name": entity_name, "group_id": gid}
        )
        
        origins = []
        for record in result.records:
            val_at = record.get("valid_at")
            val_at_str = val_at.isoformat() if hasattr(val_at, "isoformat") else str(val_at) if val_at is not None else None
                
            origins.append({
                "episode_uuid": record.get("episode_uuid"),
                "episode_name": record.get("episode_name"),
                "content": record.get("content"),
                "valid_at": val_at_str,
            })
        return origins

    async def get_story_timeline(
        self,
        *,
        focus_entity: str | None = None,
        group_id: str | None = None,
    ) -> list[dict[str, Any]]:
        """Get a chronological story timeline, optionally filtered by a focus entity."""
        await self._ensure_connected()
        gid = group_id or self._settings.group_id
        
        if focus_entity:
            episode_query = (
                "MATCH (e:Episodic)-[:MENTIONS]->(n:Entity) "
                "WHERE n.name = $focus_entity AND e.group_id = $group_id "
                "RETURN e.uuid AS episode_uuid, e.name AS episode_name, "
                "       e.content AS content, e.valid_at AS valid_at "
                "ORDER BY e.valid_at ASC"
            )
            ep_result = await self._graphiti.driver.execute_query(
                episode_query,
                params={"focus_entity": focus_entity, "group_id": gid}
            )
        else:
            episode_query = (
                "MATCH (e:Episodic) "
                "WHERE e.group_id = $group_id "
                "RETURN e.uuid AS episode_uuid, e.name AS episode_name, "
                "       e.content AS content, e.valid_at AS valid_at "
                "ORDER BY e.valid_at ASC"
            )
            ep_result = await self._graphiti.driver.execute_query(
                episode_query,
                params={"group_id": gid}
            )
            
        episodes = []
        for record in ep_result.records:
            val_at = record.get("valid_at")
            val_at_str = val_at.isoformat() if hasattr(val_at, "isoformat") else str(val_at) if val_at is not None else None
                
            episodes.append({
                "episode_uuid": record.get("episode_uuid"),
                "episode_name": record.get("episode_name"),
                "content": record.get("content"),
                "valid_at": val_at_str,
                "relations": []
            })
            
        if not episodes:
            return []
            
        if focus_entity:
            rel_query = (
                "MATCH (n:Entity)-[r:RELATES_TO]-(m:Entity) "
                "WHERE n.name = $focus_entity AND r.group_id = $group_id "
                "RETURN r.uuid AS edge_uuid, r.name AS relation_name, r.fact AS fact, "
                "       r.valid_at AS valid_at, r.invalid_at AS invalid_at, "
                "       m.name AS target_name, r.episodes AS episodes, n.name AS source_name"
            )
            rel_result = await self._graphiti.driver.execute_query(
                rel_query,
                params={"focus_entity": focus_entity, "group_id": gid}
            )
        else:
            rel_query = (
                "MATCH (n:Entity)-[r:RELATES_TO]->(m:Entity) "
                "WHERE r.group_id = $group_id "
                "RETURN r.uuid AS edge_uuid, r.name AS relation_name, r.fact AS fact, "
                "       r.valid_at AS valid_at, r.invalid_at AS invalid_at, "
                "       m.name AS target_name, r.episodes AS episodes, n.name AS source_name"
            )
            rel_result = await self._graphiti.driver.execute_query(
                rel_query,
                params={"group_id": gid}
            )
            
        episode_map = {ep["episode_uuid"]: ep for ep in episodes}
        
        for record in rel_result.records:
            rel_episodes = record.get("episodes") or []
            val_at = record.get("valid_at")
            inv_at = record.get("invalid_at")
            
            val_at_str = val_at.isoformat() if hasattr(val_at, "isoformat") else str(val_at) if val_at is not None else None
            inv_at_str = inv_at.isoformat() if hasattr(inv_at, "isoformat") else str(inv_at) if inv_at is not None else None
            
            rel_info = {
                "edge_uuid": record.get("edge_uuid"),
                "relation_name": record.get("relation_name"),
                "fact": record.get("fact"),
                "source_name": record.get("source_name"),
                "target_name": record.get("target_name"),
                "valid_at": val_at_str,
                "invalid_at": inv_at_str,
            }
            
            for ep_uuid in rel_episodes:
                if ep_uuid in episode_map:
                    if not any(x["edge_uuid"] == rel_info["edge_uuid"] for x in episode_map[ep_uuid]["relations"]):
                        episode_map[ep_uuid]["relations"].append(rel_info)
                        
        return episodes

    async def get_factions_outline(
        self,
        *,
        group_id: str | None = None,
    ) -> list[dict[str, Any]]:
        """Get an outline of factions/communities and their member entities."""
        await self._ensure_connected()
        gid = group_id or self._settings.group_id
        
        query = (
            "MATCH (c:Community)-[:HAS_MEMBER]->(n:Entity) "
            "WHERE c.group_id = $group_id "
            "RETURN c.uuid AS community_uuid, c.summary AS summary, "
            "       collect({name: n.name, labels: labels(n)}) AS members"
        )
        
        result = await self._graphiti.driver.execute_query(
            query,
            params={"group_id": gid}
        )
        
        communities = []
        for record in result.records:
            communities.append({
                "community_uuid": record.get("community_uuid"),
                "summary": record.get("summary"),
                "members": record.get("members") or [],
            })
        return communities

    async def get_historical_relationships(
        self,
        target_time: str,
        *,
        focus_entity: str | None = None,
        group_id: str | None = None,
    ) -> list[dict[str, Any]]:
        """Get active semantic relationships at a specific point in time."""
        await self._ensure_connected()
        gid = group_id or self._settings.group_id
        
        if focus_entity:
            query = (
                "MATCH (n:Entity)-[r:RELATES_TO]->(m:Entity) "
                "WHERE r.group_id = $group_id "
                "  AND (n.name = $focus_entity OR m.name = $focus_entity) "
                "  AND r.valid_at <= datetime($target_time) "
                "  AND (r.invalid_at IS NULL OR r.invalid_at > datetime($target_time)) "
                "RETURN n.name AS source_name, labels(n) AS source_labels, "
                "       m.name AS target_name, labels(m) AS target_labels, "
                "       r.uuid AS edge_uuid, r.name AS relation_name, r.fact AS fact, "
                "       r.valid_at AS valid_at, r.invalid_at AS invalid_at, "
                "       properties(r) AS all_props"
            )
            result = await self._graphiti.driver.execute_query(
                query,
                params={"focus_entity": focus_entity, "group_id": gid, "target_time": target_time}
            )
        else:
            query = (
                "MATCH (n:Entity)-[r:RELATES_TO]->(m:Entity) "
                "WHERE r.group_id = $group_id "
                "  AND r.valid_at <= datetime($target_time) "
                "  AND (r.invalid_at IS NULL OR r.invalid_at > datetime($target_time)) "
                "RETURN n.name AS source_name, labels(n) AS source_labels, "
                "       m.name AS target_name, labels(m) AS target_labels, "
                "       r.uuid AS edge_uuid, r.name AS relation_name, r.fact AS fact, "
                "       r.valid_at AS valid_at, r.invalid_at AS invalid_at, "
                "       properties(r) AS all_props"
            )
            result = await self._graphiti.driver.execute_query(
                query,
                params={"group_id": gid, "target_time": target_time}
            )
            
        system_keys = {
            "fact_embedding", "uuid", "created_at", "group_id", "reference_time",
            "episodes", "name", "valid_at", "invalid_at"
        }
        
        def _clean_val(val: Any) -> Any:
            if hasattr(val, "isoformat"):
                return val.isoformat()
            if isinstance(val, dict):
                return {k: _clean_val(v) for k, v in val.items()}
            if isinstance(val, list):
                return [_clean_val(v) for v in val]
            return val
        
        relationships = []
        for record in result.records:
            all_props = record.get("all_props") or {}
            attributes = {k: _clean_val(v) for k, v in all_props.items() if k not in system_keys}
            
            val_at = record.get("valid_at")
            inv_at = record.get("invalid_at")
            val_at_str = val_at.isoformat() if hasattr(val_at, "isoformat") else str(val_at) if val_at is not None else None
            inv_at_str = inv_at.isoformat() if hasattr(inv_at, "isoformat") else str(inv_at) if inv_at is not None else None
            
            relationships.append({
                "source_name": record.get("source_name"),
                "source_labels": record.get("source_labels") or [],
                "target_name": record.get("target_name"),
                "target_labels": record.get("target_labels") or [],
                "edge_uuid": record.get("edge_uuid"),
                "relation_name": record.get("relation_name"),
                "fact": record.get("fact"),
                "valid_at": val_at_str,
                "invalid_at": inv_at_str,
                "attributes": attributes,
            })
            
        return relationships

    async def _ensure_connected(self) -> None:
        if self._graphiti is None:
            await self.connect()
