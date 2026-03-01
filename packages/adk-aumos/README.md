# adk-aumos

AumOS governance integration for **Google ADK** agents.

`adk-aumos` hooks into the Google ADK tool execution lifecycle and enforces AumOS
governance controls — trust-level gating, static budget enforcement, and append-only
audit recording — before and after every tool call.

## Why governance on Google ADK?

Google ADK agents run tools autonomously.  Without a governance layer there is no
enforced checkpoint between the agent's decision to call a tool and the tool
executing.  `adk-aumos` adds that checkpoint without requiring changes to your
ADK agent code.

## Installation

```bash
pip install adk-aumos
# With the ADK extras:
pip install "adk-aumos[adk]"
```

## Quick start

```python
from adk_aumos import AumOSADKCallback

# 1. Create or obtain your governance engine instance.
engine = GovernanceEngine(config)

# 2. Create the callback.
callback = AumOSADKCallback(
    engine=engine,
    agent_id="research-agent",
    on_denied="raise",   # or "skip" / "log"
)

# 3. Attach to your ADK agent.
#    The exact attachment mechanism depends on the ADK version you use.
#    Typically you pass it via the `callbacks` parameter of your agent class.
agent = MyADKAgent(tools=[search_tool, calculator_tool], callbacks=[callback])
```

## What the callback does

For every tool call the ADK agent attempts:

1. `before_tool_call` is invoked — governance is evaluated synchronously.
2. If denied, the configured `on_denied` action fires (`raise`, `skip`, or `log`).
3. If permitted, the tool executes normally.
4. `after_tool_call` is invoked — the outcome is recorded to the audit trail.

## Denial modes

| Mode | Behaviour |
|------|-----------|
| `raise` | Raises `GovernanceDeniedError`. The agent run fails. |
| `skip` | Logs the denial at INFO level. Tool does not execute. Agent continues. |
| `log` | Logs at WARNING level. Tool executes regardless. |

## Governance constraints

- **Trust changes are MANUAL ONLY** — the callback never modifies trust levels.
- **Budget allocation is STATIC ONLY** — limits come from the engine configuration.
- **Audit logging is RECORDING ONLY** — no anomaly detection, no counterfactuals.

## Using the Protocol for type safety

```python
from adk_aumos.protocol import GovernanceEngineProtocol

def build_callback(engine: GovernanceEngineProtocol) -> AumOSADKCallback:
    """mypy --strict will verify engine satisfies the protocol."""
    return AumOSADKCallback(engine=engine)
```

## License

Apache 2.0 — see [LICENSE](LICENSE).

Copyright (c) 2026 MuVeraAI Corporation.
