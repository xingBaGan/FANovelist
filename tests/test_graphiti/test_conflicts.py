"""Tests for setting conflict detection."""

from types import SimpleNamespace

from openharness.graphiti.conflicts import (
    build_conflict_report,
    detect_conflicts_from_facts,
)


def test_birth_place_conflict_critical() -> None:
    facts = [
        SimpleNamespace(uuid="e1", fact="李默生于江城"),
        SimpleNamespace(uuid="e2", fact="李默生于邺城"),
    ]
    conflicts = detect_conflicts_from_facts(facts)
    assert any(c.severity == "critical" and c.category == "identity" for c in conflicts)


def test_no_conflict_single_place() -> None:
    facts = [SimpleNamespace(uuid="e1", fact="李默生于江城")]
    assert detect_conflicts_from_facts(facts) == []


def test_tc_ss_04_gate_blocks_on_critical() -> None:
    """TC-SS-04: conflicting birth places block approve."""
    facts = [
        SimpleNamespace(uuid="e1", fact="李默生于江城"),
        SimpleNamespace(uuid="e2", fact="李默生于江北邺城"),
    ]
    report = build_conflict_report(detect_conflicts_from_facts(facts))
    assert report.blocked is True
    assert len(report.critical) == 1
    assert "李默" in report.critical[0].message


def test_gate_passes_without_conflict() -> None:
    report = build_conflict_report([])
    assert report.blocked is False


def test_relationship_single_value_conflict() -> None:
    # 1. Chinese Standard single-valued relation conflict
    facts_zh = [
        SimpleNamespace(uuid="r1", fact="李默的父亲是李战"),
        SimpleNamespace(uuid="r2", fact="李默的父亲是王虎"),
    ]
    conflicts_zh = detect_conflicts_from_facts(facts_zh)
    assert len(conflicts_zh) == 1
    assert conflicts_zh[0].severity == "critical"
    assert conflicts_zh[0].category == "relationship"
    assert "关系冲突" in conflicts_zh[0].message
    assert "李默" in conflicts_zh[0].message
    assert "father" in conflicts_zh[0].message or "父亲" in conflicts_zh[0].message
    assert "r1" in conflicts_zh[0].fact_uuids
    assert "r2" in conflicts_zh[0].fact_uuids

    # 2. English Standard single-valued relation conflict
    facts_en = [
        SimpleNamespace(uuid="r3", fact="Li Mo's father is Li Zhan"),
        SimpleNamespace(uuid="r4", fact="Li Mo's father is Wang Hu"),
    ]
    conflicts_en = detect_conflicts_from_facts(facts_en)
    assert len(conflicts_en) == 1
    assert conflicts_en[0].category == "relationship"

    # 3. English Inverse single-valued relation conflict
    facts_en_inv = [
        SimpleNamespace(uuid="r5", fact="Li Zhan is the father of Li Mo"),
        SimpleNamespace(uuid="r6", fact="Wang Hu is the father of Li Mo"),
    ]
    conflicts_en_inv = detect_conflicts_from_facts(facts_en_inv)
    assert len(conflicts_en_inv) == 1
    assert conflicts_en_inv[0].category == "relationship"

    # 4. Non-single-valued relationships (multiple masters/disciples should be allowed)
    facts_allowed = [
        SimpleNamespace(uuid="r7", fact="李默的师父是白眉"),
        SimpleNamespace(uuid="r8", fact="李默的师父是赤霞"),
    ]
    assert detect_conflicts_from_facts(facts_allowed) == []


def test_relationship_circularity_conflict() -> None:
    # 1. Parent-child circularity (Li Mo is father of Li Zhan, and Li Zhan is father of Li Mo)
    facts_pc = [
        SimpleNamespace(uuid="c1", fact="李默的父亲是李战"),
        SimpleNamespace(uuid="c2", fact="李战的父亲是李默"),
    ]
    conflicts_pc = detect_conflicts_from_facts(facts_pc)
    assert len(conflicts_pc) == 1
    assert conflicts_pc[0].severity == "critical"
    assert conflicts_pc[0].category == "relationship"
    assert "循环亲属关系" in conflicts_pc[0].message

    # 2. Master-disciple circularity (Li Mo is master of Bai Mei, and Bai Mei is master of Li Mo)
    facts_md = [
        SimpleNamespace(uuid="c3", fact="白眉的师父是李默"),
        SimpleNamespace(uuid="c4", fact="李默的师父是白眉"),
    ]
    conflicts_md = detect_conflicts_from_facts(facts_md)
    assert len(conflicts_md) == 1
    assert conflicts_md[0].severity == "critical"
    assert conflicts_md[0].category == "relationship"
    assert "循环师徒关系" in conflicts_md[0].message


def test_timeline_death_active_conflict() -> None:
    # 1. Chinese death vs active conflict
    facts_zh = [
        SimpleNamespace(uuid="d1", fact="李战在三年前战死"),
        SimpleNamespace(uuid="d2", fact="李战目前在江城修炼"),
    ]
    conflicts_zh = detect_conflicts_from_facts(facts_zh)
    assert len(conflicts_zh) == 1
    assert conflicts_zh[0].severity == "critical"
    assert conflicts_zh[0].category == "timeline"
    assert "生死冲突" in conflicts_zh[0].message

    # 2. English death vs active conflict
    facts_en = [
        SimpleNamespace(uuid="d3", fact="Li Zhan died"),
        SimpleNamespace(uuid="d4", fact="Li Zhan is alive and active in Yecheng now"),
    ]
    conflicts_en = detect_conflicts_from_facts(facts_en)
    assert len(conflicts_en) == 1
    assert conflicts_en[0].category == "timeline"

    # 3. No conflict if active fact is historical (no current/active keywords)
    facts_ok = [
        SimpleNamespace(uuid="d5", fact="李战去世"),
        SimpleNamespace(uuid="d6", fact="李战在黑石山和敌人战斗"),
    ]
    assert detect_conflicts_from_facts(facts_ok) == []


def test_timeline_birth_death_years_conflict() -> None:
    # 1. Conflicting years (born in 100, died in 90)
    facts_bad = [
        SimpleNamespace(uuid="y1", fact="李默出生于大乾历100年"),
        SimpleNamespace(uuid="y2", fact="李默死于大乾历90年"),
    ]
    conflicts_bad = detect_conflicts_from_facts(facts_bad)
    assert len(conflicts_bad) == 1
    assert conflicts_bad[0].severity == "critical"
    assert conflicts_bad[0].category == "timeline"
    assert "时间线冲突" in conflicts_bad[0].message

    # 2. English conflicting years
    facts_en_bad = [
        SimpleNamespace(uuid="y3", fact="Li Mo was born in 100"),
        SimpleNamespace(uuid="y4", fact="Li Mo died in year 90"),
    ]
    conflicts_en_bad = detect_conflicts_from_facts(facts_en_bad)
    assert len(conflicts_en_bad) == 1
    assert conflicts_en_bad[0].category == "timeline"

    # 3. Valid sequence (born 100, died 150)
    facts_ok = [
        SimpleNamespace(uuid="y5", fact="李默生于大乾历100年"),
        SimpleNamespace(uuid="y6", fact="李默死于大乾历150年"),
    ]
    assert detect_conflicts_from_facts(facts_ok) == []

