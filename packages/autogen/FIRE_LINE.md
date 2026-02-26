# Fire Line — autogen-aumos

## What is a Fire Line?

A fire line defines the absolute boundary between open-source code and proprietary IP.

## What's IN (Open Source — Apache 2.0)

- `GovernedConversableAgent` — composition wrapper with governance hooks
- `MessageGuard` — standalone message governance
- `ToolGuard` — standalone tool execution governance
- Configuration model for the integration
- Examples showing governed group chat patterns

## What's EXCLUDED (Proprietary)

- AutoGen memory/teachability integration (PWM territory)
- Inter-agent trust negotiation
- Adaptive permission escalation based on conversation history
- Real-time behavioral analysis of agent messages

## Dependency Constraint

This package depends ONLY on:
- `aumos-governance` (required)
- `pyautogen` (peer dependency)

No other AumOS packages. No proprietary imports.

## Forbidden Identifiers

These must NEVER appear in source code:

```
progressLevel      promoteLevel       computeTrustScore  behavioralScore
adaptiveBudget     optimizeBudget     predictSpending
detectAnomaly      generateCounterfactual
PersonalWorldModel MissionAlignment   SocialTrust
CognitiveLoop      AttentionFilter    GOVERNANCE_PIPELINE
```
