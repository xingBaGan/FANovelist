"""Align previous and current paragraph sets before ingest."""

from __future__ import annotations

from dataclasses import dataclass

from openharness.graphiti.ingest_store import StoredParagraph
from openharness.graphiti.paragraphs import ParagraphBlock


@dataclass(frozen=True)
class ReconcileResult:
    edited: tuple[tuple[ParagraphBlock, StoredParagraph], ...]
    added: tuple[ParagraphBlock, ...]
    deleted: tuple[StoredParagraph, ...]
    skipped: tuple[ParagraphBlock, ...]
    ambiguous: tuple[ParagraphBlock, ...]


def reconcile_paragraphs(
    old_paragraphs: list[StoredParagraph],
    new_paragraphs: list[ParagraphBlock],
) -> ReconcileResult:
    """Match paragraphs by paragraph_uid only (v1)."""
    old_by_uid = {p.paragraph_uid: p for p in old_paragraphs}
    matched_new_uids: set[str] = set()
    matched_old_uids: set[str] = set()

    edited: list[tuple[ParagraphBlock, StoredParagraph]] = []
    skipped: list[ParagraphBlock] = []

    for new in new_paragraphs:
        old = old_by_uid.get(new.paragraph_uid)
        if old is None:
            continue
        matched_new_uids.add(new.paragraph_uid)
        matched_old_uids.add(old.paragraph_uid)
        if old.content_hash != new.content_hash:
            edited.append((new, old))
        else:
            skipped.append(new)

    added = tuple(p for p in new_paragraphs if p.paragraph_uid not in matched_new_uids)
    deleted = tuple(p for p in old_paragraphs if p.paragraph_uid not in matched_old_uids)

    return ReconcileResult(
        edited=tuple(edited),
        added=added,
        deleted=deleted,
        skipped=tuple(skipped),
        ambiguous=(),
    )
