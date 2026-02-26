# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 MuVeraAI Corporation
"""
Multi-agent budget control — enforce per-agent spending limits in a CrewAI crew.

This example shows how to configure the AumOS governance integration to track
and enforce spending limits across multiple agents in the same crew. Each agent
is assigned a trust level and may have tools that carry spend amounts.

The spending envelope is defined once, at engine initialization, by the
operator. It is a static policy value — never derived from runtime behaviour.

Prerequisites:
    pip install crewai-aumos crewai aumos-governance

Usage:
    python examples/multi_agent_budget.py
"""

from crewai import Agent, Crew, Process, Task  # type: ignore[import]
from crewai.tools import BaseTool  # type: ignore[import]

# --- Define tools that carry spend amounts in their inputs -------------------

class LLMApiTool(BaseTool):
    name: str = "call_llm_api"
    description: str = (
        "Call an external LLM API. Pass 'prompt' and 'amount' (estimated USD cost)."
    )

    def _run(self, prompt: str, amount: float = 0.0) -> str:
        return f"[llm_api] response to: {prompt[:60]}... (cost: ${amount:.4f})"


class DatabaseQueryTool(BaseTool):
    name: str = "query_database"
    description: str = (
        "Run a SQL query against the data warehouse. Pass 'sql' and "
        "'amount' (estimated compute cost in USD)."
    )

    def _run(self, sql: str, amount: float = 0.0) -> str:
        return f"[database] results for: {sql[:60]}... (cost: ${amount:.4f})"


class ReportGeneratorTool(BaseTool):
    name: str = "generate_report"
    description: str = "Generate a formatted report from structured data. Free to use."

    def _run(self, data: str) -> str:
        return f"[report] Generated report from data: {data[:80]}..."


# --- Build the crew ---------------------------------------------------------

analyst = Agent(
    role="analyst",
    goal="Analyse data by querying the warehouse and calling external APIs.",
    backstory="You are a data analyst who works with large datasets.",
    tools=[LLMApiTool(), DatabaseQueryTool()],
    verbose=True,
)

reporter = Agent(
    role="reporter",
    goal="Produce clean, readable reports from analysed data.",
    backstory="You are a report writer who formats data into prose.",
    tools=[ReportGeneratorTool()],
    verbose=True,
)

analysis_task = Task(
    description=(
        "Analyse Q4 revenue by region. Query the data warehouse and use the "
        "LLM API to interpret the results."
    ),
    expected_output="A structured analysis of Q4 revenue with regional breakdowns.",
    agent=analyst,
)

report_task = Task(
    description="Produce an executive summary from the analysis.",
    expected_output="A one-page executive summary of the Q4 revenue analysis.",
    agent=reporter,
)

crew = Crew(
    agents=[analyst, reporter],
    tasks=[analysis_task, report_task],
    process=Process.sequential,
    verbose=True,
)

# --- Configure governance with per-agent trust levels and spending envelope --

from aumos_governance import GovernanceEngine, GovernanceEngineConfig  # type: ignore[import]
from crewai_aumos import GovernedCrew
from crewai_aumos.config import CrewGovernanceConfig
from crewai_aumos.types import DeniedAction

# Spending envelope is set statically by the operator.
# The analyst has a higher budget ceiling because it uses paid external APIs.
# The reporter only uses free tooling — its envelope is smaller.
engine_config = GovernanceEngineConfig(
    spending_envelope={
        "analyst_llm": 0.50,      # USD ceiling for analyst LLM API spend
        "analyst_db": 0.20,       # USD ceiling for analyst database queries
        "reporter_reports": 0.0,  # Free tier — no spend tracked
    },
)
engine = GovernanceEngine(engine_config)

governance_config = CrewGovernanceConfig(
    on_denied=DeniedAction.RAISE,
    amount_field="amount",
    tool_scope_mapping={
        "call_llm_api": "analyst_llm",
        "query_database": "analyst_db",
        "generate_report": "reporter_reports",
    },
    audit_all_calls=True,
)

# Trust levels are assigned manually by the operator — never computed.
# analyst = trust level 2 (can use paid external APIs)
# reporter = trust level 1 (can only use internal tooling)
governed = GovernedCrew(
    crew=crew,
    engine=engine,
    config=governance_config,
    agent_trust_levels={
        "analyst": 2,
        "reporter": 1,
    },
)

# --- Run -------------------------------------------------------------------

if __name__ == "__main__":
    from crewai_aumos.errors import GovernanceDeniedError

    print("Running multi-agent governed crew...")
    print("Trust levels: analyst=2, reporter=1")
    print()

    try:
        result = governed.kickoff()
        print("Crew output:", result)
    except GovernanceDeniedError as error:
        print()
        print(f"Budget limit reached — '{error.subject}' was denied.")
        print(f"Agent role: {error.agent_role}")
        print(f"Reason: {error.reason}")
