---
name: "pipelines/framework-smoke/executive-producer"
description: "Executive Producer — Framework Smoke Pipeline. A minimal 2-stage orchestrator (research → script) used to exercise the OpenMontage framework contracts (slash command, om_enter_stage, checkpoint hook, trace/cost hooks, human-approval gate) end-to-end. NOT a production pipeline — artifacts are deliberately minimal placeholders, not schema-perfect cinematic deliverables."
when_to_use: "When the agent needs guidance for: executive producer — framework smoke pipeline."
---

# Executive Producer — Framework Smoke Pipeline

## When to Use

You are the EP for the `framework-smoke` pipeline. This pipeline exists to
**verify the OpenMontage framework is wired up correctly** — not to produce a
real video. There are zero `tools_available` on either stage, no per-stage
director skills, and the artifact content is intentionally trivial.

A successful smoke run proves all of these are intact:

- The `/montage_framework-smoke` slash command loads this EP skill.
- `om_enter_stage` accepts `stage` / `pipeline` and is recognised by
  `CheckpointHook`.
- The agent can sequence stages in manifest order.
- The human-approval gate fires (both stages have
  `human_approval_default: true`).
- A run directory is created with `trace.jsonl`, `cost.csv`,
  `artifact_diff.jsonl`, and `checkpoints/`.

If the user wants a real video, refuse this pipeline and redirect them to
`cinematic`, `explainer`, `documentary-montage`, etc.

## Prerequisites

| Layer | Resource | Purpose |
|-------|----------|---------|
| Manifest | `pipelines/framework-smoke.yaml` | Stage definitions |
| Meta skill | `meta/checkpoint-protocol` | Checkpoint + approval flow |
| Native tool | `om_enter_stage` | Stage attribution |
| Native tools | `write_file`, `read_file` | Persist toy artifacts to disk |

## Stages

The manifest declares exactly two stages in this order:

1. `research` → produces `research_brief`
2. `script` (requires `research_brief`) → produces `script`

Both have `checkpoint_required: true` and `human_approval_default: true`.

## Execution Protocol

For **each** stage, in declaration order:

1. **Enter the stage** — call `om_enter_stage` with:

   ```json
   {"stage": "<stage_name>", "pipeline": "framework-smoke"}
   ```

   Confirm the tool returned `{"ok": true, ...}`.

2. **Produce the artifact** — write a minimal placeholder JSON to
   `./artifacts/framework-smoke/<stage>/<artifact_name>.json` using
   `write_file`. Use the templates in the next section. These deliberately do
   **not** satisfy the production `research_brief` / `script` JSON schemas —
   the smoke test only validates framework wiring, not artifact content. If a
   future hook starts strict-validating, swap in real schema-valid stubs.

3. **Follow `meta/checkpoint-protocol`** — load it once at the start of the
   run (you may have already), then for each stage:
   - State the artifact summary to the user (1–3 lines).
   - State that this is a smoke-test artifact (so the user does not mistake it
     for a real deliverable).
   - Ask: **"Approve `<stage>` artifact and continue to next stage?
     [yes / revise]"**
   - Only proceed after explicit `yes`. On `revise`, edit the file and
     re-ask.

4. **Move to the next stage** — repeat from step 1, or finish if the last
   stage just completed.

After the final stage, present the **smoke report**:

- Number of stages completed.
- Run directory path (look it up from `current_session().run_dir`, or, if not
  exposed, from `.openharness/montage/runs/` — newest folder).
- List the files inside that run directory and confirm `trace.jsonl`,
  `artifact_diff.jsonl`, `cost.csv`, and `checkpoints/` all exist.
- Final verdict: `framework-smoke: PASS` or `framework-smoke: FAIL — <reason>`.

## Toy Artifact Templates

### `research` stage

Write to `./artifacts/framework-smoke/research/research_brief.json`:

```json
{
  "version": "1.0",
  "topic": "framework-smoke",
  "research_date": "<today's date in YYYY-MM-DD>",
  "summary": "Smoke-test placeholder. The framework-smoke pipeline does not perform real research; this artifact exists only to verify that the research stage produced a file at the expected path.",
  "_smoke_test": true
}
```

### `script` stage

Write to `./artifacts/framework-smoke/script/script.json`:

```json
{
  "version": "1.0",
  "title": "framework-smoke",
  "total_duration_seconds": 1,
  "sections": [
    {
      "id": "smoke-1",
      "text": "Smoke-test placeholder script.",
      "start_seconds": 0,
      "end_seconds": 1
    }
  ],
  "_smoke_test": true
}
```

The `_smoke_test: true` marker makes it obvious these are not real
deliverables if anyone greps the workspace later.

## Stop Conditions

Halt the smoke run and surface a structured failure if **any** of these occur:

- `om_enter_stage` returns `{"ok": false, ...}` — record the error and stop.
- `write_file` cannot create the artifact path — record the error and stop.
- The user denies approval at a stage and asks to abort.
- More than 5 turns elapse without progress on a single stage (the smoke run
  should finish in a handful of turns; if it doesn't, something is wedged).

## Common Pitfalls

- **Don't run real research tools.** `tools_available: []` for both stages is
  intentional — calling `web_search`, `transcriber`, etc. defeats the smoke
  test's purpose and will pollute the cost log.
- **Don't skip the human-approval gate.** Both stages have
  `human_approval_default: true`. The gate is part of what we're testing.
- **Don't try to satisfy the production `research_brief` / `script` schemas.**
  Those require ≥3 existing_content, ≥5 sources, etc. — pointless padding for
  a smoke test. Use the templates above as-is.
- **Don't invent new stages.** The manifest is canonical: `research` then
  `script`, that's it.
