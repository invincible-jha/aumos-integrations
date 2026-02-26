# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 MuVeraAI Corporation
"""
Quickstart — add AumOS governance to a CrewAI crew in a few lines.

This example shows the minimal integration. ``GovernedCrew`` wraps an existing
``Crew`` and installs governance checkpoints on every agent tool and every task
dispatch before kickoff proceeds.

Prerequisites:
    pip install crewai-aumos crewai aumos-governance

Usage:
    python examples/quickstart.py
"""

from crewai import Agent, Crew, Process, Task  # type: ignore[import]
from crewai.tools import BaseTool  # type: ignore[import]

# --- Define placeholder tools -----------------------------------------------

class WebSearchTool(BaseTool):
    name: str = "web_search"
    description: str = "Search the web for up-to-date information on a topic."

    def _run(self, query: str) -> str:
        # Placeholder — replace with a real search implementation.
        return f"[web_search] Results for: {query}"


class SummariseTool(BaseTool):
    name: str = "summarise"
    description: str = "Produce a concise summary of a body of text."

    def _run(self, text: str) -> str:
        # Placeholder — replace with a real summarisation implementation.
        return f"[summarise] Summary: {text[:100]}..."


# --- Build the CrewAI crew as normal ----------------------------------------

researcher = Agent(
    role="researcher",
    goal="Find accurate information on the given topic.",
    backstory="You are a meticulous researcher who verifies sources.",
    tools=[WebSearchTool()],
    verbose=True,
)

writer = Agent(
    role="writer",
    goal="Produce a clear, concise report based on research findings.",
    backstory="You are a professional technical writer.",
    tools=[SummariseTool()],
    verbose=True,
)

research_task = Task(
    description="Research the current state of AI governance frameworks.",
    expected_output="A bullet-point summary of the top 5 AI governance frameworks.",
    agent=researcher,
)

write_task = Task(
    description="Write a short report on AI governance based on the research findings.",
    expected_output="A 3-paragraph report suitable for a technical audience.",
    agent=writer,
)

crew = Crew(
    agents=[researcher, writer],
    tasks=[research_task, write_task],
    process=Process.sequential,
    verbose=True,
)

# --- The AumOS integration — wrap the crew ----------------------------------

from aumos_governance import GovernanceEngine, GovernanceEngineConfig  # type: ignore[import]
from crewai_aumos import GovernedCrew

engine = GovernanceEngine(GovernanceEngineConfig())
governed = GovernedCrew(crew=crew, engine=engine)

# --- Run the governed crew --------------------------------------------------

if __name__ == "__main__":
    from crewai_aumos.errors import GovernanceDeniedError

    try:
        result = governed.kickoff(inputs={"topic": "AI safety"})
        print("Crew output:", result)
    except GovernanceDeniedError as error:
        print(f"Crew was denied by governance: {error.reason}")
        print(f"Subject: {error.subject} | Agent role: {error.agent_role}")
