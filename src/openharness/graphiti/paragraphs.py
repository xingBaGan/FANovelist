"""Markdown natural-paragraph splitting and paragraph_uid handling."""

from __future__ import annotations

import hashlib
import re
import uuid
from collections.abc import Callable
from dataclasses import dataclass

from openharness.graphiti.constants import PARAGRAPH_MIN_CHARS, PARAGRAPH_UID_PATTERN

_HEADING_RE = re.compile(r"^#{1,6}\s+")


@dataclass(frozen=True)
class ParagraphBlock:
    """One natural paragraph with stable uid and provenance fields."""

    paragraph_uid: str
    text: str
    paragraph_index: int
    section_heading: str | None
    content_hash: str


def normalize_paragraph_text(text: str) -> str:
    """Collapse whitespace for hashing and similarity."""
    return " ".join(text.split()).strip()


def content_hash(text: str) -> str:
    """SHA-256 hex of normalized paragraph text."""
    normalized = normalize_paragraph_text(text)
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _parse_uid_line(line: str) -> str | None:
    match = PARAGRAPH_UID_PATTERN.match(line.strip())
    return match.group(1) if match else None


def split_paragraphs(
    markdown: str,
    *,
    new_uid: Callable[[], str] | None = None,
) -> list[ParagraphBlock]:
    """Split markdown into natural paragraphs; headings are standalone blocks."""
    gen = new_uid or (lambda: str(uuid.uuid4()))
    lines = markdown.splitlines()
    raw_blocks: list[tuple[str | None, list[str]]] = []
    pending_uid: str | None = None
    current_lines: list[str] = []

    def flush() -> None:
        nonlocal current_lines, pending_uid
        if not current_lines:
            return
        raw_blocks.append((pending_uid, current_lines.copy()))
        current_lines = []
        pending_uid = None

    for line in lines:
        stripped = line.strip()
        uid = _parse_uid_line(stripped) if stripped else None
        if uid is not None:
            flush()
            pending_uid = uid
            continue
        if _HEADING_RE.match(stripped):
            flush()
            raw_blocks.append((gen(), [stripped]))
            continue
        if stripped == "":
            flush()
            continue
        current_lines.append(line)
    flush()

    merged = _merge_short_blocks(raw_blocks, gen)
    result: list[ParagraphBlock] = []
    section: str | None = None
    for index, (uid, lines_block) in enumerate(merged):
        text = "\n".join(lines_block).strip()
        if not text:
            continue
        if _HEADING_RE.match(text):
            section = text.lstrip("#").strip()
            continue
        result.append(
            ParagraphBlock(
                paragraph_uid=uid,
                text=text,
                paragraph_index=len(result),
                section_heading=section,
                content_hash=content_hash(text),
            )
        )
    return result


def _merge_short_blocks(
    blocks: list[tuple[str | None, list[str]]],
    gen: Callable[[], str],
) -> list[tuple[str, list[str]]]:
    """Merge a short block only into the immediately following block."""
    out: list[tuple[str, list[str]]] = []
    pending_short: tuple[str, list[str]] | None = None

    for uid, lines_block in blocks:
        block_uid = uid or gen()
        text = "\n".join(lines_block).strip()
        if pending_short is not None:
            short_uid, short_lines = pending_short
            if block_uid != short_uid:
                out.append(pending_short)
                pending_short = None
            else:
                out.append((short_uid, short_lines + [""] + lines_block))
                pending_short = None
                continue
        if len(normalize_paragraph_text(text)) < PARAGRAPH_MIN_CHARS and not _HEADING_RE.match(text):
            pending_short = (block_uid, lines_block.copy())
            continue
        out.append((block_uid, lines_block))

    if pending_short is not None:
        out.append(pending_short)
    return out
