# ZHC-Nova

ZHC-Nova is a Telegram-first orchestration and coding runtime scaffold for Jacob's two-tier environment:

- Ubuntu laptop: heavy coding execution (OpenCode/Codex)
- Raspberry Pi 5 fleet (ARM64): always-on orchestration and alerts (ZeroClaw)

This repository is a v1 foundation focused on safe routing, explicit approval gates, and clear data boundaries.

## Current v1 Status

- Working v1 components:
  - SQLite task registry schema + CLI utility
  - Rule-based task router (PI_LIGHT vs UBUNTU_HEAVY)
  - Telegram long-polling runtime (`services/telegram-control/bot_longpoll.py`)
  - OpenCode wrapper (`zrun.sh`) with artifact/log output
  - Pi-to-Ubuntu dispatch wrapper (`zdispatch.sh`) as SSH-based starter
  - Policy/config templates and ops bootstrap scripts
- Stubbed integrations:
  - Telegram webhook mode (long-polling already implemented)
  - Real ZeroClaw runtime execution wiring
  - Real OpenCode automation command contract (guarded via TODO markers)

## Architecture (v1)

- Telegram is the primary control interface (long-polling runtime in v1).
- Router classifies tasks by rules + policy and determines execution tier.
- All tasks/events/approvals are written to SQLite.
- Heavy tasks are dispatched to Ubuntu and run through `infra/opencode/wrappers/zrun.sh`.
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
