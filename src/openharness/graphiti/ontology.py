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
        description="role | skill | title | item — 如 外门弟子、基础剑法、长生剑",
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


class SocialRelation(BaseModel):
    """表示社会、组织、身份、同盟或敌对等关系。"""

    role: str | None = Field(
        default=None,
        description="具体的职位、称号或身份，例如：外门弟子、内门弟子、长老、盟友、仇敌、下属、掌门",
    )
    detail: str | None = Field(
        default=None,
        description="关系的详细描述或背景说明，如同盟契约、敌对原因",
    )


class KinshipRelation(BaseModel):
    """表示人物之间的血缘或婚姻等家庭关系。"""

    kinship: str | None = Field(
        default=None,
        description="具体的称谓或亲属类型，例如：父亲、母亲、丈夫、妻子、兄弟、姐妹、师徒",
    )
    detail: str | None = Field(
        default=None,
        description="补充说明，如养子、前妻等",
    )


class EmotionalRelation(BaseModel):
    """表示人物之间或人物对事物的主观情感、心理态度。"""

    emotion: str | None = Field(
        default=None,
        description="具体的情感或态度，例如：爱慕、极度仇恨、敬畏、信任、崇拜",
    )
    detail: str | None = Field(
        default=None,
        description="情感产生的原因或背景事件",
    )


class ActionRelation(BaseModel):
    """表示具体动作、突发事件、单次或重复的交互行为。"""

    action_type: str | None = Field(
        default=None,
        description="具体的动作或行为，例如：杀死、救助、击伤、赠送、背叛、学过",
    )
    context: str | None = Field(
        default=None,
        description="动作发生的背景、起因、时空（时间/地点）等详细信息",
    )


class PhysicalRelation(BaseModel):
    """表示物理空间、位置分布或对物品的拥有/控制关系。"""

    relation_kind: str | None = Field(
        default=None,
        description="具体的物理或拥有关系，例如：拥有、在其内部、在其上方",
    )
    detail: str | None = Field(
        default=None,
        description="补充细节，如临时保管、佩戴、掌握",
    )


NOVEL_EDGE_TYPES: dict[str, type[BaseModel]] = {
    # SocialRelation
    "BELONGS_TO": SocialRelation,
    "MEMBER_OF": SocialRelation,
    "MASTER_OF": SocialRelation,
    "DISCIPLE_OF": SocialRelation,
    "ENEMY_OF": SocialRelation,
    "ALLY_OF": SocialRelation,
    "FRIEND_OF": SocialRelation,
    "WORKED_AT": SocialRelation,
    "LEADER_OF": SocialRelation,
    # KinshipRelation
    "PARENT_OF": KinshipRelation,
    "CHILD_OF": KinshipRelation,
    "SPOUSE_OF": KinshipRelation,
    "SIBLING_OF": KinshipRelation,
    "FATHER_OF": KinshipRelation,
    "MOTHER_OF": KinshipRelation,
    "WIFE_OF": KinshipRelation,
    "HUSBAND_OF": KinshipRelation,
    # EmotionalRelation
    "LOVES": EmotionalRelation,
    "HATES": EmotionalRelation,
    "FEARS": EmotionalRelation,
    "TRUSTS": EmotionalRelation,
    "RESPECTS": EmotionalRelation,
    "ADMIRES": EmotionalRelation,
    # ActionRelation
    "KILLED": ActionRelation,
    "SAVED": ActionRelation,
    "HELPED": ActionRelation,
    "ATTACKED": ActionRelation,
    "DEFEATED": ActionRelation,
    "BETRAYED": ActionRelation,
    "GAVE_ITEM_TO": ActionRelation,
    "STOLE_FROM": ActionRelation,
    "STUDIED": ActionRelation,
    "LEARNED": ActionRelation,
    "PARTICIPATED_IN": ActionRelation,
    "INVOLVED_IN": ActionRelation,
    "WITNESSED": ActionRelation,
    "CAUSED": ActionRelation,
    "TRIGGERS": ActionRelation,
    "LEADS_TO": ActionRelation,
    "RESULTED_IN": ActionRelation,
    "TRANSFORMED_TO": ActionRelation,
    "BECOMES": ActionRelation,
    "EVOLVED_INTO": ActionRelation,
    "SPENT": ActionRelation,
    "CONSUMED": ActionRelation,
    "CONSUMED_BY": ActionRelation,
    # PhysicalRelation
    "OWNS": PhysicalRelation,
    "HAS_ITEM": PhysicalRelation,
    "LOCATED_AT": PhysicalRelation,
    "LOCATED_IN": PhysicalRelation,
    "ABOVE": PhysicalRelation,
    "BELOW": PhysicalRelation,
    "INSIDE": PhysicalRelation,
    "HAPPENED_AT": PhysicalRelation,
}

_CHAR_LABELS = ["MajorCharacter", "MinorCharacter", "RelatedPerson"]
_ORG_LABELS = ["Organization"]
_LOC_LABELS = ["Location"]
_ELEMENT_LABELS = ["NarrativeElement"]
_EVENT_LABELS = ["Event"]

NOVEL_EDGE_TYPE_MAP: dict[tuple[str, str], list[str]] = {}

# Character to Character relations
for _c1 in _CHAR_LABELS:
    for _c2 in _CHAR_LABELS:
        NOVEL_EDGE_TYPE_MAP[(_c1, _c2)] = [
            "MASTER_OF", "DISCIPLE_OF", "ENEMY_OF", "ALLY_OF", "FRIEND_OF", "LEADER_OF",
            "PARENT_OF", "CHILD_OF", "SPOUSE_OF", "SIBLING_OF", "FATHER_OF", "MOTHER_OF", "WIFE_OF", "HUSBAND_OF",
            "LOVES", "HATES", "FEARS", "TRUSTS", "RESPECTS", "ADMIRES",
            "KILLED", "SAVED", "HELPED", "ATTACKED", "DEFEATED", "BETRAYED", "GAVE_ITEM_TO", "STOLE_FROM", "STUDIED", "LEARNED",
            "TRANSFORMED_TO", "BECOMES"
        ]

# Character to Organization relations
for _c in _CHAR_LABELS:
    for _org in _ORG_LABELS:
        NOVEL_EDGE_TYPE_MAP[(_c, _org)] = [
            "BELONGS_TO", "MEMBER_OF", "WORKED_AT", "LEADER_OF", "ENEMY_OF", "ALLY_OF"
        ]

# Character to Location relations
for _c in _CHAR_LABELS:
    for _loc in _LOC_LABELS:
        NOVEL_EDGE_TYPE_MAP[(_c, _loc)] = [
            "LOCATED_AT", "LOCATED_IN", "ABOVE", "BELOW", "INSIDE"
        ]

# Character to NarrativeElement (items, skills, resources) relations
for _c in _CHAR_LABELS:
    for _elem in _ELEMENT_LABELS:
        NOVEL_EDGE_TYPE_MAP[(_c, _elem)] = [
            "OWNS", "HAS_ITEM", "STUDIED", "LEARNED", "TRANSFORMED_TO", "BECOMES", "EVOLVED_INTO",
            "SPENT", "CONSUMED", "CONSUMED_BY"
        ]

# NarrativeElement to Character relations
for _elem in _ELEMENT_LABELS:
    for _c in _CHAR_LABELS:
        NOVEL_EDGE_TYPE_MAP[(_elem, _c)] = [
            "TRANSFORMED_TO", "BECOMES", "EVOLVED_INTO", "CONSUMED_BY"
        ]

# Character to Event relations
for _c in _CHAR_LABELS:
    for _ev in _EVENT_LABELS:
        NOVEL_EDGE_TYPE_MAP[(_c, _ev)] = [
            "PARTICIPATED_IN", "INVOLVED_IN", "WITNESSED", "KILLED", "SAVED", "DEFEATED", "LOVES", "HATES"
        ]

# Event to Location relations
for _ev in _EVENT_LABELS:
    for _loc in _LOC_LABELS:
        NOVEL_EDGE_TYPE_MAP[(_ev, _loc)] = [
            "LOCATED_AT", "LOCATED_IN", "HAPPENED_AT", "INSIDE"
        ]

# Event to NarrativeElement relations
for _ev in _EVENT_LABELS:
    for _elem in _ELEMENT_LABELS:
        NOVEL_EDGE_TYPE_MAP[(_ev, _elem)] = [
            "HAS_ITEM", "OWNS", "INVOLVED_IN", "CAUSED", "TRIGGERS", "LEADS_TO", "RESULTED_IN"
        ]

# Event to Event relations
for _ev1 in _EVENT_LABELS:
    for _ev2 in _EVENT_LABELS:
        NOVEL_EDGE_TYPE_MAP[(_ev1, _ev2)] = [
            "CAUSED", "TRIGGERS", "LEADS_TO", "RESULTED_IN"
        ]

# Event to Character relations
for _ev in _EVENT_LABELS:
    for _c in _CHAR_LABELS:
        NOVEL_EDGE_TYPE_MAP[(_ev, _c)] = [
            "CAUSED", "TRIGGERS", "LEADS_TO", "RESULTED_IN"
        ]

# Event to Organization relations
for _ev in _EVENT_LABELS:
    for _org in _ORG_LABELS:
        NOVEL_EDGE_TYPE_MAP[(_ev, _org)] = [
            "CAUSED", "TRIGGERS", "LEADS_TO", "RESULTED_IN"
        ]

# Organization to Location relations
for _org in _ORG_LABELS:
    for _loc in _LOC_LABELS:
        NOVEL_EDGE_TYPE_MAP[(_org, _loc)] = [
            "LOCATED_AT", "LOCATED_IN", "INSIDE"
        ]

# Organization to Organization relations
for _org1 in _ORG_LABELS:
    for _org2 in _ORG_LABELS:
        NOVEL_EDGE_TYPE_MAP[(_org1, _org2)] = [
            "TRANSFORMED_TO", "BECOMES", "EVOLVED_INTO", "ENEMY_OF", "ALLY_OF"
        ]

# NarrativeElement to NarrativeElement relations
for _elem1 in _ELEMENT_LABELS:
    for _elem2 in _ELEMENT_LABELS:
        NOVEL_EDGE_TYPE_MAP[(_elem1, _elem2)] = [
            "TRANSFORMED_TO", "BECOMES", "EVOLVED_INTO"
        ]

# Location to Location relations
for _loc1 in _LOC_LABELS:
    for _loc2 in _LOC_LABELS:
        NOVEL_EDGE_TYPE_MAP[(_loc1, _loc2)] = [
            "LOCATED_AT", "LOCATED_IN", "ABOVE", "BELOW", "INSIDE"
        ]

NOVEL_EXTRACTION_INSTRUCTIONS = """
语言：与原文同语言（中文 → 全中文）。
背景知识（勿建节点）：丧父、丧母、幼年、性格X、抚养、身世 等 → 只写入 MajorCharacter.background。
身份/技能/称谓/物品/资源：外门弟子、基础剑法、长生剑、贡献点、灵石、长老（非专名）→ NarrativeElement，禁止裸 Entity 标签。
具名人物/地名/门派：MajorCharacter / Location / Organization。
怪物、妖兽、具名敌人（如 赤炼毒蛇）：MinorCharacter，禁止标为 NarrativeElement。
Event 仅用于有明确主体的事件；「丧父」不是 Event。
优先把「李默是外门弟子」写入李默的 current_status，而非单独「外门弟子」节点（除非需跨章追踪该称谓）。
生命周期：NarrativeElement 随多段文本可提升为 MinorCharacter，再提升为 MajorCharacter（ingest 后自动评估）。
所有字段可选；勿把 A 的背景写到 B。

关系提取与命名规则：
1. 优先使用已定义的标准关系类型：
   - 社交/同盟：BELONGS_TO, MEMBER_OF, MASTER_OF (师父/主子), DISCIPLE_OF (徒弟/下属), ENEMY_OF, ALLY_OF, FRIEND_OF, WORKED_AT, LEADER_OF
   - 亲属血缘：PARENT_OF, CHILD_OF, SPOUSE_OF, SIBLING_OF, FATHER_OF, MOTHER_OF, WIFE_OF, HUSBAND_OF
   - 情感态度：LOVES, HATES, FEARS, TRUSTS, RESPECTS, ADMIRES
   - 行为动作：KILLED, SAVED, HELPED, ATTACKED, DEFEATED, BETRAYED, GAVE_ITEM_TO, STOLE_FROM, STUDIED, LEARNED, PARTICIPATED_IN, INVOLVED_IN, WITNESSED, SPENT, CONSUMED, CONSUMED_BY
   - 因果逻辑：CAUSED, TRIGGERS, LEADS_TO, RESULTED_IN
   - 状态转化：TRANSFORMED_TO, BECOMES, EVOLVED_INTO
   - 物理/拥有：OWNS, HAS_ITEM, LOCATED_AT, LOCATED_IN, ABOVE, BELOW, INSIDE, HAPPENED_AT
2. 动态关系命名：如果标准类型无法完全契合，LLM 可以自行发明合适的大写下划线关系（如 CHALLENGED_TO_DUEL）。
3. 时空与细节属性：任何关系（如爱恨、动作、学过技能等），凡是伴随程度、职位或特定时空上下文的，必须在关系的 fact 字符串中写明（如「李默大乾历100年在江城击杀了赤炼毒蛇」，「李默极度怨恨张三」，「李默是天机阁的外门弟子」），以供系统自动提取属性。
4. 时空与事件建模规范：
   - 拥有物品或技能：必须将物品/技能抽取为独立的 NarrativeElement，并用 OWNS 或 HAS_ITEM 等关系连接（如：李默 ─[HAS_ITEM]─► 长生剑）。千万不要把物品当作地点或只写在边属性里。
   - 资源消耗与获取：涉及虚拟资源的消耗或获取（如花费贡献点、获取灵石等），必须将该资源（如 贡献点、灵石）抽取为独立的 NarrativeElement 节点，并通过关系（如 SPENT, CONSUMED, OWNS, HAS_ITEM 等）进行连接，且在关系的 fact 属性中写明具体的变化和数量（如：「李默耗费了五百贡献点」）。
   - 描述一个人正在干某事或干过某事：通过 `STUDIED` / `LEARNED` 等动作关系连至技能/事物（如：李默 ─[STUDIED]─► 长生诀）。
   - 战斗击杀（必提，与武器/技能并列）：文中出现击杀/斩杀/杀死/击败/诛灭等，必须将受害者建为 MinorCharacter，并建立施害者 ─[KILLED 或 DEFEATED]─► 受害者（如：李默 ─[KILLED]─► 赤炼毒蛇）；不得只提取 HAS_ITEM / STUDIED 而漏掉击杀。
   - 描述一个人在某个时间、某个地方做了某件复杂的动作/事件：实例化一个 `Event` 节点（如：李默江城杀蛇），让人物通过 `PARTICIPATED_IN` 或 `INVOLVED_IN` 连接到该 `Event` 节点，并让 `Event` 节点通过 `HAPPENED_AT` / `LOCATED_IN` 连接至 `Location` 节点，且在 `Event` 和边上描述时间点（如 `time_hint` 属性）。
5. 因果与转化（时空流转）规范：
   - 因果（情节）：通过 `Event` ─[CAUSED / TRIGGERS / LEADS_TO / RESULTED_IN]─► `Event` 建立情节逻辑链条（如：“李默杀死王虎”事件 ─[CAUSED]─► “王虎之子复仇”事件）。
   - 转化（人物弧光与状态流转）：
     - 身份与心态转化：人物 ─[TRANSFORMED_TO / BECOMES]─► 叙事要素（NarrativeElement）表示状态/称谓/身份演变（如：李默 ─[BECOMES]─► 恶龙）。
     - 关系与情感转化：在不同时间点建立不同的关系边（如在 t1 建立 LOVES，在 t2 建立 HATES/ENEMY_OF），由 Graphiti 基于时间线（valid_at）进行多层关系演变分析。
     - 事物/技能/组织转化：事物 ─[EVOLVED_INTO / TRANSFORMED_TO]─► 事物（如：“长生诀” ─[EVOLVED_INTO]─► “长生仙经”；“铁剑门” ─[TRANSFORMED_TO]─► “天剑宗”）。
6. 规范实体命名与提示词引导（[canon-hints]）：
   - 如果文本最后附带有 `[canon-hints]` 段落，提取时必须严格遵循其中指定的实体名称、标签和关系说明。
   - 必须完全使用 `[canon-hints]` 中给出的实体名称（例如，若提示为「雷暴义眼」，提取的实体名称必须为「雷暴义眼」，绝不能提取为「军用级雷暴义眼」等其他变体；若提示为「苏默」，绝不能提取为「拾荒者苏默」）。
   - 必须按照 `[canon-hints]` 中指示的关系逻辑进行提取，确保边关系和方向符合物理与逻辑常识（例如，应为：林德 ─[SPENT]─► 信用点，以及 林德 ─[HAS_ITEM/OWNS]─► 雷暴义眼，绝不能将关系反向或将雷暴义眼错当作 SPENT 的目标）。
""".strip()


