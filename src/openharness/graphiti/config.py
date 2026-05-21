"""Environment configuration for Graphiti."""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class GraphitiSettings:
    neo4j_uri: str
    neo4j_user: str
    neo4j_password: str
    neo4j_database: str
    group_id: str
    openai_api_key: str | None

    @classmethod
    def from_env(cls, *, group_id: str | None = None) -> GraphitiSettings:
        return cls(
            neo4j_uri=os.environ.get("NEO4J_URI", "bolt://localhost:7687"),
            neo4j_user=os.environ.get("NEO4J_USER", "neo4j"),
            neo4j_password=os.environ.get("NEO4J_PASSWORD", "password"),
            neo4j_database=os.environ.get("NEO4J_DATABASE", "neo4j"),
            group_id=group_id or os.environ.get("GRAPHITI_GROUP_ID", "default"),
            openai_api_key=os.environ.get("OPENAI_API_KEY"),
        )

    @property
    def is_configured(self) -> bool:
        return bool(self.neo4j_uri and self.neo4j_user and self.neo4j_password)
