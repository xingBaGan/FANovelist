"""Thin async wrapper around graphiti-core."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from openharness.graphiti.config import GraphitiSettings
from openharness.graphiti.ontology import NOVEL_ENTITY_TYPES, NOVEL_EXTRACTION_INSTRUCTIONS
from openharness.graphiti.prompts_patch import apply_novel_language_prompt_patches

try:
    from graphiti_core import Graphiti
    from graphiti_core.driver.neo4j_driver import Neo4jDriver
    from graphiti_core.edges import EntityEdge
    from graphiti_core.graphiti import AddEpisodeResults
    from graphiti_core.nodes import EpisodeType

    _GRAPHITI_AVAILABLE = True
except ImportError:
    Graphiti = None  # type: ignore[misc, assignment]
    Neo4jDriver = None  # type: ignore[misc, assignment]
    EntityEdge = None  # type: ignore[misc, assignment]
    AddEpisodeResults = None  # type: ignore[misc, assignment]
    EpisodeType = None  # type: ignore[misc, assignment]
    _GRAPHITI_AVAILABLE = False


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
        self._graphiti = Graphiti(graph_driver=driver)
        await self._graphiti.build_indices_and_constraints()

    async def close(self) -> None:
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
        group_id: str | None = None,
        entity_types: dict[str, type[Any]] | None = None,
        custom_extraction_instructions: str | None = None,
        excluded_entity_types: list[str] | None = None,
    ) -> tuple[str, list[str]]:
        """Return (episode_uuid, edge_uuids)."""
        await self._ensure_connected()
        types = entity_types if entity_types is not None else NOVEL_ENTITY_TYPES
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
            reference_time=datetime.now(timezone.utc),
            source=EpisodeType.text,
            group_id=group_id or self._settings.group_id,
            entity_types=types,
            excluded_entity_types=excluded,
            custom_extraction_instructions=instructions,
        )
        episode_uuid = result.episode.uuid
        edge_uuids = [edge.uuid for edge in result.edges]
        return episode_uuid, edge_uuids

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

    async def _ensure_connected(self) -> None:
        if self._graphiti is None:
            await self.connect()
