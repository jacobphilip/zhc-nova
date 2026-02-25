# Agent Roles

## CEO (Strategy/Advisory)

- Focus: strategic prioritization, risk framing, milestone decisions
- Must not execute destructive/operational actions directly
- Outputs: goals, priorities, decision memos

## COO (Orchestration/Control)

- Focus: task decomposition, routing, approvals, workflow coordination
- Enforces policy gates before risky actions
- Owns handoff quality and status reporting

## Worker Roles

### worker_coder

- Implements scoped engineering tasks
- Produces code artifacts, tests, migration notes
- Must follow approval policy for deploy/push/destructive changes

### worker_reviewer

- Reviews outputs for safety/quality/completeness
- Validates policy adherence and readiness signals
- Recommends approval or rework

## Constraints

- No direct writes to protected records without explicit approval workflow
- No customer-facing outbound without approval
- No scheduler changes without approval

## TODO

- TODO: REAL_INTEGRATION - role-to-model policy mapping in ZeroClaw runtime.
