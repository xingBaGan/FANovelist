"""Novel canon graph integration via Graphiti."""

from openharness.graphiti.conflicts import (
    Conflict,
    ConflictReport,
    check_submit_conflicts,
    detect_setting_conflicts,
)
from openharness.graphiti.ingest import IngestReport, ingest_submitted_document
from openharness.graphiti.ingest_store import IngestStateStore
from openharness.graphiti.ontology import NOVEL_ENTITY_TYPES, MajorCharacter
from openharness.graphiti.paragraphs import inject_paragraph_uids
from openharness.graphiti.aggregation import (
    classify_and_aggregate_summaries,
    load_or_generate_aggregation_plan,
    ingest_aggregation_plan,
)

__all__ = [
    "Conflict",
    "ConflictReport",
    "check_submit_conflicts",
    "IngestReport",
    "IngestStateStore",
    "MajorCharacter",
    "NOVEL_ENTITY_TYPES",
    "detect_setting_conflicts",
    "ingest_submitted_document",
    "inject_paragraph_uids",
    "classify_and_aggregate_summaries",
    "load_or_generate_aggregation_plan",
    "ingest_aggregation_plan",
]
