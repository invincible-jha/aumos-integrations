# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 MuVeraAI Corporation
"""
Per-crew budget management for crewai-aumos.

Each crew receives a static spending envelope at allocation time. The envelope
defines the maximum spend (in the operator-chosen currency/unit) for that crew's
entire run. Spend is recorded against the envelope as tool calls complete.

All limits are static integers or floats set by the operator. There is no
adaptive reallocation, no ML-based forecasting, and no automatic limit changes.
Budget exhaustion is a hard stop — the operator must explicitly allocate a new
envelope to continue.

Design notes:
- ``CrewBudgetTracker`` is intentionally not backed by a persistent store. For
  production use, subclass or compose it with a store-aware implementation that
  persists envelope state between process restarts.
- Thread safety: the tracker uses a per-envelope ``threading.Lock`` so that
  concurrent tool calls within a crew do not corrupt envelope state. For
  asyncio-based CrewAI flows, acquire the lock in an executor.
"""

from __future__ import annotations

import logging
import threading
from datetime import datetime, timezone
from typing import Final

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

_UNALLOCATED_REASON: Final[str] = "No budget envelope has been allocated for this crew."


# ---------------------------------------------------------------------------
# Result and summary types
# ---------------------------------------------------------------------------


class BudgetDecision(BaseModel):
    """
    Result of a ``check_crew_budget`` call.

    Attributes:
        permitted: True if the proposed spend fits within the remaining envelope.
        crew_id: The crew identifier this decision applies to.
        remaining_before: Envelope balance before the proposed spend.
        proposed_amount: The spend amount that was checked.
        reason: Human-readable explanation of the decision.
    """

    permitted: bool = Field(description="True if the proposed spend is within budget.")
    crew_id: str = Field(description="Crew identifier.")
    remaining_before: float = Field(
        description="Envelope balance before the proposed spend."
    )
    proposed_amount: float = Field(description="The spend amount that was evaluated.")
    reason: str = Field(description="Human-readable decision explanation.")

    model_config = {"frozen": True}


class SpendRecord(BaseModel):
    """
    A single recorded spend entry against a crew envelope.

    Attributes:
        amount: Spend amount recorded.
        recorded_at: UTC timestamp of the record.
        note: Optional human-readable label for the spend entry.
    """

    amount: float = Field(description="Spend amount.")
    recorded_at: datetime = Field(description="UTC timestamp of this record.")
    note: str | None = Field(default=None, description="Optional label.")

    model_config = {"frozen": True}


class CrewBudgetSummary(BaseModel):
    """
    Summary of a crew's budget envelope and spend history.

    Attributes:
        crew_id: The crew identifier.
        currency: Currency or unit label as set at allocation time.
        limit: Static spend limit for this envelope.
        total_spent: Sum of all recorded spend entries.
        remaining: Remaining balance (limit minus total_spent).
        spend_records: Chronological list of all recorded spend entries.
        allocated_at: UTC timestamp when the envelope was created.
    """

    crew_id: str = Field(description="Crew identifier.")
    currency: str = Field(description="Currency or unit label.")
    limit: float = Field(description="Static spend limit.")
    total_spent: float = Field(description="Sum of all recorded spend entries.")
    remaining: float = Field(description="Remaining balance.")
    spend_records: list[SpendRecord] = Field(
        default_factory=list,
        description="Chronological spend history.",
    )
    allocated_at: datetime = Field(description="UTC timestamp of envelope creation.")

    model_config = {"frozen": True}


# ---------------------------------------------------------------------------
# Internal envelope
# ---------------------------------------------------------------------------


class _BudgetEnvelope:
    """
    Internal mutable envelope holding the state for one crew's budget.

    Not part of the public API. Accessed only through ``CrewBudgetTracker``.
    """

    def __init__(self, crew_id: str, limit: float, currency: str) -> None:
        self.crew_id = crew_id
        self.limit = limit
        self.currency = currency
        self.total_spent: float = 0.0
        self.spend_records: list[SpendRecord] = []
        self.allocated_at: datetime = datetime.now(tz=timezone.utc)
        self._lock = threading.Lock()

    @property
    def remaining(self) -> float:
        """Return the remaining balance."""
        return max(0.0, self.limit - self.total_spent)

    def record(self, amount: float, note: str | None = None) -> None:
        """Append a spend record and update the running total. Thread-safe."""
        with self._lock:
            self.total_spent += amount
            self.spend_records.append(
                SpendRecord(
                    amount=amount,
                    recorded_at=datetime.now(tz=timezone.utc),
                    note=note,
                )
            )

    def check(self, proposed_amount: float) -> BudgetDecision:
        """Return a BudgetDecision for the proposed spend. Thread-safe (read)."""
        with self._lock:
            remaining = self.remaining
            permitted = proposed_amount <= remaining
            if permitted:
                reason = (
                    f"Spend of {proposed_amount} {self.currency} approved; "
                    f"{remaining} {self.currency} remains in envelope."
                )
            else:
                reason = (
                    f"Spend of {proposed_amount} {self.currency} denied; "
                    f"only {remaining} {self.currency} remains in envelope "
                    f"(limit: {self.limit} {self.currency})."
                )
            return BudgetDecision(
                permitted=permitted,
                crew_id=self.crew_id,
                remaining_before=remaining,
                proposed_amount=proposed_amount,
                reason=reason,
            )

    def to_summary(self) -> CrewBudgetSummary:
        """Return an immutable summary snapshot. Thread-safe (read)."""
        with self._lock:
            return CrewBudgetSummary(
                crew_id=self.crew_id,
                currency=self.currency,
                limit=self.limit,
                total_spent=self.total_spent,
                remaining=self.remaining,
                spend_records=list(self.spend_records),
                allocated_at=self.allocated_at,
            )


# ---------------------------------------------------------------------------
# Public tracker
# ---------------------------------------------------------------------------


class CrewBudgetTracker:
    """
    Manage per-crew static spending envelopes.

    Each crew identified by ``crew_id`` can have at most one active envelope at
    a time. Calling ``allocate_budget`` for a crew that already has an envelope
    replaces the existing one — the previous spend history is discarded. The
    operator is responsible for deciding when to re-allocate.

    This class is safe for use from multiple threads (one lock per envelope).
    For asyncio contexts, call spend and check methods from a thread executor.

    Example::

        tracker = CrewBudgetTracker()
        tracker.allocate_budget("research-crew", limit=100.0, currency="USD")

        decision = tracker.check_crew_budget("research-crew", proposed_amount=5.0)
        if decision.permitted:
            tracker.record_crew_spend("research-crew", amount=5.0)
    """

    def __init__(self) -> None:
        self._envelopes: dict[str, _BudgetEnvelope] = {}
        self._registry_lock = threading.Lock()

    def allocate_budget(
        self,
        crew_id: str,
        limit: float,
        currency: str = "USD",
    ) -> None:
        """
        Create a static spending envelope for the given crew.

        If an envelope already exists for ``crew_id`` it is replaced. Any
        previous spend history is discarded. Limits are set once and not
        modified automatically.

        Args:
            crew_id: Non-empty string identifying the crew.
            limit: Maximum total spend for this envelope. Must be positive.
            currency: Currency or unit label used in audit messages. Defaults
                to ``"USD"``. Pass ``"tokens"`` or ``"credits"`` as needed.

        Raises:
            ValueError: If ``crew_id`` is empty or ``limit`` is not positive.
        """
        if not crew_id:
            raise ValueError("crew_id must be a non-empty string.")
        if limit <= 0:
            raise ValueError(f"Budget limit must be positive; got {limit!r}.")

        envelope = _BudgetEnvelope(crew_id=crew_id, limit=limit, currency=currency)
        with self._registry_lock:
            self._envelopes[crew_id] = envelope

        logger.debug(
            "CrewBudgetTracker: allocated envelope for crew '%s' "
            "(limit=%s %s)",
            crew_id,
            limit,
            currency,
        )

    def record_crew_spend(
        self,
        crew_id: str,
        amount: float,
        note: str | None = None,
    ) -> None:
        """
        Record a spend amount against the crew's envelope.

        Recording proceeds even if the envelope is already exhausted — the
        tracker records what actually happened for audit purposes. Callers
        should call ``check_crew_budget`` before executing a tool call to
        prevent overspend.

        Args:
            crew_id: The crew whose envelope to debit.
            amount: The spend amount. Must be positive.
            note: Optional human-readable label (e.g., tool name).

        Raises:
            KeyError: If no envelope has been allocated for ``crew_id``.
            ValueError: If ``amount`` is not positive.
        """
        if amount <= 0:
            raise ValueError(f"Spend amount must be positive; got {amount!r}.")
        envelope = self._get_envelope(crew_id)
        envelope.record(amount=amount, note=note)
        logger.debug(
            "CrewBudgetTracker: recorded spend of %s for crew '%s' "
            "(remaining: %s %s)",
            amount,
            crew_id,
            envelope.remaining,
            envelope.currency,
        )

    def check_crew_budget(
        self,
        crew_id: str,
        proposed_amount: float,
    ) -> BudgetDecision:
        """
        Check whether a proposed spend fits within the crew's envelope.

        Does not modify envelope state. Call ``record_crew_spend`` separately
        after a permitted tool call completes.

        Args:
            crew_id: The crew whose envelope to check.
            proposed_amount: The spend amount to evaluate.

        Returns:
            A ``BudgetDecision`` indicating whether the spend is permitted and
            the remaining balance before the proposed spend.

        Raises:
            KeyError: If no envelope has been allocated for ``crew_id``.
        """
        if not self.has_envelope(crew_id):
            return BudgetDecision(
                permitted=False,
                crew_id=crew_id,
                remaining_before=0.0,
                proposed_amount=proposed_amount,
                reason=_UNALLOCATED_REASON,
            )
        envelope = self._get_envelope(crew_id)
        return envelope.check(proposed_amount)

    def get_crew_budget_summary(self, crew_id: str) -> CrewBudgetSummary:
        """
        Return an immutable summary of the crew's envelope and spend history.

        Args:
            crew_id: The crew to summarise.

        Returns:
            A ``CrewBudgetSummary`` snapshot.

        Raises:
            KeyError: If no envelope has been allocated for ``crew_id``.
        """
        return self._get_envelope(crew_id).to_summary()

    def has_envelope(self, crew_id: str) -> bool:
        """Return True if an envelope has been allocated for ``crew_id``."""
        with self._registry_lock:
            return crew_id in self._envelopes

    def _get_envelope(self, crew_id: str) -> _BudgetEnvelope:
        """Return the envelope for ``crew_id`` or raise ``KeyError``."""
        with self._registry_lock:
            try:
                return self._envelopes[crew_id]
            except KeyError:
                raise KeyError(
                    f"No budget envelope allocated for crew '{crew_id}'. "
                    "Call allocate_budget() first."
                ) from None
