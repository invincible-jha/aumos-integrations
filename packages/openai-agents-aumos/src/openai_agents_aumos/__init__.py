# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 MuVeraAI Corporation
"""
openai-agents-aumos — AumOS governance integration for OpenAI Agents SDK.

Add AumOS governance to any OpenAI Agents SDK agent in a few lines:

.. code-block:: python

    from openai_agents_aumos import AumOSGuardrail

    engine = GovernanceEngine(config)
    guardrail = AumOSGuardrail(engine=engine, agent_id="support-agent")
    # agent = Agent(name="support", guardrails=[guardrail], ...)

Public API
----------
AumOSGuardrail
    Governance guardrail that checks tool calls via ``before_tool_call`` and
    ``after_tool_call`` hooks compatible with the OpenAI Agents SDK guardrail
    interface.

GuardrailConfig
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

GuardrailCheckContext
    Pydantic model holding contextual information for a governed tool call.

GuardrailResult
    Pydantic model for the outcome of a guardrail check.

AuditRecord
    Pydantic model for a completed tool execution audit entry.
"""

from .config import GuardrailConfig
from .errors import GovernanceDeniedError
from .guardrail import AumOSGuardrail
from .protocol import GovernanceAction, GovernanceDecision, GovernanceEngineProtocol
from .types import AuditRecord, DeniedAction, GuardrailCheckContext, GuardrailResult

__all__ = [
    "AumOSGuardrail",
    "GuardrailConfig",
    "GovernanceDeniedError",
    "GovernanceAction",
    "GovernanceDecision",
    "GovernanceEngineProtocol",
    "AuditRecord",
    "DeniedAction",
    "GuardrailCheckContext",
    "GuardrailResult",
]

__version__ = "0.1.0"
