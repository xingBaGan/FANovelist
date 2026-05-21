"""Setting conflict detection for novel canon (v1 heuristics)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

from openharness.graphiti.client import GraphitiClient

ConflictSeverity = Literal["critical", "warning"]


@dataclass(frozen=True)
class Conflict:
    severity: ConflictSeverity
    category: str
    message: str
    fact_uuids: tuple[str, ...] = ()


@dataclass(frozen=True)
class ConflictReport:
    conflicts: tuple[Conflict, ...]
    blocked: bool

    @property
    def critical(self) -> list[Conflict]:
        return [c for c in self.conflicts if c.severity == "critical"]

    @property
    def warnings(self) -> list[Conflict]:
        return [c for c in self.conflicts if c.severity == "warning"]


_BIRTH_RE = re.compile(r"(生于|出生于|出生地|born in)\s*([\u4e00-\u9fffA-Za-z]{1,8})")
_NAME_TAIL_RE = re.compile(r"([\u4e00-\u9fff]{2,6})\s*$")


def _subject_from_fact(text: str, match: re.Match[str]) -> str:
    prefix = text[: match.start()].strip()
    tail = _NAME_TAIL_RE.search(prefix)
    return tail.group(1) if tail else (prefix[-4:] if prefix else "unknown")


def _birth_places_from_facts(facts: list[object]) -> dict[str, set[str]]:
    """Map subject name -> set of birth place strings from fact text."""
    by_subject: dict[str, set[str]] = {}
    uuids_by_subject: dict[str, list[str]] = {}
    for fact in facts:
        text = str(getattr(fact, "fact", fact))
        uuid = str(getattr(fact, "uuid", "") or "")
        for match in _BIRTH_RE.finditer(text):
            subject = _subject_from_fact(text, match)
            place = match.group(2)
            by_subject.setdefault(subject, set()).add(place)
            if uuid:
                uuids_by_subject.setdefault(subject, []).append(uuid)
    return by_subject, uuids_by_subject


def detect_conflicts_from_facts(facts: list[object]) -> list[Conflict]:
    """Offline-friendly conflict rules on search fact objects."""
    by_subject, uuids_by_subject = _birth_places_from_facts(facts)
    conflicts: list[Conflict] = []
    for subject, places in by_subject.items():
        if len(places) > 1:
            conflicts.append(
                Conflict(
                    severity="critical",
                    category="identity",
                    message=f"出生地冲突 ({subject}): {', '.join(sorted(places))}",
                    fact_uuids=tuple(uuids_by_subject.get(subject, ())),
                )
            )
    return conflicts


def build_conflict_report(conflicts: list[Conflict]) -> ConflictReport:
    blocked = any(c.severity == "critical" for c in conflicts)
    return ConflictReport(conflicts=tuple(conflicts), blocked=blocked)


async def detect_setting_conflicts(
    client: GraphitiClient,
    query: str,
    *,
    group_id: str | None = None,
) -> ConflictReport:
    """Search graph facts and apply v1 contradiction heuristics."""
    if not client.available:
        return ConflictReport(conflicts=(), blocked=False)
    await client._ensure_connected()
    try:
        facts = await client.search_facts(query, group_id=group_id)
    except Exception:  # noqa: BLE001
        return ConflictReport(conflicts=(), blocked=False)
    return build_conflict_report(detect_conflicts_from_facts(list(facts)))


async def check_submit_conflicts(
    client: GraphitiClient,
    draft_text: str,
    *,
    focus_character: str | None = None,
    group_id: str | None = None,
) -> ConflictReport:
    """Pre-approve gate: check canon graph for conflicts relevant to draft."""
    query = focus_character or _guess_focus_character(draft_text) or "主角"
    return await detect_setting_conflicts(client, query, group_id=group_id)


def _guess_focus_character(text: str) -> str | None:
    """Pick the most frequent 2-3 char name-like token in Chinese prose."""
    names = re.findall(r"[\u4e00-\u9fff]{2,3}", text)
    if not names:
        return None
    counts: dict[str, int] = {}
    for n in names:
        counts[n] = counts.get(n, 0) + 1
    return max(counts, key=counts.get)
