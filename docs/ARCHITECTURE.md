# Architecture

## Overview

ZHC-Nova is a two-tier orchestration system:

- **Ubuntu tier (heavy execution)**: OpenCode/Codex jobs, larger code tasks, deeper analysis.
- **Pi tier (always-on orchestration)**: Telegram command plane, scheduling, monitoring, lightweight workers.

Primary interface is Telegram. Web dashboard is a future secondary interface.

## Core Components

- `services/telegram-control/` - Telegram command contract and future runtime service.
- `services/task-router/router.py` - v1 rule-based classifier and dispatcher.
- `shared/task-registry/` - SQLite schema + CLI utility.
- `infra/opencode/wrappers/zrun.sh` - OpenCode task runner wrapper.
- `infra/opencode/wrappers/zdispatch.sh` - Pi-to-Ubuntu remote dispatch wrapper.
- `shared/policies/` - routing and approval policy definitions.

## Data Flow (v1)

1. User issues command (Telegram contract in `docs/TELEGRAM_COMMANDS.md`).
2. Router classifies task as `PI_LIGHT` or `UBUNTU_HEAVY`.
3. Router writes task + events to SQLite registry.
4. Router dispatches execution:
   - `UBUNTU_HEAVY`: remote dispatch to Ubuntu and run `zrun.sh`.
   - `PI_LIGHT`: execute local worker stub.
   - `UBUNTU_HEAVY` dispatch is gated on planner/reviewer artifacts (review verdict must be `pass`).
5. Execution writes artifacts under `storage/tasks/<task_id>/`.
6. Router records telemetry metadata (dispatch duration, estimated cost, model hints) per task.
6. Registry status/events are updated and returned to user.
7. If action is gated, approval state blocks execution progression.

## Task Flow and Approvals

Risk categories are defined in `shared/policies/approvals.yaml`.
Default behavior is deny-by-default for risky actions until explicit human approval.

Approval-required examples:

- Git push
- Deploy/restart
- File deletion
- Scheduler modifications
- Compliance/spray finalization
- Customer-facing outbound communication

## Boundaries

- `storage/records/` is official/protected records only.
- `storage/memory/` is assistant memory and context.
- `storage/tasks/` is ephemeral task artifacts and logs.
- `storage/vault-mirror/` is secure mirror staging.

No automatic writes to official records in v1 runtime flows.

## TODOs

- TODO: REAL_INTEGRATION - Telegram bot service implementation.
- TODO: REAL_INTEGRATION - ZeroClaw runtime command bindings.
- TODO: REAL_INTEGRATION - Multi-node fleet dispatch and health routing.
