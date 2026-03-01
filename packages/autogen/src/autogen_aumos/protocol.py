# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 MuVeraAI Corporation
"""
GovernanceEngineProtocol — typed structural interface for the AumOS governance engine.

This module defines a ``typing.Protocol`` that every AumOS governance engine must
satisfy when used with autogen-aumos.  Using a Protocol instead of ``Any`` allows
mypy --strict to verify that the engine instance passed to the integration actually
exposes the methods this package calls: ``evaluate_sync`` and ``record_audit_event``.

Why a Protocol?
---------------
The ``aumos-governance`` SDK ships as a separate package.  Integration packages must
not import its concrete classes directly — that would couple the integration to a
specific SDK version and make it impossible to swap in a custom engine.  A Protocol
gives us full static type safety without creating a hard dependency.

Usage
-----
.. code-block:: python

    from autogen_aumos.protocol import GovernanceEngineProtocol

    def build_message_guard(engine: GovernanceEngineProtocol) -> MessageGuard:
        return MessageGuard(engine=engine)
"""

from __future__ import annotations

from typing import Protocol, TypedDict, runtime_checkable


class GovernanceAction(TypedDict, total=False):
    """
    Input payload submitted to the governance engine for evaluation.

    Required fields
    ~~~~~~~~~~~~~~~
    agentId
        Name of the AutoGen agent requesting the action.
    action
        Free-text name of the action being evaluated
        (e.g. ``'message:send'`` or ``'tool:function_call'``).
    category
        Governance category string (e.g. ``'message'``, ``'tool'``, ``'external'``).

    Optional fields
    ~~~~~~~~~~~~~~~
    requiredTrustLevel
        Minimum trust level that the agent must hold for this action to be
        permitted.  When omitted the engine uses its default minimum.
    cost
        Estimated spend for the action in USD.  When present the engine checks
        the value against the agent's configured budget envelope before
        returning a decision.  Budget allocation is STATIC — the engine never
        adjusts limits dynamically.
    """

    agentId: str  # required
    action: str  # required
    category: str  # required
    requiredTrustLevel: int  # optional
    cost: float  # optional


class GovernanceDecision(TypedDict, total=False):
    """
    Decision returned by the governance engine after evaluating a
    ``GovernanceAction``.

    Required fields
    ~~~~~~~~~~~~~~~
    permitted
        ``True`` when the action is allowed to proceed, ``False`` when it is
        denied.  The integration uses this field to gate message sends and
        function calls.
    reason
        Human-readable explanation of the decision.  Non-empty on denial;
        may be a short summary on permit.
    trustLevel
        The current trust level of the agent at the time of evaluation.
        This is the level that was held — it is never modified by the engine.
        Trust changes are MANUAL ONLY.
    metadata
        Arbitrary key-value pairs attached by the engine for audit purposes.
        Integration code must not interpret the contents of this dict.
    """

    permitted: bool  # required
    reason: str  # required
    trustLevel: int  # required
    metadata: dict[str, object]  # required


@runtime_checkable
class GovernanceEngineProtocol(Protocol):
    """
    Structural protocol that all AumOS governance engines must satisfy.

    Any object passed to autogen-aumos as an ``engine`` must expose at
    minimum these two methods.  mypy --strict will verify the contract at
    call-site without requiring the caller to import this Protocol.

    Methods
    -------
    evaluate_sync(agent_id, scope, amount)
        Synchronous governance evaluation used inside ``MessageGuard`` and
        ``ToolGuard``.  AutoGen function-call hooks are synchronous so the
        engine must provide a non-async evaluation path.

    record_audit_event(agent_id, tool_name, run_id, succeeded, ...)
        Append-only audit recording called after a message send or function
        call completes or fails.  Audit logging is RECORDING ONLY — the engine
        must not trigger side effects beyond persisting the event.
    """

    def evaluate_sync(
        self,
        *,
        agent_id: str,
        scope: str,
        amount: float | None = None,
    ) -> GovernanceDecision:
        """
        Evaluate a governance action synchronously.

        Args:
            agent_id: Name of the AutoGen agent requesting the action.
            scope: Governance scope string inferred from the message or function.
            amount: Optional estimated spend for budget checking.

        Returns:
            A ``GovernanceDecision`` indicating whether the action is permitted.
        """
        ...

    def record_audit_event(
        self,
        *,
        agent_id: str,
        tool_name: str,
        run_id: str | None,
        succeeded: bool,
        error_message: str | None = None,
        output_preview: str | None = None,
    ) -> None:
        """
        Record the outcome of a message send or function call to the append-only
        audit trail.

        Args:
            agent_id: Name of the AutoGen agent that triggered the event.
            tool_name: Name of the function/tool or ``'message'`` for message events.
            run_id: Optional correlation identifier for this execution.
            succeeded: ``True`` if the action completed without error or denial.
            error_message: Exception message when ``succeeded`` is ``False``.
            output_preview: Truncated preview of the output (max 256 chars).
        """
        ...
