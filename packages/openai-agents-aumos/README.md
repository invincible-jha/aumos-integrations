# openai-agents-aumos

AumOS governance integration for the **OpenAI Agents SDK**.

`openai-agents-aumos` implements the OpenAI Agents SDK guardrail pattern and
enforces AumOS governance controls — trust-level gating, static budget
enforcement, and append-only audit recording — before and after every tool call.

## Why governance on OpenAI Agents SDK?

The OpenAI Agents SDK provides a built-in guardrail interface designed for
exactly this kind of checkpoint.  `openai-agents-aumos` plugs AumOS governance
into that interface, giving you:

- A consistent governance policy across all tools in any agent.
- Structured audit records for every tool invocation.
- Static budget caps that prevent runaway spending.
- Trust-level gating so low-trust agents cannot call high-privilege tools.

## Installation

```bash
pip install openai-agents-aumos
# With the OpenAI Agents extras:
pip install "openai-agents-aumos[openai-agents]"
```

## Quick start

```python
from openai_agents_aumos import AumOSGuardrail

# 1. Create or obtain your governance engine instance.
engine = GovernanceEngine(config)

# 2. Create the guardrail.
guardrail = AumOSGuardrail(
    engine=engine,
    agent_id="support-agent",
    on_denied="raise",   # or "skip" / "log"
)

# 3. Attach to your OpenAI Agents SDK agent.
#    The exact attachment mechanism depends on the SDK version.
#    Typically you pass it via the `guardrails` parameter.
# agent = Agent(name="support", guardrails=[guardrail], tools=[...])
```

## Guardrail hooks

The ``AumOSGuardrail`` class exposes two hooks that match the OpenAI Agents SDK
guardrail interface:

| Hook | When called | What it does |
|------|-------------|--------------|
| `before_tool_call(tool_name, tool_input, ...)` | Before every tool execution | Evaluates governance; raises/skips/logs on denial |
| `after_tool_call(tool_name, tool_output, ...)` | After every tool execution | Records outcome to audit trail |

## Denial modes

| Mode | Behaviour |
|------|-----------|
| `raise` | Raises `GovernanceDeniedError`. The tool invocation fails. |
| `skip` | Logs the denial at INFO level. Returns a denied `GuardrailResult`. |
| `log` | Logs at WARNING level. Tool executes regardless. |

## Governance constraints

- **Trust changes are MANUAL ONLY** — the guardrail never modifies trust levels.
- **Budget allocation is STATIC ONLY** — limits come from the engine configuration.
- **Audit logging is RECORDING ONLY** — no anomaly detection, no counterfactuals.

## Using the Protocol for type safety

```python
from openai_agents_aumos.protocol import GovernanceEngineProtocol

def build_guardrail(engine: GovernanceEngineProtocol) -> AumOSGuardrail:
    """mypy --strict will verify engine satisfies the protocol."""
    return AumOSGuardrail(engine=engine)
```

## License

Apache 2.0 — see [LICENSE](LICENSE).

Copyright (c) 2026 MuVeraAI Corporation.
