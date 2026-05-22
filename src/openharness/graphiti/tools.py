"""OpenHarness tools wrapping Graphiti SDK (MCP-parity names)."""

from __future__ import annotations

import json
from typing import Any

from pydantic import BaseModel, Field

from openharness.graphiti.canon_classify import classification_guide, classify_snippet
from openharness.graphiti.client import GraphitiClient
from openharness.graphiti.config import GraphitiSettings
from openharness.tools.base import BaseTool, ToolExecutionContext, ToolResult


class _GraphitiTool(BaseTool):
    def __init__(self, name: str, description: str, input_model: type[BaseModel]) -> None:
        self.name = name
        self.description = description
        self.input_model = input_model

    def _client(self, context: ToolExecutionContext) -> GraphitiClient:
        group_id = str(context.metadata.get("graphiti_group_id", "default"))
        return GraphitiClient(GraphitiSettings.from_env(group_id=group_id))


class GraphitiGetStatusInput(BaseModel):
    pass


class GraphitiGetStatusTool(_GraphitiTool):
    def __init__(self) -> None:
        super().__init__("get_status", "Check Graphiti / Neo4j connectivity.", GraphitiGetStatusInput)

    async def execute(self, arguments: GraphitiGetStatusInput, context: ToolExecutionContext) -> ToolResult:
        del arguments
        status = await self._client(context).get_status()
        return ToolResult(output=json.dumps({"connected": status.connected, "message": status.message}))


class GraphitiAddEpisodeInput(BaseModel):
    name: str
    episode_body: str
    source_description: str = "openharness"
    group_id: str | None = None


class GraphitiAddEpisodeTool(_GraphitiTool):
    def __init__(self) -> None:
        super().__init__(
            "add_episode",
            "Add an episode to the Graphiti knowledge graph.",
            GraphitiAddEpisodeInput,
        )

    async def execute(self, arguments: GraphitiAddEpisodeInput, context: ToolExecutionContext) -> ToolResult:
        client = self._client(context)
        if not client.available:
            return ToolResult(output="Graphiti not configured.", is_error=True)
        try:
            await client.connect()
            episode_uuid, edge_uuids = await client.add_episode(
                name=arguments.name,
                episode_body=arguments.episode_body,
                source_description=arguments.source_description,
                group_id=arguments.group_id,
            )
            return ToolResult(output=json.dumps({"episode_uuid": episode_uuid, "edge_uuids": edge_uuids}))
        except Exception as exc:  # noqa: BLE001
            return ToolResult(output=str(exc), is_error=True)


class ClassifyCanonSnippetInput(BaseModel):
    text: str = Field(description="Novel snippet to classify (Chinese)")
    focus_character: str | None = Field(
        default=None,
        description="Main character name for context, e.g. 李默",
    )


class ClassifyCanonSnippetTool(_GraphitiTool):
    def __init__(self) -> None:
        super().__init__(
            "classify_canon_snippet",
            "Classify text as entity, NarrativeElement, or background (not a node). "
            "Call before add_canon_episode when unsure.",
            ClassifyCanonSnippetInput,
        )

    async def execute(
        self,
        arguments: ClassifyCanonSnippetInput,
        context: ToolExecutionContext,
    ) -> ToolResult:
        del context
        items = [
            {
                "phrase": c.phrase,
                "kind": c.kind,
                "entity_type": c.entity_type,
                "target_field": c.target_field,
                "reason": c.reason,
            }
            for c in classify_snippet(arguments.text, focus_character=arguments.focus_character)
        ]
        return ToolResult(
            output=json.dumps(
                {"classifications": items, "entity_types": classification_guide()},
                ensure_ascii=False,
                indent=2,
            )
        )


class AddCanonEpisodeInput(BaseModel):
    name: str = Field(description="Episode id, e.g. ch01#paragraph_uid")
    text: str = Field(description="Source snippet in original language")
    focus_character: str | None = Field(default=None, description="POV character for background fields")
    source_description: str = Field(default="agent:canon", description="Provenance")
    group_id: str | None = None
    preclassified: bool = Field(
        default=False,
        description="Set true if agent already ran classify_canon_snippet",
    )


class AddCanonEpisodeTool(_GraphitiTool):
    def __init__(self) -> None:
        super().__init__(
            "add_canon_episode",
            "Ingest canon text with novel ontology (excludes bare Entity label). "
            "Use classify_canon_snippet first for ambiguous phrases like 丧父 or 外门弟子.",
            AddCanonEpisodeInput,
        )

    async def execute(self, arguments: AddCanonEpisodeInput, context: ToolExecutionContext) -> ToolResult:
        client = self._client(context)
        if not client.available:
            return ToolResult(output="Graphiti not configured.", is_error=True)
        hints = ""
        if not arguments.preclassified:
            items = classify_snippet(arguments.text, focus_character=arguments.focus_character)
            hints = "\n".join(f"- {i.phrase}: {i.kind} ({i.reason})" for i in items)
        body = arguments.text
        if hints:
            body = f"{arguments.text}\n\n[canon-hints]\n{hints}"
        try:
            await client.connect()
            episode_uuid, edge_uuids = await client.add_episode(
                name=arguments.name,
                episode_body=body,
                source_description=arguments.source_description,
                group_id=arguments.group_id,
            )
            return ToolResult(
                output=json.dumps(
                    {"episode_uuid": episode_uuid, "edge_uuids": edge_uuids},
                    ensure_ascii=False,
                )
            )
        except Exception as exc:  # noqa: BLE001
            return ToolResult(output=str(exc), is_error=True)


class PromoteCanonEntitiesInput(BaseModel):
    group_id: str | None = Field(default=None, description="Graph partition, default from env")


class PromoteCanonEntitiesTool(_GraphitiTool):
    def __init__(self) -> None:
        super().__init__(
            "promote_canon_entities",
            "Re-evaluate entity label promotions (NarrativeElement→MinorCharacter→MajorCharacter) "
            "after new chapters were ingested.",
            PromoteCanonEntitiesInput,
        )

    async def execute(
        self,
        arguments: PromoteCanonEntitiesInput,
        context: ToolExecutionContext,
    ) -> ToolResult:
        client = self._client(context)
        if not client.available:
            return ToolResult(output="Graphiti not configured.", is_error=True)
        gid = arguments.group_id or client._settings.group_id
        try:
            await client.connect()
            from openharness.graphiti.promotion_runner import run_entity_promotions

            applied = await run_entity_promotions(client, gid)
            payload = [
                {"name": p.name, "from": p.from_label, "to": p.to_label, "reason": p.reason}
                for p in applied
            ]
            return ToolResult(
                output=json.dumps({"promoted": len(applied), "items": payload}, ensure_ascii=False)
            )
        except Exception as exc:  # noqa: BLE001
            return ToolResult(output=str(exc), is_error=True)


class CheckCanonConflictsInput(BaseModel):
    source_path: str = Field(description="Path to draft markdown file")
    focus_character: str | None = Field(default=None, description="Focus character e.g. 李默")
    group_id: str | None = None


class CheckCanonConflictsTool(_GraphitiTool):
    def __init__(self) -> None:
        super().__init__(
            "check_canon_conflicts",
            "Pre-approve gate: detect critical canon conflicts. Returns blocked=true if must stop.",
            CheckCanonConflictsInput,
        )

    async def execute(
        self,
        arguments: CheckCanonConflictsInput,
        context: ToolExecutionContext,
    ) -> ToolResult:
        from pathlib import Path

        from openharness.graphiti.conflicts import check_submit_conflicts

        client = self._client(context)
        if not client.available:
            return ToolResult(output="Graphiti not configured.", is_error=True)
        text = Path(arguments.source_path).read_text(encoding="utf-8")
        gid = arguments.group_id or client._settings.group_id
        try:
            await client.connect()
            report = await check_submit_conflicts(
                client, text, focus_character=arguments.focus_character, group_id=gid
            )
            await client.close()
            payload = {
                "blocked": report.blocked,
                "critical": [{"category": c.category, "message": c.message} for c in report.critical],
                "warnings": [{"category": c.category, "message": c.message} for c in report.warnings],
            }
            return ToolResult(
                output=json.dumps(payload, ensure_ascii=False, indent=2),
                is_error=report.blocked,
            )
        except Exception as exc:  # noqa: BLE001
            return ToolResult(output=str(exc), is_error=True)


def _clean_val(val: Any) -> Any:
    if hasattr(val, "isoformat"):
        return val.isoformat()
    if isinstance(val, dict):
        return {k: _clean_val(v) for k, v in val.items()}
    if isinstance(val, list):
        return [_clean_val(v) for v in val]
    return val


class SearchFactsInput(BaseModel):
    query: str = Field(description="Semantic search query")
    group_id: str | None = Field(default=None, description="Graph partition")


class SearchFactsTool(_GraphitiTool):
    def __init__(self) -> None:
        super().__init__(
            "search_facts",
            "Search semantic facts inside the Graphiti knowledge graph using semantic query.",
            SearchFactsInput,
        )

    async def execute(self, arguments: SearchFactsInput, context: ToolExecutionContext) -> ToolResult:
        client = self._client(context)
        if not client.available:
            return ToolResult(output="Graphiti not configured.", is_error=True)
        gid = arguments.group_id or client._settings.group_id
        try:
            await client.connect()
            res = await client.search_facts(arguments.query, group_id=gid)
            cleaned = []
            for edge in res:
                d = edge.dict() if hasattr(edge, "dict") else edge.__dict__
                d.pop("fact_embedding", None)
                cleaned.append(_clean_val(d))
            await client.close()
            return ToolResult(output=json.dumps(cleaned, ensure_ascii=False, indent=2))
        except Exception as exc:
            return ToolResult(output=str(exc), is_error=True)


class RemoveEpisodeInput(BaseModel):
    episode_uuid: str = Field(description="The UUID of the episode to remove")


class RemoveEpisodeTool(_GraphitiTool):
    def __init__(self) -> None:
        super().__init__(
            "remove_episode",
            "Remove an episode from the Graphiti knowledge graph by its UUID.",
            RemoveEpisodeInput,
        )

    async def execute(self, arguments: RemoveEpisodeInput, context: ToolExecutionContext) -> ToolResult:
        client = self._client(context)
        if not client.available:
            return ToolResult(output="Graphiti not configured.", is_error=True)
        try:
            await client.connect()
            await client.remove_episode(arguments.episode_uuid)
            await client.close()
            return ToolResult(
                output=json.dumps({"success": True, "message": f"Episode {arguments.episode_uuid} removed."})
            )
        except Exception as exc:
            return ToolResult(output=str(exc), is_error=True)


class DeleteEntityEdgeInput(BaseModel):
    edge_uuid: str = Field(description="The UUID of the relationship edge to delete")


class DeleteEntityEdgeTool(_GraphitiTool):
    def __init__(self) -> None:
        super().__init__(
            "delete_entity_edge",
            "Delete a specific relationship/edge from the graph by its UUID.",
            DeleteEntityEdgeInput,
        )

    async def execute(self, arguments: DeleteEntityEdgeInput, context: ToolExecutionContext) -> ToolResult:
        client = self._client(context)
        if not client.available:
            return ToolResult(output="Graphiti not configured.", is_error=True)
        try:
            await client.connect()
            await client.delete_entity_edge(arguments.edge_uuid)
            await client.close()
            return ToolResult(
                output=json.dumps({"success": True, "message": f"Edge {arguments.edge_uuid} deleted."})
            )
        except Exception as exc:
            return ToolResult(output=str(exc), is_error=True)


class TraceEntityOriginsInput(BaseModel):
    entity_name: str = Field(description="Entity name to trace, e.g. 李默")
    group_id: str | None = Field(default=None, description="Graph partition")


class TraceEntityOriginsTool(_GraphitiTool):
    def __init__(self) -> None:
        super().__init__(
            "trace_entity_origins",
            "Find all episodic source paragraphs mentioning the given entity.",
            TraceEntityOriginsInput,
        )

    async def execute(self, arguments: TraceEntityOriginsInput, context: ToolExecutionContext) -> ToolResult:
        client = self._client(context)
        if not client.available:
            return ToolResult(output="Graphiti not configured.", is_error=True)
        gid = arguments.group_id or client._settings.group_id
        try:
            await client.connect()
            res = await client.trace_entity_origins(arguments.entity_name, group_id=gid)
            await client.close()
            return ToolResult(output=json.dumps(res, ensure_ascii=False, indent=2))
        except Exception as exc:
            return ToolResult(output=str(exc), is_error=True)


class GetStoryTimelineInput(BaseModel):
    focus_entity: str | None = Field(default=None, description="Focus character or entity name to filter the timeline")
    group_id: str | None = Field(default=None, description="Graph partition")


class GetStoryTimelineTool(_GraphitiTool):
    def __init__(self) -> None:
        super().__init__(
            "get_story_timeline",
            "Get a chronological story timeline, optionally filtered by a focus entity.",
            GetStoryTimelineInput,
        )

    async def execute(self, arguments: GetStoryTimelineInput, context: ToolExecutionContext) -> ToolResult:
        client = self._client(context)
        if not client.available:
            return ToolResult(output="Graphiti not configured.", is_error=True)
        gid = arguments.group_id or client._settings.group_id
        try:
            await client.connect()
            res = await client.get_story_timeline(focus_entity=arguments.focus_entity, group_id=gid)
            await client.close()
            return ToolResult(output=json.dumps(res, ensure_ascii=False, indent=2))
        except Exception as exc:
            return ToolResult(output=str(exc), is_error=True)


class GetFactionsOutlineInput(BaseModel):
    group_id: str | None = Field(default=None, description="Graph partition")


class GetFactionsOutlineTool(_GraphitiTool):
    def __init__(self) -> None:
        super().__init__(
            "get_factions_outline",
            "Get an outline of factions/communities and their member entities.",
            GetFactionsOutlineInput,
        )

    async def execute(self, arguments: GetFactionsOutlineInput, context: ToolExecutionContext) -> ToolResult:
        client = self._client(context)
        if not client.available:
            return ToolResult(output="Graphiti not configured.", is_error=True)
        gid = arguments.group_id or client._settings.group_id
        try:
            await client.connect()
            res = await client.get_factions_outline(group_id=gid)
            await client.close()
            return ToolResult(output=json.dumps(res, ensure_ascii=False, indent=2))
        except Exception as exc:
            return ToolResult(output=str(exc), is_error=True)


class GetCanonStateInput(BaseModel):
    target_time: str = Field(description="Target ISO-8601 time string, e.g. '2020-12-01T00:00:00Z'")
    focus_entity: str | None = Field(default=None, description="Focus character or entity name to filter active relationships")
    group_id: str | None = Field(default=None, description="Graph partition")


class GetCanonStateTool(_GraphitiTool):
    def __init__(self) -> None:
        super().__init__(
            "get_canon_state",
            "Get active semantic relationships (canon state) at a specific point in time.",
            GetCanonStateInput,
        )

    async def execute(self, arguments: GetCanonStateInput, context: ToolExecutionContext) -> ToolResult:
        client = self._client(context)
        if not client.available:
            return ToolResult(output="Graphiti not configured.", is_error=True)
        gid = arguments.group_id or client._settings.group_id
        try:
            await client.connect()
            res = await client.get_historical_relationships(
                target_time=arguments.target_time,
                focus_entity=arguments.focus_entity,
                group_id=gid,
            )
            await client.close()
            return ToolResult(output=json.dumps(res, ensure_ascii=False, indent=2))
        except Exception as exc:
            return ToolResult(output=str(exc), is_error=True)


def graphiti_tools() -> list[BaseTool]:
    return [
        GraphitiGetStatusTool(),
        GraphitiAddEpisodeTool(),
        ClassifyCanonSnippetTool(),
        AddCanonEpisodeTool(),
        PromoteCanonEntitiesTool(),
        CheckCanonConflictsTool(),
        SearchFactsTool(),
        RemoveEpisodeTool(),
        DeleteEntityEdgeTool(),
        TraceEntityOriginsTool(),
        GetStoryTimelineTool(),
        GetFactionsOutlineTool(),
        GetCanonStateTool(),
    ]
