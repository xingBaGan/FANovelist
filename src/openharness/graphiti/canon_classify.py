"""Classify novel snippets as entity vs background vs narrative element."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

CanonKind = Literal[
    "entity",  # named node (person, place, org)
    "narrative_element",  # role, skill, title — one label
    "background",  # goes on MajorCharacter.background, not a node
    "character_field",  # personality / current_status on existing character
    "skip",
]

_ENTITY_TYPE_HINTS: dict[str, str] = {
    "MajorCharacter": "具名主角/核心人物",
    "MinorCharacter": "次要具名人物",
    "RelatedPerson": "李默的母亲 等亲属",
    "Location": "江城、后山 等地名",
    "Organization": "天机阁 等门派组织",
    "Event": "有明确主体的情节事件（非丧父等背景短语）",
    "NarrativeElement": "外门弟子、基础剑法 等身份/技能/称谓",
}

_BACKGROUND_RE = re.compile(
    r"丧父|丧母|幼年|抚养|性格|坚毅|生于|去世|病逝|独自.*养|家庭|身世"
)
_NARRATIVE_RE = re.compile(
    r"外门|内门|弟子|剑法|功法|长老|掌门|学徒|境界|修为|比武|头衔"
)
_ORG_RE = re.compile(r"[\u4e00-\u9fff]{2,8}(?:阁|宗|派|教|会|军|山庄)$")
_PLACE_RE = re.compile(r"^[\u4e00-\u9fff]{2,6}(?:城|山|谷|岛|镇|村|洲|海)$")


@dataclass(frozen=True)
class CanonClassification:
    phrase: str
    kind: CanonKind
    entity_type: str | None = None
    target_field: str | None = None
    reason: str = ""


def classify_snippet(text: str, *, focus_character: str | None = None) -> list[CanonClassification]:
    """Rule-based canon classification for agent tooling (Chinese fiction)."""
    text = text.strip()
    if not text:
        return []

    results: list[CanonClassification] = []
    clauses = re.split(r"[。；;，,]", text)
    for clause in clauses:
        clause = clause.strip()
        if len(clause) < 2:
            continue
        results.append(_classify_clause(clause, focus_character=focus_character))

    if not results and text:
        results.append(_classify_clause(text, focus_character=focus_character))
    return results


def _classify_clause(clause: str, *, focus_character: str | None) -> CanonClassification:
    if _BACKGROUND_RE.search(clause):
        return CanonClassification(
            phrase=clause,
            kind="background",
            target_field="background",
            reason="身世/家庭/性格类叙述，写入人物 background，不建节点",
        )
    if "性格" in clause and focus_character:
        return CanonClassification(
            phrase=clause,
            kind="character_field",
            entity_type="MajorCharacter",
            target_field="personality",
            reason="性格描写写入 personality 或 background",
        )
    if _NARRATIVE_RE.search(clause):
        return CanonClassification(
            phrase=clause,
            kind="narrative_element",
            entity_type="NarrativeElement",
            reason="身份/技能/称谓，用 NarrativeElement 标签，勿用裸 Entity",
        )
    org_match = _ORG_RE.search(clause)
    if org_match:
        return CanonClassification(
            phrase=org_match.group(0),
            kind="entity",
            entity_type="Organization",
            reason="组织/门派专名",
        )
    if _PLACE_RE.search(clause):
        return CanonClassification(
            phrase=clause,
            kind="entity",
            entity_type="Location",
            reason="地名",
        )
    if focus_character and focus_character in clause:
        return CanonClassification(
            phrase=clause,
            kind="entity",
            entity_type="MajorCharacter",
            reason="涉及焦点人物",
        )
    return CanonClassification(
        phrase=clause,
        kind="entity",
        entity_type=None,
        reason="默认按具名实体处理；若仅为背景请改用 classify 后写 background",
    )


def classification_guide() -> dict[str, str]:
    """Ontology hints for agents."""
    return dict(_ENTITY_TYPE_HINTS)
