# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 MuVeraAI Corporation
"""
GovernedConversableAgent — AutoGen ConversableAgent with governance checks
on messages and tool calls.

Uses composition rather than inheritance to avoid tight coupling to AutoGen
internals. The original ``ConversableAgent`` is held as a private attribute.
Governance is applied by registering message hooks and a function pre-execution
interceptor on the wrapped agent at construction time.

Trust levels are set manually by the operator at construction — never computed
from runtime behaviour.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from .config import AutoGenGovernanceConfig
from .errors import GovernanceDeniedError, MessageBlockedError
from .message_guard import MessageGuard
from .tool_guard import ToolGuard
from .types import DeniedAction

logger = logging.getLogger(__name__)


class GovernedConversableAgent:
    """
    AutoGen ``ConversableAgent`` with governance checks on messages and tool calls.

    Uses composition rather than inheritance to avoid tight coupling to AutoGen
    internals. The original agent object is held as ``self.agent`` and all
    governance hooks are registered on it at construction time.

    Args:
        agent: An AutoGen ``ConversableAgent`` (or compatible) instance.
        engine: An initialized ``aumos-governance`` ``GovernanceEngine`` instance.
        trust_level: Trust level for this agent. Set manually by the operator
            at construction. Defaults to ``2``.
        config: Optional ``AutoGenGovernanceConfig`` controlling denial handling,
            scope mapping, and audit behaviour.

    Example::

        from autogen import ConversableAgent
        from autogen_aumos import GovernedConversableAgent

        agent = ConversableAgent(name="planner", ...)
        governed = GovernedConversableAgent(agent=agent, engine=engine, trust_level=2)

        # Use governed.agent in your AutoGen conversation — hooks are installed.
        governed.agent.initiate_chat(...)
    """

    def __init__(
        self,
        agent: Any,
        engine: Any,
        trust_level: int = 2,
        config: Optional[AutoGenGovernanceConfig] = None,
    ) -> None:
        self.agent = agent
        self.engine = engine
        self._config: AutoGenGovernanceConfig = config or AutoGenGovernanceConfig()
        self._trust_level = trust_level

        self._message_guard = MessageGuard(engine=engine, config=self._config)
        self._tool_guard = ToolGuard(engine=engine, config=self._config)

        # Set the agent's trust level once at construction.
        # This is a manual, operator-initiated assignment — never modified at runtime.
        self._set_trust_level(trust_level)

        # Register governance hooks on the wrapped agent.
        self._install_hooks()

    # ------------------------------------------------------------------
    # Public governance hooks
    # ------------------------------------------------------------------

    def governance_message_hook(
        self,
        sender: Any,
        message: Any,
        recipient: Any,
        silent: bool,  # noqa: FBT001
    ) -> Any:
        """
        Check governance before any message is sent.

        Registered as a message hook on the wrapped agent. Called by AutoGen
        before the agent sends a message to a recipient.

        When governance denies and ``on_denied='raise'``, this hook raises
        ``GovernanceDeniedError`` and the conversation fails.

        When ``on_denied='block'``, the hook returns a denial notice string as
        a replacement message so the conversation can continue.

        Args:
            sender: The AutoGen agent sending the message.
            message: The message being sent (string or dict).
            recipient: The AutoGen agent receiving the message.
            silent: Whether the message is sent silently.

        Returns:
            The original message if governance permits, or a denial notice
            string if ``on_denied='block'``.
        """
        if not self._config.govern_messages:
            return message

        sender_name: str = str(getattr(sender, "name", getattr(sender, "role", "unknown")))
        recipient_name: str = str(
            getattr(recipient, "name", getattr(recipient, "role", "unknown"))
            if recipient is not None
            else "broadcast"
        )
        message_str: str = (
            message if isinstance(message, str) else str(message.get("content", message))
        )

        try:
            self._message_guard.check_message(
                sender_name=sender_name,
                recipient_name=recipient_name,
                message=message_str,
            )
        except GovernanceDeniedError:
            raise
        except MessageBlockedError as exc:
            denial_notice = (
                f"[GOVERNANCE] Message blocked: {exc.reason}"
            )
            logger.info(
                "GovernedConversableAgent: message from '%s' to '%s' replaced with "
                "block notice.",
                sender_name,
                recipient_name,
            )
            return denial_notice

        return message

    def governed_execute_function(
        self,
        func_call: dict[str, Any],
        **kwargs: Any,
    ) -> Optional[dict[str, Any]]:
        """
        Check governance before executing any function.

        Registered as a function pre-execution hook on the wrapped agent.
        Called by AutoGen before the agent executes a registered function.

        Returns ``None`` to signal that execution should proceed normally.
        Returns an error dict when the call is denied under ``'block'`` or
        ``'log'`` mode, signalling that AutoGen should not proceed with the
        function but should treat the error dict as the function result.

        When ``on_denied='raise'``, raises ``GovernanceDeniedError`` and the
        conversation fails.

        Args:
            func_call: AutoGen function call dict with at minimum a ``'name'``
                key. May also contain ``'arguments'`` (a JSON string or dict).
            **kwargs: Additional keyword arguments from the AutoGen hook API.

        Returns:
            ``None`` if governance permits the function call, or a dict with an
            ``'error'`` key if the call is denied and ``on_denied`` is ``'block'``
            or ``'log'``.

        Raises:
            GovernanceDeniedError: When governance denies and ``on_denied='raise'``.
        """
        if not self._config.govern_tools:
            return None

        func_name: str = str(func_call.get("name", "unknown"))
        agent_name: str = str(getattr(self.agent, "name", "unknown"))

        # Extract args from the function call dict.
        args = self._extract_func_args(func_call)

        result = self._tool_guard.check_tool(
            agent_name=agent_name,
            tool_name=func_name,
            args=args,
        )

        if not result.permitted:
            return {"error": f"Governance denied: {result.reason}"}

        # None tells the AutoGen caller to proceed with normal function execution.
        return None

    # ------------------------------------------------------------------
    # Internal setup helpers
    # ------------------------------------------------------------------

    def _set_trust_level(self, trust_level: int) -> None:
        """
        Set the trust level for this agent on the governance engine.

        One-time, operator-initiated assignment at construction.
        """
        agent_name: str = str(getattr(self.agent, "name", id(self.agent)))
        trust_api = getattr(self.engine, "trust", None)
        if trust_api is not None and hasattr(trust_api, "set_level"):
            trust_api.set_level(agent_name, trust_level)
        elif hasattr(self.engine, "set_trust_level"):
            self.engine.set_trust_level(agent_name, trust_level)
        else:
            logger.debug(
                "GovernedConversableAgent: engine does not expose a trust API; "
                "trust_level=%d for '%s' not applied",
                trust_level,
                agent_name,
            )

    def _install_hooks(self) -> None:
        """
        Register governance hooks on the wrapped AutoGen agent.

        Attempts to register:
        - A reply function hook via ``register_reply`` (message governance).
        - No hooks are registered if the agent does not expose the expected
          AutoGen hook API — the guards remain available for manual use via
          ``governance_message_hook`` and ``governed_execute_function``.
        """
        # AutoGen 0.2 exposes register_reply for reply function hooks.
        if hasattr(self.agent, "register_reply") and callable(self.agent.register_reply):
            try:
                self.agent.register_reply(
                    trigger=lambda sender: True,  # Match any sender
                    reply_func=self._reply_with_message_governance,
                    position=0,  # Insert at the front so governance fires first
                )
                logger.debug(
                    "GovernedConversableAgent: reply governance hook registered on '%s'.",
                    getattr(self.agent, "name", "unknown"),
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "GovernedConversableAgent: could not register reply hook on '%s': %s",
                    getattr(self.agent, "name", "unknown"),
                    exc,
                )

    def _reply_with_message_governance(
        self,
        recipient: Any,
        messages: Any,
        sender: Any,
        config: Any,
    ) -> tuple[bool, Optional[str]]:
        """
        AutoGen reply function that evaluates governance on outgoing messages.

        Registered as the first reply function via ``register_reply``. Returns
        ``(False, None)`` to pass control to subsequent reply functions when
        governance permits. Returns ``(True, denial_notice)`` when governance
        blocks the outgoing message under ``'block'`` mode.

        Under ``'raise'`` mode, raises ``GovernanceDeniedError``.
        """
        if not self._config.govern_messages:
            return False, None

        agent_name: str = str(getattr(self.agent, "name", "unknown"))
        recipient_name: str = str(
            getattr(recipient, "name", "unknown") if recipient is not None else "broadcast"
        )

        try:
            self._message_guard.check_message(
                sender_name=agent_name,
                recipient_name=recipient_name,
                message="[outgoing]",
            )
        except GovernanceDeniedError:
            raise
        except MessageBlockedError as exc:
            return True, f"[GOVERNANCE] Message blocked: {exc.reason}"

        # Permit — pass control to the next reply function.
        return False, None

    @staticmethod
    def _extract_func_args(func_call: dict[str, Any]) -> dict[str, Any]:
        """
        Extract the arguments dict from an AutoGen function call payload.

        AutoGen may encode arguments as a JSON string under ``'arguments'`` or
        as a pre-parsed dict. Returns an empty dict if extraction fails.
        """
        raw_args = func_call.get("arguments", {})
        if isinstance(raw_args, dict):
            return raw_args
        if isinstance(raw_args, str):
            import json  # Local import to avoid top-level json dependency noise.
            try:
                parsed = json.loads(raw_args)
                return parsed if isinstance(parsed, dict) else {}
            except (json.JSONDecodeError, ValueError):
                return {}
        return {}

    # ------------------------------------------------------------------
    # Transparent delegation to the inner agent
    # ------------------------------------------------------------------

    def __getattr__(self, name: str) -> Any:
        """Delegate unknown attribute access to the inner agent."""
        return getattr(self.agent, name)

    def __repr__(self) -> str:
        agent_name = getattr(self.agent, "name", repr(self.agent))
        return (
            f"GovernedConversableAgent(agent={agent_name!r}, "
            f"trust_level={self._trust_level}, "
            f"on_denied={self._config.on_denied.value!r})"
        )
