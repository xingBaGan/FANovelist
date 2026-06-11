"""One-off rewriter that re-anchors OpenMontage imports under openharness.openmontage.

Run from the OpenHarness repo root::

    python scripts/rewrite_openmontage_imports.py

Idempotent: re-running is a no-op once the rewrite is complete.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent / "src" / "openharness" / "openmontage"
PREFIX = "openharness.openmontage"
TOP_LEVEL_PACKAGES = ("tools", "lib", "schemas", "styles")

# Match `from X.Y import` or `from X import` or `import X` / `import X.Y`.
# We rewrite only top-level matches so we don't accidentally re-prefix already-rewritten imports.
FROM_PATTERN = re.compile(
    r"^(\s*)from\s+(" + "|".join(TOP_LEVEL_PACKAGES) + r")(\.[A-Za-z0-9_.]+)?\s+import\s+",
    re.MULTILINE,
)
IMPORT_PATTERN = re.compile(
    r"^(\s*)import\s+(" + "|".join(TOP_LEVEL_PACKAGES) + r")(\.[A-Za-z0-9_.]+)?(\s+as\s+\w+)?\s*$",
    re.MULTILINE,
)


def rewrite_source(src: str) -> str:
    def _from_repl(m: re.Match[str]) -> str:
        indent, pkg, sub = m.group(1), m.group(2), m.group(3) or ""
        return f"{indent}from {PREFIX}.{pkg}{sub} import "

    def _import_repl(m: re.Match[str]) -> str:
        indent, pkg, sub, alias = m.group(1), m.group(2), m.group(3) or "", m.group(4) or ""
        return f"{indent}import {PREFIX}.{pkg}{sub}{alias}"

    out = FROM_PATTERN.sub(_from_repl, src)
    out = IMPORT_PATTERN.sub(_import_repl, out)
    return out


def main() -> None:
    changed = 0
    scanned = 0
    for path in ROOT.rglob("*.py"):
        # Skip vendored 3rd-party (none expected here) and __pycache__
        if "__pycache__" in path.parts:
            continue
        scanned += 1
        original = path.read_text(encoding="utf-8")
        rewritten = rewrite_source(original)
        if rewritten != original:
            path.write_text(rewritten, encoding="utf-8")
            changed += 1
            rel = path.relative_to(ROOT)
            print(f"  rewrote {rel}")

    # Hardcoded path rename: pipeline_defs → pipelines (Python source only).
    pl = ROOT / "lib" / "pipeline_loader.py"
    if pl.is_file():
        s = pl.read_text(encoding="utf-8")
        new = s.replace('"pipeline_defs"', '"pipelines"')
        if new != s:
            pl.write_text(new, encoding="utf-8")
            print("  patched lib/pipeline_loader.py: pipeline_defs -> pipelines")

    print(f"\nScanned {scanned} .py files, rewrote {changed}.")


if __name__ == "__main__":
    main()
