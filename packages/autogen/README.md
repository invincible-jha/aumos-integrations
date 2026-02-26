# autogen-aumos

AumOS governance integration for Microsoft AutoGen conversations.

## Overview

Add governance checks to any AutoGen agent's messages and tool calls. Each agent gets independent trust levels, budget tracking, and consent verification.

## Installation

```bash
pip install autogen-aumos
```

## Quick Start

```python
from autogen import ConversableAgent
from aumos_governance import GovernanceEngine, GovernanceConfig
from autogen_aumos import GovernedConversableAgent

# Create governance engine
engine = GovernanceEngine(GovernanceConfig.default())

# Create your AutoGen agent
agent = ConversableAgent(name="assistant", llm_config={"model": "gpt-4"})

# Wrap with governance
governed = GovernedConversableAgent(agent=agent, engine=engine, trust_level=2)

# Use governed.agent in your conversations — hooks are installed
governed.agent.initiate_chat(other_agent, message="Hello")
```

## Features

- **Message governance** — Every message send is checked against governance policy
- **Tool governance** — Function/tool execution requires governance approval
- **Group chat support** — Each agent in a group chat governed independently
- **Composition-based** — Wraps agents without subclassing AutoGen internals

## API

### GovernedConversableAgent

Wraps an AutoGen `ConversableAgent` with governance hooks.

### MessageGuard

Standalone message governance — check individual messages against policy.

### ToolGuard

Standalone tool execution governance — check tool calls against policy.

## Fire Line

See [FIRE_LINE.md](FIRE_LINE.md) for IP boundary constraints.

## License

Apache 2.0 — Copyright (c) 2026 MuVeraAI Corporation
