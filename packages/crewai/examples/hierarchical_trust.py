# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 MuVeraAI Corporation
"""
Hierarchical trust — different agent roles with different trust levels.

This example demonstrates how to configure CrewAI agents with distinct trust
levels in a hierarchical crew where agents have escalating levels of access.
Trust levels are assigned manually at crew initialization — they are a static
policy decision made by the operator, never computed from runtime behaviour.

A high-trust agent (trust level 3) can invoke privileged tools.
A low-trust agent (trust level 1) is restricted to safe, read-only operations.
The governance engine enforces the boundary — this integration only passes the
level through.

Prerequisites:
    pip install crewai-aumos crewai aumos-governance

Usage:
    python examples/hierarchical_trust.py
"""

from crewai import Agent, Crew, Process, Task  # type: ignore[import]
from crewai.tools import BaseTool  # type: ignore[import]

# --- Tools with different privilege requirements ----------------------------

class ReadPublicDataTool(BaseTool):
    name: str = "read_public_data"
    description: str = "Read publicly available data. Requires no special access."

    def _run(self, query: str) -> str:
        return f"[public_data] Data for: {query}"


class ReadInternalDataTool(BaseTool):
    name: str = "read_internal_data"
    description: str = "Read internal company data. Requires elevated access."

    def _run(self, query: str) -> str:
        return f"[internal_data] Internal data for: {query}"


class WriteRecordsTool(BaseTool):
    name: str = "write_records"
    description: str = "Write records to the internal database. Requires high trust."

    def _run(self, payload: str) -> str:
        return f"[write_records] Written: {payload[:80]}..."


class AuditLogReaderTool(BaseTool):
    name: str = "read_audit_log"
    description: str = "Read audit logs. Reserved for the compliance officer role."

    def _run(self, filter_query: str) -> str:
        return f"[audit_log] Log entries for: {filter_query}"


# --- Build agents with role-appropriate tools --------------------------------

# junior_researcher: trust level 1 — read-only, public data only
junior_researcher = Agent(
    role="junior_researcher",
    goal="Gather publicly available information on the assigned topic.",
    backstory="A new team member with limited system access.",
    tools=[ReadPublicDataTool()],
    verbose=True,
)

# senior_analyst: trust level 2 — can read internal data, cannot write
senior_analyst = Agent(
    role="senior_analyst",
    goal="Analyse internal data and produce insights.",
    backstory="An experienced analyst with access to internal databases.",
    tools=[ReadPublicDataTool(), ReadInternalDataTool()],
    verbose=True,
)

# compliance_officer: trust level 3 — can write and read audit logs
compliance_officer = Agent(
    role="compliance_officer",
    goal="Review findings, update records, and verify audit compliance.",
    backstory="A compliance officer with full read-write system access.",
    tools=[ReadInternalDataTool(), WriteRecordsTool(), AuditLogReaderTool()],
    verbose=True,
)

# --- Define tasks -----------------------------------------------------------

gather_task = Task(
    description="Gather publicly available information about AI regulations in the EU.",
    expected_output="A list of current EU AI regulation documents with brief descriptions.",
    agent=junior_researcher,
)

analyse_task = Task(
    description=(
        "Cross-reference the gathered public information against internal policy documents."
    ),
    expected_output="A gap analysis identifying which internal policies need updating.",
    agent=senior_analyst,
)

compliance_task = Task(
    description=(
        "Update the compliance records with the gap analysis findings and verify "
        "the audit log for any prior compliance events on this topic."
    ),
    expected_output="Confirmation that records have been updated and audit reviewed.",
    agent=compliance_officer,
)

crew = Crew(
    agents=[junior_researcher, senior_analyst, compliance_officer],
    tasks=[gather_task, analyse_task, compliance_task],
    process=Process.sequential,
    verbose=True,
)

# --- Govern the crew with explicit, manually assigned trust levels ----------

from aumos_governance import GovernanceEngine, GovernanceEngineConfig  # type: ignore[import]
from crewai_aumos import GovernedCrew
from crewai_aumos.config import CrewGovernanceConfig
from crewai_aumos.types import DeniedAction

engine_config = GovernanceEngineConfig()
engine = GovernanceEngine(engine_config)

governance_config = CrewGovernanceConfig(
    on_denied=DeniedAction.RAISE,
    # Map privileged tools to distinct governance scopes so the engine can
    # apply the correct policy for each access tier.
    tool_scope_mapping={
        "read_public_data": "data_access:public",
        "read_internal_data": "data_access:internal",
        "write_records": "data_write:internal",
        "read_audit_log": "data_access:audit",
    },
    # Task-level scopes vary by agent role.
    agent_task_scope_mapping={
        "junior_researcher": "task:restricted",
        "senior_analyst": "task:standard",
        "compliance_officer": "task:privileged",
    },
    audit_all_calls=True,
)

# Trust level assignment is a manual, operator-controlled decision.
# These values are static for the lifetime of this crew run.
governed = GovernedCrew(
    crew=crew,
    engine=engine,
    config=governance_config,
    agent_trust_levels={
        "junior_researcher": 1,
        "senior_analyst": 2,
        "compliance_officer": 3,
    },
)

# --- Run the governed crew --------------------------------------------------

if __name__ == "__main__":
    from crewai_aumos.errors import GovernanceDeniedError

    print("Running hierarchical trust crew...")
    print("Trust levels: junior_researcher=1, senior_analyst=2, compliance_officer=3")
    print()

    try:
        result = governed.kickoff()
        print("Crew output:", result)
    except GovernanceDeniedError as error:
        print()
        print(f"Access denied — '{error.subject}' blocked.")
        print(f"Agent role: {error.agent_role}")
        print(f"Reason: {error.reason}")
        print(
            "The crew was stopped because an agent attempted to exceed its trust level."
        )
