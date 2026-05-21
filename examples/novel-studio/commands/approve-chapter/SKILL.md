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
3. Copy `studio/chapters/chNN.draft.md` → `studio/chapters/chNN.md`.
4. Append approval note to `studio/reviews/chNN.json` field `human_approved_at` (ISO timestamp) if editing JSON is allowed; else write `studio/.approved-chNN` marker file.

Confirm final path to the human.
