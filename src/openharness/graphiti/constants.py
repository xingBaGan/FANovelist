"""Shared constants for novel graphiti ingest."""

from __future__ import annotations

import re

PARAGRAPH_MIN_CHARS = 80
PARAGRAPH_UID_PATTERN = re.compile(
    r"<!--\s*paragraph_uid:\s*([0-9a-fA-F-]{36})\s*-->",
)
RECONCILE_SIMILARITY_THRESHOLD = 0.85
