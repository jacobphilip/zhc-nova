# v1.1 Execution Plan (47 -> 75+)

This plan converts the latest audit gaps into a concrete implementation sequence.

## Objective

- Raise ZHC-Nova from baseline 47/100 to >=75/100.
- Preserve safety gates while enabling practical supervised autonomy.

## Workstreams

Status snapshot (2026-02-25):

- Workstream 1: implemented (router-backed approval/resume)
- Workstream 2: implemented (`readonly`/`supervised`/`auto`)
- Workstream 3: implemented (strict execution policy)
- Workstream 4: implemented baseline (planner/reviewer gate)
- Workstream 5: pending
- Workstream 6: in progress (telemetry metadata + summary command)

1) Telegram Runtime + Approval Resume
- Implement real command handlers for `/newtask`, `/status`, `/list`, `/approve`, `/stop`, `/board`.
- Wire `/approve` to approvals table updates and blocked-task resume logic.
- Files: `services/telegram-control/*`, `services/task-router/router.py`, `shared/task-registry/task_registry.py`.
- Acceptance: blocked task transitions to running/succeeded after explicit approval.

2) Autonomy Modes Enforcement
- Add runtime mode config: `readonly`, `supervised`, `auto`.
- Enforce per-route behavior in router and wrappers.
- Files: `.env.example`, `shared/policies/*.yaml`, `services/task-router/router.py`, `infra/opencode/wrappers/*.sh`.
- Acceptance: high-risk tasks cannot execute in `auto` without explicit gate approval.

3) Secure Execution Policy Layer
- Add explicit command allowlists and non-root execution guidance.
- Add control-plane request signing TODO boundary and verification hooks.
- Files: `docs/SECURITY.md`, wrapper scripts, router checks.
- Acceptance: disallowed actions are rejected with audit events.

4) Multi-Agent Role Flow (Planner/Critic/Executor)
- Define worker contract for planner/reviewer execution path.
- Enforce reviewer pass before high-risk state transitions.
- Files: `shared/prompts/*.md`, routing policy, task metadata schema use.
- Acceptance: each heavy task records planner + reviewer artifacts before completion.

5) Memory + Context Optimization
- Add memory indexing design doc and initial storage strategy.
- Add prompt-compaction runbook and measurement fields.
- Files: `docs/ARCHITECTURE.md`, `docs/DATA_MODEL.md`, `docs/OPERATIONS.md`.
- Acceptance: each task records compacted context size and retrieval source.

6) Telemetry + Cost Tracking
- Extend task metadata to track model/provider, token estimate, runtime, and cost estimate.
- Publish per-iteration trend in audit reports.
- Files: `shared/task-registry/schema.sql`, `shared/task-registry/task_registry.py`, wrappers.
- Acceptance: latest 20 tasks include telemetry fields for cost/latency reporting.

## Delivery Sequence

1. Secure/autonomy foundations (workstreams 2 and 3)
2. Telegram runtime path (workstream 1)
3. Multi-agent process gates (workstream 4)
4. Memory/telemetry layers (workstreams 5 and 6)
5. Run iteration audit and publish report under `docs/audits/`

## Definition of Done

- `make healthcheck` passes
- Safety gates still block risky actions by default
- One end-to-end task runs through approve/resume path
- Audit report generated with `scripts/audit_score.py`
- Score reaches >=75/100 or remaining blockers are explicitly listed
