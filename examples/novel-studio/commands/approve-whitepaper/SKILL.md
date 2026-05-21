---
description: Human gate — promote whitepaper draft to locked whitepaper
---

# Approve Whitepaper

**Human gate.** Only run after the author has read `studio/whitepaper.draft.md`.

## Steps

1. Confirm with the human that the draft is acceptable (use `ask_user_question` if needed).
2. **Conflict gate** (if canon graph already has content):

```bash
set -a && source .env && set +a
uv run openharness graphiti check-conflicts \
  --source studio/whitepaper.draft.md \
  --group-id "${GRAPHITI_GROUP_ID:-my-novel}"
```

Stop if exit code is `1` (`blocked: true`).

3. Copy `studio/whitepaper.draft.md` → `studio/whitepaper.md` (or merge edits the human made in place).
4. Ingest canon graph:

```bash
set -a && source .env && set +a
uv run openharness graphiti ingest \
  --studio-root studio \
  --source studio/whitepaper.md \
  --gate approve-whitepaper \
  --kind whitepaper \
  --scope chapter_all \
  --group-id "${GRAPHITI_GROUP_ID:-my-novel}"
```

5. Write marker file `studio/.approved-whitepaper` with ISO date.
6. Reply: Phase 2 unlocked. Use `/novel-studio:chapter 1` to start chapter pipeline.

If the draft is not ready, stop and list required fixes instead of copying.
