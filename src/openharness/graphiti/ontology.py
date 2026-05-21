"""Novel-studio prescribed ontology (Graphiti entity_types)."""

from __future__ import annotations

from pydantic import BaseModel, Field

# Fields must not collide with EntityNode: uuid, name, group_id, labels, created_at,
# name_embedding, summary, attributes.


class MajorCharacter(BaseModel):
    """主角或段落主体；各字段均可空，只填本文对该人明确写到的内容。"""

    personality: str | None = Field(
        default=None,
        description="性格特点；如 坚毅。未写则留空。",
    )
    background: str | None = Field(
        default=None,
        description=(
            "身世背景综述（一段）：出生地、家庭、父母、成长、重大经历等合并叙述，"
            "与原文同语言。不要把丧父/母亲等拆成多个字段。"
        ),
    )
    appearance: str | None = Field(
        default=None,
        description="着装与佩戴：衣着、首饰、武器等。未提及则留空。",
    )
    current_status: str | None = Field(
        default=None,
        description="当前身份或处境，如 外门弟子、江湖崭露头角。",
    )


class MinorCharacter(BaseModel):
    """次要出场人物；仅记录本场戏份，无身世字段。"""

    scene_note: str | None = Field(
        default=None,
        description="本场做了什么/什么身份，与原文同语言。",
    )


class RelatedPerson(BaseModel):
    """亲属或关联人；只记与锚定角色的关系。"""

    anchor_name: str | None = Field(default=None, description="关联的主角名，如 李默")
    relationship: str | None = Field(default=None, description="关系，如 母亲、师父")
    role_note: str | None = Field(default=None, description="文中对该人的简述")


class Location(BaseModel):
    """地名、场所。"""

    place_note: str | None = Field(default=None, description="地点说明，与原文同语言")


class Event(BaseModel):
    """情节事件。"""

    event_note: str | None = Field(default=None, description="事件简述，与原文同语言")
    time_hint: str | None = Field(default=None, description="时间提示，若有")


class Organization(BaseModel):
    """门派、组织、势力。"""

    org_note: str | None = Field(default=None, description="组织说明，与原文同语言")


class NarrativeElement(BaseModel):
    """身份、技能、称谓等叙事要素（统一标签，替代裸 Entity）。"""

    element_kind: str | None = Field(
        default=None,
        description="role | skill | title | item — 如 外门弟子、基础剑法",
    )
    element_note: str | None = Field(
        default=None,
        description="与原文同语言的简短说明",
    )


NOVEL_ENTITY_TYPES: dict[str, type[BaseModel]] = {
    "MajorCharacter": MajorCharacter,
    "MinorCharacter": MinorCharacter,
    "RelatedPerson": RelatedPerson,
    "Location": Location,
    "Event": Event,
    "Organization": Organization,
    "NarrativeElement": NarrativeElement,
}

NOVEL_EXTRACTION_INSTRUCTIONS = """
语言：与原文同语言（中文 → 全中文）。
背景知识（勿建节点）：丧父、丧母、幼年、性格X、抚养、身世 等 → 只写入 MajorCharacter.background。
身份/技能/称谓：外门弟子、基础剑法、长老（非专名）→ NarrativeElement，禁止裸 Entity 标签。
具名人物/地名/门派：MajorCharacter / Location / Organization。
Event 仅用于有明确主体的事件；「丧父」不是 Event。
优先把「李默是外门弟子」写入李默的 current_status，而非单独「外门弟子」节点（除非需跨章追踪该称谓）。
生命周期：NarrativeElement 随多段文本可提升为 MinorCharacter，再提升为 MajorCharacter（ingest 后自动评估）。
所有字段可选；勿把 A 的背景写到 B。
""".strip()
