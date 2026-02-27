# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 MuVeraAI Corporation
"""
LCEL governance step — a ``RunnableSerializable`` that enforces AumOS governance
inside a LangChain Expression Language pipe chain.

Insert ``GovernanceRunnable`` anywhere in a pipe chain with the ``|`` operator::

    from langchain_aumos.lcel_step import GovernanceRunnable, GovernanceRunnableConfig

    config = GovernanceRunnableConfig(agent_id="rag-agent", required_trust_level=2)
    governance_step = GovernanceRunnable(engine, config)

    chain = prompt | llm | governance_step | output_parser

When governance denies, ``GovernanceRunnable`` raises ``GovernanceError`` so the
pipe stops cleanly.  Configure ``on_denied='skip'`` to pass a denial message
downstream instead of raising.

The runnable is transparent — it passes the input value through unchanged when
governance allows.  Pair it with a downstream step that can handle the
denial-message string when ``on_denied='skip'``.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Iterator, Optional

from langchain_core.runnables import RunnableConfig, RunnableSerializable
from langchain_core.runnables.utils import Input, Output
from pydantic import BaseModel, Field

from .errors import GovernanceDeniedError
from .types import DeniedAction

logger = logging.getLogger(__name__)

_DENIAL_PASS_MESSAGE = "[governance] request denied by policy — execution skipped"


# ---------------------------------------------------------------------------
# Configuration model
# ---------------------------------------------------------------------------


class GovernanceRunnableConfig(BaseModel):
    """
    Configuration for ``GovernanceRunnable``.

    Attributes:
        agent_id: Agent identifier forwarded to all engine evaluations.
        required_trust_level: Minimum static trust level for the check (manual
            ``>=`` comparison).
        spending_limit: Static per-invocation USD ceiling.  Compared with
            ``<=`` against ``spend_amount`` when present in the input dict.
            When ``None`` the budget check is skipped.
        require_consent: When ``True``, reads ``consent_granted`` from the
            input dict and denies if falsy.
        scope: Governance scope string forwarded to the engine.
        on_denied: ``'raise'`` (default) raises ``GovernanceError``.
            ``'skip'`` passes the denial message string downstream.
            ``'log'`` logs the denial and passes the original input through.
        spend_amount_key: Key in an input dict carrying the spend amount.
            Ignored when the input is not a dict.
        consent_key: Key in an input dict carrying the consent flag.
    """

    agent_id: str = Field(default="default", min_length=1)
    required_trust_level: int = Field(default=0, ge=0)
    spending_limit: float | None = Field(default=None, ge=0.0)
    require_consent: bool = Field(default=False)
    scope: str = Field(default="lcel_step", min_length=1)
    on_denied: DeniedAction = Field(default=DeniedAction.RAISE)
    spend_amount_key: str = Field(default="spend_amount")
    consent_key: str = Field(default="consent_granted")

    model_config = {"frozen": True}


# ---------------------------------------------------------------------------
# GovernanceRunnable
# ---------------------------------------------------------------------------


class GovernanceRunnable(RunnableSerializable[Input, Output]):  # type: ignore[type-arg]
    """
    LCEL-compatible governance step.

    Wraps AumOS governance as a ``RunnableSerializable`` so it can be composed
    into any LangChain Expression Language pipe with ``|``.

    The runnable passes its input through unchanged when governance allows.
    On denial, behaviour depends on ``config.on_denied``:

    * ``'raise'``: raises ``GovernanceDeniedError``.
    * ``'skip'``: returns the denial message string so downstream steps receive
      a signal they can handle.
    * ``'log'``: logs the denial and passes the original input through.

    Args:
        engine: Initialized ``aumos-governance`` ``GovernanceEngine``.
        config: ``GovernanceRunnableConfig`` controlling all check parameters.
    """

    # RunnableSerializable requires Pydantic fields for serialisation.
    # We store the engine outside Pydantic to avoid serialisation issues with
    # arbitrary engine objects.
    runnable_config: GovernanceRunnableConfig = Field(
        default_factory=GovernanceRunnableConfig
    )

    class Config:
        arbitrary_types_allowed = True

    def __init__(
        self,
        engine: Any,
        config: Optional[GovernanceRunnableConfig] = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(
            runnable_config=config or GovernanceRunnableConfig(),
            **kwargs,
        )
        # Store outside Pydantic model fields
        object.__setattr__(self, "_engine", engine)

    # ------------------------------------------------------------------
    # RunnableSerializable interface
    # ------------------------------------------------------------------

    def invoke(
        self,
        input: Input,  # noqa: A002
        config: Optional[RunnableConfig] = None,
        **kwargs: Any,
    ) -> Output:
        """
        Evaluate governance synchronously and pass ``input`` through on allow.

        Args:
            input: The value flowing through the LCEL pipe.
            config: Optional LangChain runnable config (ignored internally).

        Returns:
            The original ``input`` unchanged (allow) or the denial message
            string (skip mode).

        Raises:
            GovernanceDeniedError: When governance denies and ``on_denied='raise'``.
        """
        decision = self._evaluate_sync(input)
        return self._act_on_decision(decision, input)

    async def ainvoke(
        self,
        input: Input,  # noqa: A002
        config: Optional[RunnableConfig] = None,
        **kwargs: Any,
    ) -> Output:
        """
        Evaluate governance asynchronously and pass ``input`` through on allow.

        Args:
            input: The value flowing through the LCEL pipe.
            config: Optional LangChain runnable config (ignored internally).

        Returns:
            The original ``input`` unchanged (allow) or the denial message
            string (skip mode).

        Raises:
            GovernanceDeniedError: When governance denies and ``on_denied='raise'``.
        """
        decision = await self._evaluate_async(input)
        return self._act_on_decision(decision, input)

    def batch(
        self,
        inputs: list[Input],
        config: Optional[RunnableConfig | list[RunnableConfig]] = None,
        **kwargs: Any,
    ) -> list[Output]:
        """
        Evaluate governance on a batch of inputs sequentially.

        Each input is evaluated independently; a denial in one does not block
        others.

        Args:
            inputs: List of values to evaluate.
            config: Optional LangChain runnable config(s).

        Returns:
            List of outputs in the same order as inputs.
        """
        return [self.invoke(item, config=None) for item in inputs]

    async def abatch(
        self,
        inputs: list[Input],
        config: Optional[RunnableConfig | list[RunnableConfig]] = None,
        **kwargs: Any,
    ) -> list[Output]:
        """
        Evaluate governance on a batch of inputs concurrently.

        Args:
            inputs: List of values to evaluate.
            config: Optional LangChain runnable config(s).

        Returns:
            List of outputs in the same order as inputs.
        """
        return list(await asyncio.gather(*[self.ainvoke(item) for item in inputs]))

    # ------------------------------------------------------------------
    # Evaluation helpers
    # ------------------------------------------------------------------

    def _evaluate_sync(self, input_value: Any) -> Any:
        """Build eval kwargs from input and call the engine synchronously."""
        return self._engine.evaluate_sync(**self._build_eval_kwargs(input_value))

    async def _evaluate_async(self, input_value: Any) -> Any:
        """Build eval kwargs from input and call the engine asynchronously."""
        kwargs = self._build_eval_kwargs(input_value)
        if hasattr(self._engine, "evaluate"):
            return await self._engine.evaluate(**kwargs)
        return self._engine.evaluate_sync(**kwargs)

    def _build_eval_kwargs(self, input_value: Any) -> dict[str, Any]:
        """Construct the keyword arguments for a governance engine evaluation."""
        cfg = self.runnable_config
        eval_kwargs: dict[str, Any] = {
            "agent_id": cfg.agent_id,
            "scope": cfg.scope,
            "required_trust_level": cfg.required_trust_level,
        }
        if isinstance(input_value, dict):
            amount = input_value.get(cfg.spend_amount_key)
            if amount is not None:
                try:
                    eval_kwargs["amount"] = float(amount)
                except (TypeError, ValueError):
                    pass
            if cfg.require_consent:
                eval_kwargs["consent_granted"] = bool(
                    input_value.get(cfg.consent_key, False)
                )
        return eval_kwargs

    def _act_on_decision(self, decision: Any, original_input: Any) -> Any:
        """
        Apply the denial mode when governance denies; pass input through on allow.
        """
        if self._is_allowed(decision):
            return original_input

        reason = self._extract_reason(decision)
        cfg = self.runnable_config

        if cfg.on_denied == DeniedAction.RAISE:
            raise GovernanceDeniedError(
                tool_name=cfg.scope,
                agent_id=cfg.agent_id,
                reason=reason,
                decision=decision,
            )
        if cfg.on_denied == DeniedAction.SKIP:
            logger.info(
                "GovernanceRunnable '%s' skipped for agent '%s': %s",
                cfg.scope,
                cfg.agent_id,
                reason,
            )
            return _DENIAL_PASS_MESSAGE

        # DeniedAction.LOG — record and pass original input through
        logger.warning(
            "GovernanceRunnable '%s' denied for agent '%s' (logged, continuing): %s",
            cfg.scope,
            cfg.agent_id,
            reason,
        )
        return original_input

    def _is_allowed(self, decision: Any) -> bool:
        """Return True if the engine decision permits execution."""
        if hasattr(decision, "allowed"):
            return bool(decision.allowed)
        return bool(decision)

    def _extract_reason(self, decision: Any) -> str:
        """Return a human-readable denial reason from an engine decision."""
        if hasattr(decision, "reason") and decision.reason:
            return str(decision.reason)
        return "governance policy denied this LCEL step"
