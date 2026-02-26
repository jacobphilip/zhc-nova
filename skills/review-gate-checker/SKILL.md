---
name: review-gate-checker
description: Verify planner/reviewer artifacts and gate readiness before approval/resume.
owner: zhc-nova
version: 0.1.0
risk_level: medium
requires_approval: true
required_gates:
  - plan
  - review_pass
allowed_tools:
  - task_registry
  - task_router
forbidden_actions:
  - forced_status_override
---

# Review Gate Checker

## Goal

Prevent premature resume by validating artifact and checklist completeness.

## Procedure

1. Read task status, route class, and review gate status.
2. Confirm planner artifact exists for heavy tasks.
3. Confirm reviewer verdict is `pass` and checklist is complete.
4. Return explicit blocker list if any requirement is missing.

## Success Condition

- Returns `ready_for_approval` or `ready_for_resume` only when all gate checks pass.
