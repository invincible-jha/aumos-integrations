# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 MuVeraAI Corporation
"""
Governed RAG pipeline cookbook — governance at retrieval and generation steps.

This example builds a retrieval-augmented generation (RAG) chain where AumOS
governance is inserted as an LCEL pipe step via ``GovernanceRunnable``:

    query → retrieval_governance → retriever → generation_governance → mock_llm → answer

Three scenarios are demonstrated:

1. Normal RAG query at trust level L2 — all checks pass, answer is returned.
2. Query on confidential documents — the retrieval governance step requires L3;
   the operator has configured the agent at L2, so this is denied before any
   documents are fetched.
3. Query within budget but with a spend amount that exceeds the static $5.00
   generation budget ceiling — denied at the generation governance step.

No real LLM is required. A ``MockLLM`` runnable returns stub text so the
cookbook runs offline without any API keys.

``GovernanceRunnable`` from ``lcel_step`` is used as the LCEL step at both
the retrieval gate and the generation gate. It raises ``GovernanceDeniedError``
on denial (``on_denied=DeniedAction.RAISE``).

Prerequisites:
    pip install langchain-aumos aumos-governance

Usage:
    python cookbook/governed-rag.py
"""

from __future__ import annotations

from typing import Any

from langchain_core.documents import Document
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import RunnableLambda

from aumos_governance import GovernanceEngine, GovernanceEngineConfig  # type: ignore[import]
from langchain_aumos.errors import GovernanceDeniedError
from langchain_aumos.lcel_step import GovernanceRunnable, GovernanceRunnableConfig
from langchain_aumos.types import DeniedAction

# ---------------------------------------------------------------------------
# Mock LLM — no API key required
# ---------------------------------------------------------------------------


class MockLLM:
    """Stub LLM that echoes the last human message for offline demos."""

    def invoke(self, prompt_value: Any, **kwargs: Any) -> str:
        """Return a canned answer regardless of the prompt content."""
        return "Mock LLM answer: based on the retrieved context."

    def __or__(self, other: Any) -> Any:
        """Support the LCEL pipe operator for chaining."""
        from langchain_core.runnables import RunnableLambda

        def _pipe(prompt_value: Any) -> Any:
            result = self.invoke(prompt_value)
            return other.invoke(result) if hasattr(other, "invoke") else other(result)

        return RunnableLambda(_pipe)


# ---------------------------------------------------------------------------
# Mock vector store retriever — returns in-memory documents
# ---------------------------------------------------------------------------


def build_stub_retriever() -> Any:
    """Return a simple in-memory stub retriever for demo purposes."""

    _public_documents = [
        Document(
            page_content="Product adoption rate in APAC increased by 18% in Q4.",
            metadata={"confidential": False},
        ),
        Document(
            page_content="Overall platform NPS for Q4 was 78, up from 71 in Q3.",
            metadata={"confidential": False},
        ),
    ]
    _confidential_documents = [
        Document(
            page_content="Alice Smith's individual NPS score is 92. Renewal risk: low.",
            metadata={"confidential": True},
        ),
        Document(
            page_content="Bob Jones' churn risk score is high. Last login: 30 days ago.",
            metadata={"confidential": True},
        ),
    ]

    class StubRetriever:
        def invoke(self, chain_input: dict[str, Any], **kwargs: Any) -> dict[str, Any]:
            """
            Return documents based on the confidential flag in the input dict.

            In a real pipeline this would query a vector store. The confidential
            flag here is operator-supplied at query time, not derived from runtime
            signals.
            """
            if chain_input.get("confidential_query"):
                docs = _confidential_documents
            else:
                docs = _public_documents
            context = "\n\n".join(doc.page_content for doc in docs)
            return {**chain_input, "context": context}

    return StubRetriever()


# ---------------------------------------------------------------------------
# Governance engine — operator-configured static policy (trust level L2)
# ---------------------------------------------------------------------------

engine_config = GovernanceEngineConfig(
    agent_id="rag-agent",
    trust_level=2,
    spending_envelope={
        "rag_generation": 5.00,     # USD ceiling for generation spend (static)
        "rag_retrieval": 0.00,      # no monetary cost for retrieval
    },
)
engine = GovernanceEngine(engine_config)

# ---------------------------------------------------------------------------
# Governance step 1 — retrieval gate
#
# Public documents: required_trust_level=2 (passes for this L2 agent).
# Confidential documents: required_trust_level=3 (fails for this L2 agent).
#
# The trust level is static — operator-configured once.  It is never raised
# based on the outcome of any prior request.
# ---------------------------------------------------------------------------

retrieval_governance_public = GovernanceRunnable(
    engine,
    GovernanceRunnableConfig(
        agent_id="rag-agent",
        required_trust_level=2,     # L2 — matches current agent configuration
        scope="rag_retrieval",
        on_denied=DeniedAction.RAISE,
    ),
)

retrieval_governance_confidential = GovernanceRunnable(
    engine,
    GovernanceRunnableConfig(
        agent_id="rag-agent",
        required_trust_level=3,     # L3 required — current agent is L2, so denied
        scope="rag_retrieval_confidential",
        on_denied=DeniedAction.RAISE,
    ),
)

# ---------------------------------------------------------------------------
# Governance step 2 — generation gate
#
# Static budget ceiling of $5.00 USD per generation call.  The spend_amount
# key in the chain input carries the estimated cost, supplied by the caller.
# ---------------------------------------------------------------------------

generation_governance = GovernanceRunnable(
    engine,
    GovernanceRunnableConfig(
        agent_id="rag-agent",
        required_trust_level=2,
        spending_limit=5.00,            # static, operator-set ceiling
        scope="rag_generation",
        on_denied=DeniedAction.RAISE,
        spend_amount_key="spend_amount",
    ),
)

# ---------------------------------------------------------------------------
# Retriever and mock LLM
# ---------------------------------------------------------------------------

retriever = build_stub_retriever()
mock_llm = MockLLM()

# ---------------------------------------------------------------------------
# RAG prompt
# ---------------------------------------------------------------------------

rag_prompt = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            "You are a data analyst assistant. "
            "Answer the question using only the provided context. "
            "If the context does not contain enough information, say so.\n\n"
            "Context:\n{context}",
        ),
        ("human", "{query}"),
    ]
)

# ---------------------------------------------------------------------------
# Chain assembly helpers
# ---------------------------------------------------------------------------


def make_rag_chain(retrieval_step: GovernanceRunnable) -> Any:
    """
    Assemble a governed RAG chain with the given retrieval governance step.

    Chain layout:
        retrieval_governance → retriever → generation_governance
                             → rag_prompt → mock_llm → StrOutputParser

    Args:
        retrieval_step: The ``GovernanceRunnable`` to use at the retrieval gate.

    Returns:
        A composed LCEL chain.
    """
    return (
        retrieval_step
        | RunnableLambda(retriever.invoke)
        | generation_governance
        | rag_prompt
        | RunnableLambda(mock_llm.invoke)
        | StrOutputParser()
    )


# ---------------------------------------------------------------------------
# Helper for section headers
# ---------------------------------------------------------------------------


def section(title: str) -> None:
    """Print a formatted section header to stdout."""
    print(f"\n{'=' * 60}")
    print(f"  {title}")
    print(f"{'=' * 60}")


# ---------------------------------------------------------------------------
# Run scenarios
# ---------------------------------------------------------------------------


def run_scenarios() -> None:
    """Demonstrate the three RAG governance scenarios."""

    # ------------------------------------------------------------------
    # Scenario 1: Normal RAG query at L2 — all checks pass.
    # The agent is configured at trust level L2.  The public retrieval gate
    # requires L2, so it passes.  The spend amount is within the $5.00 ceiling.
    # ------------------------------------------------------------------
    section("Scenario 1: Normal RAG query at L2 (expect: ALLOWED)")
    public_chain = make_rag_chain(retrieval_governance_public)
    try:
        answer = public_chain.invoke(
            {
                "query": "What was the platform NPS in Q4?",
                "confidential_query": False,
                "spend_amount": 0.35,
            }
        )
        print(f"Answer: {answer}")
    except GovernanceDeniedError as error:
        print(f"[DENIED] scope='{error.tool_name}' reason='{error.reason}'")

    # ------------------------------------------------------------------
    # Scenario 2: Query on confidential documents — retrieval gate requires L3.
    # The agent is configured at trust level L2.  The confidential retrieval
    # gate requires L3, so the request is denied before any documents are
    # fetched.  Trust level is static; it is never raised automatically.
    # ------------------------------------------------------------------
    section(
        "Scenario 2: Confidential document query requiring L3 "
        "(expect: DENIED at retrieval gate)"
    )
    confidential_chain = make_rag_chain(retrieval_governance_confidential)
    try:
        answer = confidential_chain.invoke(
            {
                "query": "What is Alice's individual NPS score?",
                "confidential_query": True,
                "spend_amount": 0.35,
            }
        )
        print(f"Answer: {answer}")
    except GovernanceDeniedError as error:
        print(f"[DENIED] scope='{error.tool_name}' reason='{error.reason}'")
        print(
            "  Confidential retrieval blocked — agent trust level L2 is below "
            "the required L3.  Operator must explicitly grant L3 to unblock."
        )

    # ------------------------------------------------------------------
    # Scenario 3: Budget exceeded at the generation step.
    # The query reaches the retrieval step (public gate, L2 passes), but the
    # estimated generation cost of $7.50 exceeds the static $5.00 ceiling.
    # The generation governance step blocks execution.
    # ------------------------------------------------------------------
    section(
        "Scenario 3: Generation spend exceeds static $5.00 ceiling "
        "(expect: DENIED at generation gate)"
    )
    public_chain_for_budget = make_rag_chain(retrieval_governance_public)
    try:
        answer = public_chain_for_budget.invoke(
            {
                "query": "Provide a full narrative summary of all Q4 metrics.",
                "confidential_query": False,
                "spend_amount": 7.50,   # exceeds the static $5.00 generation ceiling
            }
        )
        print(f"Answer: {answer}")
    except GovernanceDeniedError as error:
        print(f"[DENIED] scope='{error.tool_name}' reason='{error.reason}'")
        print(
            "  LLM generation blocked — the estimated spend of $7.50 exceeds "
            "the operator-set static budget of $5.00."
        )


if __name__ == "__main__":
    run_scenarios()
