---
name: ops-health
description: Run compact operational health checks and summarize status.
owner: zhc-nova
version: 0.1.0
risk_level: low
requires_approval: false
required_gates: []
allowed_tools:
  - task_registry
  - telegram-runtime
forbidden_actions:
  - service_reconfiguration
  - destructive_recovery
---

# Ops Health

## Goal

Answer "is the system healthy now" using existing summary surfaces.

## Procedure

1. Run `/ops` (or `ops-summary`) and capture status/reasons.
2. Check stale lease count and timeout counters.
3. If status is `degraded`, report exact reason keys and affected counts.

## Output Format

- `status`
- `tasks` summary
- `leases` summary
- `timeouts` summary
- `recommended_next_step`
