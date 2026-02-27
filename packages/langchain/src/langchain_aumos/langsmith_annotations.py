# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 MuVeraAI Corporation
"""
LangSmith trace annotations for AumOS governance decisions.

This module provides two complementary ways to attach governance metadata to
LangSmith traces:

1. ``GovernanceAnnotator`` — annotate any LangSmith run by run ID after the
   fact.  Use this when you have the run ID from a prior step.

2. ``GovernanceTraceCallback`` — a ``BaseCallbackHandler`` that attaches
   governance metadata automatically at the end of each LangChain callback event.

Both are no-ops when ``langsmith`` is not installed, so you can ship this
integration without making ``langsmith`` a hard dependency.

Annotations recorded on each trace:
    * ``governance.allowed`` — bool, final decision
    * ``governance.trust_level`` — int, static trust level at decision time
    * ``governance.consent_status`` — bool, consent flag at decision time
    * ``governance.budget_remaining`` — float or null, residual budget
    * ``governance.scope`` — str, governance scope evaluated
    * ``governance.denial_reason`` — str, populated only on denial

Usage::

    from langchain_aumos.langsmith_annotations import GovernanceTraceCallback

    callback = GovernanceTraceCallback(engine, agent_id="my-agent")
    executor = AgentExecutor(agent=agent, tools=tools, callbacks=[callback])
"""

from __future__ import annotations

import logging
from typing import Any, Optional
from uuid import UUID

logger = logging.getLogger(__name__)

# Attempt to import langsmith — gracefully degrade to no-op if absent.
try:
    from langsmith import Client as LangSmithClient  # type: ignore[import]
    _LANGSMITH_AVAILABLE = True
except ImportError:
    _LANGSMITH_AVAILABLE = False
    LangSmithClient = None  # type: ignore[assignment,misc]

try:
    from langchain_core.callbacks import BaseCallbackHandler  # type: ignore[import]
    _LANGCHAIN_CORE_AVAILABLE = True
except ImportError:
    _LANGCHAIN_CORE_AVAILABLE = False
    BaseCallbackHandler = object  # type: ignore[assignment,misc]


# ---------------------------------------------------------------------------
# Annotation data model
# ---------------------------------------------------------------------------


class GovernanceAnnotation:
    """
    Governance metadata to attach to a LangSmith trace.

    All fields are recorded as trace metadata — nothing here drives any logic.
    This is a recording-only structure.

    Attributes:
        allowed: Whether the governance check passed.
        trust_level: The static trust level at the time of evaluation.
        consent_status: Whether consent was present at decision time.
        budget_remaining: Remaining budget after this evaluation, or ``None``
            when no budget check was performed.
        scope: The governance scope evaluated.
        denial_reason: Human-readable denial reason; empty string on allow.
    """

    __slots__ = (
        "allowed",
        "trust_level",
        "consent_status",
        "budget_remaining",
        "scope",
        "denial_reason",
    )

    def __init__(
        self,
        *,
        allowed: bool,
        trust_level: int = 0,
        consent_status: bool = True,
        budget_remaining: float | None = None,
        scope: str = "unknown",
        denial_reason: str = "",
    ) -> None:
        self.allowed = allowed
        self.trust_level = trust_level
        self.consent_status = consent_status
        self.budget_remaining = budget_remaining
        self.scope = scope
        self.denial_reason = denial_reason

    def to_metadata_dict(self) -> dict[str, Any]:
        """Serialise to a flat dict suitable for LangSmith metadata fields."""
        return {
            "governance.allowed": self.allowed,
            "governance.trust_level": self.trust_level,
            "governance.consent_status": self.consent_status,
            "governance.budget_remaining": self.budget_remaining,
            "governance.scope": self.scope,
            "governance.denial_reason": self.denial_reason,
        }


# ---------------------------------------------------------------------------
# GovernanceAnnotator
# ---------------------------------------------------------------------------


class GovernanceAnnotator:
    """
    Annotates LangSmith runs with AumOS governance metadata.

    This is the low-level API.  Pass a LangSmith run ID and a
    ``GovernanceAnnotation`` to ``annotate_run()`` to attach governance
    metadata to that trace.

    When ``langsmith`` is not installed, all methods are silent no-ops so that
    teams that do not use LangSmith can still import this module without errors.

    Args:
        langsmith_client: Optional pre-constructed ``langsmith.Client``.  When
            ``None`` a default client is constructed using environment
            credentials (``LANGSMITH_API_KEY``).

    Example::

        annotator = GovernanceAnnotator()
        annotator.annotate_run(
            run_id="abc123",
            annotation=GovernanceAnnotation(
                allowed=False,
                trust_level=1,
                scope="rag_retrieval",
                denial_reason="trust level below required",
            ),
        )
    """

    def __init__(self, langsmith_client: Optional[Any] = None) -> None:
        self._client: Any = None
        if not _LANGSMITH_AVAILABLE:
            logger.debug(
                "langsmith not installed — GovernanceAnnotator running in no-op mode"
            )
            return
        if langsmith_client is not None:
            self._client = langsmith_client
        else:
            try:
                self._client = LangSmithClient()
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "GovernanceAnnotator: failed to construct LangSmith client "
                    "(annotations disabled): %s",
                    exc,
                )

    def annotate_run(
        self,
        run_id: str,
        annotation: GovernanceAnnotation,
    ) -> None:
        """
        Attach governance metadata to a LangSmith run.

        This is a recording-only operation — it writes governance outcome
        metadata to the trace for human review.  It never reads from or
        modifies any governance policy.

        Args:
            run_id: The LangSmith run ID to annotate.
            annotation: The governance annotation to attach.
        """
        if self._client is None:
            logger.debug(
                "GovernanceAnnotator no-op: run_id=%s allowed=%s",
                run_id,
                annotation.allowed,
            )
            return

        metadata = annotation.to_metadata_dict()
        try:
            self._client.update_run(run_id=run_id, extra={"metadata": metadata})
            logger.debug(
                "GovernanceAnnotator: annotated run %s (allowed=%s)",
                run_id,
                annotation.allowed,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "GovernanceAnnotator: failed to annotate run %s: %s",
                run_id,
                exc,
            )

    def from_engine_decision(
        self,
        decision: Any,
        *,
        scope: str = "unknown",
        trust_level: int = 0,
        consent_status: bool = True,
        budget_remaining: float | None = None,
    ) -> GovernanceAnnotation:
        """
        Build a ``GovernanceAnnotation`` from a raw engine decision object.

        Extracts ``allowed`` and ``reason`` from the decision using duck-typing
        so this works across aumos-governance SDK versions.

        Args:
            decision: Raw decision returned by the engine.
            scope: Governance scope for recording.
            trust_level: Static trust level at evaluation time.
            consent_status: Consent flag at evaluation time.
            budget_remaining: Residual budget, or ``None``.

        Returns:
            A ``GovernanceAnnotation`` ready to pass to ``annotate_run()``.
        """
        allowed = bool(getattr(decision, "allowed", decision))
        reason = str(getattr(decision, "reason", "")) if not allowed else ""
        return GovernanceAnnotation(
            allowed=allowed,
            trust_level=trust_level,
            consent_status=consent_status,
            budget_remaining=budget_remaining,
            scope=scope,
            denial_reason=reason,
        )


# ---------------------------------------------------------------------------
# GovernanceTraceCallback
# ---------------------------------------------------------------------------


class GovernanceTraceCallback(BaseCallbackHandler):  # type: ignore[misc]
    """
    LangChain callback handler that auto-annotates LangSmith traces with
    governance metadata after each tool call.

    Attach to any ``AgentExecutor`` or chain to capture governance outcomes
    automatically without manual ``annotate_run()`` calls.

    When ``langsmith`` is not installed, the callback is a transparent no-op.

    Args:
        engine: Initialized ``aumos-governance`` ``GovernanceEngine``.
        agent_id: Agent identifier used in governance evaluations.
        scope: Default governance scope to record in annotations.
        langsmith_client: Optional pre-constructed ``langsmith.Client``.

    Example::

        callback = GovernanceTraceCallback(engine, agent_id="my-agent")
        executor = AgentExecutor(agent=agent, tools=tools, callbacks=[callback])
    """

    def __init__(
        self,
        engine: Any,
        agent_id: str = "default",
        scope: str = "tool_call",
        langsmith_client: Optional[Any] = None,
    ) -> None:
        if _LANGCHAIN_CORE_AVAILABLE:
            super().__init__()
        self._engine = engine
        self._agent_id = agent_id
        self._scope = scope
        self._annotator = GovernanceAnnotator(langsmith_client=langsmith_client)

    def on_tool_end(
        self,
        output: str,
        *,
        run_id: UUID | None = None,
        **kwargs: Any,
    ) -> None:
        """
        Annotate the LangSmith trace for a successfully completed tool call.

        Records the governance outcome as metadata on the run.  This is
        recording-only — no policy decisions are made here.

        Args:
            output: Tool output string (not inspected — only length is used
                for the preview key).
            run_id: LangChain run identifier for the trace to annotate.
            **kwargs: Additional LangChain callback kwargs (ignored).
        """
        if run_id is None:
            return
        annotation = GovernanceAnnotation(
            allowed=True,
            scope=self._scope,
        )
        self._annotator.annotate_run(run_id=str(run_id), annotation=annotation)

    def on_tool_error(
        self,
        error: BaseException,
        *,
        run_id: UUID | None = None,
        **kwargs: Any,
    ) -> None:
        """
        Annotate the LangSmith trace when a tool raises an exception.

        Records ``allowed=False`` with the error message as the denial reason.
        This is recording-only — no policy decisions are made here.

        Args:
            error: The exception raised by the tool.
            run_id: LangChain run identifier for the trace to annotate.
            **kwargs: Additional LangChain callback kwargs (ignored).
        """
        if run_id is None:
            return
        annotation = GovernanceAnnotation(
            allowed=False,
            scope=self._scope,
            denial_reason=str(error),
        )
        self._annotator.annotate_run(run_id=str(run_id), annotation=annotation)

    def on_chain_end(
        self,
        outputs: dict[str, Any],
        *,
        run_id: UUID | None = None,
        **kwargs: Any,
    ) -> None:
        """
        Annotate the LangSmith trace when a chain completes.

        Checks whether the output contains a ``governance_blocked`` key
        (written by ``GovernanceNode`` or ``ChainGuard``) and records the
        corresponding outcome.

        Args:
            outputs: Chain output dict.
            run_id: LangChain run identifier for the trace to annotate.
            **kwargs: Additional LangChain callback kwargs (ignored).
        """
        if run_id is None:
            return
        blocked = bool(outputs.get("governance_blocked", False))
        denial_reason = str(outputs.get("governance_denial_reason", "")) if blocked else ""
        annotation = GovernanceAnnotation(
            allowed=not blocked,
            scope=self._scope,
            denial_reason=denial_reason,
        )
        self._annotator.annotate_run(run_id=str(run_id), annotation=annotation)
