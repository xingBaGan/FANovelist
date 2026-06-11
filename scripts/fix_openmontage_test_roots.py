"""Repoint PROJECT_ROOT in moved OpenMontage tests at the subpackage root.

After moving ``OpenMontage/tests/`` to ``OpenHarness/tests/openmontage/``,
``parent.parent.parent`` resolves to the OpenHarness repo root, but the tests
that read ``AGENT_GUIDE.md``/``CLAUDE.md`` need the OpenMontage subpackage root
(``OpenHarness/src/openharness/openmontage/``).

This rewrite is small and surgical: it replaces the literal line so we don't
risk perturbing anything else. Idempotent.
"""

from __future__ import annotations

from pathlib import Path

REPLACEMENTS: list[tuple[str, str]] = [
    (
        "PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent",
        "PROJECT_ROOT = Path(__file__).resolve().parents[3] "
        '/ "src" / "openharness" / "openmontage"',
    ),
    # Bare inline `Path(__file__).resolve().parent.parent.parent` used by
    # tests/openmontage/tools/test_hyperframes_compose.py et al. After the
    # move, that resolves to OpenHarness root, but those tests want the
    # OpenMontage subpackage root.
    (
        "Path(__file__).resolve().parent.parent.parent",
        'Path(__file__).resolve().parents[3] / "src" / "openharness" / "openmontage"',
    ),
]


def main() -> None:
    root = Path(__file__).resolve().parent.parent / "tests" / "openmontage"
    changed = 0
    for path in root.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        new_text = text
        for old, new in REPLACEMENTS:
            new_text = new_text.replace(old, new)
        if new_text != text:
            path.write_text(new_text, encoding="utf-8")
            changed += 1
            print(f"  patched {path.relative_to(root)}")
    print(f"\n{changed} test file(s) repointed.")


if __name__ == "__main__":
    main()
