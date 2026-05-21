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
