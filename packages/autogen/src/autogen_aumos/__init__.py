# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 MuVeraAI Corporation
"""
autogen-aumos — AumOS governance integration for Microsoft AutoGen conversations.

Add AumOS governance to any AutoGen agent in a few lines:

.. code-block:: python

    from autogen import ConversableAgent
    from autogen_aumos import GovernedConversableAgent

    engine = GovernanceEngine(config)
    governed = GovernedConversableAgent(agent=agent, engine=engine, trust_level=2)

    # Use governed.agent in your AutoGen conversation — hooks are installed.
    governed.agent.initiate_chat(other_agent, message="Hello")

Every message send and every function call the agent makes is evaluated against
your governance policy before execution. Denied actions raise
``GovernanceDeniedError``, return a block notice, or are logged — your choice.

Public API
----------
GovernedConversableAgent
    Wraps an AutoGen ``ConversableAgent`` with governance checks on messages
    and tool/function calls. Uses composition — the original agent is held as
    ``self.agent`` with hooks installed at construction time.

MessageGuard
    Standalone message governance. Evaluates governance on message sends
    between AutoGen agents.

ToolGuard
    Standalone tool execution governance. Evaluates governance before any
    registered function is executed.

AutoGenGovernanceConfig
    Pydantic v2 configuration model for the integration.

GovernanceDeniedError
    Raised when governance denies an action and ``on_denied='raise'``.

MessageBlockedError
    Raised when governance denies a message and ``on_denied='block'``.

DeniedAction
    Enum of denial handling modes: ``RAISE``, ``BLOCK``, ``LOG``.

GuardResult
    Outcome of a governance guard check. Returned by ``MessageGuard.check_message``
    and ``ToolGuard.check_tool``.
"""

from .config import AutoGenGovernanceConfig
from .conversation_governance import ConversationGovernanceManager
from .errors import GovernanceDeniedError, MessageBlockedError
from .governed_agent import GovernedConversableAgent
from .message_guard import MessageGuard
from .tool_guard import ToolGuard
from .types import (
    AuditRecord,
    DeniedAction,
    GuardResult,
    MessageContext,
    ToolCallContext,
)

__all__ = [
    "GovernedConversableAgent",
    "MessageGuard",
    "ToolGuard",
    "ConversationGovernanceManager",
    "AutoGenGovernanceConfig",
    "GovernanceDeniedError",
    "MessageBlockedError",
    "DeniedAction",
    "GuardResult",
    "AuditRecord",
    "MessageContext",
    "ToolCallContext",
]

__version__ = "0.1.0"
