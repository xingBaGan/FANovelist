# Novel Studio Plugin (OpenHarness)

Six-agent novel writing workflow with human gates at whitepaper and chapter approval.

## Install in your novel project

```bash
# From your novel project root
mkdir -p .openharness/plugins
cp -R /path/to/OpenHarness/examples/novel-studio .openharness/plugins/novel-studio

# Seed studio workspace
mkdir -p studio/{characters,plot,scenes,chapters,reviews}
cp -R .openharness/plugins/novel-studio/studio-templates/* studio/

cd your-novel-project
oh plugin enable novel-studio
```

Create `.openharness/plugins/novel-studio/plugin.json` if missing:

```json
{
  "name": "novel-studio",
  "version": "0.1.0",
  "description": "Six-agent novel writing studio with human approval gates",
  "enabled_by_default": true
}
```

## Run

```bash
export CLAUDE_CODE_COORDINATOR_MODE=1
oh
```

Slash commands (plugin namespace):

| Command | Purpose |
|---------|---------|
| `/novel-studio:init` | Phase 1 — draft whitepaper |
| `/novel-studio:approve-whitepaper` | Human gate — lock whitepaper |
| `/novel-studio:chapter` | Phase 2 — scene brief → draft → review |
| `/novel-studio:approve-chapter` | Human gate — promote draft to final |

## Agent spawn names

| Role | `subagent_type` |
|------|-----------------|
| Showrunner | `novel-studio:showrunner:showrunner` |
| Character Director | `novel-studio:character-director:character-director` |
| Plot Architect | `novel-studio:plot-architect:plot-architect` |
| Scene Builder | `novel-studio:scene-builder:scene-builder` |
| Ghostwriter | `novel-studio:ghostwriter:ghostwriter` |
| Executive Editor | `novel-studio:executive-editor:executive-editor` |

## Project `CLAUDE.md` (recommended)

Add coordinator SOP: never write final chapters directly; use agents; respect `studio/whitepaper.md` after approval.
