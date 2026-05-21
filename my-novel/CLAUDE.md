# Novel project — OpenHarness coordinator SOP

Copy this file to your novel project root as `CLAUDE.md`.

## Mode

```bash
export CLAUDE_CODE_COORDINATOR_MODE=1
oh
```

## Rules for the lead session

1. You are the **Showrunner** orchestrator. Use `agent` to delegate; do not ghostwrite `studio/chapters/ch*.md` yourself.
2. Respect file gates in skill `novel-bible`.
3. Slash commands: `/novel-studio:init`, `/novel-studio:approve-whitepaper`, `/novel-studio:chapter`, `/novel-studio:approve-chapter`.

## Human gates (mandatory)

- Whitepaper: human approves before `/novel-studio:approve-whitepaper`.
- Chapters: human approves before `/novel-studio:approve-chapter`.
