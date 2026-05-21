---
description: Human gate — promote whitepaper draft to locked whitepaper
---

# Approve Whitepaper

**Human gate.** Only run after the author has read `studio/whitepaper.draft.md`.

## Steps

1. Confirm with the human that the draft is acceptable (use `ask_user_question` if needed).
2. Copy `studio/whitepaper.draft.md` → `studio/whitepaper.md` (or merge edits the human made in place).
3. Write marker file `studio/.approved-whitepaper` with ISO date.
4. Reply: Phase 2 unlocked. Use `/novel-studio:chapter 1` to start chapter pipeline.

If the draft is not ready, stop and list required fixes instead of copying.
