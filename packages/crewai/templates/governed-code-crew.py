# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 MuVeraAI Corporation
"""
Template: Governed Code Review Crew

A three-agent code review crew where each agent has a distinct trust level
and all tool calls are evaluated against governance policy before execution.

Agent roles and trust levels:
    code_reviewer        (L2) — can read source files and run the linter.
    security_auditor     (L3) — can read, run the linter, and execute tests.
                                Elevated trust because test execution runs code.
    documentation_writer (L1) — read-only access to produce documentation.
                                Lowest trust; cannot modify source files.

Trust levels are assigned once by the operator at crew construction.  They
are never modified based on task outcomes or runtime signals.

Budget limits are static per-crew envelopes set by the operator. Adjust the
``limit`` value in ``budget_tracker.allocate_budget`` to match your cost model.

Prerequisites:
    pip install crewai-aumos crewai aumos-governance

Usage:
    python governed-code-crew.py
"""

from __future__ import annotations

from crewai import Agent, Crew, Process, Task  # type: ignore[import]
from crewai.tools import BaseTool  # type: ignore[import]

from aumos_governance import GovernanceEngine, GovernanceEngineConfig  # type: ignore[import]
from crewai_aumos import GovernedCrew
from crewai_aumos.config import CrewGovernanceConfig
from crewai_aumos.crew_budget import CrewBudgetTracker
from crewai_aumos.errors import GovernanceDeniedError
from crewai_aumos.types import DeniedAction

# ---------------------------------------------------------------------------
# Placeholder tools — replace with real implementations
# ---------------------------------------------------------------------------


class ReadFileTool(BaseTool):
    """Read a source file from the workspace."""

    name: str = "read_file"
    description: str = "Read a source file and return its contents."

    def _run(self, file_path: str) -> str:
        # Replace with a real file reader.
        return f"[read_file] Contents of: {file_path}"


class LintTool(BaseTool):
    """Run the linter against a source file and return diagnostics."""

    name: str = "run_linter"
    description: str = "Run the configured linter against a source file."

    def _run(self, file_path: str) -> str:
        # Replace with a real linter invocation (ruff, eslint, etc.).
        # Governance reason: linting is read-side. Both code_reviewer (L2) and
        # security_auditor (L3) are authorised; documentation_writer (L1) is not.
        return f"[run_linter] No issues found in: {file_path}"


class RunTestsTool(BaseTool):
    """Execute the test suite for the specified module or file."""

    name: str = "run_tests"
    description: str = "Run the test suite for the specified module or file."

    def _run(self, target: str) -> str:
        # Replace with a real test runner (pytest, jest, etc.).
        # Governance reason: running tests executes code in the environment.
        # security_auditor at L3 is authorised; code_reviewer at L2 is not.
        # This prevents the model from running arbitrary execution without the
        # operator having explicitly granted the security_auditor role L3 access.
        return f"[run_tests] All tests passed for: {target}"


class WriteDocsTool(BaseTool):
    """Write a documentation file to the workspace."""

    name: str = "write_docs"
    description: str = "Write documentation content to a file."

    def _run(self, file_path: str, content: str = "") -> str:
        # Replace with a real documentation writer.
        # Governance reason: documentation_writer (L1) only needs to produce
        # documentation artefacts; restricting it to write_docs (not write_file)
        # prevents unintended modification of source code.
        return f"[write_docs] Wrote {len(content)} chars to: {file_path}"


# ---------------------------------------------------------------------------
# Budget setup — static envelope for the code review crew
# ---------------------------------------------------------------------------

budget_tracker = CrewBudgetTracker()

# Static budget for API calls made during code review. Adjust to your cost model.
# This limit covers LLM completions, linter API calls, and test runner costs.
budget_tracker.allocate_budget(
    crew_id="code-review-crew",
    limit=20.0,
    currency="USD",
)

# ---------------------------------------------------------------------------
# Governance configuration
# ---------------------------------------------------------------------------

governance_config = CrewGovernanceConfig(
    # RAISE means any governance denial aborts the crew run immediately.
    # Change to SKIP if you want the crew to continue past denied tool calls.
    on_denied=DeniedAction.RAISE,
    default_tool_scope="code_review_tool_call",
    tool_scope_mapping={
        "read_file": "file_read_scope",
        "run_linter": "lint_scope",
        "run_tests": "test_exec_scope",
        "write_docs": "docs_write_scope",
    },
    # Record every tool call — both permitted and denied — so the operator
    # can review the complete trail of governance decisions after the run.
    audit_all_calls=True,
    audit_output_preview_length=256,
)

# ---------------------------------------------------------------------------
# Agent definitions
# ---------------------------------------------------------------------------

# Code reviewer — trust level 2 (L2)
# Can read source files and run the linter. Cannot execute tests.
# Governance reason: code review is read-side plus static analysis. Limiting to
# L2 means a code reviewer cannot trigger arbitrary code execution.
code_reviewer = Agent(
    role="code_reviewer",
    goal=(
        "Review the submitted code for correctness, style, and maintainability. "
        "Run the linter and return structured feedback."
    ),
    backstory=(
        "You are a senior engineer who reviews code for correctness, style, and "
        "maintainability. You rely on the linter for style checks and read the "
        "source directly for logic review."
    ),
    tools=[ReadFileTool(), LintTool()],
    verbose=True,
)

# Security auditor — trust level 3 (L3)
# Can read source files, run the linter, and execute the test suite.
# Governance reason: executing tests runs code in the environment — higher stakes
# than reading or linting. L3 ensures the operator explicitly granted this capability.
security_auditor = Agent(
    role="security_auditor",
    goal=(
        "Audit the submitted code for security vulnerabilities and test coverage. "
        "Run the test suite and linter. Return a structured security assessment."
    ),
    backstory=(
        "You are a security-focused engineer who identifies vulnerabilities, "
        "verifies test coverage, and ensures the code meets security standards."
    ),
    tools=[ReadFileTool(), LintTool(), RunTestsTool()],
    verbose=True,
)

# Documentation writer — trust level 1 (L1)
# Read-only access plus documentation writing. Cannot run linter or tests.
# Governance reason: documentation is a low-risk output artefact. L1 prevents
# the documentation role from triggering any code execution or source mutation.
documentation_writer = Agent(
    role="documentation_writer",
    goal=(
        "Read the source code and produce clear, accurate documentation. "
        "Write the documentation to the docs output file."
    ),
    backstory=(
        "You are a technical writer who produces clear API documentation and "
        "usage guides from source code. You translate implementation details "
        "into accessible explanations for developers."
    ),
    tools=[ReadFileTool(), WriteDocsTool()],
    verbose=True,
)

# ---------------------------------------------------------------------------
# Task definitions
# ---------------------------------------------------------------------------

review_code_task = Task(
    description=(
        "Review the implementation of: {feature_description}. "
        "Read the relevant source files. Run the linter. "
        "Return a structured review covering correctness, style, and any "
        "blocking issues. Include specific file and line references."
    ),
    expected_output=(
        "Structured code review with: APPROVED or CHANGES_REQUESTED verdict, "
        "linter output summary, and a list of specific feedback items."
    ),
    agent=code_reviewer,
)

security_scan_task = Task(
    description=(
        "Perform a security audit of: {feature_description}. "
        "Read the implementation, run the linter for security-relevant warnings, "
        "and execute the test suite. Return a security assessment."
    ),
    expected_output=(
        "Security assessment with: vulnerability findings (NONE / LOW / MEDIUM / HIGH), "
        "test results summary, and recommended mitigations for any findings."
    ),
    agent=security_auditor,
)

update_docs_task = Task(
    description=(
        "Write documentation for: {feature_description}. "
        "Read the relevant source files and produce clear API documentation. "
        "Write the finished documentation to the output file."
    ),
    expected_output=(
        "A documentation file covering: overview, public API reference with "
        "parameter descriptions, usage examples, and any known limitations."
    ),
    agent=documentation_writer,
)

# ---------------------------------------------------------------------------
# Crew assembly
# ---------------------------------------------------------------------------

crew = Crew(
    agents=[code_reviewer, security_auditor, documentation_writer],
    tasks=[review_code_task, security_scan_task, update_docs_task],
    process=Process.sequential,
    verbose=True,
)

# ---------------------------------------------------------------------------
# Governance wrap
# ---------------------------------------------------------------------------

# Trust levels are passed as a manual, operator-set mapping. The engine never
# promotes or adjusts these levels based on agent performance or task outcomes.
engine = GovernanceEngine(GovernanceEngineConfig())
governed_crew = GovernedCrew(
    crew=crew,
    engine=engine,
    config=governance_config,
    agent_trust_levels={
        "code_reviewer": 2,        # L2 — read + lint
        "security_auditor": 3,     # L3 — read + lint + run tests
        "documentation_writer": 1, # L1 — read + write docs only
    },
)

# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> None:
    """Run the governed code review crew and print governance decisions."""
    feature = "Add pagination support to the user listing endpoint"

    try:
        result = governed_crew.kickoff(inputs={"feature_description": feature})
        print("\n=== Code Review Output ===")
        print(result)

        # Print budget summary after the run for operator review.
        summary = budget_tracker.get_crew_budget_summary("code-review-crew")
        print(f"\n=== Budget Summary for '{summary.crew_id}' ===")
        print(f"Limit:     {summary.limit} {summary.currency}")
        print(f"Spent:     {summary.total_spent} {summary.currency}")
        print(f"Remaining: {summary.remaining} {summary.currency}")
        print(f"\nAudit trail: {len(summary.spend_records)} spend record(s).")
        for record in summary.spend_records:
            print(
                f"  {record.recorded_at.isoformat()}  "
                f"{record.amount} {summary.currency}  "
                f"{record.note or ''}"
            )

    except GovernanceDeniedError as error:
        # The governance engine denied a tool call. The crew is aborted.
        # Inspect error.subject and error.agent_role to understand which
        # agent triggered the denial and which tool was blocked.
        print("\nGovernance denial — crew aborted.")
        print(f"  Tool/step:  {error.subject}")
        print(f"  Agent role: {error.agent_role}")
        print(f"  Reason:     {error.reason}")


if __name__ == "__main__":
    main()
