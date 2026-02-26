# AumOSGovernanceCallback API Reference

`AumOSGovernanceCallback` is a LangChain `BaseCallbackHandler` that enforces
AumOS governance on every tool call an agent makes.

---

## Constructor

```python
AumOSGovernanceCallback(
    engine,
    agent_id="default",
    on_denied="raise",
    config=None,
)
```

### Parameters

**engine** (`GovernanceEngine`)
: An initialized `aumos-governance` `GovernanceEngine` instance. Required.

**agent_id** (`str`, default `"default"`)
: Identifier for the agent this callback governs. Appears in all governance
  evaluation requests and audit records. Ignored when `config` is provided.

**on_denied** (`"raise" | "skip" | "log"`, default `"raise"`)
: What to do when the governance engine returns a denial:
  - `"raise"` — raise `GovernanceDeniedError`. The agent run stops.
  - `"skip"` — return the denial message as the tool output. The agent continues.
  - `"log"` — log the denial at WARNING level and allow execution to proceed.
  Ignored when `config` is provided.

**config** (`GovernanceConfig | None`, default `None`)
: A fully-specified `GovernanceConfig` object. When provided, `agent_id` and
  `on_denied` parameters are ignored. Use this for scope mappings, spend amount
  extraction, and audit configuration.

---

## GovernanceConfig

`GovernanceConfig` is a Pydantic v2 model. All fields are validated at
construction time.

```python
from langchain_aumos import GovernanceConfig

config = GovernanceConfig(
    agent_id="my-agent",
    on_denied="raise",
    default_scope="tool_call",
    scope_mapping={"web_search": "external_api"},
    amount_field="cost",
    audit_all_calls=True,
    audit_output_preview_length=256,
)
```

### Fields

| Field | Type | Default | Description |
|---|---|---|---|
| `agent_id` | `str` | `"default"` | Agent identifier for evaluations and audit records. |
| `on_denied` | `DeniedAction` | `DeniedAction.RAISE` | Denial handling mode. |
| `default_scope` | `str` | `"tool_call"` | Governance scope for tools not in `scope_mapping`. |
| `scope_mapping` | `dict[str, str]` | `{}` | Per-tool scope overrides. |
| `amount_field` | `str \| None` | `None` | JSON field name to extract as spend amount. |
| `audit_all_calls` | `bool` | `True` | Record an audit event for every tool call. |
| `audit_output_preview_length` | `int` | `256` | Max characters of tool output in audit records. |

---

## Callback hooks

The callback implements three `BaseCallbackHandler` methods.

### on_tool_start

Called before each tool executes. Performs the governance evaluation.

**Raises** `GovernanceDeniedError` if `on_denied="raise"` and the engine denies
the call.

### on_tool_end

Called after each tool completes successfully. Records an audit event when
`audit_all_calls=True`.

### on_tool_error

Called when a tool raises an exception. Always records an audit event regardless
of `audit_all_calls`, so that errors are always visible in the audit trail.

---

## Scope mapping

Use `scope_mapping` to send specific governance scopes for specific tools:

```python
config = GovernanceConfig(
    scope_mapping={
        "web_search": "external_api_call",
        "database_query": "data_access",
        "send_email": "outbound_communication",
    },
    default_scope="tool_call",
)
```

Tools not in `scope_mapping` receive `default_scope`.

---

## Spend amount extraction

When tools carry a cost or spend amount in their JSON input, configure
`amount_field` to extract it:

```python
config = GovernanceConfig(amount_field="cost")
```

The callback will attempt to JSON-parse the tool input and extract the named
field as a float. If the field is absent or the input is not JSON, the amount
is omitted from the evaluation — this is always valid.

---

## Audit records

The callback calls `engine.record_audit_event()` after each tool call. The
record includes:

- `tool_name` — name of the tool
- `agent_id` — agent identifier
- `run_id` — LangChain run ID for correlation
- `succeeded` — whether the call completed without error
- `error_message` — exception string if the call failed
- `output_preview` — truncated tool output (up to `audit_output_preview_length` characters)

If the engine does not expose `record_audit_event`, the callback logs to
`langchain_aumos.callback` at DEBUG level instead.

---

## Error types

### GovernanceDeniedError

Raised when `on_denied="raise"` and the engine returns a denial.

```python
error.tool_name   # str — name of the denied tool
error.agent_id    # str — agent identifier
error.reason      # str — human-readable reason from the engine
error.decision    # Any — raw decision object from the engine
```

### ToolSkippedError

Internal signal raised when `on_denied="skip"`. Caught by the callback before
propagating to the caller. Exposed in the public API for subclasses that need
custom skip handling.
