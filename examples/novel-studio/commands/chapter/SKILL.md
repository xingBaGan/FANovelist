---
description: Phase 2 — scene brief, draft, executive review for one chapter
argument-hint: "CHAPTER_NUMBER e.g. 3"
---

# Novel Studio — Chapter Pipeline

Chapter number from args: **$ARGUMENTS** (zero-pad as `ch03` in paths).

## Preconditions

- `studio/whitepaper.md` exists.
- `studio/.approved-whitepaper` exists.

## Pipeline (sequential spawns)

1. **Plot Architect** — create/update `studio/scenes/chNN.brief.md` (scene goal, turn, plants/payoffs). Skill: `scene-brief`.
2. **Scene Builder** — enrich setting, sensory, blocking, POV constraints in the same brief file.
3. **Character Director** — append character state to the brief; refresh cards if arc shifted.
4. **Ghostwriter** — write `studio/chapters/chNN.draft.md` from the brief + whitepaper style.
5. **Executive Editor** — write `studio/reviews/chNN.json` only (skill: `editor-rubric`).

## After pipeline

Tell the human:

- Read `studio/chapters/chNN.draft.md` and `studio/reviews/chNN.json`.
- If satisfied: `/novel-studio:approve-chapter NN`
- If `verdict` is REVISE: respawn Ghostwriter with `required_revisions` from JSON.

Never write `studio/chapters/chNN.md` in this command.
