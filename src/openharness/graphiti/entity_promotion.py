"""Promote entities from abstract labels to richer types as canon grows."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

PromotionTarget = Literal["MinorCharacter", "MajorCharacter"]

_LADDER: dict[str, PromotionTarget | None] = {
    "NarrativeElement": "MinorCharacter",
    "MinorCharacter": "MajorCharacter",
    "RelatedPerson": None,
    "Location": None,
    "Organization": None,
    "Event": None,
    "MajorCharacter": None,
}

_NAMED_PERSON_RE = re.compile(r"^[\u4e00-\u9fff]{2,8}(?:长老|真人|先生|姑娘|公子)$")


@dataclass(frozen=True)
class EntitySnapshot:
    uuid: str
    name: str
    primary_label: str
    summary: str
    episode_mentions: int
    background: str | None
    scene_note: str | None
    element_note: str | None


@dataclass(frozen=True)
class PromotionDecision:
    uuid: str
    name: str
    from_label: str
    to_label: PromotionTarget
    reason: str


def suggest_promotion(entity: EntitySnapshot) -> PromotionDecision | None:
    """Return promotion if entity accumulated enough detail."""
    target = _LADDER.get(entity.primary_label)
    if target is None:
        return None

    if entity.primary_label == "NarrativeElement" and target == "MinorCharacter":
        if _should_promote_narrative_to_minor(entity):
            return PromotionDecision(
                uuid=entity.uuid,
                name=entity.name,
                from_label=entity.primary_label,
                to_label=target,
                reason=_minor_reason(entity),
            )
        return None

    if entity.primary_label == "MinorCharacter" and target == "MajorCharacter":
        if _should_promote_minor_to_major(entity):
            return PromotionDecision(
                uuid=entity.uuid,
                name=entity.name,
                from_label=entity.primary_label,
                to_label=target,
                reason=_major_reason(entity),
            )
        return None

    return None


def _should_promote_narrative_to_minor(e: EntitySnapshot) -> bool:
    if e.episode_mentions >= 2:
        return True
    if e.scene_note:
        return True
    if e.element_note and len(e.element_note) >= 12:
        return True
    if _NAMED_PERSON_RE.match(e.name):
        return True
    return len(e.summary) >= 40 and any(k in e.summary for k in ("遇见", "赠", "说", "道", "看"))


def _should_promote_minor_to_major(e: EntitySnapshot) -> bool:
    if e.background:
        return True
    if e.episode_mentions >= 3:
        return True
    return len(e.summary) >= 180


def _minor_reason(e: EntitySnapshot) -> str:
    if e.episode_mentions >= 2:
        return f"跨 {e.episode_mentions} 段出现"
    if _NAMED_PERSON_RE.match(e.name):
        return "具名角色"
    return "戏份/描述增多"


def _major_reason(e: EntitySnapshot) -> str:
    if e.background:
        return "已有背景综述"
    if e.episode_mentions >= 3:
        return f"跨 {e.episode_mentions} 段持续出场"
    return "summary 信息密度足够"
