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
    desire: str | None = Field(
        default=None,
        description="人物当下的核心动机与欲望。仅在此处发生变动或被明确提及填写。",
    )
    fear: str | None = Field(
        default=None,
        description="人物的核心软肋与恐惧。",
    )
    emotional_state: str | None = Field(
        default=None,
        description="人物当前主导情绪，如：焦虑、愤怒、决绝、信任。仅在此处发生显著改变时填写。",
    )
    physical_status: str | None = Field(
        default=None,
        description="当前生命与物理肉体状态，如：健康、重伤、中毒、真气耗尽。",
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


class Belief(BaseModel):
    """认知或信念节点，用于刻画人物认知和信息差。"""

    content: str = Field(description="相信的具体信念或所知晓的事情，必须是具体的客观陈述。")
    is_misconception: bool = Field(default=False, description="是否为误解、误判或谎言。若为误解则为 True。")


class ChekhovsGun(BaseModel):
    """契诃夫之枪，指对剧情有关键推动作用的实体道具。"""

    nature: str = Field(description="道具的戏剧性本质，例如：伪造的信件、致命毒药。")
    state: str | None = Field(default=None, description="道具当前状态，如：未拆封、已被发现、已损坏。")


class DramaEvent(BaseModel):
    """戏剧事件，具有明确前因后果的事件。"""

    description: str = Field(description="动作或核心事件的极简叙述，如：出示伪造信、咸菜贿赂。")
    consequence: str | None = Field(default=None, description="该事件直接触发的表面后果。")


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
    "Belief": Belief,
    "ChekhovsGun": ChekhovsGun,
    "DramaEvent": DramaEvent,
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
    "BELIEVES": SocialRelation,
    "KNOWS_SECRET_OF": SocialRelation,
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
    "CONCEALS_FROM": EmotionalRelation,
    "SUSPECTS": EmotionalRelation,
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
    "ALTERS": ActionRelation,
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
_EVENT_LABELS = ["Event", "DramaEvent"]
_BELIEF_LABELS = ["Belief"]
_GUN_LABELS = ["ChekhovsGun"]

NOVEL_EDGE_TYPE_MAP: dict[tuple[str, str], list[str]] = {}

# Character to Character relations
for _c1 in _CHAR_LABELS:
    for _c2 in _CHAR_LABELS:
        NOVEL_EDGE_TYPE_MAP[(_c1, _c2)] = [
            "MASTER_OF", "DISCIPLE_OF", "ENEMY_OF", "ALLY_OF", "FRIEND_OF", "LEADER_OF",
            "PARENT_OF", "CHILD_OF", "SPOUSE_OF", "SIBLING_OF", "FATHER_OF", "MOTHER_OF", "WIFE_OF", "HUSBAND_OF",
            "LOVES", "HATES", "FEARS", "TRUSTS", "RESPECTS", "ADMIRES", "CONCEALS_FROM", "SUSPECTS", "KNOWS_SECRET_OF",
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

# Character to Belief relations
for _c in _CHAR_LABELS:
    for _b in _BELIEF_LABELS:
        NOVEL_EDGE_TYPE_MAP[(_c, _b)] = [
            "BELIEVES", "TRUSTS", "FEARS", "SUSPECTS", "HATES"
        ]

# Character to ChekhovsGun relations
for _c in _CHAR_LABELS:
    for _gun in _GUN_LABELS:
        NOVEL_EDGE_TYPE_MAP[(_c, _gun)] = [
            "OWNS", "HAS_ITEM", "STOLE_FROM", "GAVE_ITEM_TO", "ALTERS", "TRUSTS", "FEARS", "LOVES", "HATES", "SUSPECTS"
        ]

# NarrativeElement to Character relations
for _elem in _ELEMENT_LABELS:
    for _c in _CHAR_LABELS:
        NOVEL_EDGE_TYPE_MAP[(_elem, _c)] = [
            "TRANSFORMED_TO", "BECOMES", "EVOLVED_INTO", "CONSUMED_BY"
        ]

# ChekhovsGun to Character relations
for _gun in _GUN_LABELS:
    for _c in _CHAR_LABELS:
        NOVEL_EDGE_TYPE_MAP[(_gun, _c)] = [
            "TRANSFORMED_TO", "BECOMES", "EVOLVED_INTO", "CONSUMED_BY"
        ]

# Character to Event relations (restricted to semantically valid options)
for _c in _CHAR_LABELS:
    for _ev in _EVENT_LABELS:
        NOVEL_EDGE_TYPE_MAP[(_c, _ev)] = [
            "PARTICIPATED_IN", "INVOLVED_IN", "WITNESSED", "LOVES", "HATES", "FEARS"
        ]

# Event to Location relations (restricted to semantically valid options)
for _ev in _EVENT_LABELS:
    for _loc in _LOC_LABELS:
        NOVEL_EDGE_TYPE_MAP[(_ev, _loc)] = [
            "HAPPENED_AT", "LOCATED_IN"
        ]

# Event to NarrativeElement relations (restricted to semantically valid options)
for _ev in _EVENT_LABELS:
    for _elem in _ELEMENT_LABELS:
        NOVEL_EDGE_TYPE_MAP[(_ev, _elem)] = [
            "INVOLVED_IN", "CAUSED", "TRIGGERS", "LEADS_TO", "RESULTED_IN"
        ]

# Event to Belief relations
for _ev in _EVENT_LABELS:
    for _b in _BELIEF_LABELS:
        NOVEL_EDGE_TYPE_MAP[(_ev, _b)] = [
            "CAUSED", "TRIGGERS", "LEADS_TO", "RESULTED_IN", "ALTERS"
        ]

# Event to ChekhovsGun relations (restricted to semantically valid options)
for _ev in _EVENT_LABELS:
    for _gun in _GUN_LABELS:
        NOVEL_EDGE_TYPE_MAP[(_ev, _gun)] = [
            "INVOLVED_IN", "CAUSED", "TRIGGERS", "LEADS_TO", "RESULTED_IN", "ALTERS"
        ]

# Event to Event relations
for _ev1 in _EVENT_LABELS:
    for _ev2 in _EVENT_LABELS:
        NOVEL_EDGE_TYPE_MAP[(_ev1, _ev2)] = [
            "CAUSED", "TRIGGERS", "LEADS_TO", "RESULTED_IN", "ALTERS"
        ]

# Event to Character relations
for _ev in _EVENT_LABELS:
    for _c in _CHAR_LABELS:
        NOVEL_EDGE_TYPE_MAP[(_ev, _c)] = [
            "CAUSED", "TRIGGERS", "LEADS_TO", "RESULTED_IN", "ALTERS"
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
核心原则：仅在图谱中建模“戏剧冲突、信息差与核心因果链”相关的实体和关系。其余静态背景、大段景色、普通对话应从图谱剥离。

实体提取规范：
1. MajorCharacter / MinorCharacter / RelatedPerson：
   - 必须记录角色的心理与状态流转（仅在发生变化或被明确提及该状态时更新，未变动或未提及则留空）：
     * desire: 人物当下最迫切的欲望/主导动机。
     * fear: 软肋/最深层的恐惧。
     * emotional_state: 主导情绪，如：焦虑、愤怒、决绝、惊喜。
     * physical_status: 身体/生命状态，如：中毒、健康、气海破碎。
   - 勿创建关于角色的静态性格节点。性格特征 personality 和静态身世 background（如：生于江城、由母亲抚养长大）必须直接写入 MajorCharacter 的字段，绝不要建立成独立节点。
2. Belief (信念/认知)：用于刻画人物脑中的认知 and 信息差。
   - content: 必须是一个明确的客观陈述（如「李默是杀害王虎的凶手」，「咸菜盒子里藏有毒药」）。
   - is_misconception: 若文中明确该认知为误解、谣言、虚假信息或谎言，则标为 True。
3. ChekhovsGun (契诃夫之枪)：具有推动剧情发展、改变人物命运或引爆冲突的核心道具（如：伪造的信件、密室钥匙、致命毒药、长生剑）。
   - nature: 道具戏剧本质说明（如：能自证清白的物证）。
   - state: 道具当前的状态（如：已拆封、已损坏、下落不明）。
4. DramaEvent (戏剧事件)：指改变人物关系、心理或推动因果走向的核心动作（如：李默出示伪造信、咸菜制造误会、王虎遭下毒）。
5. Organization / Location / NarrativeElement:
   - 仅建模对故事走向有直接戏剧性作用的组织、地点或基础叙事要素。

关系提取与命名规则：
1. 信息差/认知链：
   - 人物 ─[BELIEVES]─► Belief (例如：李默 ─[BELIEVES]─► 「咸菜里有毒」)。
   - 人物 ─[CONCEALS_FROM]─► 人物 (例如：张三 ─[CONCEALS_FROM]─► 李默。在关系 fact 中写明隐瞒的具体内容或 Belief)。
   - 人物 ─[KNOWS_SECRET_OF]─► 人物 (例如：李默 ─[KNOWS_SECRET_OF]─► 张三。在 fact 中写明知道什么秘密)。
2. 情感/态度连线：
   - 人物 ─[LOVES / HATES / FEARS / TRUSTS / SUSPECTS / ADMIRES / RESPECTS]─► 人物 / 道具 (如：李默 ─[SUSPECTS]─► 张三)。
3. 因果/变化链：
   - 事件/信念 ─[CAUSED / TRIGGERS / LEADS_TO / RESULTED_IN / ALTERS]─► 事件/信念/人物/道具 (例如：「李默杀王虎」事件 ─[TRIGGERS]─► 「王家复仇」事件；「识破谎言」事件 ─[ALTERS]─► 「李默 ─[BELIEVES]─► X」信念)。
4. 拥有与物理：
   - 人物 ─[OWNS / HAS_ITEM]─► 契诃夫之枪/物品。
   - 实体 ─[LOCATED_AT / LOCATED_IN]─► 地点。
5. 动态关系命名：如果标准类型无法完全契合，LLM 可以自行发明合适的大写下划线关系（如 CHALLENGED_TO_DUEL）。
6. 时空与细节属性：任何关系（如爱恨、动作、学过技能等），凡是伴随程度、职位或特定时空上下文的，必须在关系的 fact 字符串中写明，以供系统自动提取属性。
""".strip()
