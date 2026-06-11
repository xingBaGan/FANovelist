"""CLI sub-app: ``oh montage ...`` commands.

Add this to the main OpenHarness CLI via::

    from openharness.openmontage.bridge.cli import app as montage_app
    app.add_typer(montage_app)

Available subcommands:

* ``oh montage list`` — list every pipeline manifest.
* ``oh montage info <pipeline>`` — show stages, tools, skills for a pipeline.
* ``oh montage doctor`` — verify which OM tools are currently runnable.
* ``oh montage tool <om_tool_name> [--inputs JSON]`` — invoke a single OM
  tool directly through the adapter. Bypasses the agent — perfect for
  unit-level debugging.
* ``oh montage agent <pipeline> [PROMPT]`` — run the full pipeline agent
  loop. Wires the bridge plugin into OpenHarness's plugin set for the
  duration of the call, then delegates to ``oh -p "/montage_<pipeline> ..."``.

The first four are always safe; the fifth requires API credentials and
the same external tooling (Remotion, FFmpeg, etc.) the underlying
OpenMontage tools depend on.
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from typing import Any, Optional

import typer
import yaml

from openharness.openmontage.bridge.hooks import (
    BridgeHookSession,
    bind_session,
    install_default_hooks,
    reset_session,
)
from openharness.openmontage.bridge.pipeline_to_plugin import (
    PIPELINES_DIR,
    build_plugin,
)
from openharness.openmontage.bridge.tool_adapter import (
    OMToolAdapter,
    adapt_all_tools,
)
from openharness.openmontage.tools.base_tool import ToolStatus
from openharness.openmontage.tools.tool_registry import registry as om_registry
from openharness.tools.base import ToolExecutionContext

app = typer.Typer(
    name="montage",
    help="OpenMontage pipelines and tools hosted inside OpenHarness.",
    no_args_is_help=True,
)


# ---------------------------------------------------------------------------
# list / info / doctor — read-only introspection
# ---------------------------------------------------------------------------


@app.command("list")
def list_pipelines() -> None:
    """List every OpenMontage pipeline manifest."""
    if not PIPELINES_DIR.is_dir():
        typer.echo("(no pipelines directory found)")
        raise typer.Exit(code=1)
    rows: list[tuple[str, str, str]] = []
    for path in sorted(PIPELINES_DIR.glob("*.yaml")):
        manifest = _load_manifest(path)
        rows.append(
            (
                manifest.get("name", path.stem),
                manifest.get("stability", "?"),
                _strip(manifest.get("description") or "", 80),
            )
        )
    if not rows:
        typer.echo("(no pipelines)")
        raise typer.Exit(code=1)
    width_name = max(len(r[0]) for r in rows)
    width_stab = max(len(r[1]) for r in rows)
    for name, stability, description in rows:
        typer.echo(f"{name.ljust(width_name)}  {stability.ljust(width_stab)}  {description}")


@app.command("info")
def info(pipeline: str = typer.Argument(..., help="Pipeline name (without .yaml)")) -> None:
    """Show stages, tool whitelist, and skill references for a pipeline."""
    manifest_path = PIPELINES_DIR / f"{pipeline}.yaml"
    if not manifest_path.is_file():
        typer.echo(f"Pipeline manifest not found: {manifest_path}", err=True)
        raise typer.Exit(code=1)
    manifest = _load_manifest(manifest_path)

    typer.echo(f"Pipeline: {manifest.get('name', pipeline)}")
    typer.echo(f"Stability: {manifest.get('stability', '?')}")
    typer.echo(f"Description: {_strip(manifest.get('description') or '', 200)}")
    orchestration = manifest.get("orchestration") or {}
    typer.echo(
        f"Orchestrator skill: {orchestration.get('skill', '(none)')}, "
        f"budget=${orchestration.get('budget_default_usd', 0.0):.2f}"
    )
    typer.echo("\nStages:")
    for stage in manifest.get("stages", []) or []:
        tools = stage.get("tools_available") or []
        typer.echo(
            f"  - {stage.get('name'):<14} skill={stage.get('skill')} "
            f"tools={'+'.join(tools[:6]) + ('+...' if len(tools) > 6 else '')}"
        )

    typer.echo("\nRequired skills:")
    for ref in manifest.get("required_skills", []) or []:
        typer.echo(f"  - {ref}")


@app.command("doctor")
def doctor() -> None:
    """Report status of every OpenMontage tool (env vars, binaries, etc.)."""
    om_registry.ensure_discovered()
    available: list[tuple[str, str]] = []
    unavailable: list[tuple[str, str, str]] = []
    for name, tool in sorted(om_registry._tools.items()):  # noqa: SLF001
        status = tool.get_status()
        provider = tool.provider
        if status == ToolStatus.AVAILABLE:
            available.append((name, provider))
        else:
            unavailable.append((name, provider, tool.install_instructions[:80]))
    typer.echo(f"Available ({len(available)} tools):")
    for name, provider in available:
        typer.echo(f"  + {name}  [{provider}]")
    typer.echo(f"\nUnavailable ({len(unavailable)} tools):")
    for name, provider, hint in unavailable:
        typer.echo(f"  - {name}  [{provider}]  {hint}")


# ---------------------------------------------------------------------------
# tool — direct single-tool invocation (great for unit-level debugging)
# ---------------------------------------------------------------------------


@app.command("tool")
def run_single_tool(
    name: str = typer.Argument(..., help="OpenMontage tool name (without `om_` prefix)"),
    inputs: Optional[str] = typer.Option(
        None,
        "--inputs",
        "-i",
        help="JSON object with tool inputs. Use '-' to read JSON from stdin.",
    ),
    inputs_file: Optional[Path] = typer.Option(
        None,
        "--inputs-file",
        "-f",
        help="Path to a JSON file containing tool inputs.",
    ),
    cwd: Optional[Path] = typer.Option(
        None,
        "--cwd",
        help="Working directory for the tool (defaults to current).",
    ),
    trace: bool = typer.Option(
        False,
        "--trace/--no-trace",
        help="Write trace.jsonl + cost.csv to .openharness/montage/runs/<id>/.",
    ),
) -> None:
    """Invoke a single OM tool through the adapter and print the ToolResult.

    Bypasses the LLM and the agent loop. The bridge still applies — so
    the same translation and metadata you'd see in production reaches
    your shell. Excellent for debugging a single tool's inputs/outputs
    without paying for model tokens.
    """
    om_registry.ensure_discovered()
    om_tool = om_registry.get(name)
    if om_tool is None:
        typer.echo(f"Unknown OpenMontage tool: {name}", err=True)
        typer.echo("Hint: run `oh montage doctor` to see all registered tools.", err=True)
        raise typer.Exit(code=1)

    payload = _resolve_inputs(inputs, inputs_file)
    adapter = OMToolAdapter(om_tool)
    work_dir = (cwd or Path.cwd()).resolve()
    context = ToolExecutionContext(cwd=work_dir)
    args = adapter.input_model(inputs=payload)

    token = None
    session: Optional[BridgeHookSession] = None
    if trace:
        session = BridgeHookSession.for_pipeline(pipeline=None, root=work_dir)
        install_default_hooks(session)
        token = bind_session(session)
        typer.echo(f"-> tracing to {session.run_dir}", err=True)

    try:
        result = asyncio.run(adapter.execute(args, context))
    finally:
        if token is not None:
            reset_session(token)

    typer.echo(result.output)
    if result.is_error:
        raise typer.Exit(code=1)


# ---------------------------------------------------------------------------
# agent — full pipeline run (delegates to OpenHarness print mode)
# ---------------------------------------------------------------------------


@app.command("agent")
def run_agent(
    pipeline: str = typer.Argument(..., help="Pipeline name"),
    prompt: Optional[str] = typer.Argument(
        None,
        help='Creative prompt. Example: "make a 60s explainer about black holes".',
    ),
    extra_args: list[str] = typer.Argument(
        None,
        help="Additional args forwarded to `oh -p`.",
    ),
) -> None:
    """Run the pipeline end-to-end through OpenHarness's agent loop.

    Internally:

    1. Monkeypatches ``openharness.plugins.load_plugins`` to inject the
       in-memory OpenMontage bridge plugin alongside whatever is on
       disk.
    2. Calls the OpenHarness Typer app with
       ``-p "/montage_<pipeline> <prompt>"`` so the print-mode session
       runs the slash command.
    """
    if not (PIPELINES_DIR / f"{pipeline}.yaml").is_file():
        typer.echo(f"Pipeline manifest not found for `{pipeline}`.", err=True)
        raise typer.Exit(code=1)

    _inject_bridge_plugin()

    session = BridgeHookSession.for_pipeline(pipeline=pipeline, root=Path.cwd())
    install_default_hooks(session)
    token = bind_session(session)
    typer.echo(f"-> trace dir: {session.run_dir}", err=True)

    from openharness import cli as harness_cli

    body = " ".join([f"/montage_{pipeline}", prompt or ""]).strip()
    argv = ["-p", body]
    if extra_args:
        argv.extend(extra_args)
    typer.echo(f"-> oh {' '.join(argv)}", err=True)
    try:
        # Calling the underlying Typer app re-enters the main callback in
        # the same process so the monkeypatch + bound session are honored.
        harness_cli.app(argv, standalone_mode=False)
    finally:
        reset_session(token)


# ---------------------------------------------------------------------------
# Internals
# ---------------------------------------------------------------------------


def _load_manifest(path: Path) -> dict[str, Any]:
    try:
        with open(path, encoding="utf-8") as fh:
            data = yaml.safe_load(fh) or {}
    except yaml.YAMLError as exc:
        typer.echo(f"Failed to parse {path}: {exc}", err=True)
        raise typer.Exit(code=1)
    if not isinstance(data, dict):
        typer.echo(f"Pipeline manifest is not a mapping: {path}", err=True)
        raise typer.Exit(code=1)
    return data


def _strip(text: str, limit: int) -> str:
    flat = " ".join(text.split())
    if len(flat) <= limit:
        return flat
    return flat[: limit - 3] + "..."


def _resolve_inputs(inline: Optional[str], path: Optional[Path]) -> dict[str, Any]:
    if path is not None:
        return _load_json(path.read_text(encoding="utf-8"), source=str(path))
    if inline == "-":
        return _load_json(sys.stdin.read(), source="<stdin>")
    if inline:
        return _load_json(inline, source="--inputs")
    return {}


def _load_json(raw: str, *, source: str) -> dict[str, Any]:
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        typer.echo(f"Invalid JSON in {source}: {exc}", err=True)
        raise typer.Exit(code=1)
    if not isinstance(data, dict):
        typer.echo(f"Tool inputs must be a JSON object (got {type(data).__name__}).", err=True)
        raise typer.Exit(code=1)
    return data


def _inject_bridge_plugin() -> None:
    """Wrap ``load_plugins`` so the bridge plugin is included automatically.

    Idempotent: a sentinel attribute on the wrapped function prevents
    repeat wrapping when the bridge CLI is reentered.
    """
    from openharness.plugins import loader as plugin_loader

    if getattr(plugin_loader.load_plugins, "_om_bridge_wrapped", False):
        return

    original = plugin_loader.load_plugins

    def wrapper(settings, cwd, extra_roots=None):
        plugins = original(settings, cwd, extra_roots=extra_roots)
        try:
            bridge = build_plugin()
        except Exception as exc:  # pragma: no cover - defensive
            typer.echo(f"warning: failed to build OpenMontage bridge plugin: {exc}", err=True)
            return plugins
        # Replace any existing plugin with the same name to be deterministic.
        plugins = [p for p in plugins if p.manifest.name != bridge.manifest.name]
        plugins.append(bridge)
        return plugins

    wrapper._om_bridge_wrapped = True  # type: ignore[attr-defined]
    plugin_loader.load_plugins = wrapper  # type: ignore[assignment]


if __name__ == "__main__":  # pragma: no cover - manual invocation only
    app()
