# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 MuVeraAI Corporation
"""
ConversationGovernanceManager — multi-agent conversation governance for AutoGen
group chats.

Monitors every message turn in a group chat and evaluates each one against a
static trust configuration and a cumulative budget ceiling.  The manager never
inspects or modifies message content — governance is allow/deny at the message
level only.  All decisions are appended to an in-memory, append-only audit trail.

Trust levels are set manually by the operator via ``ConversationConfig`` at
construction time.  They are never changed automatically at runtime.

Budget tracking accumulates per-turn costs supplied by the caller and compares
the running total against a static ceiling.  The ceiling is never adjusted by
the manager.

Usage::

    from autogen_aumos import ConversationGovernanceManager
    from autogen_aumos.conversation_governance import (
        ConversationConfig,
        GovernanceDecision,
    )

    config = ConversationConfig(
        allowed_agent_ids={"planner", "executor", "reviewer"},
        per_agent_trust_levels={"planner": 3, "executor": 2, "reviewer": 2},
        conversation_budget_limit=10.0,
        max_turns=50,
    )
    manager = ConversationGovernanceManager(config=config)

    decision = manager.evaluate_message(
        sender_id="planner",
        message="Please start the analysis.",
        context={"turn": 1, "cost": 0.05},
    )
    if not decision.permitted:
        print(f"Message denied: {decision.reason}")
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Protocol for AutoGen GroupChat — no hard dependency on the autogen package
# ---------------------------------------------------------------------------


@runtime_checkable
class GroupChatProtocol(Protocol):
    """Structural protocol describing the parts of an AutoGen GroupChat that the
    governance manager interacts with.

    No concrete AutoGen import is required.  Any object that exposes these
    attributes satisfies the protocol.

    Attributes:
        agents: An iterable of agent-like objects in the group chat.
        messages: The current message history as a sequence of dicts.
        max_round: The configured maximum number of rounds.
    """

    agents: Any
    messages: Any
    max_round: int


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


@dataclass
class ConversationConfig:
    """Static configuration for a governed group-chat conversation.

    All fields are set by the operator at construction time and are never
    modified by the manager at runtime.

    Attributes:
        allowed_agent_ids: Set of agent identifiers permitted to send messages
            in this conversation.  Any agent not in this set is denied.
        per_agent_trust_levels: Mapping from agent ID to its static trust level
            (integer in [0, 5]).  Agents not in this map receive trust level 0
            (untrusted) when the manager evaluates their messages.
        conversation_budget_limit: Maximum cumulative cost for the conversation.
            Costs are supplied per turn by the caller via the ``cost`` key in
            the ``context`` dict.  When the running total would exceed this
            ceiling, the message is denied.  The ceiling is static and is never
            modified by the manager.
        max_turns: Maximum number of message turns allowed in this conversation.
            A turn is counted each time ``evaluate_message`` records a permitted
            decision.  When the turn count reaches this value, further messages
            are denied.
    """

    allowed_agent_ids: set[str] = field(default_factory=set)
    per_agent_trust_levels: dict[str, int] = field(default_factory=dict)
    conversation_budget_limit: float = 100.0
    max_turns: int = 100

    def __post_init__(self) -> None:
        if self.conversation_budget_limit < 0:
            raise ValueError(
                f"conversation_budget_limit must be >= 0, "
                f"got {self.conversation_budget_limit!r}"
            )
        if self.max_turns < 1:
            raise ValueError(
                f"max_turns must be >= 1, got {self.max_turns!r}"
            )
        for agent_id, level in self.per_agent_trust_levels.items():
            if not (0 <= level <= 5):
                raise ValueError(
                    f"trust level for {agent_id!r} must be in [0, 5], got {level!r}"
                )

    def trust_level_for(self, agent_id: str) -> int:
        """Return the static trust level for ``agent_id``.

        Returns 0 (untrusted) for agents not in the per-agent map.

        Args:
            agent_id: The agent identifier to look up.

        Returns:
            An integer in [0, 5].
        """
        return self.per_agent_trust_levels.get(agent_id, 0)


# ---------------------------------------------------------------------------
# Governance decision
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class GovernanceDecision:
    """Immutable record of a single governance evaluation for one message turn.

    Appended to the manager's audit trail on every call to ``evaluate_message``.
    Frozen after creation to preserve tamper-evident audit records.

    Attributes:
        permitted: ``True`` if the message is allowed to proceed.
        reason: Machine-readable reason code.  ``'permitted'`` on allow;
            one of the denial codes on deny.
        sender_id: The agent that sent (or attempted to send) the message.
        turn_number: The sequential turn index at the time of this decision
            (1-based, counting permitted turns only).
        sender_trust_level: The static trust level of the sender at decision
            time.
        cumulative_cost: The cumulative conversation cost at the time this
            decision was recorded.

    Denial reason codes:
        - ``sender_not_allowed``: Sender is not in ``allowed_agent_ids``.
        - ``insufficient_trust``: Sender trust level is 0 (untrusted).
        - ``budget_exceeded``: Adding this turn's cost would exceed the static
          ``conversation_budget_limit``.
        - ``max_turns_exceeded``: The conversation has reached ``max_turns``.
    """

    permitted: bool
    reason: str
    sender_id: str
    turn_number: int
    sender_trust_level: int
    cumulative_cost: float


# ---------------------------------------------------------------------------
# Manager
# ---------------------------------------------------------------------------


class ConversationGovernanceManager:
    """Governance manager for AutoGen multi-agent group-chat conversations.

    Evaluates each message turn against four sequential checks and records
    every decision in an append-only audit trail.  The audit trail is a
    recording mechanism only — it is never read by the manager's decision logic.

    The four checks, in order:

    1. **Sender allowed** — the sender must be in ``config.allowed_agent_ids``.
    2. **Sender trusted** — the sender must hold trust level >= 1 (trust level 0
       means untrusted).
    3. **Budget ceiling** — the cumulative conversation cost must not exceed
       ``config.conversation_budget_limit`` after adding this turn's cost.
    4. **Max turns** — the count of permitted turns must not have reached
       ``config.max_turns``.

    Trust levels are set by the operator in ``ConversationConfig`` and are never
    modified by this manager.  Budget tracking uses a static ceiling; only the
    running total changes.

    Args:
        config: The static ``ConversationConfig`` for this conversation.

    Example::

        manager = ConversationGovernanceManager(
            config=ConversationConfig(
                allowed_agent_ids={"agent-a", "agent-b"},
                per_agent_trust_levels={"agent-a": 3, "agent-b": 2},
                conversation_budget_limit=5.0,
                max_turns=20,
            )
        )
        decision = manager.evaluate_message(
            sender_id="agent-a",
            message="Hello.",
            context={"cost": 0.01},
        )
        assert decision.permitted
    """

    # Minimum trust level required to participate in a governed conversation.
    MINIMUM_TRUST_LEVEL: int = 1

    def __init__(self, config: ConversationConfig) -> None:
        self._config = config
        self._turn_count: int = 0
        self._cumulative_cost: float = 0.0
        self._audit_trail: list[GovernanceDecision] = []

    # ------------------------------------------------------------------
    # Primary evaluation surface
    # ------------------------------------------------------------------

    def evaluate_message(
        self,
        sender_id: str,
        message: str,
        context: dict[str, Any] | None = None,
    ) -> GovernanceDecision:
        """Evaluate governance for an incoming message in the group chat.

        Runs four checks in order and short-circuits on the first denial.
        On permit, the turn counter is incremented and this turn's cost is
        added to the cumulative total.

        The ``message`` parameter is accepted for API symmetry with AutoGen
        hooks but its content is never inspected or stored — governance operates
        at the allow/deny level only.

        Args:
            sender_id: Identifier of the agent sending the message.
            message: The message content.  Not inspected by the manager.
            context: Optional mapping that may contain a ``'cost'`` key
                (``float``) representing the cost of this turn.  Any other keys
                are ignored.  If omitted or if ``'cost'`` is absent, the turn
                cost is treated as 0.0.

        Returns:
            A ``GovernanceDecision`` describing the outcome.  Always appended
            to the audit trail before returning.
        """
        _ = message  # Content is not evaluated — governance is allow/deny only.
        turn_cost: float = _extract_turn_cost(context)
        # The turn_number in a denied decision is what the next permitted turn
        # would have been; for permitted decisions it is the incremented count.
        next_turn_number = self._turn_count + 1
        sender_trust = self._config.trust_level_for(sender_id)

        # Check 1 — sender must be in the allowed set
        if sender_id not in self._config.allowed_agent_ids:
            decision = GovernanceDecision(
                permitted=False,
                reason="sender_not_allowed",
                sender_id=sender_id,
                turn_number=next_turn_number,
                sender_trust_level=sender_trust,
                cumulative_cost=self._cumulative_cost,
            )
            self._record(decision)
            logger.info(
                "ConversationGovernanceManager: message from '%s' denied — "
                "sender_not_allowed (turn %d)",
                sender_id,
                next_turn_number,
            )
            return decision

        # Check 2 — sender must hold at least the minimum trust level
        if sender_trust < self.MINIMUM_TRUST_LEVEL:
            decision = GovernanceDecision(
                permitted=False,
                reason="insufficient_trust",
                sender_id=sender_id,
                turn_number=next_turn_number,
                sender_trust_level=sender_trust,
                cumulative_cost=self._cumulative_cost,
            )
            self._record(decision)
            logger.info(
                "ConversationGovernanceManager: message from '%s' denied — "
                "insufficient_trust (level=%d, turn=%d)",
                sender_id,
                sender_trust,
                next_turn_number,
            )
            return decision

        # Check 3 — cumulative budget ceiling (static, never modified)
        projected_cost = self._cumulative_cost + turn_cost
        if projected_cost > self._config.conversation_budget_limit:
            decision = GovernanceDecision(
                permitted=False,
                reason="budget_exceeded",
                sender_id=sender_id,
                turn_number=next_turn_number,
                sender_trust_level=sender_trust,
                cumulative_cost=self._cumulative_cost,
            )
            self._record(decision)
            logger.info(
                "ConversationGovernanceManager: message from '%s' denied — "
                "budget_exceeded (turn=%d)",
                sender_id,
                next_turn_number,
            )
            return decision

        # Check 4 — max turns ceiling
        if self._turn_count >= self._config.max_turns:
            decision = GovernanceDecision(
                permitted=False,
                reason="max_turns_exceeded",
                sender_id=sender_id,
                turn_number=next_turn_number,
                sender_trust_level=sender_trust,
                cumulative_cost=self._cumulative_cost,
            )
            self._record(decision)
            logger.info(
                "ConversationGovernanceManager: message from '%s' denied — "
                "max_turns_exceeded (turn=%d)",
                sender_id,
                next_turn_number,
            )
            return decision

        # All checks passed — advance counters and record permit
        self._turn_count += 1
        self._cumulative_cost = projected_cost

        decision = GovernanceDecision(
            permitted=True,
            reason="permitted",
            sender_id=sender_id,
            turn_number=self._turn_count,
            sender_trust_level=sender_trust,
            cumulative_cost=self._cumulative_cost,
        )
        self._record(decision)
        logger.debug(
            "ConversationGovernanceManager: message from '%s' permitted "
            "(turn=%d, cumulative_cost=%.4f)",
            sender_id,
            self._turn_count,
            self._cumulative_cost,
        )
        return decision

    # ------------------------------------------------------------------
    # Audit trail
    # ------------------------------------------------------------------

    def get_audit_trail(self) -> list[GovernanceDecision]:
        """Return a snapshot of the conversation audit trail.

        The returned list is a shallow copy — mutations to it do not affect the
        manager's internal trail.  Each entry is an immutable
        ``GovernanceDecision``.

        The audit trail records all decisions, including denials, in the order
        they were made.  It is never read by decision logic — it is a recording
        mechanism only.

        Returns:
            A list of ``GovernanceDecision`` instances ordered from oldest to
            newest.
        """
        return list(self._audit_trail)

    def audit_trail_size(self) -> int:
        """Return the number of decisions recorded in the audit trail."""
        return len(self._audit_trail)

    # ------------------------------------------------------------------
    # Conversation state accessors (read-only)
    # ------------------------------------------------------------------

    def turn_count(self) -> int:
        """Return the number of permitted message turns recorded so far."""
        return self._turn_count

    def cumulative_cost(self) -> float:
        """Return the total conversation cost accumulated across permitted turns."""
        return self._cumulative_cost

    def remaining_budget(self) -> float:
        """Return the remaining conversation budget (static ceiling minus spent).

        This value is informational only.  The manager's denial logic compares
        the projected cost directly against the ceiling and does not use this
        accessor internally.

        Returns:
            A float >= 0.0.
        """
        return max(0.0, self._config.conversation_budget_limit - self._cumulative_cost)

    def is_conversation_active(self) -> bool:
        """Return True if the conversation can still accept permitted messages.

        A conversation is considered active when the turn count is below
        ``max_turns`` and the cumulative cost is below the budget ceiling.
        This is a convenience accessor — actual enforcement happens inside
        ``evaluate_message``.

        Returns:
            ``True`` if further messages could be permitted (subject to trust
            and sender checks), ``False`` if the budget or turn ceiling has
            already been reached.
        """
        return (
            self._turn_count < self._config.max_turns
            and self._cumulative_cost < self._config.conversation_budget_limit
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _record(self, decision: GovernanceDecision) -> None:
        """Append a decision to the internal audit trail."""
        self._audit_trail.append(decision)

    def __repr__(self) -> str:
        return (
            f"ConversationGovernanceManager("
            f"turns={self._turn_count}, "
            f"cumulative_cost={self._cumulative_cost:.4f}, "
            f"agents={len(self._config.allowed_agent_ids)})"
        )


# ---------------------------------------------------------------------------
# Module-level helpers
# ---------------------------------------------------------------------------


def _extract_turn_cost(context: dict[str, Any] | None) -> float:
    """Extract the turn cost from the evaluation context dict.

    Returns 0.0 if ``context`` is ``None``, if the ``'cost'`` key is absent,
    or if the value cannot be interpreted as a non-negative float.

    Args:
        context: Optional dict that may contain a ``'cost'`` key.

    Returns:
        A non-negative float.
    """
    if context is None:
        return 0.0
    raw = context.get("cost", 0.0)
    try:
        cost = float(raw)  # type: ignore[arg-type]
        return max(cost, 0.0)
    except (TypeError, ValueError):
        return 0.0
