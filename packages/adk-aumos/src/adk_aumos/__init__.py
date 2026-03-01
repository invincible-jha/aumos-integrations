# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 MuVeraAI Corporation
"""
adk-aumos — AumOS governance integration for Google ADK.

Add AumOS governance to any Google ADK agent in a few lines:

.. code-block:: python

    from adk_aumos import AumOSADKCallback

    engine = GovernanceEngine(config)
    callback = AumOSADKCallback(engine=engine, agent_id="research-agent")
    # Attach callback to your ADK agent via its callbacks parameter.

Public API
----------
AumOSADKCallback
    Governance callback that hooks into the ADK tool execution lifecycle
    via ``before_tool_call`` and ``after_tool_call``.

GovernanceConfig
    Pydantic v2 configuration model for the integration.

GovernanceEngineProtocol
    ``typing.Protocol`` defining the engine interface.  Use this for type
    annotations instead of ``Any``.

GovernanceAction
    ``TypedDict`` describing the governance evaluation input payload.

GovernanceDecision
    ``TypedDict`` describing the governance decision returned by the engine.

GovernanceDeniedError
    Raised when governance denies a tool call and ``on_denied='raise'``.

DeniedAction
    Enum of denial handling modes: ``RAISE``, ``SKIP``, ``LOG``.

ToolCallContext
    Pydantic model holding contextual information for a governed tool call.

AuditRecord
    Pydantic model for a completed tool execution audit entry.
"""

from .callback import AumOSADKCallback
from .config import GovernanceConfig
from .errors import GovernanceDeniedError
from .protocol import GovernanceAction, GovernanceDecision, GovernanceEngineProtocol
from .types import AuditRecord, DeniedAction, ToolCallContext

__all__ = [
    "AumOSADKCallback",
    "GovernanceConfig",
    "GovernanceDeniedError",
    "GovernanceAction",
    "GovernanceDecision",
    "GovernanceEngineProtocol",
    "AuditRecord",
    "DeniedAction",
    "ToolCallContext",
]

__version__ = "0.1.0"
