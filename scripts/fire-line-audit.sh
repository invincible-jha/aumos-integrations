#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 MuVeraAI Corporation
#
# Fire Line Audit — scans all integration source files for forbidden identifiers.
# Exit code 1 if any violation is found.

set -euo pipefail

FORBIDDEN=(
  "progressLevel"
  "promoteLevel"
  "computeTrustScore"
  "behavioralScore"
  "adaptiveBudget"
  "optimizeBudget"
  "predictSpending"
  "detectAnomaly"
  "generateCounterfactual"
  "PersonalWorldModel"
  "MissionAlignment"
  "SocialTrust"
  "CognitiveLoop"
  "AttentionFilter"
  "GOVERNANCE_PIPELINE"
)

SEARCH_DIRS=(
  "packages/langchain/src"
  "packages/langchain/examples"
  "packages/langchain/docs"
)

violations=0

for dir in "${SEARCH_DIRS[@]}"; do
  if [ ! -d "$dir" ]; then
    continue
  fi
  for term in "${FORBIDDEN[@]}"; do
    matches=$(grep -r --include="*.py" --include="*.md" --include="*.toml" -l "$term" "$dir" 2>/dev/null || true)
    if [ -n "$matches" ]; then
      echo "FIRE LINE VIOLATION: '$term' found in:"
      echo "$matches" | sed 's/^/  /'
      violations=$((violations + 1))
    fi
  done
done

if [ "$violations" -gt 0 ]; then
  echo ""
  echo "FAILED: $violations fire line violation(s) detected."
  exit 1
else
  echo "PASSED: No fire line violations found."
  exit 0
fi
