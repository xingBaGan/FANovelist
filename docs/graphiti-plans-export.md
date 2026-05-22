# Graphiti 计划文件导出（供其他 LLM 使用）

> 从 Cursor 计划导出，日期：2026-05-21  
> 仓库：`/Users/jzj/ai_writing/OpenHarness`  
> 配套交接：[`graphiti-novel-handoff.md`](graphiti-novel-handoff.md)

---

## 如何使用本文档

1. 将 **Part A（总计划）** 作为产品/架构规格与 Phase 0–9 路线图。  
2. 将 **Part B（剩余工作 / 实现状态）** 作为当前 sprint 进度与下一步。  
3. 将 **Part C（机器可读 TODO）** 直接粘贴给其他 LLM 作任务列表。  
4. 实现细节以代码为准：`src/openharness/graphiti/`；测试：`tests/test_graphiti/`（**36 passed**）。


---

# Part C — 机器可读 TODO（合并状态，2026-05-21）

```yaml
project: OpenHarness novel-studio Graphiti integration
repo: /Users/jzj/ai_writing/OpenHarness
tests: "uv run pytest tests/test_graphiti -q  # 36 passed"

completed:
  - define-v1-ontology: Major/Minor/Related/NarrativeElement + lifecycle
  - paragraph pipeline: split, reconcile, supersede, ingest_store SQLite
  - inject_paragraph_uids + write-back on approve
  - GraphitiClient + ontology + excluded bare Entity + Chinese summary patch
  - entity promotion: NarrativeElement -> MinorCharacter -> MajorCharacter
  - canon_classify + graphiti tools registered
  - CLI: openharness graphiti ingest | check-conflicts
  - approve-chapter/whitepaper skills wired
  - conflicts gate: ConflictReport + TC-SS-04 + Neo4j live test
  - E2E fixtures story.v1-v4 + TC-SS-01..07 (offline)
  - docs: graphiti-schema-v1, docker-compose, handoff
  - openai_summarizer: OpenAI-backed summarization with Chinese/English bilingual support and unit tests (36 passed)
  - conflict-rules: timeline and relationship rules implemented and unit tested (36 passed)
  - causality-and-transformation: causal and transformational edge schemas integrated and unit tested (36 passed)

in_progress: []

pending:
  - MCP tools: search_facts, remove_episode, delete_entity_edge wrappers
  - get_canon_state novel-specific query tool
  - pytest.mark.integration for live Neo4j CI
  - graphiti-ops.md runbook
  - approve-character skill for character_card ingest
```

---

# Part B — 细项实现计划（原 `graphiti_remaining_work_9249c0bd.plan.md`）

```yaml
name: Graphiti Remaining Work
overview: "Graphiti novel-canon integration — core pipeline, openai summarizer, and timeline/relationship conflict rules done (36 tests). Remaining: MCP search/remove tools, optional Neo4j integration CI."
todos:
  - id: inject-uids
    content: Implement inject_paragraph_uids in paragraphs.py + unit test; fix ingest write_uids path
    status: completed
  - id: register-tools
    content: Register graphiti_tools() in create_default_tool_registry; add search/remove tools incrementally
    status: completed
  - id: cli-ingest
    content: Add openharness graphiti ingest subcommand; update approve-chapter/whitepaper SKILL steps
    status: completed
  - id: conflicts-v1
    content: Add conflicts.py detect_setting_conflicts; critical blocks approve in skills
    status: completed
  - id: e2e-fixtures
    content: Add story.v2/v3/v4 fixtures + TC-SS-03..07 offline tests; optional Neo4j integration mark
    status: completed
  - id: summarizer-ontology
    content: openai_summarizer (ontology + entity promotion + NarrativeElement already done)
    status: completed
  - id: mcp-parity-tools
    content: search_facts, remove_episode, delete_entity_edge tool wrappers
    status: pending
  - id: integration-test-neo4j
    content: "@pytest.mark.integration live ingest test; skip without NEO4J_URI"
    status: pending
```

## Summary

| Area | Status |
|------|--------|
| Core ingest pipeline | **Done** |
| Prescribed ontology + lifecycle promotion | **Done** |
| Agent tools (classify, add_canon, promote, check_conflicts) | **Done** |
| CLI `openharness graphiti ingest` / `check-conflicts` | **Done** |
| Approve skill ingest + conflict gate | **Done** |
| E2E offline tests | **36 passed** |
| `openai_summarizer` | **Done** |
| MCP search/remove tools | **Pending** |

## Implemented modules

| Component | Path |
|-----------|------|
| Paragraph split / uid / reconcile | `src/openharness/graphiti/paragraphs.py`, `reconcile.py` |
| SQLite ingest + submit audit | `ingest_store.py` |
| Ingest + promotion | `ingest.py`, `promotion_runner.py`, `entity_promotion.py` |
| Ontology | `ontology.py` |
| Classify + conflicts | `canon_classify.py`, `conflicts.py` |
| Chinese summaries | `prompts_patch.py` |
| Client | `client.py` |
| Tools | `tools.py` → `openharness/tools/__init__.py` |
| CLI | `graphiti/cli.py` |
| Docs | `my-novel/docs/graphiti-schema-v1.md`, `my-novel/docker-compose.yml` |

## Phase status

- **A UID write-back** — Done (`inject_paragraph_uids`, TC-SS-07)
- **B Register tools** — Done (partial: search/remove pending)
- **C CLI + approve skills** — Done
- **D Conflicts gate** — Done (`check-conflicts`, exit 1, TC-SS-04, Neo4j 江城/邺城)
- **E E2E fixtures** — Done offline
- **F Production summarizer** — Done
- **G Ontology** — Done

## Next steps

1. MCP `search_facts`, `remove_episode`, `delete_entity_edge`
2. `@pytest.mark.integration`

---

# Part A — 总计划（原 `graphiti_novel_todo_5077ebaf.plan.md`）

```yaml
name: Graphiti Novel Todo
overview: Build a phased implementation plan to integrate Graphiti as dynamic memory for novel settings, with contradiction detection and provenance, while keeping markdown as the human-facing layer.
todos:
  - id: define-v1-ontology
    content: Define layered Prescribed Ontology (Major/Minor/Related/NarrativeElement + lifecycle promotion).
    status: completed
  - id: bootstrap-graphiti-adapter
    content: GraphitiClient + ingest pipeline + excluded bare Entity; MCP search/remove tools still pending.
    status: in_progress
  - id: build-markdown-sync
    content: Submit-triggered ingest, supersede, inject_paragraph_uids; openai_summarizer completed.
    status: completed
  - id: expose-agent-tools
    content: graphiti_tools registered (classify, add_canon, promote, check_conflicts); get_canon_state pending.
    status: completed
  - id: implement-conflict-rules
    content: conflicts.py birthplace, timeline, and relationship rules implemented and unit tested.
    status: completed
  - id: wire-approval-gates
    content: approve ingest CLI + check-conflicts before copy done.
    status: completed
  - id: add-tests-and-ci
    content: TC-SS-01..07 offline + timeline/relationship + causality/transformation (36 tests); live Neo4j integration mark pending.
    status: in_progress
  - id: document-ops
    content: graphiti-schema-v1.md + docker-compose + .env.example + handoff done.
    status: completed
```

## Goal

Replace static-only setting management with a temporal, queryable, and contradiction-aware memory layer, while preserving current markdown workflow for human editing and review.

## Principles

- Keep markdown as source-of-authoring UX, Graphiti as machine consistency layer.
- Small iterations: each task should be implementable in a short PR.
- Define contradiction rules explicitly (business rules first, model second).

## Architecture — 存储分层

| 数据 | 存储位置 | 作用 |
|------|----------|------|
| 正文 | `studio/**/*.md` | 人类可读完整文稿 |
| 草稿 | `*.draft.md` | 不 ingest |
| 段落状态 | `studio/.graphiti/ingest.db` | uid, hash, episode/edge 映射, submit 审计 |
| 本体 | `graphiti-schema-v1.md` + `ontology.py` | Prescribed Ontology |
| Canon 图 | Neo4j via Graphiti | 实体、关系、段 episode |

**进入 Graphiti：** 每自然段一条 `add_episode`（概述 + 抽取）；hard delete supersede。  
**不进入：** 草稿、完整排版原文（原文在 Markdown）。

## Phase 0 — Scope & Contract

- Contradiction scope: `identity`, `timeline`, `relationship`
- Layered ontology L0/L1/L2 + edge enums
- **Option A（已选）：** Graphiti Python SDK + Pydantic ontology（非 MCP 做主路径）

## Phase 1 — Minimal Infrastructure

- `graphiti-core` optional extra; Neo4j Docker
- `GraphitiClient` + MCP-parity tools
- Tool registry in `openharness/tools/__init__.py`

## Phase 2 — Submit-Triggered Ingestion（核心）

- 仅 submit 后写图；每自然段 → 一条概述 → 一条 `add_episode`
- `source_kind`: whitepaper | chapter | character_card
- `submit_scope`: changed_paragraphs | chapter_all | single_paragraph | character_card_all
- `paragraph_uid` 主键；approve 写回 `<!-- paragraph_uid: uuid -->`
- `reconcile_paragraphs` → supersede (hard delete) → re-ingest
- SQLite: documents, paragraphs, paragraph_episodes, paragraph_edges, submit_runs, submit_paragraph_events
- `PARAGRAPH_MIN_CHARS=80`

## Phase 3 — Query APIs

- Layer 1: search_nodes, search_facts, get_episodes (partial)
- Layer 2: get_canon_state, get_fact_sources, detect_setting_conflicts

## Phase 4 — Contradiction Detection v1

- Rules: birthplace, dead/active, timeline, relationship symmetry, etc.
- `detect_setting_conflicts`; critical blocks submit

## Phase 5 — Human-in-the-Loop

- cross_paragraph_retcon, setting_revision classification

## Phase 6 — Novel Studio Flow Integration

1. Human submit + scope  
2. Promote draft → final  
3. submit_runs + paragraph_uid write-back  
4. ingest_submitted_document  
5. detect_setting_conflicts  
6. Report + **critical 阻断**

## Phase 7 — Testing

### E2E 用例 TC-SS-01 .. 07

| ID | 场景 |
|----|------|
| TC-SS-01 | 首次 submit 建图 |
| TC-SS-02 | 幂等 re-submit |
| TC-SS-03 | 新增段 |
| TC-SS-04 | 设定/出生地冲突 |
| TC-SS-05 | 删除段 supersede |
| TC-SS-06 | 改段 supersede + re-ingest |
| TC-SS-07 | inject uid 幂等 |

夹具：`tests/fixtures/short_story/story.v1.md` … `story.v4-edit.md`

## Phase 8–9 — Performance & Ops

- Idempotency, metrics, reindex runbook (`graphiti-ops.md` 待写)

## Decisions Log（已拍板）

| 项 | 选择 |
|----|------|
| Ingest 索引 | SQLite ingest.db |
| 图数据库 | Neo4j |
| Graphiti | Python SDK |
| 冲突门禁 | critical 阻断 |
| 段落粒度 | 每自然段一条 episode |
| 删改 | reconcile + hard delete |
| paragraph_uid | approve 写回 Markdown |
| 短段合并 | 80 字 |
| Graphiti 删改 | Hard delete |

## Definition of Done (v1)

- Submit 后按段 ingest；草稿不写图
- 短篇小说 TC-SS-01..07 通过
- Agents 可查询 canon；冲突可检测、可溯源
- critical 阻断 submit

---

## 实现与计划差异说明（给 LLM）

以下为**已实现但总计划未逐条展开**的内容，避免其他 LLM 重复造轮子：

| 能力 | 说明 |
|------|------|
| `NarrativeElement` | 外门弟子、基础剑法等统一标签；`excluded_entity_types=['Entity']` |
| `MajorCharacter.background` | 丧父/性格等合并一段，非 father_status 等碎字段 |
| 实体生命周期 | ingest 后 `run_entity_promotions` |
| `canon_classify` + `classify_canon_snippet` 工具 | 背景 vs 实体分流 |
| 中文 summary | `prompts_patch.py` |
| `check_canon_conflicts` | approve 前门禁，exit code 1 |

**总计划中仍准确有效的部分：** Phase 0–2 数据模型、SQLite 表设计、reconcile 语义、TC-SS 用例、SDK API 对照表、approve 流程六步。

---

*End of export.*
