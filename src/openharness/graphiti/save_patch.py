"""Patch graphiti-core save paths to drop null-like attribute values before Neo4j writes."""

from __future__ import annotations

import json
from collections.abc import Callable
from functools import wraps
from typing import Any, TypeVar

from graphiti_core.driver.driver import GraphProvider
from graphiti_core.models.edges.edge_db_queries import (
    get_entity_edge_save_bulk_query,
    get_episodic_edge_save_bulk_query,
)
from graphiti_core.models.nodes.node_db_queries import (
    EPISODIC_NODE_RETURN,
    EPISODIC_NODE_RETURN_NEPTUNE,
    get_entity_node_save_bulk_query,
    get_episode_node_save_bulk_query,
)
from graphiti_core.nodes import EpisodeType, get_episodic_node_from_record
from graphiti_core.utils import bulk_utils

_PATCHED = False
_T = TypeVar("_T")


def _is_null_like(value: Any) -> bool:
    if value is None:
        return True
    if value.__class__.__name__ == "NoValue":
        return True
    return repr(value) == "NO_VALUE" or str(value) == "NO_VALUE"


def _sanitize(value: Any) -> Any:
    if isinstance(value, dict):
        cleaned: dict[Any, Any] = {}
        for key, item in value.items():
            if _is_null_like(item):
                continue
            if isinstance(item, dict):
                cleaned[key] = json.dumps(_sanitize(item), ensure_ascii=False, default=str)
            elif isinstance(item, list):
                sanitized_list = []
                for entry in item:
                    if _is_null_like(entry):
                        continue
                    if isinstance(entry, dict):
                        sanitized_list.append(json.dumps(_sanitize(entry), ensure_ascii=False, default=str))
                    else:
                        sanitized_list.append(_sanitize(entry))
                cleaned[key] = sanitized_list
            elif isinstance(item, tuple):
                sanitized_tuple = []
                for entry in item:
                    if _is_null_like(entry):
                        continue
                    if isinstance(entry, dict):
                        sanitized_tuple.append(
                            json.dumps(_sanitize(entry), ensure_ascii=False, default=str)
                        )
                    else:
                        sanitized_tuple.append(_sanitize(entry))
                cleaned[key] = tuple(sanitized_tuple)
            else:
                cleaned[key] = item
        return cleaned
    if isinstance(value, list):
        sanitized_list = []
        for item in value:
            if _is_null_like(item):
                continue
            if isinstance(item, dict):
                sanitized_list.append(json.dumps(_sanitize(item), ensure_ascii=False, default=str))
            else:
                sanitized_list.append(_sanitize(item))
        return sanitized_list
    if isinstance(value, tuple):
        sanitized_tuple = []
        for item in value:
            if _is_null_like(item):
                continue
            if isinstance(item, dict):
                sanitized_tuple.append(json.dumps(_sanitize(item), ensure_ascii=False, default=str))
            else:
                sanitized_tuple.append(_sanitize(item))
        return tuple(sanitized_tuple)
    return value


class SanitizingGraphOperationsProxy:
    """Minimal graph operations interface that strips nested maps before bulk writes."""

    @staticmethod
    def _prepare_payloads(items: list[Any]) -> list[dict[str, Any]]:
        prepared: list[dict[str, Any]] = []
        for item in items:
            if isinstance(item, dict):
                prepared.append(_sanitize(item))
            elif hasattr(item, "model_dump"):
                prepared.append(_sanitize(item.model_dump()))
            else:
                prepared.append(_sanitize(dict(item)))
        return prepared

    async def node_save_bulk(self, _cls: Any, driver: Any, transaction: Any, nodes: list[Any], batch_size: int = 100) -> None:
        prepared = self._prepare_payloads(nodes)
        query = get_entity_node_save_bulk_query(driver.provider, prepared)
        await transaction.run(query, nodes=prepared)

    async def edge_save_bulk(self, _cls: Any, driver: Any, transaction: Any, edges: list[Any], batch_size: int = 100) -> None:
        prepared = self._prepare_payloads(edges)
        query = get_entity_edge_save_bulk_query(driver.provider)
        await transaction.run(query, entity_edges=prepared)

    async def episodic_node_save_bulk(self, _cls: Any, driver: Any, transaction: Any, nodes: list[Any], batch_size: int = 100) -> None:
        prepared = self._prepare_payloads(nodes)
        query = get_episode_node_save_bulk_query(driver.provider)
        await transaction.run(query, episodes=prepared)

    async def episodic_edge_save_bulk(self, _cls: Any, driver: Any, transaction: Any, episodic_edges: list[Any], batch_size: int = 100) -> None:
        prepared = self._prepare_payloads(episodic_edges)
        query = get_episodic_edge_save_bulk_query(driver.provider)
        await transaction.run(query, episodic_edges=prepared)

    async def retrieve_episodes(
        self,
        driver: Any,
        reference_time: Any,
        last_n: int = 3,
        group_ids: list[str] | None = None,
        source: EpisodeType | None = None,
        saga: str | None = None,
    ) -> list[Any]:
        if saga is not None:
            group_id = group_ids[0] if group_ids else None
            source_filter = 'AND e.source = $source' if source is not None else ''
            records, _, _ = await driver.execute_query(
                f"""
                MATCH (s:Saga {{name: $saga_name, group_id: $group_id}})-[:HAS_EPISODE]->(e:Episodic)
                WHERE e.valid_at <= $reference_time
                {source_filter}
                RETURN
                """
                + (
                    EPISODIC_NODE_RETURN_NEPTUNE
                    if driver.provider == GraphProvider.NEPTUNE
                    else EPISODIC_NODE_RETURN
                )
                + """
                ORDER BY e.valid_at DESC
                LIMIT $num_episodes
                """,
                saga_name=saga,
                group_id=group_id,
                reference_time=reference_time,
                source=source.name if source else None,
                num_episodes=last_n,
            )
            episodes = [get_episodic_node_from_record(record) for record in records]
            return list(reversed(episodes))

        query_params: dict[str, Any] = {}
        query_filter = ''
        if group_ids and len(group_ids) > 0:
            query_filter += '\nAND e.group_id IN $group_ids'
            query_params['group_ids'] = group_ids
        if source is not None:
            query_filter += '\nAND e.source = $source'
            query_params['source'] = source.name

        records, _, _ = await driver.execute_query(
            """
                                    MATCH (e:Episodic)
                                    WHERE e.valid_at <= $reference_time
                                    """
            + query_filter
            + """
            RETURN
            """
            + (
                EPISODIC_NODE_RETURN_NEPTUNE
                if driver.provider == GraphProvider.NEPTUNE
                else EPISODIC_NODE_RETURN
            )
            + """
            ORDER BY e.valid_at DESC
            LIMIT $num_episodes
            """,
            reference_time=reference_time,
            num_episodes=last_n,
            **query_params,
        )
        episodes = [get_episodic_node_from_record(record) for record in records]
        return list(reversed(episodes))

    async def saga_get_previous_episode_uuid(
        self,
        driver: Any,
        saga_uuid: str,
        current_episode_uuid: str,
    ) -> str | None:
        records, _, _ = await driver.execute_query(
            """
            MATCH (s:Saga {uuid: $saga_uuid})-[:HAS_EPISODE]->(e:Episodic)
            WHERE e.uuid <> $current_episode_uuid
            RETURN e.uuid AS uuid
            ORDER BY e.valid_at DESC, e.created_at DESC
            LIMIT 1
            """,
            saga_uuid=saga_uuid,
            current_episode_uuid=current_episode_uuid,
            routing_='r',
        )
        if records:
            return records[0]['uuid']
        return None

    async def saga_get_episode_contents(
        self,
        driver: Any,
        saga_uuid: str,
        since: Any | None = None,
        limit: int = 200,
    ) -> list[tuple[str, Any | None]] | None:
        query = """
            MATCH (s:Saga {uuid: $saga_uuid})-[:HAS_EPISODE]->(e:Episodic)
            WHERE ($since IS NULL OR e.created_at > $since)
            RETURN e.content AS content, e.valid_at AS valid_at
            ORDER BY e.valid_at ASC
            LIMIT $limit
        """
        records, _, _ = await driver.execute_query(
            query,
            saga_uuid=saga_uuid,
            since=since,
            limit=limit,
            routing_='r',
        )
        return [(record['content'], record['valid_at']) for record in records]


def install_sanitizing_graph_operations_interface(driver: Any) -> None:
    """Attach a lightweight graph ops proxy that keeps Neo4j payloads primitive-only."""
    driver.graph_operations_interface = SanitizingGraphOperationsProxy()


def _wrap_save(save_fn: Callable[..., Any]) -> Callable[..., Any]:
    @wraps(save_fn)
    async def wrapped(self: Any, driver: Any, *args: Any, **kwargs: Any) -> Any:
        attributes = getattr(self, "attributes", None)
        if not attributes:
            return await save_fn(self, driver, *args, **kwargs)

        cleaned = _sanitize(attributes)
        if cleaned == attributes:
            return await save_fn(self, driver, *args, **kwargs)

        original_attributes = attributes
        self.attributes = cleaned
        try:
            return await save_fn(self, driver, *args, **kwargs)
        finally:
            self.attributes = original_attributes

    return wrapped


def apply_graphiti_save_patches() -> None:
    """Idempotently strip null-like node and edge attributes before persistence."""
    global _PATCHED
    if _PATCHED:
        return

    from graphiti_core.driver.neo4j.operations.entity_edge_ops import Neo4jEntityEdgeOperations
    from graphiti_core.driver.neo4j.operations.entity_node_ops import Neo4jEntityNodeOperations
    from graphiti_core.edges import EntityEdge
    from graphiti_core.nodes import EntityNode

    EntityNode.save = _wrap_save(EntityNode.save)  # type: ignore[assignment]
    EntityEdge.save = _wrap_save(EntityEdge.save)  # type: ignore[assignment]

    original_node_save = Neo4jEntityNodeOperations.save
    original_node_save_bulk = Neo4jEntityNodeOperations.save_bulk
    original_edge_save = Neo4jEntityEdgeOperations.save
    original_edge_save_bulk = Neo4jEntityEdgeOperations.save_bulk

    @wraps(original_node_save)
    async def node_save(
        self: Any,
        executor: Any,
        node: Any,
        tx: Any = None,
    ) -> Any:
        original = getattr(node, "attributes", None)
        if original:
            node.attributes = _sanitize(original)
            try:
                return await original_node_save(self, executor, node, tx)
            finally:
                node.attributes = original
        return await original_node_save(self, executor, node, tx)

    @wraps(original_node_save_bulk)
    async def node_save_bulk(
        self: Any,
        executor: Any,
        nodes: list[Any],
        tx: Any = None,
        batch_size: int = 100,
    ) -> Any:
        originals: list[tuple[Any, Any]] = []
        prepared: list[Any] = []
        for node in nodes:
            if isinstance(node, dict):
                prepared.append(_sanitize(node))
                continue
            original = getattr(node, "attributes", None)
            if original:
                originals.append((node, original))
                node.attributes = _sanitize(original)
            prepared.append(node)
        try:
            return await original_node_save_bulk(self, executor, prepared, tx, batch_size)
        finally:
            for node, original in originals:
                node.attributes = original

    @wraps(original_edge_save)
    async def edge_save(
        self: Any,
        executor: Any,
        edge: Any,
        tx: Any = None,
    ) -> Any:
        original = getattr(edge, "attributes", None)
        if original:
            edge.attributes = _sanitize(original)
            try:
                return await original_edge_save(self, executor, edge, tx)
            finally:
                edge.attributes = original
        return await original_edge_save(self, executor, edge, tx)

    @wraps(original_edge_save_bulk)
    async def edge_save_bulk(
        self: Any,
        executor: Any,
        edges: list[Any],
        tx: Any = None,
        batch_size: int = 100,
    ) -> Any:
        originals: list[tuple[Any, Any]] = []
        prepared: list[Any] = []
        for edge in edges:
            if isinstance(edge, dict):
                prepared.append(_sanitize(edge))
                continue
            original = getattr(edge, "attributes", None)
            if original:
                originals.append((edge, original))
                edge.attributes = _sanitize(original)
            prepared.append(edge)
        try:
            return await original_edge_save_bulk(self, executor, prepared, tx, batch_size)
        finally:
            for edge, original in originals:
                edge.attributes = original

    Neo4jEntityNodeOperations.save = node_save  # type: ignore[assignment]
    Neo4jEntityNodeOperations.save_bulk = node_save_bulk  # type: ignore[assignment]
    Neo4jEntityEdgeOperations.save = edge_save  # type: ignore[assignment]
    Neo4jEntityEdgeOperations.save_bulk = edge_save_bulk  # type: ignore[assignment]

    original_bulk_tx = bulk_utils.add_nodes_and_edges_bulk_tx

    @wraps(original_bulk_tx)
    async def sanitized_bulk_tx(
        tx: Any,
        episodic_nodes: list[Any],
        episodic_edges: list[Any],
        entity_nodes: list[Any],
        entity_edges: list[Any],
        embedder: Any,
        driver: Any,
    ) -> Any:
        for node in entity_nodes:
            original = getattr(node, "attributes", None)
            if original:
                node.attributes = _sanitize(original)
        for edge in entity_edges:
            original = getattr(edge, "attributes", None)
            if original:
                edge.attributes = _sanitize(original)
        return await original_bulk_tx(
            tx,
            episodic_nodes,
            episodic_edges,
            entity_nodes,
            entity_edges,
            embedder,
            driver,
        )

    bulk_utils.add_nodes_and_edges_bulk_tx = sanitized_bulk_tx  # type: ignore[assignment]
    _PATCHED = True
