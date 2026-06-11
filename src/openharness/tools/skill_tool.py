"""Tool for reading skill contents."""

from __future__ import annotations

from pydantic import BaseModel, Field

from openharness.skills import load_skill_registry
from openharness.tools.base import BaseTool, ToolExecutionContext, ToolResult


class SkillToolInput(BaseModel):
    """Arguments for skill lookup."""

    name: str = Field(description="Skill name")


class SkillTool(BaseTool):
    """Return the content of a loaded skill."""

    name = "skill"
    description = "Read a bundled, user, project, or plugin skill by name."
    input_model = SkillToolInput

    def is_read_only(self, arguments: SkillToolInput) -> bool:
        del arguments
        return True

    async def execute(self, arguments: SkillToolInput, context: ToolExecutionContext) -> ToolResult:
        registry = load_skill_registry(
            context.cwd,
            extra_skill_dirs=context.metadata.get("extra_skill_dirs"),
            extra_plugin_roots=context.metadata.get("extra_plugin_roots"),
        )
        skill = registry.get(arguments.name) or registry.get(arguments.name.lower()) or registry.get(arguments.name.title())
        if skill is None:
            return ToolResult(output=f"Skill not found: {arguments.name}", is_error=True)
        # `disable_model_invocation` was designed for user-only slash commands
        # ("deploy", "build", etc. — short, flat names the model could pick
        # up from context or guess). For such skills we keep blocking the
        # model from invoking them via the skill tool.
        #
        # Hierarchically-namespaced skills (names containing "/", e.g.
        # "pipelines/cinematic/executive-producer", "meta/checkpoint-protocol")
        # are addressed by their exact path. They're hidden from the
        # auto-listing in `prompts/context.py` so the model can only learn
        # the path from explicit instructions (e.g. a plugin's slash-command
        # prompt). Loading them when asked by full name is the documented
        # intent — see the comment in
        # `openharness.openmontage.bridge.pipeline_to_plugin._build_skills`.
        if skill.disable_model_invocation and "/" not in skill.name:
            command_name = skill.command_name or skill.name
            return ToolResult(
                output=f"Skill {command_name} can only be invoked by the user as /{command_name}.",
                is_error=True,
            )
        return ToolResult(output=skill.content)
