"""OpenHarness tools wrapping Graphiti SDK (MCP-parity names)."""

from __future__ import annotations

import json

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


def graphiti_tools() -> list[BaseTool]:
    return [
        GraphitiGetStatusTool(),
        GraphitiAddEpisodeTool(),
        ClassifyCanonSnippetTool(),
        AddCanonEpisodeTool(),
        PromoteCanonEntitiesTool(),
    ]
