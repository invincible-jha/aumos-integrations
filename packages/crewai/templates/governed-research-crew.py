# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 MuVeraAI Corporation
"""
Template: Governed Research Crew

A three-agent research crew where each agent has a distinct trust level and all
tool calls are evaluated against governance policy before execution.

Governance decisions explained in comments throughout. Copy this file and
replace the placeholder tools and task descriptions with your own.

Trust levels in this template:
    researcher (L1) — broad information access, low write permissions.
    analyst    (L2) — can invoke structured data tools that researcher cannot.
    writer     (L3) — elevated trust because it produces the final artefact
                      and may write to output destinations.

These levels are set once at crew construction by the operator. They are never
modified based on the outcome of any task or tool call.

This template also imports ``GovernedFlow`` for use cases where the research
pipeline is orchestrated as a CrewAI Flow rather than a plain sequential crew.
See the ``GovernedFlow`` comment block near the bottom for details.

Prerequisites:
    pip install crewai-aumos crewai aumos-governance

Usage:
    python governed-research-crew.py
"""

from __future__ import annotations

from crewai import Agent, Crew, Process, Task  # type: ignore[import]
from crewai.tools import BaseTool  # type: ignore[import]

from aumos_governance import GovernanceEngine, GovernanceEngineConfig  # type: ignore[import]
from crewai_aumos import GovernedCrew
from crewai_aumos.config import CrewGovernanceConfig
from crewai_aumos.crew_budget import CrewBudgetTracker
from crewai_aumos.errors import GovernanceDeniedError
from crewai_aumos.flows import FlowGovernanceConfig, GovernedFlow
from crewai_aumos.types import DeniedAction

# ---------------------------------------------------------------------------
# Placeholder tools — replace with your real implementations
# ---------------------------------------------------------------------------


class WebSearchTool(BaseTool):
    """Search the web for information on a topic."""

    name: str = "web_search"
    description: str = "Search the web for up-to-date information on a topic."

    def _run(self, query: str) -> str:
        # Replace with a real search client (e.g., Serper, Tavily, Exa).
        return f"[web_search] Results for: {query}"


class DocumentReaderTool(BaseTool):
    """Read a document by URL or path and return its text content."""

    name: str = "read_document"
    description: str = "Read a document and return its text content."

    def _run(self, source: str) -> str:
        # Replace with a real document reader.
        return f"[read_document] Content of: {source}"


class DataAnalysisTool(BaseTool):
    """Run structured data analysis on a dataset identifier."""

    name: str = "analyse_data"
    description: str = "Run structured analysis on a dataset."

    def _run(self, dataset_id: str) -> str:
        # Replace with a real analytics client.
        # Governance reason: analyst (L2) gets this tool; researcher (L1) does not.
        # This prevents the model from running expensive analysis without the
        # operator having explicitly granted the researcher elevated access.
        return f"[analyse_data] Analysis of dataset: {dataset_id}"


class ReportWriterTool(BaseTool):
    """Write a research report to the output store."""

    name: str = "write_report"
    description: str = "Write a formatted report to the output destination."

    def _run(self, content: str) -> str:
        # Replace with a real output writer (file, database, API).
        # Governance reason: writer (L3) gets this tool exclusively because
        # writing to the output store is a higher-stakes action than reading.
        return f"[write_report] Report written ({len(content)} chars)"


# ---------------------------------------------------------------------------
# Budget setup — create a shared static envelope for the crew
# ---------------------------------------------------------------------------

# The budget tracker is created outside GovernedCrew so that budget state
# survives across multiple crew runs in the same process.
budget_tracker = CrewBudgetTracker()

# Allocate a static envelope for this crew. The limit is set by the operator
# and never adjusted automatically. Adjust the limit to match your cost model.
budget_tracker.allocate_budget(
    crew_id="research-crew",
    limit=50.0,      # 50 USD (or tokens, credits — match your cost unit)
    currency="USD",
)

# ---------------------------------------------------------------------------
# Governance configuration
# ---------------------------------------------------------------------------

# Tool scope mapping routes each tool to its budget category in the engine.
# Tools not listed here fall back to the default_tool_scope.
governance_config = CrewGovernanceConfig(
    on_denied=DeniedAction.RAISE,  # any denial aborts the run
    default_tool_scope="research_tool_call",
    tool_scope_mapping={
        "web_search": "search_scope",
        "read_document": "document_scope",
        "analyse_data": "analysis_scope",
        "write_report": "output_scope",
    },
    audit_all_calls=True,  # record every tool call in the audit trail
    audit_output_preview_length=256,
)

# ---------------------------------------------------------------------------
# Agent definitions
# ---------------------------------------------------------------------------

# Researcher — trust level 1 (L1)
# Can search the web and read documents. Cannot run analysis or write output.
# Governance reason: broad information retrieval is low-risk. Limiting to L1
# means a compromised or confused researcher cannot escalate to write actions.
researcher = Agent(
    role="researcher",
    goal="Find accurate, up-to-date information on the assigned topic.",
    backstory=(
        "You are a meticulous researcher who gathers information from "
        "multiple sources and evaluates their credibility."
    ),
    tools=[WebSearchTool(), DocumentReaderTool()],
    verbose=True,
)

# Analyst — trust level 2 (L2)
# Inherits researcher's read access and additionally can run data analysis.
# Governance reason: structured data analysis may touch sensitive datasets;
# requiring L2 ensures the operator has explicitly granted this capability.
analyst = Agent(
    role="analyst",
    goal="Synthesise research findings using structured data analysis.",
    backstory=(
        "You are a data analyst who distils large bodies of information "
        "into clear, evidence-based conclusions."
    ),
    tools=[WebSearchTool(), DocumentReaderTool(), DataAnalysisTool()],
    verbose=True,
)

# Writer — trust level 3 (L3)
# Can do everything the analyst can, plus write the final report output.
# Governance reason: writing to output destinations (files, APIs, databases)
# is the highest-stakes action in the pipeline. L3 ensures the operator
# must have explicitly authorized the writer role before the crew runs.
writer = Agent(
    role="writer",
    goal="Produce a clear, well-structured research report from the analysis.",
    backstory=(
        "You are a professional technical writer who transforms analytical "
        "findings into accessible, actionable reports."
    ),
    tools=[ReportWriterTool()],
    verbose=True,
)

# ---------------------------------------------------------------------------
# Task definitions
# ---------------------------------------------------------------------------

research_task = Task(
    description=(
        "Research the current landscape of {topic}. "
        "Identify the top sources, key developments, and open questions."
    ),
    expected_output="A bullet-point summary of key findings with source references.",
    agent=researcher,
)

analysis_task = Task(
    description=(
        "Analyse the research findings on {topic}. "
        "Identify trends, contradictions, and evidence gaps."
    ),
    expected_output="A structured analysis with supporting data points.",
    agent=analyst,
)

writing_task = Task(
    description=(
        "Write a research report on {topic} based on the analysis. "
        "The report should be suitable for a technical decision-making audience."
    ),
    expected_output="A 4-section report: Executive Summary, Findings, Analysis, Recommendations.",
    agent=writer,
)

# ---------------------------------------------------------------------------
# Crew assembly
# ---------------------------------------------------------------------------

crew = Crew(
    agents=[researcher, analyst, writer],
    tasks=[research_task, analysis_task, writing_task],
    process=Process.sequential,
    verbose=True,
)

# ---------------------------------------------------------------------------
# Governance wrap — this is the only change from a plain Crew
# ---------------------------------------------------------------------------

# Trust levels are passed as a manual, operator-set mapping. The engine
# never promotes or changes these levels based on agent performance.
engine = GovernanceEngine(GovernanceEngineConfig())
governed_crew = GovernedCrew(
    crew=crew,
    engine=engine,
    config=governance_config,
    agent_trust_levels={
        "researcher": 1,  # L1 — read-only information access
        "analyst": 2,     # L2 — read + structured data analysis
        "writer": 3,      # L3 — read + analysis + output writing
    },
)

# ---------------------------------------------------------------------------
# Optional: GovernedFlow pattern
#
# When the research pipeline is orchestrated as a CrewAI Flow rather than a
# sequential Crew, wrap the Flow object with GovernedFlow instead.  The API
# mirrors GovernedCrew: pass the engine, an agent identity, and a static trust
# level inherited from the operator context.
#
# Example (replace MyResearchFlow with your actual Flow class):
#
#   flow_config = FlowGovernanceConfig(
#       agent_id="research-flow",
#       inherited_trust_level=2,   # operator-set, never adjusted at runtime
#       on_denied=DeniedAction.RAISE,
#   )
#   governed_flow = GovernedFlow(flow=MyResearchFlow(), engine=engine, config=flow_config)
#   governed_flow.kickoff(inputs={"topic": "enterprise AI governance"})
#
# See crewai_aumos.flows for the full GovernedFlow and FlowGovernanceConfig API.
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    try:
        result = governed_crew.kickoff(inputs={"topic": "enterprise AI governance"})
        print("\n=== Research Report ===")
        print(result)

        # Print budget summary after the run for operator review.
        summary = budget_tracker.get_crew_budget_summary("research-crew")
        print(f"\n=== Budget Summary for '{summary.crew_id}' ===")
        print(f"Limit:   {summary.limit} {summary.currency}")
        print(f"Spent:   {summary.total_spent} {summary.currency}")
        print(f"Remaining: {summary.remaining} {summary.currency}")

    except GovernanceDeniedError as error:
        print(f"\nCrew denied by governance: {error.reason}")
        print(f"Subject: {error.subject} | Agent: {error.agent_role}")
