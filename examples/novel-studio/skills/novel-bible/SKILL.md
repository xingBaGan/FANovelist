---
name: novel-bible
description: Whitepaper structure, premise/theme guardrails, and approval gates for the novel studio
---

# Novel Bible

## Whitepaper sections (required before chapter work)

1. **Premise** — one-paragraph story promise
2. **Theme** — what the book argues or makes the reader feel
3. **Structure** — acts, turning points, ending direction
4. **Style Bible** — POV, tone, taboos, audience
5. **Character Index** — pointers to `studio/characters/*.yaml`
6. **Plot Index** — pointers to `studio/plot/`

## Red lines (Showrunner may veto)

- New theme contradicting locked `studio/whitepaper.md`
- POV breaks (head-hopping without deliberate craft)
- Character acts against documented motivation without arc setup
- Unplanted payoffs or forgotten foreshadowing

## File state machine

| State | Condition |
|-------|-----------|
| Phase 1 only | No `studio/whitepaper.md` |
| Phase 2 allowed | `studio/whitepaper.md` exists |
| Chapter draft | `studio/chapters/chNN.draft.md` |
| Review ready | `studio/reviews/chNN.json` exists |
| Final chapter | Human ran approve-chapter; `studio/chapters/chNN.md` |

Invoke this skill before merging drafts or approving chapters.
