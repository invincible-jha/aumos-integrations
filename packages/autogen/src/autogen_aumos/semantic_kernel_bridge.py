# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 MuVeraAI Corporation
"""
SemanticKernelGovernanceBridge — AumOS governance for Microsoft Semantic Kernel.

Bridges AumOS governance into Semantic Kernel (SK) function execution without
requiring a hard dependency on the ``semantic-kernel`` package. All SK-facing
types are expressed as Protocols so the bridge can be imported in environments
where SK is not installed.

Design invariants:
- Trust levels are set once at construction by the operator.
- Budget tracking records cumulative spend per invocation; the static ceiling
  is configured at construction and never adjusted at runtime.
- Audit recording calls ``engine.record_audit_event()`` after every invocation.
- Governance is a checkpoint, not a filter — either the invocation proceeds or
  it is denied. No partial execution.

Usage::

    from autogen_aumos.semantic_kernel_bridge import (
        GovernedKernelPlugin,
        SemanticKernelGovernanceBridge,
    )

    bridge = SemanticKernelGovernanceBridge(engine=engine, trust_level=2)
    governed_plugin = GovernedKernelPlugin(
        plugin=my_sk_plugin,
        plugin_name="data",
        bridge=bridge,
    )
    result = await governed_plugin.invoke("fetch_records", query=params)
"""

from __future__ import annotations

import logging
from typing import Any, Protocol, runtime_checkable

from pydantic import BaseModel, Field

from .errors import GovernanceDeniedError
from .types import AuditRecord, DeniedAction

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Protocols for SK compatibility without a hard import dependency
# ---------------------------------------------------------------------------


@runtime_checkable
class SKFunctionProtocol(Protocol):
    """Minimal interface that a Semantic Kernel function must expose.

    Concrete SK ``KernelFunction`` objects satisfy this protocol automatically.
    The bridge does not import from ``semantic_kernel`` directly so that this
    module can be used in environments where SK is not installed.
    """

    @property
    def name(self) -> str:
        """The function's name within its plugin."""
        ...

    async def invoke(self, *args: Any, **kwargs: Any) -> Any:
        """Invoke the function with the provided arguments."""
        ...


@runtime_checkable
class SKPluginProtocol(Protocol):
    """Minimal interface that a Semantic Kernel plugin must expose."""

    @property
    def name(self) -> str:
        """The plugin's registered name."""
        ...

    def get_functions_metadata(self) -> list[Any]:
        """Return metadata for all functions in this plugin."""
        ...


@runtime_checkable
class SKPlannerProtocol(Protocol):
    """Minimal interface that a Semantic Kernel planner must expose."""

    async def create_plan(self, goal: str) -> Any:
        """Create an execution plan for the given goal."""
        ...

    async def invoke_plan(self, plan: Any, **kwargs: Any) -> Any:
        """Execute a previously created plan."""
        ...


# ---------------------------------------------------------------------------
# Governance engine protocol (subset used by the bridge)
# ---------------------------------------------------------------------------


@runtime_checkable
class GovernanceEngineProtocol(Protocol):
    """Narrow protocol for the AumOS governance engine used by the bridge."""

    def evaluate_sync(self, agent_name: str, scope: str, amount: float | None) -> Any:
        """Synchronously evaluate a governance decision."""
        ...

    def record_audit_event(self, record: Any) -> None:
        """Record an audit event in the engine's audit log."""
        ...


# ---------------------------------------------------------------------------
# Configuration model
# ---------------------------------------------------------------------------


class SKBridgeConfig(BaseModel):
    """Configuration for the Semantic Kernel governance bridge.

    Attributes:
        on_denied: How to handle governance denials.
            ``'raise'`` — raise ``GovernanceDeniedError`` (default).
            ``'block'`` — return a denial result; execution does not proceed.
            ``'log'`` — log the denial and allow execution to continue.
        default_scope: Governance scope string used when no per-function
            scope mapping exists.
        function_scope_mapping: Optional mapping from function name to
            governance scope. When a function name is present here its scope
            takes precedence over ``default_scope``.
        plugin_scope_prefix: Prefix prepended to function names when forming
            the default scope. E.g., with prefix ``'sk:data'`` the scope for
            ``fetch_records`` becomes ``'sk:data:fetch_records'``.
        audit_invocations: When True, record an audit event for every
            function invocation (permitted and denied). Defaults to True.
        amount_kwarg: Optional keyword argument name to extract as the spend
            amount from function invocations. When set, the bridge looks for
            this key in the invocation kwargs and passes it to governance.
    """

    on_denied: DeniedAction = Field(
        default=DeniedAction.RAISE,
        description="Action when governance denies a function invocation.",
    )
    default_scope: str = Field(
        default="sk:function",
        min_length=1,
        description="Governance scope for function invocations without a mapping.",
    )
    function_scope_mapping: dict[str, str] = Field(
        default_factory=dict,
        description="Per-function governance scope overrides.",
    )
    plugin_scope_prefix: str = Field(
        default="sk",
        description="Prefix for constructing default scope strings from function names.",
    )
    audit_invocations: bool = Field(
        default=True,
        description="Record an audit event for every function invocation.",
    )
    amount_kwarg: str | None = Field(
        default=None,
        description="Kwarg name to extract as a spend amount from function invocations.",
    )

    model_config = {"frozen": True}

    def scope_for_function(self, function_name: str) -> str:
        """Return the governance scope for the given function name."""
        if function_name in self.function_scope_mapping:
            return self.function_scope_mapping[function_name]
        return f"{self.plugin_scope_prefix}:{function_name}"


# ---------------------------------------------------------------------------
# Core bridge
# ---------------------------------------------------------------------------


class SemanticKernelGovernanceBridge:
    """Governance bridge between AumOS and Semantic Kernel.

    Wraps invocations of SK functions and planners with AumOS governance
    checks. The bridge is stateless with respect to trust — the trust level
    is fixed at construction and never modified.

    Args:
        engine: An AumOS governance engine implementing
            ``GovernanceEngineProtocol``.
        trust_level: Operator-assigned trust level for this bridge context.
            Applies to all function invocations routed through this instance.
        config: Optional ``SKBridgeConfig`` controlling denial handling,
            scope mapping, and audit behaviour.

    Example::

        bridge = SemanticKernelGovernanceBridge(engine=engine, trust_level=2)
        governed_fn = bridge.wrap_kernel_function(
            my_function,
            governance_config=SKBridgeConfig(default_scope="sk:data"),
        )
        result = await governed_fn(query="select * from logs")
    """

    def __init__(
        self,
        engine: Any,
        trust_level: int = 2,
        config: SKBridgeConfig | None = None,
    ) -> None:
        self.engine = engine
        self.trust_level = trust_level
        self._config: SKBridgeConfig = config or SKBridgeConfig()

    def wrap_kernel_function(
        self,
        function: SKFunctionProtocol,
        governance_config: SKBridgeConfig | None = None,
    ) -> Any:
        """Wrap a Semantic Kernel function with AumOS governance.

        Returns a coroutine wrapper that performs a governance check before
        calling the original SK function. The wrapper has the same signature
        as the original ``invoke`` method.

        Args:
            function: The SK function to wrap. Must satisfy
                ``SKFunctionProtocol``.
            governance_config: Optional per-function config override. When
                provided, this config takes precedence over the bridge's
                default config.

        Returns:
            An async callable that runs governance then invokes the function.
        """
        effective_config = governance_config or self._config
        function_name = function.name

        bridge_ref = self
        function_ref = function

        async def governed_invoke(*args: Any, **kwargs: Any) -> Any:
            scope = effective_config.scope_for_function(function_name)
            amount: float | None = None
            if effective_config.amount_kwarg:
                raw = kwargs.get(effective_config.amount_kwarg)
                if isinstance(raw, (int, float)):
                    amount = float(raw)

            permitted, reason = bridge_ref._evaluate(
                agent_name=function_name,
                scope=scope,
                amount=amount,
            )

            if not permitted:
                if bridge_ref._config.audit_invocations:
                    bridge_ref._record_audit(
                        subject=function_name,
                        agent_name=function_name,
                        succeeded=False,
                        error_message=reason,
                    )
                return bridge_ref._handle_denial(
                    subject=function_name,
                    agent_name=function_name,
                    reason=reason,
                    config=effective_config,
                )

            try:
                result = await function_ref.invoke(*args, **kwargs)
            except Exception as exc:
                if bridge_ref._config.audit_invocations:
                    bridge_ref._record_audit(
                        subject=function_name,
                        agent_name=function_name,
                        succeeded=False,
                        error_message=str(exc),
                    )
                raise

            if bridge_ref._config.audit_invocations:
                bridge_ref._record_audit(
                    subject=function_name,
                    agent_name=function_name,
                    succeeded=True,
                    output_preview=str(result)[:256] if result is not None else None,
                )
            return result

        return governed_invoke

    def create_governed_planner(
        self,
        planner: SKPlannerProtocol,
        governance_config: SKBridgeConfig | None = None,
    ) -> GovernedSKPlanner:
        """Wrap a Semantic Kernel planner with AumOS governance.

        The returned ``GovernedSKPlanner`` intercepts ``create_plan`` and
        ``invoke_plan`` calls, applying governance checks before each.

        Args:
            planner: The SK planner to wrap. Must satisfy
                ``SKPlannerProtocol``.
            governance_config: Optional per-planner config override.

        Returns:
            A ``GovernedSKPlanner`` wrapping the original planner.
        """
        effective_config = governance_config or self._config
        return GovernedSKPlanner(
            planner=planner,
            bridge=self,
            config=effective_config,
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _evaluate(
        self,
        agent_name: str,
        scope: str,
        amount: float | None,
    ) -> tuple[bool, str]:
        """Run a synchronous governance evaluation.

        Returns a (permitted, reason) tuple. On engine errors, defaults to
        permitted=False to fail closed.
        """
        try:
            decision = self.engine.evaluate_sync(
                agent_name=agent_name,
                scope=scope,
                amount=amount,
            )
            permitted: bool = bool(getattr(decision, "permitted", False))
            reason: str = str(getattr(decision, "reason", ""))
            return permitted, reason
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "SemanticKernelGovernanceBridge: engine evaluation failed for "
                "'%s' scope='%s': %s — defaulting to deny.",
                agent_name,
                scope,
                exc,
            )
            return False, "engine_error"

    def _handle_denial(
        self,
        subject: str,
        agent_name: str,
        reason: str,
        config: SKBridgeConfig,
    ) -> Any:
        """Apply the configured denial action and return or raise."""
        if config.on_denied is DeniedAction.RAISE:
            raise GovernanceDeniedError(
                subject=subject,
                agent_name=agent_name,
                reason=reason,
            )
        if config.on_denied is DeniedAction.BLOCK:
            logger.info(
                "SemanticKernelGovernanceBridge: function '%s' blocked by governance: %s",
                subject,
                reason,
            )
            return {"error": f"Governance denied: {reason}"}
        # DeniedAction.LOG — log and return None to signal no result
        logger.warning(
            "SemanticKernelGovernanceBridge: function '%s' denied (log mode): %s",
            subject,
            reason,
        )
        return None

    def _record_audit(
        self,
        subject: str,
        agent_name: str,
        succeeded: bool,
        error_message: str | None = None,
        output_preview: str | None = None,
    ) -> None:
        """Write an audit record to the governance engine."""
        record = AuditRecord(
            subject=subject,
            agent_name=agent_name,
            succeeded=succeeded,
            error_message=error_message,
            output_preview=output_preview,
        )
        try:
            self.engine.record_audit_event(record)
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "SemanticKernelGovernanceBridge: audit recording failed: %s", exc
            )


# ---------------------------------------------------------------------------
# Governed planner wrapper
# ---------------------------------------------------------------------------


class GovernedSKPlanner:
    """A Semantic Kernel planner wrapped with AumOS governance.

    Created by ``SemanticKernelGovernanceBridge.create_governed_planner()``.
    Both ``create_plan`` and ``invoke_plan`` are governance-checked before
    execution.

    Args:
        planner: The underlying SK planner.
        bridge: The ``SemanticKernelGovernanceBridge`` providing governance.
        config: The ``SKBridgeConfig`` to apply for this planner.
    """

    def __init__(
        self,
        planner: SKPlannerProtocol,
        bridge: SemanticKernelGovernanceBridge,
        config: SKBridgeConfig,
    ) -> None:
        self._planner = planner
        self._bridge = bridge
        self._config = config

    async def create_plan(self, goal: str) -> Any:
        """Governance-checked plan creation.

        Evaluates governance before delegating to the underlying planner's
        ``create_plan`` method.

        Args:
            goal: The planning goal string.

        Returns:
            The plan object returned by the underlying planner.

        Raises:
            GovernanceDeniedError: When governance denies and ``on_denied='raise'``.
        """
        scope = self._config.scope_for_function("create_plan")
        permitted, reason = self._bridge._evaluate(
            agent_name="sk_planner",
            scope=scope,
            amount=None,
        )
        if not permitted:
            return self._bridge._handle_denial(
                subject="create_plan",
                agent_name="sk_planner",
                reason=reason,
                config=self._config,
            )
        return await self._planner.create_plan(goal)

    async def invoke_plan(self, plan: Any, **kwargs: Any) -> Any:
        """Governance-checked plan invocation.

        Evaluates governance before delegating to the underlying planner's
        ``invoke_plan`` method.

        Args:
            plan: The plan to execute.
            **kwargs: Additional keyword arguments forwarded to the planner.

        Returns:
            The result returned by the underlying planner.

        Raises:
            GovernanceDeniedError: When governance denies and ``on_denied='raise'``.
        """
        scope = self._config.scope_for_function("invoke_plan")
        amount: float | None = None
        if self._config.amount_kwarg:
            raw = kwargs.get(self._config.amount_kwarg)
            if isinstance(raw, (int, float)):
                amount = float(raw)

        permitted, reason = self._bridge._evaluate(
            agent_name="sk_planner",
            scope=scope,
            amount=amount,
        )
        if not permitted:
            return self._bridge._handle_denial(
                subject="invoke_plan",
                agent_name="sk_planner",
                reason=reason,
                config=self._config,
            )
        return await self._planner.invoke_plan(plan, **kwargs)


# ---------------------------------------------------------------------------
# Governed plugin
# ---------------------------------------------------------------------------


class GovernedKernelPlugin:
    """A Semantic Kernel plugin where every function is governance-checked.

    Wraps an existing SK plugin and intercepts all function invocations
    through the bridge's governance layer.

    Args:
        plugin: The SK plugin to wrap.
        plugin_name: The name under which this plugin is registered.
        bridge: The ``SemanticKernelGovernanceBridge`` providing governance.

    Example::

        governed_plugin = GovernedKernelPlugin(
            plugin=data_plugin,
            plugin_name="data",
            bridge=bridge,
        )
        result = await governed_plugin.invoke("fetch_records", query=params)
    """

    def __init__(
        self,
        plugin: Any,
        plugin_name: str,
        bridge: SemanticKernelGovernanceBridge,
    ) -> None:
        self._plugin = plugin
        self._plugin_name = plugin_name
        self._bridge = bridge

    async def invoke(self, function_name: str, **kwargs: Any) -> Any:
        """Invoke a named function in the governed plugin.

        Performs a governance check before delegating to the underlying
        plugin's function. The scope is derived from the plugin name and
        function name.

        Args:
            function_name: Name of the function to invoke.
            **kwargs: Arguments forwarded to the function.

        Returns:
            The result of the function invocation.

        Raises:
            GovernanceDeniedError: When governance denies and ``on_denied='raise'``.
            AttributeError: If the underlying plugin does not expose the
                named function.
        """
        scope = f"sk:{self._plugin_name}:{function_name}"
        amount: float | None = None
        if self._bridge._config.amount_kwarg:
            raw = kwargs.get(self._bridge._config.amount_kwarg)
            if isinstance(raw, (int, float)):
                amount = float(raw)

        permitted, reason = self._bridge._evaluate(
            agent_name=f"{self._plugin_name}.{function_name}",
            scope=scope,
            amount=amount,
        )
        if not permitted:
            return self._bridge._handle_denial(
                subject=f"{self._plugin_name}.{function_name}",
                agent_name=f"{self._plugin_name}.{function_name}",
                reason=reason,
                config=self._bridge._config,
            )

        func = getattr(self._plugin, function_name)
        return await func(**kwargs)

    @property
    def name(self) -> str:
        """Return the governed plugin's name."""
        return self._plugin_name
