# ZHC-Nova

ZHC-Nova is a Telegram-first orchestration and coding runtime scaffold for Jacob's two-tier environment:

- Ubuntu laptop: heavy coding execution (OpenCode/Codex)
- Raspberry Pi 5 fleet (ARM64): always-on orchestration and alerts (ZeroClaw)

This repository is a v1 foundation focused on safe routing, explicit approval gates, and clear data boundaries.

## Current v1 Status

- Working v1 components:
  - SQLite task registry schema + CLI utility
  - Rule-based task router (PI_LIGHT vs UBUNTU_HEAVY)
  - Ubuntu single-node runtime mode (`ZHC_RUNTIME_MODE=single_node`) for local heavy execution
  - Telegram long-polling runtime (`services/telegram-control/bot_longpoll.py`)
  - OpenCode wrapper (`zrun.sh`) with artifact/log output
  - Pi-to-Ubuntu dispatch wrapper (`zdispatch.sh`) as SSH-based starter
  - Policy/config templates and ops bootstrap scripts
  - Durable dispatch lease ownership + recovery semantics (`task_dispatch_lease`)
  - Durable idempotency keys for Telegram command dedupe and dispatch replay safety
  - Fast control-plane harness (`make smoke-fast`) and invariant suite (`make test-control`)
  - End-to-end `trace_id` propagation (`tg-<update_id>`) into router metadata/events
- Stubbed integrations:
  - Telegram webhook mode (long-polling already implemented)
  - Real ZeroClaw runtime execution wiring
  - Deep OpenCode automation contract hardening (one-shot execution is implemented)

## Architecture (v1)

- Telegram is the primary control interface (long-polling runtime in v1).
- Router classifies tasks by rules + policy and determines execution tier.
- All tasks/events/approvals are written to SQLite.
- Heavy tasks run locally in single-node mode or dispatch over SSH in multi-node mode.
- Light tasks execute locally on Pi via worker stubs.
- Approval gates block risky operations until explicit human approval.

See `docs/ARCHITECTURE.md` and `docs/DATA_MODEL.md` for details.

## Quickstart (Ubuntu dev)

1. Copy env template and fill TODO values:

```bash
cp .env.example .env
```

2. Bootstrap and initialize DB:

```bash
make init-dev
make db-init
```

3. Run healthcheck:

```bash
make healthcheck
```

4. Create and route a sample task:

```bash
python3 services/task-router/router.py route \
  --task-type code_refactor \
  --prompt "Refactor irrigation scheduler module for readability"
```

## Repo Guide

- `docs/`: architecture, deployment, operations, security, troubleshooting
- `infra/`: ZeroClaw/OpenCode profiles, wrappers, systemd templates
- `services/`: router and service stubs
- `shared/`: task registry, policy definitions, prompt templates
- `storage/`: runtime task artifacts, memory, protected records, vault mirrors
- `scripts/`: setup and diagnostics scripts

## Telegram Runtime Ops

- Long-polling runtime: `services/telegram-control/bot_longpoll.py`
- Smoke-test checklist: `docs/TELEGRAM_SMOKETEST.md`
- Fast validation gate: `make smoke-fast`
- Control invariant tests: `make test-control`
- Command semantics + reliability controls: `docs/TELEGRAM_COMMANDS.md`

## Reliability And Traceability

- Timeout/retry matrix is configured through `.env` (`TELEGRAM_*` and `ZHC_DISPATCH_*` knobs).
- Task event timeline by task id:

```bash
python3 shared/task-registry/task_registry.py --json events --task-id <task_id> --limit 200
```

- Task event timeline by trace id:

```bash
python3 shared/task-registry/task_registry.py --json trace-events --trace-id <trace_id> --limit 500
```

## ZeroClaw Bring-Up

- Gateway unit template: `infra/zeroclaw/systemd/zeroclaw-gateway.service`
- Preflight check: `./scripts/zeroclaw_preflight.sh`

## Safety Defaults

- Human approval required by default for destructive/deploy/compliance/money/customer-facing actions.
- Autonomy modes: `readonly`, `supervised` (default), `auto`.
- Execution policy is enforced before dispatch (`shared/policies/execution_policy.yaml`).
- No production deploy automation in v1.
- No secret embedding in code.

## Next Phase

See `ROADMAP.md` for milestones from single-node v1 to multi-node swarm orchestration.

## Iteration Audits

- Repeatable audit process: `docs/AUDIT_PROCESS.md`
- Latest rolling audit: `docs/audits/latest_report.md`
- Closed-loop metrics snapshots: `docs/audits/metrics/latest_metrics.md`

Generate both audit and metrics:

```bash
make audit
make metrics
```
