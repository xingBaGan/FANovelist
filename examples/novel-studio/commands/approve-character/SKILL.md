---
description: Human gate — promote character draft to locked character card
argument-hint: "CHARACTER_NAME e.g. 李默"
---

# Approve Character

**Human gate.** Character: **$ARGUMENTS** → paths `studio/characters/$ARGUMENTS`.

## Preconditions

- `studio/characters/$ARGUMENTS.draft.md` exists.
- Human has read and approved the draft.

## Steps

1. Confirm with the human that the draft is acceptable (use `ask_user_question` if needed).
2. **Conflict gate** (before copy; requires Neo4j + existing canon). If exit code `1`, stop and report conflicts to the human:

```bash
set -a && source .env && set +a
uv run openharness graphiti check-conflicts \
  --source studio/characters/$ARGUMENTS.draft.md \
  --focus "$ARGUMENTS" \
  --group-id "${GRAPHITI_GROUP_ID:-my-novel}"
```

Or use tool `check_canon_conflicts` with the draft path. **Do not copy or ingest while `blocked: true`.**

3. Copy `studio/characters/$ARGUMENTS.draft.md` → `studio/characters/$ARGUMENTS.md`.
4. Stage the paragraph summaries for human review:

```bash
set -a && source .env && set +a
uv run openharness graphiti stage-summary \
  --studio-root studio \
  --source studio/characters/$ARGUMENTS.md
```

5. Ask the human to review the generated summary buffer file at `studio/characters/$ARGUMENTS.summary.md`. Once the human approves, ingest the approved summaries into the canon graph:

```bash
set -a && source .env && set +a
uv run openharness graphiti ingest \
  --studio-root studio \
  --source studio/characters/$ARGUMENTS.md \
  --gate approve-character \
  --kind character_card \
  --group-id "${GRAPHITI_GROUP_ID:-my-novel}" \
  --approved
```

6. Write marker file `studio/.approved-character-$ARGUMENTS` with ISO date.

Confirm final path and ingest results (paragraphs ingested, entities promoted) to the human.
