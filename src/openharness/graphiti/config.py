"""Environment configuration for Graphiti."""

from __future__ import annotations

import os
from dataclasses import dataclass


def _apply_openai_compat_fallbacks() -> None:
    """Populate OPENAI-compatible env vars from provider-specific keys.

    Priority:
    1) Respect explicit OPENAI_API_KEY (user override)
    2) Fall back to XIAOMI_API_KEY
    3) Fall back to DEEPSEEK_API_KEY
    """
    if os.environ.get("OPENAI_API_KEY"):
        return

    xiaomi_key = os.environ.get("XIAOMI_API_KEY")
    if xiaomi_key:
        os.environ.setdefault("OPENAI_API_KEY", xiaomi_key)
        os.environ.setdefault("OPENAI_BASE_URL", "https://api.xiaomimimo.com/v1")
        os.environ.setdefault("OPENAI_MODEL", os.environ.get("XIAOMI_MODEL", "mimo-v2-pro"))
        return

    deepseek_key = os.environ.get("DEEPSEEK_API_KEY")
    if deepseek_key:
        os.environ.setdefault("OPENAI_API_KEY", deepseek_key)
        os.environ.setdefault("OPENAI_BASE_URL", "https://api.deepseek.com")
        os.environ.setdefault("OPENAI_MODEL", os.environ.get("DEEPSEEK_MODEL", "deepseek-chat"))


@dataclass(frozen=True)
class GraphitiSettings:
    neo4j_uri: str
    neo4j_user: str
    neo4j_password: str
    neo4j_database: str
    group_id: str
    openai_api_key: str | None
    deepseek_api_key: str | None = None
    siliconflow_api_key: str | None = None
    xiaomi_api_key: str | None = None

    @classmethod
    def from_env(cls, *, group_id: str | None = None) -> GraphitiSettings:
        _apply_openai_compat_fallbacks()
        return cls(
            neo4j_uri=os.environ.get("NEO4J_URI", "bolt://localhost:7687"),
            neo4j_user=os.environ.get("NEO4J_USER", "neo4j"),
            neo4j_password=os.environ.get("NEO4J_PASSWORD", "password"),
            neo4j_database=os.environ.get("NEO4J_DATABASE", "neo4j"),
            group_id=group_id or os.environ.get("GRAPHITI_GROUP_ID", "default"),
            openai_api_key=os.environ.get("OPENAI_API_KEY"),
            deepseek_api_key=os.environ.get("DEEPSEEK_API_KEY"),
            siliconflow_api_key=os.environ.get("SILICONFLOW_API_KEY"),
            xiaomi_api_key=os.environ.get("XIAOMI_API_KEY"),
        )

    @property
    def is_configured(self) -> bool:
        return bool(self.neo4j_uri and self.neo4j_user and self.neo4j_password)
