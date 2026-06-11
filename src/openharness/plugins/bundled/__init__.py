"""Plugins shipped bundled inside the OpenHarness package itself."""

from __future__ import annotations

from typing import TYPE_CHECKING

from openharness.plugins.bundled.openmontage import build_bundled_openmontage_plugin

if TYPE_CHECKING:
    from openharness.plugins.types import LoadedPlugin

__all__ = ["build_bundled_openmontage_plugin", "load_bundled_plugins"]


def load_bundled_plugins(settings) -> list["LoadedPlugin"]:
    """Return every bundled plugin that loaded successfully.

    Bundled plugins live inside the OpenHarness package, are always
    discoverable (no installation step), and respect the same
    ``settings.enabled_plugins`` opt-out map as on-disk plugins.
    """
    enabled_plugins = getattr(settings, "enabled_plugins", None) or {}
    plugins: list["LoadedPlugin"] = []
    plugin = build_bundled_openmontage_plugin(enabled_plugins=enabled_plugins)
    if plugin is not None:
        plugins.append(plugin)
    return plugins
