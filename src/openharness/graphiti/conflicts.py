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


_BIRTH_RE = re.compile(r"(生于|出生于|出生在|生在|出生地|born in)\s*([\u4e00-\u9fffA-Za-z]{1,8})")
_NAME_TAIL_RE = re.compile(r"([\u4e00-\u9fff]{2,6}|[A-Za-z]+(?:\s+[A-Za-z]+)?)\s*$")

# Relationship patterns
_RELATION_ZH_RE = re.compile(
    r"的(父亲|母亲|爸爸|妈妈|妻子|丈夫|师父|徒弟|弟子)\s*(是|为)\s*([\u4e00-\u9fffA-Za-z]{2,8})"
)
_RELATION_ZH_INV_RE = re.compile(
    r"\s*(是|为)\s*([\u4e00-\u9fffA-Za-z]{2,8})的(父亲|母亲|爸爸|妈妈|妻子|丈夫|师父|徒弟|弟子)"
)
_RELATION_EN_RE = re.compile(
    r"\s*(father|mother|husband|wife|master|disciple)\s*(is|was)\s*([\u4e00-\u9fffA-Za-z]+(?:\s+[A-Za-z]+)?)"
)
_RELATION_OF_EN_RE = re.compile(
    r"\s*(is|was)\s+the\s+(father|mother|husband|wife|master|disciple)\s+of\s+([\u4e00-\u9fffA-Za-z]+(?:\s+[A-Za-z]+)?)"
)

_RELATION_MAP = {
    "父亲": "father",
    "爸爸": "father",
    "father": "father",
    "母亲": "mother",
    "妈妈": "mother",
    "mother": "mother",
    "丈夫": "husband",
    "husband": "husband",
    "妻子": "wife",
    "wife": "wife",
    "师父": "master",
    "master": "master",
    "徒弟": "disciple",
    "弟子": "disciple",
    "disciple": "disciple",
}

SINGLE_VALUED_RELATIONS = {"father", "mother", "husband", "wife"}

# Timeline/Death patterns
_DEATH_RE = re.compile(r"\s*(去世|战死|身亡|逝世|殒命|已死|牺牲|died|passed\s+away|killed)")
_ACTIVE_RE = re.compile(
    r"\s*(目前|现在|正在|生活在|居住在|活着|当前|currently|now|actively|is\s+alive|lives\s+in|resides\s+at)"
)

# Year patterns
_BIRTH_YEAR_RE = re.compile(r"(生于|出生于|born in)\s*(?:大乾历|公元|公元前|year)?\s*(\d+)")
_DEATH_YEAR_RE = re.compile(r"(死于|去世于|战死于|died in)\s*(?:大乾历|公元|公元前|year)?\s*(\d+)")

# Delimiter pattern for splitting the subject from active phrases/verbs
_DELIMITERS_RE = re.compile(
    r"(?:的|是|为|在|与|和|目前|现在|正在|出生|生于|死于|去世|战死|牺牲|\b's\b|\bis\b|\bwas\b|\bdied\b|\bborn\b)"
)


def _subject_from_fact(text: str, match: re.Match[str] | None = None) -> str:
    text_clean = text.strip()
    parts = _DELIMITERS_RE.split(text_clean)
    if parts and parts[0].strip():
        subject = parts[0].strip()
        if subject.endswith("'s"):
            subject = subject[:-2].strip()
        elif subject.endswith("'"):
            subject = subject[:-1].strip()
        if 2 <= len(subject) <= 30:
            return subject

    if match:
        prefix = text[: match.start()].strip()
        if prefix.endswith("'s"):
            prefix = prefix[:-2].strip()
        elif prefix.endswith("'"):
            prefix = prefix[:-1].strip()
        tail = _NAME_TAIL_RE.search(prefix)
        return tail.group(1) if tail else (prefix[-4:] if prefix else "unknown")

    return "unknown"


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


def _extract_relationships(facts: list[object]) -> list[dict]:
    rels = []
    for fact in facts:
        text = str(getattr(fact, "fact", fact))
        uuid = str(getattr(fact, "uuid", "") or "")
        
        # 1. Chinese Standard: X的[Relation]是Y
        for match in _RELATION_ZH_RE.finditer(text):
            subject = _subject_from_fact(text, match)
            rel = match.group(1)
            obj = match.group(3)
            rels.append({
                "subject": subject,
                "relation": _RELATION_MAP.get(rel, rel),
                "object": obj,
                "uuid": uuid
            })
            
        # 2. Chinese Inverse: Y是X的[Relation]
        for match in _RELATION_ZH_INV_RE.finditer(text):
            obj = _subject_from_fact(text, match)
            subject = match.group(2)
            rel = match.group(3)
            rels.append({
                "subject": subject,
                "relation": _RELATION_MAP.get(rel, rel),
                "object": obj,
                "uuid": uuid
            })
            
        # 3. English Standard: X's [Relation] is Y
        for match in _RELATION_EN_RE.finditer(text):
            subject = _subject_from_fact(text, match)
            rel = match.group(1)
            obj = match.group(3)
            rels.append({
                "subject": subject,
                "relation": _RELATION_MAP.get(rel, rel),
                "object": obj,
                "uuid": uuid
            })
            
        # 4. English Inverse: Y is the [Relation] of X
        for match in _RELATION_OF_EN_RE.finditer(text):
            obj = _subject_from_fact(text, match)
            rel = match.group(2)
            subject = match.group(3)
            rels.append({
                "subject": subject,
                "relation": _RELATION_MAP.get(rel, rel),
                "object": obj,
                "uuid": uuid
            })
    return rels


def _check_relationship_conflicts(facts: list[object]) -> list[Conflict]:
    rels = _extract_relationships(facts)
    conflicts: list[Conflict] = []
    
    # 1. Single-valued check
    by_subj_rel: dict[tuple[str, str], set[tuple[str, str]]] = {}
    for r in rels:
        key = (r["subject"], r["relation"])
        by_subj_rel.setdefault(key, set()).add((r["object"], r["uuid"]))
        
    for (subject, relation), val_set in by_subj_rel.items():
        if relation in SINGLE_VALUED_RELATIONS and len(val_set) > 1:
            objects = sorted(list({o for o, _ in val_set}))
            if len(objects) > 1:
                uuids = sorted(list({u for _, u in val_set if u}))
                conflicts.append(
                    Conflict(
                        severity="critical",
                        category="relationship",
                        message=f"关系冲突 ({subject}的{relation}): {', '.join(objects)}",
                        fact_uuids=tuple(uuids),
                    )
                )
                
    # 2. Circular / Reciprocal Checks
    # Parent-child circularity check
    parent_child: dict[tuple[str, str], list[str]] = {}
    for r in rels:
        if r["relation"] in ("father", "mother"):
            parent = r["object"]
            child = r["subject"]
            parent_child.setdefault((parent, child), []).append(r["uuid"])
            
    seen_pc_pairs = set()
    for (parent, child), uuids in parent_child.items():
        if (child, parent) in parent_child:
            pair = tuple(sorted([parent, child]))
            if pair not in seen_pc_pairs:
                seen_pc_pairs.add(pair)
                all_uuids = sorted(list(set(uuids + parent_child[(child, parent)])))
                conflicts.append(
                    Conflict(
                        severity="critical",
                        category="relationship",
                        message=f"循环亲属关系冲突: {parent} 和 {child} 互为父母",
                        fact_uuids=tuple(all_uuids),
                    )
                )
                
    # Master-disciple circularity check
    master_disciple: dict[tuple[str, str], list[str]] = {}
    for r in rels:
        if r["relation"] == "master":
            master = r["object"]
            disciple = r["subject"]
            master_disciple.setdefault((master, disciple), []).append(r["uuid"])
        elif r["relation"] == "disciple":
            master = r["subject"]
            disciple = r["object"]
            master_disciple.setdefault((master, disciple), []).append(r["uuid"])
            
    seen_md_pairs = set()
    for (master, disciple), uuids in master_disciple.items():
        if (disciple, master) in master_disciple:
            pair = tuple(sorted([master, disciple]))
            if pair not in seen_md_pairs:
                seen_md_pairs.add(pair)
                all_uuids = sorted(list(set(uuids + master_disciple[(disciple, master)])))
                conflicts.append(
                    Conflict(
                        severity="critical",
                        category="relationship",
                        message=f"循环师徒关系冲突: {master} 和 {disciple} 互为师徒",
                        fact_uuids=tuple(all_uuids),
                    )
                )
                
    return conflicts


def _check_timeline_conflicts(facts: list[object]) -> list[Conflict]:
    conflicts: list[Conflict] = []
    
    # 1. Death vs Active check
    deaths: dict[str, list[tuple[str, str]]] = {}
    actives: dict[str, list[tuple[str, str]]] = {}
    
    for fact in facts:
        text = str(getattr(fact, "fact", fact))
        uuid = str(getattr(fact, "uuid", "") or "")
        
        death_match = _DEATH_RE.search(text)
        if death_match:
            subject = _subject_from_fact(text, death_match)
            deaths.setdefault(subject, []).append((uuid, text))
            
        active_match = _ACTIVE_RE.search(text)
        if active_match:
            subject = _subject_from_fact(text, active_match)
            actives.setdefault(subject, []).append((uuid, text))
            
    for subject, death_list in deaths.items():
        if subject in actives:
            active_list = actives[subject]
            for duuid, dtext in death_list:
                for auuid, atext in active_list:
                    uuids = tuple(sorted(list({duuid, auuid} - {""})))
                    conflicts.append(
                        Conflict(
                            severity="critical",
                            category="timeline",
                            message=f"时空/生死冲突 ({subject}): 已死亡但有活跃记录 (死亡: '{dtext}', 活跃: '{atext}')",
                            fact_uuids=uuids,
                        )
                    )
                    
    # 2. Birth Year vs Death Year check
    birth_years: dict[str, list[tuple[int, str]]] = {}
    death_years: dict[str, list[tuple[int, str]]] = {}
    
    for fact in facts:
        text = str(getattr(fact, "fact", fact))
        uuid = str(getattr(fact, "uuid", "") or "")
        
        birth_match = _BIRTH_YEAR_RE.search(text)
        if birth_match:
            subject = _subject_from_fact(text, birth_match)
            try:
                year = int(birth_match.group(2))
                birth_years.setdefault(subject, []).append((year, uuid))
            except ValueError:
                pass
                
        death_match = _DEATH_YEAR_RE.search(text)
        if death_match:
            subject = _subject_from_fact(text, death_match)
            try:
                year = int(death_match.group(2))
                death_years.setdefault(subject, []).append((year, uuid))
            except ValueError:
                pass
                
    for subject, b_list in birth_years.items():
        if subject in death_years:
            d_list = death_years[subject]
            for b_yr, buuid in b_list:
                for d_yr, duuid in d_list:
                    if b_yr > d_yr:
                        uuids = tuple(sorted(list({buuid, duuid} - {""})))
                        conflicts.append(
                            Conflict(
                                severity="critical",
                                category="timeline",
                                message=f"时间线冲突 ({subject}): 出生年份 ({b_yr}) 晚于死亡年份 ({d_yr})",
                                fact_uuids=uuids,
                            )
                        )
                        
    return conflicts


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
    conflicts.extend(_check_relationship_conflicts(facts))
    conflicts.extend(_check_timeline_conflicts(facts))
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
    if not client.available:
        return ConflictReport(conflicts=(), blocked=False)
    await client._ensure_connected()
    
    gid = group_id or client._settings.group_id
    try:
        facts = await client.search_facts(query, group_id=gid)
    except Exception:  # noqa: BLE001
        facts = []
        
    node_summaries = []
    try:
        node_query = (
            "MATCH (n:Entity) "
            "WHERE n.name = $query AND n.group_id = $group_id "
            "RETURN properties(n) AS props"
        )
        node_result = await client._graphiti.driver.execute_query(
            node_query,
            params={"query": query, "group_id": gid}
        )
        exclude_keys = {"name", "group_id", "uuid", "created_at", "name_embedding"}
        for record in node_result.records:
            props = record.get("props") or {}
            for k, v in props.items():
                if k not in exclude_keys and isinstance(v, str) and v.strip():
                    v_clean = v.strip()
                    # Strip leading third-person pronouns if we are prepending the query name
                    if not any(name in v_clean for name in [query]):
                        for pronoun in ("他", "她", "它", "he ", "she ", "it "):
                            if v_clean.lower().startswith(pronoun):
                                v_clean = v_clean[len(pronoun):].lstrip()
                                break
                        v_clean = f"{query}{v_clean}"
                    node_summaries.append(v_clean)
    except Exception:  # noqa: BLE001
        pass
        
    episodic_contents = []
    try:
        origins = await client.trace_entity_origins(query, group_id=gid)
        for o in origins:
            content = o.get("content")
            if content and isinstance(content, str) and content.strip():
                episodic_contents.append(content.strip())
    except Exception:  # noqa: BLE001
        pass
        
    all_facts = list(facts) + node_summaries + episodic_contents + [draft_text]
    return build_conflict_report(detect_conflicts_from_facts(all_facts))


def _guess_focus_character(text: str) -> str | None:
    """Pick the most frequent 2-3 char name-like token in Chinese prose."""
    names = re.findall(r"[\u4e00-\u9fff]{2,3}", text)
    if not names:
        return None
    counts: dict[str, int] = {}
    for n in names:
        counts[n] = counts.get(n, 0) + 1
    return max(counts, key=counts.get)
