# Graphiti Operations Runbook

This document describes standard operations, maintenance procedures, and troubleshooting guides for the Graphiti + Neo4j integration in the Novel Studio.

---

## 1. Purging & Resetting Database

If you need to reset the entire setting canon and re-ingest all story materials from scratch:

### A. Reset Local SQLite Ingest Cache
The SQLite database caches paragraph IDs and hashes to prevent double ingestion. Resetting it ensures that all paragraphs are re-evaluated.
```bash
rm my-novel/studio/.graphiti/ingest.db
```

### B. Purge Neo4j Database
Connect to the Neo4j browser at `http://localhost:7474` (or your production Neo4j instance) and run the following Cypher query to delete all nodes and relationships:
```cypher
MATCH (n) DETACH DELETE n;
```
*Alternatively*, you can drop/reset the database schema if needed, but `DETACH DELETE` is sufficient for a data purge.

---

## 2. Ingesting Content from Scratch

After purging the database, you can re-ingest the whitepaper and all final chapter files:

### A. Ingest the Whitepaper
```bash
set -a && source my-novel/.env && set +a
uv run openharness graphiti ingest \
  --studio-root my-novel/studio \
  --source my-novel/studio/whitepaper.md \
  --gate approve-whitepaper \
  --kind whitepaper \
  --scope chapter_all
```

### B. Ingest All Approved Chapters
For each approved chapter (e.g. `ch01.md`, `ch02.md`, etc.):
```bash
set -a && source my-novel/.env && set +a
uv run openharness graphiti ingest \
  --studio-root my-novel/studio \
  --source my-novel/studio/chapters/ch01.md \
  --gate approve-chapter \
  --kind chapter
```

*Note:* Standard ingestion will write back `<!-- paragraph_uid: UUID -->` to the markdown source file if it doesn't already have one, helping keep subsequent updates deterministic.

---

## 3. Resolving Setting & Storyline Conflicts

When the conflict gate fails (exit code `1` or `blocked: true`), authors can debug using the query CLI subcommands.

### A. Check Conflicts Directly
```bash
set -a && source my-novel/.env && set +a
uv run openharness graphiti check-conflicts \
  --source my-novel/studio/chapters/ch01.draft.md \
  --focus "李默"
```

### B. Trace Conflicts in Story Timeline
If a character is reported as having multiple birthplaces, or active after death, fetch their full storyline timeline:
```bash
set -a && source my-novel/.env && set +a
uv run openharness graphiti story-timeline --focus "李默"
```
This shows the sequence of episodes and facts that led to the conflict. You can resolve this by editing the conflicting paragraph in the source markdown files.

---

## 4. Community Detection / Faction Rebuilding

Graphiti groups entities into hierarchical communities asynchronously. To manually trigger or inspect communities:

### A. Trigger Community Rebuilding (Python Console)
```python
import asyncio
from openharness.graphiti.client import GraphitiClient
from openharness.graphiti.config import GraphitiSettings

async def rebuild():
    client = GraphitiClient(GraphitiSettings.from_env(group_id="my-novel"))
    await client.connect()
    # Graphiti SDK provides build_communities() to partition the graph and summarize
    await client._graphiti.build_communities()
    await client.close()

asyncio.run(rebuild())
```

### B. Inspect Communities via CLI
```bash
set -a && source my-novel/.env && set +a
uv run openharness graphiti factions-outline
```

---

## 5. Troubleshooting & Health Checks

- **Neo4j logs show `EquivalentSchemaRuleAlreadyExists`**:
  This is warning noise during initialization and index creation. It is safe to ignore.
- **`Graphiti not configured` error**:
  Ensure that you have set `NEO4J_URI`, `NEO4J_USER`, `NEO4J_PASSWORD`, and `OPENAI_API_KEY` (either in `my-novel/.env` or as environment variables).
- **Driver / bolt connection errors**:
  Verify the Neo4j docker container is active:
  ```bash
  docker ps
  # If stopped, restart
  docker compose -f my-novel/docker-compose.yml up -d
  ```
