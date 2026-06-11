"""Shared constants for novel graphiti ingest."""

from __future__ import annotations

import re

PARAGRAPH_MIN_CHARS = 80
PARAGRAPH_UID_PATTERN = re.compile(
    r"<!--\s*paragraph_uid:\s*([a-zA-Z0-9_-]+)\s*-->",
)
RECONCILE_SIMILARITY_THRESHOLD = 0.85
