"""Bundled OpenMontage bridge plugin.

Wraps :func:`openharness.openmontage.bridge.pipeline_to_plugin.build_plugin`
so the OpenMontage subpackage shows up as a first-class OpenHarness plugin
without anyone having to drop a ``plugin.json`` on disk.

Importing this module is intentionally cheap; the heavy lifting (tool
discovery, pipeline manifests, skill loading) is deferred until
:func:`build_bundled_openmontage_plugin` is called.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from openharness.plugins.types import LoadedPlugin

logger = logging.getLogger(__name__)

PLUGIN_NAME = "openmontage"


def build_bundled_openmontage_plugin(
    *,
    enabled_plugins: dict[str, bool] | None = None,
) -> "LoadedPlugin | None":
    """Return the OpenMontage plugin, or ``None`` if the bridge is unavailable.

    Enabled-state semantics mirror ``load_plugin()``:

    * If ``enabled_plugins[PLUGIN_NAME]`` is set, that value wins.
    * Otherwise the bundled plugin defaults to enabled.

    Any failure to import or build the bridge is swallowed and logged, so
    a missing optional dependency in the OpenMontage subpackage never
    breaks the rest of the CLI.
    """
    explicit = (enabled_plugins or {}).get(PLUGIN_NAME)
    enabled = True if explicit is None else bool(explicit)
    try:
        from openharness.openmontage.bridge.pipeline_to_plugin import build_plugin
    except Exception as exc:
        logger.debug("OpenMontage bridge unavailable: %s", exc)
        return None
    try:
        return build_plugin(enabled=enabled)
    except Exception as exc:
        logger.warning("Failed to build bundled OpenMontage plugin: %s", exc)
        return None
