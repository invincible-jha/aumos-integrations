# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 MuVeraAI Corporation
"""
ChainGuard — governance wrapper for LangChain chain execution.

Use ``ChainGuard`` when you need to enforce governance at the chain entry point
rather than (or in addition to) individual tool calls. The guard evaluates
governance before the chain receives any input and either allows execution,
raises ``GovernanceDeniedError``, or returns a denial message.
"""

from __future__ import annotations

import logging
from typing import Any, Callable, Optional

from .errors import GovernanceDeniedError
from .types import DeniedAction

logger = logging.getLogger(__name__)


class GuardedChain:
    """
    A thin wrapper around a LangChain chain that adds a governance checkpoint
    at invocation time.

    Created by ``ChainGuard.guard()``. Exposes the same ``invoke`` and
    ``ainvoke`` interface as standard LangChain runnables.

    Args:
        chain: The original LangChain chain or runnable.
        guard: The ``ChainGuard`` instance providing evaluation logic.
        chain_name: Name used to look up trust requirements and for audit records.
    """

    def __init__(
        self,
        chain: Any,
        guard: "ChainGuard",
        chain_name: str,
    ) -> None:
        self._chain = chain
        self._guard = guard
        self._chain_name = chain_name

    def invoke(self, chain_input: Any, **kwargs: Any) -> Any:
        """
        Evaluate governance, then invoke the chain synchronously.

        Args:
            chain_input: The input dict or string passed to the chain.
            **kwargs: Additional kwargs forwarded to the chain's ``invoke`` method.

        Returns:
            The chain's output.

        Raises:
            GovernanceDeniedError: If governance denies and ``on_denied='raise'``.
        """
        self._guard._evaluate_sync_for_chain(self._chain_name)
        result = self._chain.invoke(chain_input, **kwargs)
        self._guard._audit_chain(self._chain_name, succeeded=True)
        return result

    async def ainvoke(self, chain_input: Any, **kwargs: Any) -> Any:
        """
        Evaluate governance, then invoke the chain asynchronously.

        Args:
            chain_input: The input dict or string passed to the chain.
            **kwargs: Additional kwargs forwarded to the chain's ``ainvoke`` method.

        Returns:
            The chain's output.

        Raises:
            GovernanceDeniedError: If governance denies and ``on_denied='raise'``.
        """
        await self._guard._evaluate_async_for_chain(self._chain_name)
        result = await self._chain.ainvoke(chain_input, **kwargs)
        self._guard._audit_chain(self._chain_name, succeeded=True)
        return result

    def __call__(self, chain_input: Any, **kwargs: Any) -> Any:
        """Allow the guarded chain to be called like a function."""
        return self.invoke(chain_input, **kwargs)

    def __getattr__(self, name: str) -> Any:
        """Delegate attribute access to the inner chain for compatibility."""
        return getattr(self._chain, name)


class ChainGuard:
    """
    Governance wrapper for LangChain chain execution.

    ``ChainGuard`` evaluates governance before a chain receives any input.
    This is complementary to ``AumOSGovernanceCallback``, which governs
    individual tool calls within a chain. Use ``ChainGuard`` when you need
    a coarser governance boundary at the chain entry point.

    Args:
        engine: An initialized ``aumos-governance`` ``GovernanceEngine`` instance.
        agent_id: Agent identifier used in governance evaluations. Defaults to
            ``'default'``.
        on_denied: Denial handling mode. ``'raise'`` | ``'skip'`` | ``'log'``.
            Defaults to ``'raise'``.
        trust_requirements: Optional mapping from chain name to minimum trust
            level. Passed to the engine as metadata; enforcement is performed
            by the engine, not this class.
        default_scope: Governance scope used for all chain evaluations when no
            chain-specific scope is configured. Defaults to ``'chain_execution'``.

    Example::

        guard = ChainGuard(engine=engine, trust_requirements={"summary_chain": 1})
        safe_chain = guard.guard(summary_chain)

        # Standard LangChain invocation
        result = safe_chain.invoke({"input": "Summarize this document..."})

        # Or async
        result = await safe_chain.ainvoke({"input": "..."})
    """

    def __init__(
        self,
        engine: Any,
        agent_id: str = "default",
        on_denied: DeniedAction | str = DeniedAction.RAISE,
        trust_requirements: Optional[dict[str, int]] = None,
        default_scope: str = "chain_execution",
    ) -> None:
        self._engine = engine
        self._agent_id = agent_id
        self._on_denied = (
            DeniedAction(on_denied) if isinstance(on_denied, str) else on_denied
        )
        self._trust_requirements: dict[str, int] = trust_requirements or {}
        self._default_scope = default_scope

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def guard(self, chain: Any, chain_name: str = "chain") -> GuardedChain:
        """
        Wrap a LangChain chain with a governance checkpoint.

        Args:
            chain: Any LangChain runnable or chain object.
            chain_name: Logical name for the chain, used for trust requirement
                lookups and audit records. Defaults to ``'chain'``.

        Returns:
            A ``GuardedChain`` that behaves like the original chain but evaluates
            governance before each invocation.
        """
        return GuardedChain(chain=chain, guard=self, chain_name=chain_name)

    def wrap(self, chain_name: str = "chain") -> Callable[[Any], GuardedChain]:
        """
        Decorator form of ``guard``.

        Example::

            @guard.wrap("my_chain")
            def build_chain():
                return ...
        """
        def decorator(chain: Any) -> GuardedChain:
            return self.guard(chain, chain_name=chain_name)
        return decorator

    # ------------------------------------------------------------------
    # Internal evaluation helpers (called by GuardedChain)
    # ------------------------------------------------------------------

    def _build_eval_kwargs(self, chain_name: str) -> dict[str, Any]:
        """Build keyword arguments for a governance evaluation call."""
        eval_kwargs: dict[str, Any] = {
            "agent_id": self._agent_id,
            "scope": f"chain:{chain_name}",
        }
        trust_level = self._trust_requirements.get(chain_name)
        if trust_level is not None:
            eval_kwargs["required_trust_level"] = trust_level
        return eval_kwargs

    def _evaluate_sync_for_chain(self, chain_name: str) -> None:
        """
        Submit a synchronous governance evaluation for a chain invocation.

        Raises ``GovernanceDeniedError`` or logs according to ``on_denied``
        if the decision is a denial.
        """
        decision = self._engine.evaluate_sync(**self._build_eval_kwargs(chain_name))
        if not self._is_allowed(decision):
            reason = self._extract_reason(decision)
            self._handle_denial(chain_name, reason, decision)

    async def _evaluate_async_for_chain(self, chain_name: str) -> None:
        """
        Submit an asynchronous governance evaluation for a chain invocation.
        """
        eval_kwargs = self._build_eval_kwargs(chain_name)
        if hasattr(self._engine, "evaluate"):
            decision = await self._engine.evaluate(**eval_kwargs)
        else:
            decision = self._engine.evaluate_sync(**eval_kwargs)

        if not self._is_allowed(decision):
            reason = self._extract_reason(decision)
            self._handle_denial(chain_name, reason, decision)

    def _is_allowed(self, decision: Any) -> bool:
        """Return True if the governance decision permits the chain execution."""
        if hasattr(decision, "allowed"):
            return bool(decision.allowed)
        return bool(decision)

    def _extract_reason(self, decision: Any) -> str:
        """Return a human-readable denial reason from the governance decision."""
        if hasattr(decision, "reason") and decision.reason:
            return str(decision.reason)
        return "governance policy denied this chain execution"

    def _handle_denial(
        self, chain_name: str, reason: str, decision: Any
    ) -> None:
        """
        Act on a denial according to the configured ``on_denied`` mode.

        RAISE: Raise ``GovernanceDeniedError``.
        SKIP: Log at INFO level and raise ``GovernanceDeniedError`` with a skip
            note (chains do not have a skip-to-message path the way tools do).
        LOG: Log at WARNING level and return, allowing execution to continue.
        """
        if self._on_denied in (DeniedAction.RAISE, DeniedAction.SKIP):
            raise GovernanceDeniedError(
                tool_name=chain_name,
                agent_id=self._agent_id,
                reason=reason,
                decision=decision,
            )
        else:
            # DeniedAction.LOG
            logger.warning(
                "ChainGuard denied '%s' for agent '%s' (logged, execution continues): %s",
                chain_name,
                self._agent_id,
                reason,
            )

    def _audit_chain(self, chain_name: str, succeeded: bool) -> None:
        """Record a chain execution outcome in the audit trail."""
        if hasattr(self._engine, "record_audit_event"):
            self._engine.record_audit_event(
                agent_id=self._agent_id,
                tool_name=chain_name,
                succeeded=succeeded,
            )
