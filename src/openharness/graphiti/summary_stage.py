"""Summary staging logic for reviewing chapter summaries before ingestion."""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import TYPE_CHECKING

from openharness.graphiti.config import GraphitiSettings
from openharness.graphiti.paragraphs import inject_paragraph_uids, split_paragraphs
from openharness.graphiti.summarize import passthrough_summarizer

if TYPE_CHECKING:
    from openharness.graphiti.summarize import Summarizer

logger = logging.getLogger(__name__)

UID_HASH_PATTERN = re.compile(
    r"<!--\s*paragraph_uid:\s*([a-zA-Z0-9_-]+)\s+hash:\s*([0-9a-fA-F]+)\s*-->"
)


def parse_summary_file(content: str) -> dict[str, tuple[str, str]]:
    """Parse a summary markdown file.

    Returns:
        A dict mapping paragraph_uid -> (content_hash, summary_text)
    """
    lines = content.splitlines()
    result = {}

    current_uid = None
    current_hash = None
    current_lines = []

    for line in lines:
        match = UID_HASH_PATTERN.match(line.strip())
        if match:
            if current_uid:
                result[current_uid] = (current_hash, "\n".join(current_lines).strip())
                current_lines = []
            current_uid = match.group(1)
            current_hash = match.group(2)
        else:
            if current_uid is not None:
                current_lines.append(line)

    if current_uid:
        result[current_uid] = (current_hash, "\n".join(current_lines).strip())

    return result


def serialize_summary_file(summaries: list[tuple[str, str, str]]) -> str:
    """Serialize a list of (uid, hash, summary_text) to markdown."""
    out = ["# Chapter Summary Buffer", ""]
    for uid, content_hash, summary in summaries:
        out.append(f"<!-- paragraph_uid: {uid} hash: {content_hash} -->")
        out.append(summary)
        out.append("")
    return "\n".join(out)


async def stage_chapter_summaries(
    *,
    source_path: Path,
    studio_root: Path,
    summarizer: Summarizer | None = None,
) -> tuple[Path, dict[str, int]]:
    """Generate or update the summary buffer file for the given source file.

    Returns:
        A tuple of (summary_file_path, stats_dict)
    """
    source_path = source_path.resolve()
    summary_path = source_path.with_suffix(".summary.md")

    # 1. Read source file and split into paragraphs
    markdown = source_path.read_text(encoding="utf-8")
    blocks = split_paragraphs(markdown)

    # 2. Inject UIDs back to the source file if any were missing/generated
    updated_markdown = inject_paragraph_uids(markdown, blocks)
    if updated_markdown != markdown:
        source_path.write_text(updated_markdown, encoding="utf-8")
        markdown = updated_markdown
        blocks = split_paragraphs(markdown)

    # 3. Read existing summary file if present
    existing_summaries = {}
    if summary_path.exists():
        try:
            summary_content = summary_path.read_text(encoding="utf-8")
            existing_summaries = parse_summary_file(summary_content)
        except Exception as e:
            logger.warning("Failed to parse existing summary file %s: %s", summary_path, e)

    # 4. Resolve the summarizer and batching capability
    settings = GraphitiSettings.from_env()
    use_batching = False

    if summarizer is not None:
        summarize = summarizer
    else:
        if settings.openai_api_key or settings.deepseek_api_key:
            use_batching = True
            summarize = None
        else:
            summarize = passthrough_summarizer

    # 5. Process summaries (reuse or generate)
    final_summaries = []
    stats = {"reused": 0, "updated": 0, "created": 0}

    # Identify blocks that need summarization
    blocks_to_summarize = []  # list of (block_index, block, is_update)

    for idx, block in enumerate(blocks):
        existing = existing_summaries.get(block.paragraph_uid)
        if existing and existing[0] == block.content_hash:
            final_summaries.append((block.paragraph_uid, block.content_hash, existing[1]))
            stats["reused"] += 1
        else:
            # Placeholder in final_summaries to preserve index order
            final_summaries.append(None)
            blocks_to_summarize.append((idx, block, existing is not None))

    if blocks_to_summarize:
        texts = [b.text for _, b, _ in blocks_to_summarize]

        if use_batching:
            from openharness.graphiti.summarize import openai_batch_summarizer

            batch_size = 10
            summaries = []
            for i in range(0, len(texts), batch_size):
                chunk = texts[i : i + batch_size]
                chunk_summaries = await openai_batch_summarizer(chunk)
                summaries.extend(chunk_summaries)
        else:
            summaries = []
            for t in texts:
                summaries.append(await summarize(t))

        # Populate final_summaries and update stats
        for (idx, block, is_update), summary_text in zip(blocks_to_summarize, summaries):
            final_summaries[idx] = (block.paragraph_uid, block.content_hash, summary_text)
            if is_update:
                stats["updated"] += 1
                logger.info("Updated summary for paragraph %s (hash changed)", block.paragraph_uid)
            else:
                stats["created"] += 1
                logger.info("Created summary for paragraph %s", block.paragraph_uid)

    # 6. Write final buffer file
    summary_content = serialize_summary_file(final_summaries)
    summary_path.write_text(summary_content, encoding="utf-8")

    return summary_path, stats
