"""Add YAML frontmatter to OpenMontage skill markdown files.

OpenHarness's skill registry recognizes markdown files with YAML frontmatter
(``name``, ``description``, ``when_to_use``). Layer-2 OpenMontage skills under
``src/openharness/openmontage/skills/`` were originally written as plain
markdown for human readers — the agent inferred their roles from the
``skills/INDEX.md`` map.

To make them first-class for OpenHarness's ``SkillTool``, this script:

* Walks every ``*.md`` under ``skills/`` and ``agents_skills/``.
* Skips files that already start with ``---\n`` (already have frontmatter).
* Skips index/provenance files that aren't skills.
* Adds ``name``/``description``/``when_to_use`` frontmatter.

Name convention preserves the path-like references the pipeline manifests
already use (e.g. ``pipelines/talking-head/asset-director``). Description
is derived from the first ``# Heading`` and first non-heading paragraph.

Idempotent: re-running is a no-op.
"""

from __future__ import annotations

import re
from pathlib import Path

PKG_ROOT = (
    Path(__file__).resolve().parent.parent
    / "src"
    / "openharness"
    / "openmontage"
)
SKIP_NAMES = {"INDEX.md", "PROVENANCE.md", "README.md", "CHANGELOG.md"}


def _first_heading(text: str) -> str | None:
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("# ") and not stripped.startswith("## "):
            return stripped[2:].strip() or None
    return None


def _first_paragraph(text: str) -> str | None:
    in_body = False
    paragraph: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not in_body:
            if stripped.startswith("# "):
                in_body = True
            continue
        if not stripped:
            if paragraph:
                break
            continue
        if stripped.startswith("#") or stripped.startswith("---"):
            if paragraph:
                break
            continue
        # Skip pure metadata lines like ">", "|"
        if stripped.startswith("|") or stripped.startswith(">"):
            continue
        paragraph.append(stripped)
        if len(" ".join(paragraph)) > 300:
            break
    if not paragraph:
        return None
    return " ".join(paragraph)[:300]


def _skill_name(path: Path, base: Path) -> str:
    rel = path.relative_to(base)
    parts = list(rel.with_suffix("").parts)
    return "/".join(parts)


def _yaml_quote(value: str) -> str:
    """Quote a string for safe YAML inclusion as a flow-style scalar."""
    sanitized = value.replace("\r", " ").replace("\n", " ").strip()
    sanitized = re.sub(r"\s+", " ", sanitized)
    if not sanitized:
        return '""'
    # Use double quotes and escape embedded double quotes / backslashes.
    sanitized = sanitized.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{sanitized}"'


def _build_frontmatter(name: str, description: str, when_to_use: str) -> str:
    return (
        "---\n"
        f"name: {_yaml_quote(name)}\n"
        f"description: {_yaml_quote(description)}\n"
        f"when_to_use: {_yaml_quote(when_to_use)}\n"
        "---\n\n"
    )


def _process_file(path: Path, base: Path) -> bool:
    text = path.read_text(encoding="utf-8")
    if text.startswith("---\n"):
        return False  # already has frontmatter
    if path.name in SKIP_NAMES:
        return False

    heading = _first_heading(text) or path.stem.replace("-", " ").title()
    paragraph = _first_paragraph(text) or heading
    name = _skill_name(path, base)
    # Make description short and action-oriented; OpenHarness uses it for
    # the model to pick a skill, so the first ~200 chars matter.
    description = f"{heading}. {paragraph}" if heading.lower() not in paragraph.lower() else paragraph
    description = description[:300]
    when_to_use = (
        f"When the agent needs guidance for: {heading.lower()}."
    )

    frontmatter = _build_frontmatter(name, description, when_to_use)
    path.write_text(frontmatter + text, encoding="utf-8")
    return True


def main() -> None:
    changed = 0
    skipped = 0
    for base_name in ("skills", "agents_skills"):
        base = PKG_ROOT / base_name
        if not base.is_dir():
            continue
        for md in sorted(base.rglob("*.md")):
            if _process_file(md, base):
                changed += 1
                print(f"  added frontmatter: {md.relative_to(PKG_ROOT)}")
            else:
                skipped += 1
    print(f"\nadded={changed} skipped={skipped}")


if __name__ == "__main__":
    main()
