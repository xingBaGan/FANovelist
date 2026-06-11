"""Bridge layer connecting OpenMontage to the OpenHarness runtime.

Three jobs:

1. :mod:`openharness.openmontage.bridge.tool_adapter` wraps each sync
   OpenMontage ``BaseTool`` as an async OpenHarness ``BaseTool``.
2. :mod:`openharness.openmontage.bridge.pipeline_to_plugin` compiles
   pipeline YAML + director skills into an OpenHarness ``LoadedPlugin``.
3. :mod:`openharness.openmontage.bridge.hooks` provides the trace /
   checkpoint / cost hooks that make each pipeline run replayable.

Public entry points::

    from openharness.openmontage.bridge import build_plugin, adapt_all_tools

"""

from __future__ import annotations

from openharness.openmontage.bridge.pipeline_to_plugin import build_plugin
from openharness.openmontage.bridge.tool_adapter import (
    OMToolAdapter,
    adapt_all_tools,
    adapt_tool,
)

__all__ = [
    "OMToolAdapter",
    "adapt_tool",
    "adapt_all_tools",
    "build_plugin",
]
