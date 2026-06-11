<h1 align="center">
  <img src="assets/logo.png" alt="OpenHarness" width="64" style="vertical-align: middle;">
  &nbsp;&nbsp;
  <img src="assets/ohmo.png" alt="ohmo" width="64" style="vertical-align: middle;">
  <br>
  <code>oh</code> — OpenHarness &amp; OpenMontage
</h1>

<p align="center">
  <a href="README.md"><strong>English</strong></a> ·
  <a href="README.zh-CN.md"><strong>简体中文</strong></a>
</p>

**OpenHarness** delivers core lightweight agent infrastructure: tool-use, skills, memory, and multi-agent coordination.

**OpenMontage** is a video production engine built on OpenHarness — YAML-driven pipelines that let an AI agent plan, generate, edit, and publish videos end-to-end. 87 production tools (image gen, video gen, TTS, FFmpeg, HyperFrames, Remotion…) integrated via a single bridge.

<p align="center">
  <a href="#-quick-start"><img src="https://img.shields.io/badge/Quick_Start-5_min-blue?style=for-the-badge" alt="Quick Start"></a>
  <a href="#-harness-architecture"><img src="https://img.shields.io/badge/Harness-Architecture-ff69b4?style=for-the-badge" alt="Architecture"></a>
  <a href="#-openmontage-video-pipelines"><img src="https://img.shields.io/badge/OpenMontage-Pipelines-orange?style=for-the-badge" alt="OpenMontage"></a>
  <a href="#-extending-yaml-workflows"><img src="https://img.shields.io/badge/Extend-YAML_Workflows-green?style=for-the-badge" alt="Extend"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/License-MIT-yellow?style=for-the-badge" alt="License"></a>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/python-≥3.10-blue?logo=python&logoColor=white" alt="Python">
  <img src="https://img.shields.io/badge/React+Ink-TUI-61DAFB?logo=react&logoColor=white" alt="React">
  <img src="https://img.shields.io/badge/pytest-114_pass-brightgreen" alt="Pytest">
  <img src="https://img.shields.io/badge/OM_Tools-87-orange" alt="OM Tools">
  <img src="https://img.shields.io/badge/Pipelines-13-purple" alt="Pipelines">
  <a href="https://github.com/HKUDS/OpenHarness/actions/workflows/ci.yml"><img src="https://github.com/HKUDS/OpenHarness/actions/workflows/ci.yml/badge.svg" alt="CI"></a>
</p>

<p align="center">
  <img src="assets/cli-typing.gif" alt="OpenHarness Terminal Demo" width="800">
</p>

---

## Table of Contents

- [Quick Start](#-quick-start)
- [Harness Architecture](#-harness-architecture)
- [OpenMontage Video Pipelines](#-openmontage-video-pipelines)
- [Extending YAML Workflows](#-extending-yaml-workflows)
- [Environment Variables](#-environment-variables)
- [Provider Compatibility](#-provider-compatibility)
- [Features](#-features)
- [Contributing](#-contributing)

---

## 🚀 Quick Start

### Install

```bash
# macOS / Linux / WSL
curl -fsSL https://raw.githubusercontent.com/HKUDS/OpenHarness/main/scripts/install.sh | bash
# or
pip install openharness-ai
```

```powershell
# Windows (PowerShell — use `openh` instead of `oh`)
iex (Invoke-WebRequest -Uri 'https://raw.githubusercontent.com/HKUDS/OpenHarness/main/scripts/install.ps1')
```

### Configure

```bash
oh setup    # interactive wizard — pick provider, authenticate, done
```

Supports **Claude / OpenAI / Codex / Moonshot(Kimi) / GLM / MiniMax / NVIDIA NIM** and any compatible endpoint.

### Run

```bash
oh                                    # interactive TUI
oh -p "Explain this codebase"         # single prompt → stdout
oh -p "Fix the bug" --output-format json
oh --dry-run                          # preview settings without executing
```

### Run a Video Pipeline

```bash
# Inside the OpenHarness TUI, trigger a pipeline with a slash command:
/montage_cinematic Make a 60-second cinematic teaser for our product launch
/montage_talking-head Record a talking-head explainer about climate change
/montage_short-form Create a viral TikTok clip from this YouTube link: ...
```

All 13 pipelines are available as `/montage_<name>` slash commands.

---

## 🏗️ Harness Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                      OpenHarness Core                        │
│                                                              │
│  engine/        Agent loop — stream → tool-call → loop       │
│  tools/         52 built-in tools (file, shell, web, MCP)    │
│  skills/        On-demand knowledge loading (.md files)       │
│  plugins/       Extension points (commands, hooks, agents)    │
│  permissions/   Multi-level safety, path rules, deny lists    │
│  coordinator/   Subagent spawning, team coordination          │
│  memory/        Persistent cross-session knowledge            │
│  prompts/       System prompt assembly, CLAUDE.md injection   │
│  ui/            React/Ink TUI + print/json/stream-json output │
│                                                              │
└──────────────────────────┬──────────────────────────────────┘
                           │  LoadedPlugin (bridge)
                           ▼
┌─────────────────────────────────────────────────────────────┐
│                  OpenMontage Bridge                           │
│                                                              │
│  bridge/pipeline_to_plugin.py   Compile pipelines → plugin   │
│  bridge/tool_adapter.py         Wrap sync OM tools → async    │
│  bridge/hooks.py                TraceHook / CheckpointHook   │
│  bridge/stage_tool.py           om_enter_stage (stage ctx)   │
│                                                              │
│  ┌──── 87 om_* Tools ────────────────────────────────────┐  │
│  │ om_flux_image  om_seedance_video  om_transcriber       │  │
│  │ om_video_compose  om_ffmpeg  om_remotion_caption_burn  │  │
│  │ om_elevenlabs_tts  om_music_gen  om_hyperframes_compose│  │
│  │ om_face_restore  om_upscale  om_bg_remove  …87 total   │  │
│  └────────────────────────────────────────────────────────┘  │
│                                                              │
│  3-Layer Knowledge Architecture:                             │
│    Layer 1: Tool Registry  (om_* tool names + descriptions)  │
│    Layer 2: skills/        (OpenMontage-specific workflows)   │
│    Layer 3: agents_skills/ (Provider-specific deep guides)   │
│                                                              │
│  13 YAML Pipelines → 13 /montage_* slash commands           │
│                    → 13 AgentDefinitions (tool allowlists)   │
└─────────────────────────────────────────────────────────────┘
```

### The Agent Loop

```python
while True:
    response = await api.stream(messages, tools)
    if response.stop_reason != "tool_use":
        break
    for tool_call in response.tool_uses:
        # Permission check → PreToolHook → Execute → PostToolHook → Result
        result = await harness.execute_tool(tool_call)
    messages.append(tool_results)
```

The model decides **what** to do. The harness handles **how** — safely, with full observability.

---

## 🎬 OpenMontage Video Pipelines

### How a Pipeline Run Works

```
User: /montage_cinematic Make a 60s teaser for our product launch
          │
          ▼
slash command injects Operating Contract + stage map into context
          │
          ▼
For each stage (research → proposal → script → scene → asset → edit → compose → publish):
  │
  ├─ 1. om_enter_stage({"stage": "research", "pipeline": "cinematic"})
  │       → CheckpointHook starts attributing artifacts to this stage
  │
  ├─ 2. skill(name="pipelines/cinematic/research-director")
  │       → Agent reads stage-director Markdown, knows exactly what to do
  │
  ├─ 3. om_video_analyzer / om_flux_image / om_seedance_video / …
  │       → OMToolAdapter → asyncio.to_thread → sync OM tool
  │       → TraceHook: appends record to trace.jsonl
  │       → CheckpointHook: writes checkpoints/{stage}.json with artifacts
  │       → CostHook: appends row to cost.csv
  │
  ├─ 4. skill(name="reviewer")
  │       → Agent self-reviews output against success_criteria in YAML
  │
  └─ 5. ask_user_question (if human_approval_default: true in YAML)
          → Human approval gate before moving to next stage
          │
          ▼
Final video output (mp4 / package / rendered composition)
```

### Available Pipelines

| Pipeline | Slash Command | Description |
|----------|---------------|-------------|
| `cinematic` | `/montage_cinematic` | Trailers, brand films, mood-led dramatic edits |
| `talking-head` | `/montage_talking-head` | Explainer videos with presenter + B-roll |
| `short-form` | `/montage_short-form` | TikTok / Reels / Shorts (9:16, 15–60s) |
| `documentary-montage` | `/montage_documentary-montage` | Long-form documentary style |
| `animation` | `/montage_animation` | Motion graphics with Remotion or HyperFrames |
| `animated-explainer` | `/montage_animated-explainer` | Step-by-step animated educational content |
| `avatar-spokesperson` | `/montage_avatar-spokesperson` | AI avatar as on-screen presenter |
| `screen-demo` | `/montage_screen-demo` | Screen recording with zoom + captions |
| `podcast-repurpose` | `/montage_podcast-repurpose` | Clip extraction from long audio/video |
| `clip-factory` | `/montage_clip-factory` | Multi-clip batch from a single source |
| `localization-dub` | `/montage_localization-dub` | Translate + re-dub in target language |
| `character-animation` | `/montage_character-animation` | SVG/rigged character animation |
| `hybrid` | `/montage_hybrid` | Custom mix of formats and techniques |

### 3-Layer Knowledge Architecture

```
Layer 1 — Tool Registry
  om_flux_image: "Generate images with FLUX. Layer-3 skills: flux-best-practices, bfl-api"
  om_seedance_video: "Generate video. Layer-3 skills: seedance-prompting, ai-video-gen"
  om_ffmpeg: "Trim/encode/composite video. Layer-3 skills: ffmpeg"
  …87 tools total, each declaring which Layer-3 skills they need

Layer 2 — skills/ (OpenMontage context)
  skills/meta/reviewer.md             ← self-review after every stage
  skills/meta/checkpoint-protocol.md  ← when/how to checkpoint
  skills/core/ffmpeg.md               ← FFmpeg usage in OM context
  skills/core/remotion.md             ← Remotion usage in OM context
  skills/pipelines/cinematic/research-director.md   ← stage-specific
  skills/pipelines/cinematic/asset-director.md      ← stage-specific
  …103 pipeline director skills (hidden from listing, loaded on-demand)

Layer 3 — agents_skills/ (provider-specific deep guides)
  agents_skills/flux-best-practices/SKILL.md   ← FLUX prompting mastery
  agents_skills/seedance-prompting/SKILL.md    ← Seedance cinematography
  agents_skills/ffmpeg/SKILL.md                ← FFmpeg parameter reference
  agents_skills/ai-video-gen/SKILL.md          ← universal video gen guide
  …68 packages, hidden from listing, loaded on tool-call when needed
```

> **Why 3 layers?** Layer 1 is always visible (tool descriptions). Layer 2 is listed in the system prompt for general guidance (50 skills). Layer 3 is hidden and pulled in on-demand when a tool declares it needs it — keeps the system prompt lean (16K chars vs. 92K if everything was listed).

### Tool Hooks (Auto-fired per Tool Call)

Every `om_*` tool call fires three hooks automatically:

| Hook | Output | Purpose |
|------|--------|---------|
| `TraceHook` | `run_dir/trace.jsonl` | Full input/output log per call |
| `CheckpointHook` | `run_dir/checkpoints/{stage}.json` | Artifact snapshot after each stage |
| `CostHook` | `run_dir/cost.csv` | Per-call cost tracking (USD) |

The hooks are bound via `contextvars` at session start — no configuration needed.

---

## 🔧 Extending YAML Workflows

### Pipeline YAML Anatomy

```yaml
name: my-pipeline          # Used as /montage_my-pipeline
version: "2.0"
description: >
  What this pipeline produces and when to use it.
category: custom           # cinematic | talking-head | animation | custom
stability: beta            # production | beta | experimental
default_checkpoint_policy: guided   # guided | auto | manual

orchestration:
  mode: executive-producer
  skill: pipelines/my-pipeline/executive-producer   # Layer-2 skill name
  budget_default_usd: 1.00
  max_revisions_per_stage: 3
  max_send_backs: 3
  max_wall_time_minutes: 15

extensions:
  custom_scripts: true
  custom_playbooks: true
  custom_skills: true
  custom_tools: false        # true only if you add new Python tool classes

required_skills:
  - pipelines/my-pipeline/executive-producer
  - pipelines/my-pipeline/idea-director
  - pipelines/my-pipeline/asset-director
  - pipelines/my-pipeline/compose-director
  - meta/reviewer            # always include — self-review gate
  - meta/checkpoint-protocol # always include — checkpoint instructions

stages:
  - name: idea
    skill: pipelines/my-pipeline/idea-director
    produces:
      - brief                # artifact keys your director will output
    tools_available:
      - web_search           # bare tool names (om_ prefix added automatically)
    checkpoint_required: true
    human_approval_default: true
    review_focus:
      - Brief is specific and actionable
      - Target audience and tone are clear
    success_criteria:
      - Schema-valid brief artifact produced

  - name: asset
    skill: pipelines/my-pipeline/asset-director
    required_artifacts_in:
      - brief
    produces:
      - assets_manifest
    required_tools:
      - flux_image
      - seedance_video
    optional_tools:
      - pexels_video
    checkpoint_required: true
    human_approval_default: false

  - name: compose
    skill: pipelines/my-pipeline/compose-director
    required_artifacts_in:
      - assets_manifest
    produces:
      - final_video
    required_tools:
      - video_compose
      - video_stitch
    checkpoint_required: true
    human_approval_default: true
```

### Step-by-Step: Add a New Pipeline

**1. Create the YAML manifest**

```bash
# Place it in the pipelines directory
cat > src/openharness/openmontage/pipelines/my-pipeline.yaml << 'EOF'
name: my-pipeline
version: "2.0"
description: My custom video pipeline
# ... (see anatomy above)
EOF
```

**2. Create stage director skills**

Each stage listed in `required_skills` needs a corresponding Markdown file:

```bash
mkdir -p src/openharness/openmontage/skills/pipelines/my-pipeline
```

```markdown
<!-- skills/pipelines/my-pipeline/idea-director.md -->
---
name: pipelines/my-pipeline/idea-director
description: Idea Director for My Pipeline. Develop the creative brief.
---

# Idea Director — My Pipeline

## Your Role
You are the Idea Director. Your job is to produce a `brief` artifact containing...

## Inputs
- User's request (from the slash command prompt)

## Workflow
1. Ask the user these clarifying questions: ...
2. Research the topic using `web_search`
3. Produce a `brief` JSON artifact with fields: title, target_audience, tone, ...

## Success Criteria
- brief.title is specific (not generic)
- brief.target_audience names a concrete demographic
- brief.tone is one of: educational | entertaining | inspiring | cinematic

## Artifact Schema
```json
{
  "title": "string",
  "target_audience": "string",
  "tone": "string",
  "key_messages": ["string"],
  "duration_seconds": "number"
}
```
```

**3. Create the executive-producer skill** (orchestration entry point)

```markdown
<!-- skills/pipelines/my-pipeline/executive-producer.md -->
---
name: pipelines/my-pipeline/executive-producer
description: Executive Producer for My Pipeline. Orchestrates all stages.
---

# Executive Producer — My Pipeline

## Pipeline Overview
This pipeline produces [your output] in [N] stages.

## Stage Sequence
1. **idea** — creative brief
2. **asset** — generate visual/audio assets
3. **compose** — assemble final video

## Operating Rules
- Read each stage-director skill before starting that stage
- Always call `om_enter_stage` at the beginning of each stage
- Always call `skill(name="reviewer")` before checkpointing
- Ask for human approval at stages where `human_approval_default: true`
```

**4. Verify the pipeline loads**

```bash
uv run python3 -c "
from openharness.openmontage.bridge.pipeline_to_plugin import build_plugin
p = build_plugin()
commands = [c.name for c in p.commands]
print('my-pipeline registered:', 'montage_my-pipeline' in commands)
"
```

**5. Test it**

```bash
uv run oh --dry-run -p "/montage_my-pipeline test run"
# Then launch interactively:
uv run oh
# Type: /montage_my-pipeline Make me a test video
```

### Customizing Existing Pipelines

You can override pipeline behavior without editing the source YAML by using the `extensions` flags:

| Extension | What it enables |
|-----------|----------------|
| `custom_scripts: true` | Drop `.py` scripts into a `scripts/` folder alongside the YAML |
| `custom_playbooks: true` | Add a `playbook.yaml` with visual style overrides |
| `custom_skills: true` | Add extra Markdown skills the EP can reference |
| `custom_tools: false` | New Python tool classes (requires bridge code changes) |

### Adding a Tool to a Pipeline

Tools listed in `required_tools` / `optional_tools` / `tools_available` use **bare OM names** (without the `om_` prefix). The bridge adds it automatically.

```yaml
# In your stage:
required_tools:
  - flux_image           # becomes om_flux_image
  - seedance_video       # becomes om_seedance_video
  - video_compose        # becomes om_video_compose
optional_tools:
  - pexels_video         # om_pexels_video — used if Pexels key is set
```

To see all available tool names:

```bash
uv run python3 -c "
from openharness.openmontage.bridge.pipeline_to_plugin import build_plugin
p = build_plugin()
for t in sorted(t.name for t in p.tools):
    print(t)
"
```

### Pipeline Checkpoint Protocol

Every stage runs this sequence automatically:

```
om_enter_stage({"stage": "idea", "pipeline": "my-pipeline"})
  → sets session.stage so CheckpointHook knows which stage we're in

[... agent works, calls om_* tools ...]
  → CheckpointHook writes run_dir/checkpoints/idea.json after each tool call

skill(name="reviewer")
  → agent self-reviews against YAML success_criteria

[if human_approval_default: true]
  → ask_user_question("Stage 'idea' complete. Approve to continue?")

[next stage begins]
```

Checkpoints are stored at:
```
~/.openharness/runs/<run_id>/
  trace.jsonl          # full per-call log
  cost.csv             # USD cost per tool call
  checkpoints/
    idea.json
    asset.json
    compose.json
  artifact_diff.jsonl  # artifact delta per call
```

---

## 🌍 Environment Variables

OpenMontage tools read API keys from the **project root `.env`** file (priority order):

1. `$OPENMONTAGE_ENV_FILE` — override path if set
2. Repo root `.env` — **primary** (`/path/to/OpenHarness/.env`)
3. `src/openharness/openmontage/.env` — legacy fallback (standalone OM use)

Variables already in `os.environ` are never overridden.

### Required by Category

```bash
# ── Image Generation ──────────────────────────────────────────
FAL_KEY=                      # FLUX, Recraft, Kling, MiniMax, Veo via fal.ai
GOOGLE_API_KEY=               # Google Imagen + Cloud TTS
OPENAI_API_KEY=               # DALL-E + OpenAI TTS fallback
XAI_API_KEY=                  # Grok image/video generation
IMAGE_GENERATION_API_KEY=     # OpenAI-compatible image gateway key
IMAGE_GENERATION_BASE_URL=    # e.g. https://api.siliconflow.cn/v1
IMAGE_GENERATION_MODEL=       # e.g. Kwai-Kolors/Kolors
COMFYUI_BACKEND_URL=          # Local ComfyUI (http://192.168.0.112:8190)

# ── Video Generation ──────────────────────────────────────────
HEYGEN_API_KEY=               # VEO / Sora / Runway / Kling / Seedance via HeyGen
RUNWAY_API_KEY=               # Runway Gen-4 direct API
VIDEO_GEN_LOCAL_ENABLED=true  # Enable local GPU video gen
VIDEO_GEN_LOCAL_MODEL=        # wan2.1-1.3b | hunyuan-1.5 | ltx2-local

# ── Voice & Audio ─────────────────────────────────────────────
ELEVENLABS_API_KEY=           # TTS narration, music, sound effects
DOUBAO_SPEECH_API_KEY=        # Volcengine Doubao TTS
SUNO_API_KEY=                 # Suno AI music generation

# ── Stock Media ───────────────────────────────────────────────
PEXELS_API_KEY=               # Stock footage/images (free tier available)
PIXABAY_API_KEY=              # Stock footage/images (free tier available)
UNSPLASH_ACCESS_KEY=          # Stock images (free developer key)

# ── Analysis ──────────────────────────────────────────────────
HF_TOKEN=                     # HuggingFace — speaker diarization in transcriber
```

See [`src/openharness/openmontage/.env.example`](src/openharness/openmontage/.env.example) for the full list with comments.

---

## 🔌 Provider Compatibility

OpenHarness treats providers as **workflow profiles**:

```bash
oh setup                      # interactive wizard
oh provider list              # list saved profiles
oh provider use <profile>     # switch active profile
```

### Built-in Workflows

| Workflow | API Format | Typical Backends |
|----------|------------|-----------------|
| Anthropic-Compatible | `anthropic` | Claude, Kimi, GLM, MiniMax |
| OpenAI-Compatible | `openai` | OpenAI, OpenRouter, DeepSeek, SiliconFlow, Ollama |
| Claude Subscription | `claude` | Local `~/.claude/.credentials.json` |
| Codex Subscription | `codex` | Local `~/.codex/auth.json` |
| GitHub Copilot | `copilot` | GitHub device-flow OAuth |

### Common Backends

| Backend | Base URL | Models |
|---------|----------|--------|
| Claude | `https://api.anthropic.com` | `claude-sonnet-4-6`, `claude-opus-4-6` |
| Moonshot/Kimi | `https://api.moonshot.cn/anthropic` | `kimi-k2.5` |
| OpenAI | `https://api.openai.com/v1` | `gpt-5.4`, `gpt-4.1` |
| DeepSeek | `https://api.deepseek.com` | `deepseek-chat`, `deepseek-reasoner` |
| SiliconFlow | `https://api.siliconflow.cn/v1` | `deepseek-ai/DeepSeek-V3` |
| Google Gemini | `https://generativelanguage.googleapis.com/v1beta/openai` | `gemini-2.5-flash` |
| Ollama (local) | `http://localhost:11434/v1` | any local model |

---

## ✨ Features

### 🔧 Tools (52 built-in + 87 OpenMontage)

| Category | Tools |
|----------|-------|
| **File I/O** | bash, read_file, write_file, edit_file, glob, grep |
| **Search** | web_fetch, web_search, tool_search, lsp |
| **Agent** | agent, send_message, team_create/delete |
| **Task** | task_create/get/list/update/stop/output |
| **MCP** | mcp_auth + configured servers |
| **Workflow** | enter_plan_mode, enter_worktree, cron_* |
| **Meta** | skill, config, brief, sleep, ask_user_question |
| **OM: Image** | om_flux_image, om_image_gen, om_grok_image, om_openai_image, om_pexels_image… |
| **OM: Video** | om_seedance_video, om_kling_video, om_heygen_video, om_veo_video, om_ltx_video_local… |
| **OM: Audio** | om_transcriber, om_elevenlabs_tts, om_music_gen, om_audio_mixer… |
| **OM: Edit** | om_video_compose, om_video_stitch, om_video_trimmer, om_ffmpeg, om_color_grade… |
| **OM: Enhance** | om_face_restore, om_upscale, om_bg_remove, om_face_enhance… |

### 📚 Skills System

Skills are **on-demand knowledge** loaded only when the model needs them:

```
System prompt shows 50 skills (16K chars)
─────────────────────────────────────────
meta/reviewer         ← self-review after every stage
meta/checkpoint-protocol
meta/onboarding
core/ffmpeg           ← always visible: "when to use FFmpeg"
core/whisperx
core/remotion
core/hyperframes
creative/storytelling ← visible: "how to structure narratives"
creative/video-editing
…
─────────────────────────────────────────
103 pipeline director skills   → hidden, loaded via skill(name="...")
 68 Layer-3 provider guides    → hidden, declared by tools, loaded on-demand
```

Skills can live in user, project, or plugin locations:
```
~/.openharness/skills/<skill>/SKILL.md   ← user-level
<project>/.agents/skills/<skill>/SKILL.md ← project-level
```

### 🛡️ Permissions

| Mode | Behavior | Use Case |
|------|----------|----------|
| **Default** | Ask before write/execute | Daily development |
| **Auto** | Allow everything | Sandboxed environments |
| **Plan Mode** | Block all writes | Design before coding |

### 🖥️ Terminal UI

- Command picker: Type `/` → arrow keys → Enter
- Permission dialogs with tool details
- Real-time animated spinner during execution
- Session resume with `/resume`
- Markdown rendering in assistant messages

### 📡 Non-Interactive Mode

```bash
oh -p "Explain this codebase"                        # text output
oh -p "List all functions" --output-format json      # structured JSON
oh -p "Fix the bug" --output-format stream-json      # streaming events
oh --dry-run -p "/montage_cinematic test"            # preview without executing
```

---

## 🔧 Extending OpenHarness

### Add a Custom Tool

```python
from pydantic import BaseModel, Field
from openharness.tools.base import BaseTool, ToolExecutionContext, ToolResult

class MyToolInput(BaseModel):
    query: str = Field(description="Search query")

class MyTool(BaseTool):
    name = "my_tool"
    description = "Does something useful"
    input_model = MyToolInput

    async def execute(self, arguments: MyToolInput, context: ToolExecutionContext) -> ToolResult:
        return ToolResult(output=f"Result for: {arguments.query}")
```

### Add a Custom Skill

Create `~/.openharness/skills/my-skill/SKILL.md`:

```markdown
---
name: my-skill
description: Expert guidance for my specific domain
---

# My Skill

## When to use
Use when the user asks about [your domain].

## Workflow
1. Step one
2. Step two
```

Run it as `/my-skill` from the TUI.

### Add a Plugin

Create `.openharness/plugins/my-plugin/.claude-plugin/plugin.json`:

```json
{
  "name": "my-plugin",
  "version": "1.0.0",
  "description": "My custom plugin"
}
```

Add `commands/*.md`, `hooks/hooks.json`, `agents/*.md`.

---

## 📊 Test Results

| Suite | Tests | Status |
|-------|-------|--------|
| Unit + Integration | 114 | ✅ All passing |
| CLI Flags E2E | 6 | ✅ Real model calls |
| Harness Features E2E | 9 | ✅ Retry, skills, parallel, permissions |
| React TUI E2E | 3 | ✅ Welcome, conversation, status |
| Real Skills + Plugins | 12 | ✅ anthropics/skills + claude-code/plugins |

```bash
uv run pytest -q                           # 114 unit/integration
python scripts/test_harness_features.py    # Harness E2E
python scripts/test_real_skills_plugins.py # Real plugins E2E
```

---

## 🤝 Contributing

```bash
git clone https://github.com/HKUDS/OpenHarness.git
cd OpenHarness
uv sync --extra dev
uv run pytest -q
```

| Area | Examples |
|------|---------|
| **New Pipelines** | YAML manifests + stage director skills |
| **Tools** | New `BaseTool` subclasses for specific domains |
| **Skills** | Domain knowledge `.md` files |
| **Plugins** | Workflow plugins with commands, hooks, agents |
| **Providers** | Support for more LLM backends |

See [`CONTRIBUTING.md`](CONTRIBUTING.md) · [`CHANGELOG.md`](CHANGELOG.md) · [`docs/SHOWCASE.md`](docs/SHOWCASE.md)

---

## 🔧 Troubleshooting

**Backspace in macOS Terminal.app** — If Backspace inserts characters instead of deleting, upgrade OpenHarness or use iTerm2/Warp.

**Windows** — Use `openh` instead of `oh` (PowerShell's `Oh` resolves to `Out-Host`).

**Web search unreachable** — Point to a custom endpoint:
```bash
export OPENHARNESS_WEB_SEARCH_URL="https://your-searxng.example/search"
export OPENHARNESS_WEB_PROXY="http://127.0.0.1:7890"
```

---

## 📄 License

MIT — see [LICENSE](LICENSE).

---

<p align="center">
  <img src="assets/logo.png" alt="OpenHarness" width="48">
  <br>
  <strong>Oh my Harness!</strong>
  <br>
  <em>The model is the agent. The code is the harness.</em>
</p>

<div align="center">
  <a href="https://star-history.com/#HKUDS/OpenHarness&Date">
    <picture>
      <source media="(prefers-color-scheme: dark)" srcset="https://api.star-history.com/svg?repos=HKUDS/OpenHarness&type=Date&theme=dark" />
      <source media="(prefers-color-scheme: light)" srcset="https://api.star-history.com/svg?repos=HKUDS/OpenHarness&type=Date" />
      <img alt="Star History Chart" src="https://api.star-history.com/svg?repos=HKUDS/OpenHarness&type=Date" style="border-radius: 15px; box-shadow: 0 0 30px rgba(0, 217, 255, 0.3);" />
    </picture>
  </a>
</div>

<p align="center">
  <em>Thanks for visiting ✨ OpenHarness!</em><br><br>
  <img src="https://visitor-badge.laobi.icu/badge?page_id=HKUDS.OpenHarness&style=for-the-badge&color=00d4ff" alt="Views">
</p>
