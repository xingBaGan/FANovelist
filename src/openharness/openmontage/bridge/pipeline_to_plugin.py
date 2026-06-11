"""Compile OpenMontage pipelines into a single OpenHarness LoadedPlugin.

The output is the same shape that ``openharness.plugins.loader.load_plugins``
returns from a disk-based plugin, so the QueryEngine treats this bridge
as a first-class plugin. That means:

* Each pipeline becomes a slash command (``/montage_talking-head``) the
  user can invoke from the OpenHarness TUI.
* Each pipeline also becomes an :class:`AgentDefinition` so the model can
  be spawned as a subagent constrained to that pipeline's tool whitelist.
* Every OpenMontage skill is registered as an OpenHarness
  :class:`SkillDefinition` so ``SkillTool`` can read them by their
  path-like names (``pipelines/talking-head/asset-director``).
* Every OpenMontage tool is exposed as an adapter tool with the ``om_``
  prefix so it doesn't collide with native OpenHarness tools.

Hooks aren't wired here on purpose; see
:mod:`openharness.openmontage.bridge.hooks` and the harness ``CLI``
integration point in :mod:`openharness.openmontage.bridge.cli`.
"""

from __future__ import annotations

import logging
from dataclasses import replace
from pathlib import Path
from typing import Any, Iterable

import yaml

from openharness.coordinator.agent_definitions import AgentDefinition
from openharness.openmontage import PACKAGE_ROOT
from openharness.openmontage.bridge.tool_adapter import (
    OMToolAdapter,
    adapt_all_tools,
)
from openharness.openmontage.bridge.stage_tool import OmEnterStageTool
from openharness.openmontage.native import TtsSelectorNativeTool
from openharness.plugins.schemas import PluginManifest
from openharness.plugins.types import LoadedPlugin, PluginCommandDefinition
from openharness.skills._frontmatter import parse_skill_metadata
from openharness.skills.types import SkillDefinition

logger = logging.getLogger(__name__)

PIPELINES_DIR = PACKAGE_ROOT / "pipelines"
SKILLS_DIR = PACKAGE_ROOT / "skills"
AGENT_SKILLS_DIR = PACKAGE_ROOT / "agents_skills"


# ---------------------------------------------------------------------------
# Skill loading (custom — OpenMontage skills don't use SKILL.md layout)
# ---------------------------------------------------------------------------


_SKIP_NAMES = {"INDEX.MD", "PROVENANCE.MD", "README.MD", "CHANGELOG.MD"}


def _load_openmontage_skills(
    base: Path,
    source: str,
    *,
    skill_md_only: bool = False,
    disable_model_invocation: bool = False,
) -> list[SkillDefinition]:
    """Load skills from an OpenMontage skill tree.

    Two loading modes are supported:

    ``skill_md_only=False`` (default — Layer-2 ``skills/`` tree)
        Every ``*.md`` file is a skill entry.  Used for ``skills/`` where
        each director file is its own addressable skill
        (e.g. ``pipelines/clip-factory/idea-director``).

    ``skill_md_only=True`` (Layer-3 ``agents_skills/`` tree)
        Only ``SKILL.md`` files at the *first level of each sub-package* are
        treated as skill entry points.  Companion reference documents
        (``references/*.md``, ``examples/*.md``, …) live *inside* that
        package and are not individually listed — the model loads the whole
        package via ``skill(name="…")``.  This avoids inflating the system
        prompt listing with hundreds of internal reference docs.
    """
    skills: list[SkillDefinition] = []
    if not base.is_dir():
        return skills

    if skill_md_only:
        # One level deep: <base>/<pkg>/SKILL.md
        for pkg_dir in sorted(base.iterdir()):
            if not pkg_dir.is_dir():
                continue
            skill_path = pkg_dir / "SKILL.md"
            if not skill_path.exists():
                continue
            content = skill_path.read_text(encoding="utf-8")
            rel = pkg_dir.relative_to(base)
            default_name = "/".join(rel.parts)
            meta = parse_skill_metadata(default_name, content)
            name = str(meta["name"]) or default_name
            description = str(meta["description"]) or default_name
            skills.append(
                SkillDefinition(
                    name=name,
                    description=description,
                    content=content,
                    source=source,
                    path=str(skill_path),
                    base_dir=str(pkg_dir),
                    command_name=pkg_dir.name,
                    display_name=name if name != default_name else None,
                    disable_model_invocation=disable_model_invocation,
                )
            )
        return skills

    # Full rglob walk for flat skill trees (Layer-2 directors)
    for path in sorted(base.rglob("*.md")):
        if path.name.upper() in _SKIP_NAMES:
            continue
        content = path.read_text(encoding="utf-8")
        rel = path.relative_to(base).with_suffix("")
        default_name = "/".join(rel.parts)
        meta = parse_skill_metadata(default_name, content)
        name = str(meta["name"]) or default_name
        description = str(meta["description"]) or default_name
        skills.append(
            SkillDefinition(
                name=name,
                description=description,
                content=content,
                source=source,
                path=str(path),
                base_dir=str(path.parent),
                command_name=path.stem,
                display_name=name if name != default_name else None,
                disable_model_invocation=disable_model_invocation,
            )
        )
    return skills


# ---------------------------------------------------------------------------
# Pipeline -> AgentDefinition + slash command
# ---------------------------------------------------------------------------


def _required_tools(manifest: dict[str, Any]) -> list[str]:
    """Collect every tool a pipeline mentions (preferred + optional + per-stage)."""
    out: set[str] = set()
    for key in ("preferred_tools", "fallback_tools", "tools_available"):
        out.update(manifest.get(key, []) or [])
    for stage in manifest.get("stages", []) or []:
        for key in ("required_tools", "optional_tools", "tools_available"):
            out.update(stage.get(key, []) or [])
    return sorted(out)


def _pipeline_skill_refs(manifest: dict[str, Any]) -> list[str]:
    """Return every skill reference a pipeline mentions, in display order."""
    refs: list[str] = []
    seen: set[str] = set()

    def _add(value: Any) -> None:
        if isinstance(value, str) and value and value not in seen:
            seen.add(value)
            refs.append(value)

    _add((manifest.get("orchestration") or {}).get("skill"))
    for required in manifest.get("required_skills", []) or []:
        _add(required)
    for stage in manifest.get("stages", []) or []:
        _add(stage.get("skill"))
    return refs


def _build_command_content(manifest: dict[str, Any]) -> str:
    """Render the slash command prompt that triggers the pipeline agent."""
    name = manifest.get("name", "<unnamed>")
    description = (manifest.get("description") or "").strip()
    orchestration_skill = (manifest.get("orchestration") or {}).get("skill")
    stage_skills = [
        f"  - `{stage.get('name')}` -> skill `{stage.get('skill')}`"
        for stage in manifest.get("stages", []) or []
        if stage.get("skill")
    ]

    lines: list[str] = [
        f"# /montage_{name} — Run the OpenMontage `{name}` pipeline",
        "",
        f"**Description**: {description or '(no description)'}",
        "",
        "## Operating contract",
        "",
        "1. **Read the executive-producer skill first** via the `skill` tool: "
        f"`{orchestration_skill or 'pipelines/' + str(name) + '/executive-producer'}`.",
        "2. Walk the stages in declaration order. Before doing any work in a "
        "stage: (a) call `om_enter_stage` with `{\"stage\": \"<stage_name>\", "
        "\"pipeline\": \"" + str(name) + "\"}` so the checkpoint hook can "
        "attribute artifacts, then (b) load that stage's director skill via `skill`.",
        "3. Use OpenMontage tools via their **bridge names**, prefixed with "
        "`om_` (e.g. `om_video_compose`, `om_transcriber`). The original sync "
        "contract is preserved — pass the OM-flavored args under `inputs`.",
        "4. After each stage, write a checkpoint via the bundled "
        "checkpoint hook (auto-fired) and present the artifact summary to "
        "the user for approval, per OpenMontage's checkpoint protocol.",
        "5. NEVER skip a stage, NEVER bypass the director skill, and NEVER "
        "invent a tool name. If a required tool is missing, surface a "
        "structured blocker.",
        "",
        "## Stage map",
        "",
        *(stage_skills or ["  (manifest has no declared stages)"]),
        "",
        "User prompt below:",
        "",
        "{{ARGS}}",
    ]
    return "\n".join(lines)


def _build_agent_definition(
    manifest: dict[str, Any],
    *,
    tool_names: set[str],
) -> AgentDefinition:
    """Build an AgentDefinition that bounds the model to the pipeline."""
    name = manifest.get("name", "unnamed")
    description = (
        (manifest.get("description") or "").strip()
        or f"OpenMontage pipeline `{name}` orchestrator."
    )
    pipeline_tools = _required_tools(manifest)
    allowed_tools = sorted(
        {f"om_{tool}" for tool in pipeline_tools if f"om_{tool}" in tool_names}
    )
    # Keep harness primitives the agent always needs (file IO + skill + ask).
    allowed_tools.extend(
        sorted(
            {
                "read_file",
                "write_file",
                "edit_file",
                "glob",
                "grep",
                "skill",
                "ask_user_question",
                "bash",
                "todo_write",
            }
        )
    )
    skill_refs = _pipeline_skill_refs(manifest)
    return AgentDefinition(
        name=f"montage-{name}",
        description=description,
        system_prompt=None,
        tools=allowed_tools,
        skills=skill_refs,
        permission_mode="default",
        max_turns=64,
        filename=str(PIPELINES_DIR / f"{name}.yaml"),
    )


def _build_commands(
    manifests: Iterable[dict[str, Any]],
    *,
    tool_names: set[str],
) -> tuple[list[PluginCommandDefinition], list[AgentDefinition]]:
    commands: list[PluginCommandDefinition] = []
    agents: list[AgentDefinition] = []
    for manifest in manifests:
        name = manifest.get("name") or "unnamed"
        description = (manifest.get("description") or "").strip() or f"Run the `{name}` pipeline."
        commands.append(
            PluginCommandDefinition(
                name=f"montage_{name}",
                description=description,
                content=_build_command_content(manifest),
                path=str(PIPELINES_DIR / f"{name}.yaml"),
                source="plugin:openmontage",
                base_dir=str(PIPELINES_DIR),
                argument_hint='"<creative prompt>"',
                when_to_use=description,
                version=str(manifest.get("version") or "0.0.0"),
                user_invocable=True,
                display_name=f"OpenMontage: {name}",
            )
        )
        agents.append(_build_agent_definition(manifest, tool_names=tool_names))
    return commands, agents


def _load_manifests() -> list[dict[str, Any]]:
    manifests: list[dict[str, Any]] = []
    if not PIPELINES_DIR.is_dir():
        return manifests
    for path in sorted(PIPELINES_DIR.glob("*.yaml")):
        try:
            with open(path, encoding="utf-8") as fh:
                manifest = yaml.safe_load(fh) or {}
        except yaml.YAMLError as exc:
            logger.warning("Skipping malformed pipeline manifest %s: %s", path, exc)
            continue
        if not isinstance(manifest, dict):
            logger.warning("Skipping non-mapping pipeline manifest %s", path)
            continue
        manifest.setdefault("name", path.stem)
        manifests.append(manifest)
    return manifests


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


READ_ONLY_TOOL_NAMES = {
    # Analysis-only tools — the adapter marks them read-only so OpenHarness
    # permission checks can skip the slow "are you sure?" gate. Add new
    # safe-by-default tools here as you bring them online.
    "video_analyzer",
    "video_understand",
    "scene_detect",
    "frame_sampler",
    "face_tracker",
    "audio_probe",
    "audio_energy",
    "transcript_fetcher",
    "transcriber",
    "composition_validator",
}


def build_plugin(*, enabled: bool = True) -> LoadedPlugin:
    """Build the OpenMontage plugin out of the live subpackage on disk.

    Pure function: re-running it returns an equivalent plugin. The
    returned plugin is intentionally *not* serialized to disk; the
    harness can consume it directly when constructing its plugin set.
    """
    adapters: list[OMToolAdapter] = adapt_all_tools(
        discover=True,
        read_only_names={f"om_{name}" for name in READ_ONLY_TOOL_NAMES} | READ_ONLY_TOOL_NAMES,
    )
    # Mark the matching adapters read-only after construction so callers
    # see consistent behavior regardless of how they constructed them.
    for adapter in adapters:
        bare = adapter.om_tool.name
        if bare in READ_ONLY_TOOL_NAMES:
            adapter._read_only = True  # noqa: SLF001 — internal field, deliberately mutable
    native_tools = [TtsSelectorNativeTool(), OmEnterStageTool()]
    all_tools: list[Any] = [*adapters, *native_tools]
    tool_names = {tool.name for tool in all_tools}

    manifests = _load_manifests()
    commands, agents = _build_commands(manifests, tool_names=tool_names)

    # Layer-2: pipeline directors (skills/) — core/ and meta/ entries appear in the
    # system prompt listing; pipelines/* directors are hidden (disable_model_invocation)
    # so they don't flood the listing, but remain accessible via the skill tool when
    # an executive-producer agent needs to load them at runtime.
    layer2_core = [
        replace(skill, disable_model_invocation=True)
        if skill.name.startswith("pipelines/")
        else skill
        for skill in _load_openmontage_skills(
            SKILLS_DIR,
            source="plugin:openmontage",
            skill_md_only=False,
            disable_model_invocation=False,
        )
    ]

    # Layer-3: agent skill packages (agents_skills/) — only SKILL.md entry points.
    # These are NOT listed in the system prompt because each om_* tool's description
    # already declares "Layer-3 skills: <name>" telling the model which ones to load
    # on demand via `skill(name="...")`.  Keeping them hidden avoids 68 extra listing
    # entries while still making them accessible through the skill tool.
    layer3 = _load_openmontage_skills(
        AGENT_SKILLS_DIR,
        source="plugin:openmontage",
        skill_md_only=True,
        disable_model_invocation=True,
    )

    skills = layer2_core + layer3

    manifest = PluginManifest(
        name="openmontage",
        version="0.1.0",
        description=(
            "OpenMontage video production pipelines, tools, and skills hosted "
            "inside OpenHarness. Bridges sync OM BaseTools as async OH tools."
        ),
        enabled_by_default=enabled,
    )

    return LoadedPlugin(
        manifest=manifest,
        path=PACKAGE_ROOT,
        enabled=enabled,
        skills=skills,
        commands=commands,
        agents=agents,
        tools=all_tools,
        hooks={},
        mcp_servers={},
    )


def update_plugin_enabled(plugin: LoadedPlugin, enabled: bool) -> LoadedPlugin:
    """Return a copy of ``plugin`` with the enabled flag flipped."""
    return replace(plugin, enabled=enabled)
