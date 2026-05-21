# My Novel — OpenHarness Studio

Multi-agent novel workspace using the **novel-studio** plugin.

## Quick start

```bash
cd my-novel   # or: cd OpenHarness/my-novel

# One-time: install plugin globally (already done if you ran setup)
oh plugin install "$(pwd)/.openharness/plugins/novel-studio"

export CLAUDE_CODE_COORDINATOR_MODE=1
oh
```

See [`.openharness/SETUP.md`](.openharness/SETUP.md) for project-local plugin option.

## Workflow

1. `/novel-studio:init` — your premise in the args; produces `studio/whitepaper.draft.md`
2. Edit draft → `/novel-studio:approve-whitepaper`
3. `/novel-studio:chapter 1` — pipeline → draft + `studio/reviews/ch01.json`
4. `/novel-studio:approve-chapter 1` — final `studio/chapters/ch01.md`

See [`.openharness/plugins/novel-studio/README.md`](.openharness/plugins/novel-studio/README.md) for agent spawn names and details.

## Layout

```text
studio/
  whitepaper.draft.md   # phase 1 draft
  whitepaper.md         # locked after approval
  characters/           # character cards
  plot/                 # outline, foreshadowing
  scenes/               # chNN.brief.md
  chapters/             # drafts and finals
  reviews/              # chNN.json editor reviews
```
