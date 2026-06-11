"""Tools written natively against the OpenHarness async BaseTool contract.

When the bridge starts, every legacy OpenMontage sync tool is wrapped
via :mod:`openharness.openmontage.bridge.tool_adapter`. Tools under
this package take the next step: they expose a Pydantic input model
and an ``async execute()`` directly, dropping the sync shim.

Use this package as the template when you want to port a tool from
``../tools/`` to native form. The first concrete example is
:mod:`openharness.openmontage.native.tts_selector`.
"""

from __future__ import annotations

from openharness.openmontage.native.tts_selector import TtsSelectorNativeTool

__all__ = ["TtsSelectorNativeTool"]
