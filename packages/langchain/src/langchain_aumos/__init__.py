# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 MuVeraAI Corporation
"""
langchain-aumos — AumOS governance integration for LangChain.

Add AumOS governance to any LangChain agent in 3 lines:

.. code-block:: python

    from langchain_aumos import AumOSGovernanceCallback

    engine = GovernanceEngine(config)
    callback = AumOSGovernanceCallback(engine)
    agent = create_agent(llm, tools, callbacks=[callback])

Public API
----------
AumOSGovernanceCallback
    LangChain ``BaseCallbackHandler`` that evaluates governance on every tool call.

GovernedTool
    ``BaseTool`` wrapper adding a per-tool governance gate.

govern
    Convenience function equivalent to ``GovernedTool(tool, engine, ...)``.

ChainGuard
    Governance wrapper for LangChain chain execution.

GovernanceConfig
    Pydantic v2 configuration model for the integration.

GovernanceDeniedError
    Raised when governance denies a tool call and ``on_denied='raise'``.

ToolSkippedError
    Internal signal that a tool was skipped; exposed for custom handler subclasses.

DeniedAction
    Enum of denial handling modes: ``RAISE``, ``SKIP``, ``LOG``.
"""

from .callback import AumOSGovernanceCallback
from .chain_guard import ChainGuard, GuardedChain
from .config import GovernanceConfig
from .errors import GovernanceDeniedError, ToolSkippedError
from .tool_wrapper import GovernedTool, govern
from .types import AuditRecord, DeniedAction, ToolCallContext

__all__ = [
    "AumOSGovernanceCallback",
    "ChainGuard",
    "GuardedChain",
    "GovernanceConfig",
    "GovernanceDeniedError",
    "ToolSkippedError",
    "GovernedTool",
    "govern",
    "AuditRecord",
    "DeniedAction",
    "ToolCallContext",
]

__version__ = "0.1.0"
