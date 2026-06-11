# OpenMontage Bridge for OpenHarness

This file documents how OpenMontage runs as a subpackage of OpenHarness, the
two ways to write a tool here, and the standard debugging loop for a
pipeline run.

> **Why not edit `README.md`?** That file is the upstream OpenMontage README
> and is refreshed by `git subtree pull` from `calesthio/OpenMontage`. Keep
> bridge-specific docs in this file so the diff against upstream stays clean.

## Layout

```
src/openharness/openmontage/
├── tools/             # OpenMontage sync BaseTool classes (legacy contract)
├── lib/               # Shared OM utilities (checkpoint, scoring, ...)
├── schemas/           # Artifact / pipeline JSON schemas
├── pipelines/         # Pipeline YAML manifests (was `pipeline_defs/`)
├── skills/            # Layer-2 director skills with YAML frontmatter
├── agents_skills/     # Layer-3 SDK-style skills (was `.agents/skills/`)
├── styles/            # Style playbooks
├── bridge/
│   ├── tool_adapter.py        # OM sync BaseTool -> OH async BaseTool
│   ├── pipeline_to_plugin.py  # Pipelines + skills -> LoadedPlugin
│   ├── hooks.py               # trace / checkpoint / cost session hooks
│   └── cli.py                 # `oh montage ...` Typer sub-app
├── native/
│   └── tts_selector.py        # First native-OH port (Pydantic + async)
└── BRIDGE.md          # ← you are here
```

Tests live at the OpenHarness root: `tests/openmontage/{contracts,qa,tools,...}`.

## Two ways to write a tool

### 1. Adapter route (default for legacy tools)

Drop a sync `BaseTool` subclass in `tools/<group>/` exactly the way OpenMontage
upstream does it. The bridge automatically wraps it via `OMToolAdapter` so it
surfaces in OpenHarness as `om_<name>`. No further wiring is needed.

```python
# src/openharness/openmontage/tools/audio/foo_tts.py
from openharness.openmontage.tools.base_tool import BaseTool, ToolResult, ToolTier

class FooTts(BaseTool):
    name = "foo_tts"
    capability = "tts"
    provider = "foo"
    tier = ToolTier.VOICE

    def execute(self, inputs):
        ...
        return ToolResult(success=True, data={...}, cost_usd=0.012)
```

Pros: zero rewrite cost. Cons: the model sees a permissive `inputs` dict
with no per-field schema; harder for tool-use to pick the right keys.

### 2. Native route (preferred for high-value tools)

Subclass `openharness.tools.base.BaseTool` directly and declare a Pydantic
`input_model`. See `native/tts_selector.py` for the template:

```python
class TtsSelectorInput(BaseModel):
    text: str = Field(description="...")
    voice_id: str | None = None
    ...

class TtsSelectorNativeTool(BaseTool):
    name = "tts_native"
    input_model = TtsSelectorInput

    async def execute(self, arguments, context):
        ...
        return ToolResult(output=..., metadata={...})
```

Then add an instance to `native_tools` in
`bridge/pipeline_to_plugin.py::build_plugin`. The model now sees a rich
JSON schema with field descriptions, and the engine wraps your tool in
permission checks + hooks for free.

## Standard pipeline debugging loop

### a. Discover what runs

```bash
oh montage list                       # all pipelines
oh montage info talking-head          # stages, tools, skill refs for one pipeline
oh montage doctor                     # which tools are runnable now
```

### b. Debug a single tool

```bash
oh montage tool transcriber --inputs '{"video_path":"foo.mp4"}' --trace
```

`--trace` writes a fresh run dir under `.openharness/montage/runs/<id>/`:

| File | What it captures |
| --- | --- |
| `session.json` | pipeline name, pid, start time |
| `trace.jsonl` | one record per tool call (inputs, result, cost, ms) |
| `cost.csv` | one row per non-zero-cost call |
| `artifact_diff.jsonl` | added/removed artifacts after each call |
| `checkpoints/` | OpenMontage checkpoint files keyed by stage |

The trace file is replay-friendly: each line is self-contained JSON, with
secrets redacted automatically.

### c. Run the full pipeline

```bash
oh montage agent talking-head "make a 60s explainer about black holes"
```

This:

1. Builds the in-memory bridge plugin (tools + skills + commands +
   agents).
2. Monkey-patches `openharness.plugins.load_plugins` so OpenHarness
   normal discovery picks the bridge up alongside disk plugins.
3. Binds a `BridgeHookSession` to the current context so every adapter
   call writes to the run directory shown in stderr.
4. Delegates to `oh -p "/montage_<pipeline> <prompt>"` — the slash
   command compiled by `pipeline_to_plugin` triggers the agent.

### d. Inspect after a run

```bash
ls .openharness/montage/runs/<id>/
jq -r '. | "\(.stage // "?")\t\(.tool)\t\(.result.success)\t\(.elapsed_s)s"' \
  .openharness/montage/runs/<id>/trace.jsonl
tail .openharness/montage/runs/<id>/cost.csv
```

To replay a run with a new model, feed the recorded inputs from the
trace back into `oh montage tool <tool>` per call.

## Contract recap

| Surface | OpenMontage (legacy) | OpenHarness (native) |
| --- | --- | --- |
| Tool I/O | `execute(inputs: dict) -> ToolResult` (sync) | `async execute(args: BaseModel, ctx) -> ToolResult` |
| Result | rich dataclass: `data`, `artifacts`, `cost_usd`, `model`, `seed` | `output: str` + `metadata: dict` + `is_error: bool` |
| Schema | loose JSON dict | Pydantic with field-level docs |
| Skills | path-named `*.md` (Layer 2) + Layer-3 SDK skills | the same files; frontmatter generated by `scripts/add_skill_frontmatter.py` |
| Orchestration | external agent + YAML manifest | OpenHarness `QueryEngine` + agent definition compiled from manifest |
| Hooks | external (Cursor/Claude Code-side) | Python-native via `BridgeHookSession` |

## Skill-pulling new OpenMontage updates

```bash
git fetch openmontage-local
git subtree pull --prefix=src/openharness/openmontage openmontage-local main --squash
python scripts/rewrite_openmontage_imports.py
python scripts/fix_openmontage_test_roots.py
python scripts/add_skill_frontmatter.py
pytest tests/openmontage --ignore=tests/openmontage/qa
```

If upstream renames more dirs, extend the `REPLACEMENTS` in
`scripts/fix_openmontage_test_roots.py` and the top-level packages in
`scripts/rewrite_openmontage_imports.py`.

## What to port next

Once you're comfortable with `native/tts_selector.py`, the highest-value
next ports are:

1. `image_selector` — same shape, also wraps multiple OM providers.
2. `subtitle_gen` — small, isolated; great for learning the file-output
   pattern in the OH ToolResult.
3. `video_compose` — biggest impact, but 2k+ lines; do it last, in
   slices (start with the read-only `dry_run` path).

After every native port, add a brief acceptance test under
`tests/openmontage/native/`.
