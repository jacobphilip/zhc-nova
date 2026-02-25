# v1.2 Reliable Control Plane Board

This is the execution board for the next hardening sprint.

## Milestone

- Name: `Reliable Control Plane v1`
- Target: single-node Ubuntu runtime that is replay-safe, restart-safe, and operator-predictable.
- Exit gate: pass all checks in `v1.2 Gate` section below.

## Sprint Scope (10 working days)

### CP-001 - Formal Job State Machine

- Type: feature + reliability
- Priority: P0
- Effort: M
- Description: define and enforce canonical states and legal transitions.
- Required states: `REQUESTED`, `APPROVED`, `QUEUED`, `RUNNING`, `SUCCEEDED`, `FAILED`, `CANCELED`, `EXPIRED`
- Acceptance criteria:
  - invalid transition is rejected and logged
  - terminal states cannot be resumed without explicit recovery action
  - restart does not mutate state unexpectedly
- Suggested files:
  - `services/task-router/router.py`
  - `shared/task-registry/task_registry.py`
  - `shared/task-registry/schema.sql`

### CP-002 - Approval/Resume Invariant Tests

- Type: test + governance
- Priority: P0
- Effort: S
- Description: lock control integrity in tests.
- Acceptance criteria:
  - `/approve` never dispatches heavy execution
  - `/resume` dispatches only when gates are satisfied
  - duplicate `/resume` is safe (no double execution)
- Suggested files:
  - `services/task-router/router.py`
  - `services/telegram-control/bot_longpoll.py`
  - `tests/*` (new)

### CP-003 - End-to-End Idempotency Keys

- Type: reliability
- Priority: P0
- Effort: M
- Description: add command and dispatch idempotency keys across control and execution flow.
- Acceptance criteria:
  - replayed Telegram update does not create duplicate job
  - duplicate dispatch request becomes no-op
  - idempotency events are queryable in logs
- Suggested files:
  - `services/telegram-control/bot_longpoll.py`
  - `services/task-router/router.py`
  - `shared/task-registry/*`

### CP-004 - Durable Queue + Lease Recovery

- Type: reliability
- Priority: P0
- Effort: M
- Description: persist queue state and job leases so restart recovery is deterministic.
- Acceptance criteria:
  - interrupted `RUNNING` job is recovered/reclaimed
  - no concurrent double ownership of same job
  - attempt count and last error captured
- Suggested files:
  - `shared/task-registry/schema.sql`
  - `shared/task-registry/task_registry.py`
  - `services/task-router/router.py`

### CP-005 - Timeout + Retry Policy Matrix

- Type: reliability
- Priority: P1
- Effort: S-M
- Description: standardize timeout classes and retries with backoff+jitter.
- Acceptance criteria:
  - subsystem timeouts documented and enforced
  - transient failures retry with capped budget
  - no tight restart/retry loops in fault tests
- Suggested files:
  - `.env.example`
  - `services/telegram-control/bot_longpoll.py`
  - `docs/OPERATIONS.md`

### CP-006 - Structured Logs + Correlation IDs

- Type: observability
- Priority: P1
- Effort: M
- Description: emit structured JSON logs with a trace ID from command to final task state.
- Acceptance criteria:
  - a single task can be traced end-to-end by `task_id`/trace id
  - retries, timeouts, and suppressions appear as structured events
  - latest 500 records are queryable locally
- Suggested files:
  - `services/telegram-control/bot_longpoll.py`
  - `services/task-router/router.py`
  - `docs/OPERATIONS.md`

### CP-007 - Minimal Ops Status Surface

- Type: ops UX
- Priority: P1
- Effort: S
- Description: add one compact status surface (`/ops` command or CLI summary) for queue depth, stale running, and recent failures.
- Acceptance criteria:
  - operator can identify queue health in <10s
  - stale/running anomalies are visible without log digging
- Suggested files:
  - `services/telegram-control/bot_longpoll.py`
  - `shared/task-registry/task_registry.py`
- Draft spec: `docs/CP_007_OPS_SURFACE_DRAFT.md`

### CP-008 - Chaos-Lite Reliability Suite

- Type: test + reliability
- Priority: P1
- Effort: M
- Description: scripted failure scenarios for the top control-plane risks.
- Required scenarios:
  - poll timeout burst
  - duplicate command replay
  - restart during `RUNNING`
  - success-then-reporting failure
- Acceptance criteria:
  - each scenario has expected outcome and evidence
  - no silent job loss
  - no duplicate heavy execution
- Suggested files:
  - `scripts/*`
  - `docs/TELEGRAM_SMOKETEST.md`
  - `docs/OPERATIONS.md`

### CP-009 - Deploy/Rollback Repeatability

- Type: operations
- Priority: P1
- Effort: M
- Description: make deploy changes deterministic and rollback-safe.
- Acceptance criteria:
  - preflight validates config/runtime before restart
  - rollback to previous known-good revision completes in <10 minutes
  - release artifact includes commit + config hash + test summary
- Suggested files:
  - `scripts/*`
  - `docs/DEPLOYMENT_UBUNTU.md`
  - `docs/OPERATIONS.md`

### CP-010 - v1.2 Scorecard + Evidence Bundle

- Type: governance
- Priority: P1
- Effort: S
- Description: define and enforce measurable go/no-go thresholds.
- Acceptance criteria:
  - metrics generated automatically for defined window
  - v1.2 pass/fail can be decided from artifacts only
- Suggested files:
  - `scripts/metrics_report.py`
  - `docs/audits/metrics/latest_metrics.md`
  - `docs/audits/latest_report.md`

## v1.2 Gate (must all pass)

- Command handling success rate >= 99% on soak window
- Duplicate heavy executions = 0
- Control invariants hold in automated tests
- Poll timeout recovery >= 95% on induced fault tests
- MTTR <= 10 minutes for common incidents
- End-to-end traceability exists for every sampled task

## KPI Targets

- Heavy task success rate >= 96%
- Human intervention ratio <= 15%
- Approve-to-resume latency p95 < 90s
- Outcome consistency (5 reruns) >= 90%
- System uptime >= 99.7%
- Operator active time < 60 min/day
- Audit score >= 95

## Out of Scope (this sprint)

- Multi-node swarm expansion
- New custom UI beyond minimal local status surface
- Self-modifying/meta-learning agents
- Multi-channel control plane expansion
- Advanced policy-engine integration beyond current critical-path invariants

## Execution Order

1. CP-001, CP-002
2. CP-003, CP-004
3. CP-005, CP-006, CP-007
4. CP-008
5. CP-009, CP-010
