---
description: Phase 1 — spawn character and plot agents, merge into whitepaper draft
argument-hint: "[your premise and genre notes]"
---

# Novel Studio — Init (Phase 1)

You are the **Showrunner** coordinator. The human must approve the whitepaper before chapter work.

## Preconditions

- Ensure `studio/` exists (copy from `studio-templates` if empty).
- Invoke skill `novel-bible`.

## Steps

1. Capture the human's brief from args: $ARGUMENTS
2. In parallel, spawn:
   - `agent(subagent_type="novel-studio:character-director:character-director", description="Seed character bibles", prompt="...")`
   - `agent(subagent_type="novel-studio:plot-architect:plot-architect", description="Seed plot outline", prompt="...")`
3. When both complete, synthesize `studio/whitepaper.draft.md` (premise, theme, structure, style bible, indexes).
4. Tell the human: review the draft, then run `/novel-studio:approve-whitepaper`.

Do **not** create `studio/whitepaper.md` until the human approves.
