---
name: browser-pilot-safe
description: Safe browser automation pilot workflow with strict domain and action controls.
owner: zhc-nova
version: 0.1.0
risk_level: medium
requires_approval: true
required_gates:
  - plan
  - review_pass
  - approve
allowed_tools:
  - agent-browser
  - task_registry
forbidden_actions:
  - purchases
  - account_deletion
  - billing_changes
---

# Browser Pilot Safe

## Goal

Execute browser tasks in a constrained mode suitable for pre-production pilot use.

## Required Runtime Constraints

- Allowed domains must be specified.
- Action confirmation must include `eval` and `download`.
- Max output cap must be enabled.
- Session name must be unique per task.

## Procedure

1. Verify task is approved and review gate is pass.
2. Run browser sequence with safe flags and explicit domain allowlist.
3. Capture command outputs and task trace id.
4. Stop immediately on policy conflict or unexpected domain access.

## Evidence

- Save outcome summary with task id, trace id, and command list.
