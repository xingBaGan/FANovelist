---
description: Human gate — promote chapter draft to final chapter file
argument-hint: "CHAPTER_NUMBER e.g. 3"
---

# Approve Chapter

**Human gate.** Chapter: **$ARGUMENTS** → paths `chNN`.

## Preconditions

- `studio/reviews/chNN.json` exists.
- Human has read draft and review (confirm via `ask_user_question` if unsure).

## Steps

1. If review `verdict` is `REJECT`, stop — escalate to Showrunner, do not promote.
2. If `REVISE`, stop — respawn Ghostwriter instead of approving.
3. **Conflict gate** (before copy; requires Neo4j + existing canon). If exit code `1`, stop and report conflicts to the human:

```bash
set -a && source .env && set +a
uv run openharness graphiti check-conflicts \
  --source studio/chapters/chNN.draft.md \
  --focus 李默 \
  --group-id "${GRAPHITI_GROUP_ID:-my-novel}"
```

Or use tool `check_canon_conflicts` with the draft path. **Do not copy or ingest while `blocked: true`.**

4. Copy `studio/chapters/chNN.draft.md` → `studio/chapters/chNN.md`.
5. Ingest canon graph (from novel project root, with `my-novel/.env` loaded):

```bash
set -a && source .env && set +a
uv run openharness graphiti ingest \
  --studio-root studio \
  --source studio/chapters/chNN.md \
  --gate approve-chapter \
  --kind chapter \
  --group-id "${GRAPHITI_GROUP_ID:-my-novel}"
```

6. Append approval note to `studio/reviews/chNN.json` field `human_approved_at` (ISO timestamp) if editing JSON is allowed; else write `studio/.approved-chNN` marker file.

Confirm final path and ingest JSON (`paragraphs_ingested`, `entities_promoted`) to the human.
