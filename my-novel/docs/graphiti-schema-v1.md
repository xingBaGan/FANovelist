# Graphiti schema v1 (novel studio)

> **换编辑器交接：** 完整上下文见 [`../../docs/graphiti-novel-handoff.md`](../../docs/graphiti-novel-handoff.md)

## Storage

| Layer | Path | Role |
|-------|------|------|
| Manuscript | `studio/**/*.md` | Full text |
| Ingest index | `studio/.graphiti/ingest.db` | `paragraph_uid`, submit audit |
| Canon graph | Neo4j via Graphiti SDK | Entities, facts, episodes |

## Ingest rules

- Submit only (`approve-*`); drafts never write.
- One natural paragraph → one LLM summary → one `add_episode`.
- `paragraph_uid` written on approve: `<!-- paragraph_uid: uuid -->`.
- Short blocks (&lt; 80 chars) stay separate if the next block has a different uid.
- Re-submit: reconcile by uid; supersede via `remove_episode` + `delete_entity_edge`.

## Core entity types (L1)

Implemented in `openharness.graphiti.ontology` (passed to `add_episode` as `entity_types`).

### Entity types (not every field on every person)

| Type | Who | Fields |
|------|-----|--------|
| `MajorCharacter` | 主角/段落主体 | `personality`, `background`（身世综述一段）, `appearance`（有着装才填）, `current_status` |
| `MinorCharacter` | 老者、路人 | 仅 `scene_note` |
| `RelatedPerson` | 李默的母亲 | `anchor_name`, `relationship`, `role_note` |
| `NarrativeElement` | 外门弟子、基础剑法 | `element_kind`, `element_note` |
| `Location` / `Event` / `Organization` | 地名、事件、门派 | 见 `ontology.py` |

**背景 vs 实体**：丧父、性格、抚养 → `MajorCharacter.background`，不建节点。Agent 工具：`classify_canon_snippet` → `add_canon_episode`。

### 实体生命周期（抽象 → 详细）

```text
NarrativeElement  ──(多段出现/戏份增加)──►  MinorCharacter  ──(背景综述/高密度)──►  MajorCharacter
     外门弟子、长老                              神秘老者、张长老                         李默
```

每次 `ingest` 结束后自动评估；也可调用工具 `promote_canon_entities`。

| 提升 | 条件（满足其一） |
|------|------------------|
| → MinorCharacter | 跨 2+ 段出现；或具名（×长老）；或 scene/描述变长 |
| → MajorCharacter | 已有 `background`；或跨 3+ 段；或 summary 足够长 |

**语言**：与原文一致（中文稿 → 属性、边 fact、summary 均中文）。

**原则**：未提及的字段留空；不把 A 的背景写到 B 上。ingest 默认 `excluded_entity_types=['Entity']` 禁止裸 Entity 标签。

Neo4j Browser 请按分组查询，避免看到多次测试残留：

```cypher
MATCH (n:Character) WHERE n.group_id = 'integration-test' RETURN n
```

## Edges (examples)

`MEMBER_OF`, `ENEMY_OF`, `LOVE_WITH`, `PARENT_OF`, `LOCATED_IN`, `PARTICIPATED_IN`

## Local services

**SQLite** — no server install; Python creates `studio/.graphiti/ingest.db` on first ingest.

**Neo4j** — Docker (from `my-novel/`):

```bash
cp .env.example .env   # edit NEO4J_PASSWORD if needed
docker compose up -d
```

Browser UI: http://localhost:7474 (user `neo4j`, password from `.env`).

## uv setup

```bash
uv sync --extra dev --extra graphiti
set -a && source .env && set +a   # or export vars manually
uv run pytest tests/test_graphiti -q
```
