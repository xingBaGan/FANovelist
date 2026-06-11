"""OpenMontage vertical subpackage.

Hosted inside OpenHarness as a domain-specific application for AI-orchestrated
video production. See ``src/openharness/openmontage/README.md`` and
``src/openharness/openmontage/PROJECT_CONTEXT.md`` for architecture.

Importing this package does **not** trigger tool discovery; call
``openharness.openmontage.tools.tool_registry.registry.discover()`` explicitly,
or rely on the bridge plugin in ``openharness.plugins.bundled.openmontage``.
"""

from __future__ import annotations

from pathlib import Path

PACKAGE_ROOT: Path = Path(__file__).resolve().parent

__all__ = ["PACKAGE_ROOT"]
