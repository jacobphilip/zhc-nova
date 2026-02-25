# Deployment on Ubuntu (Dev + Heavy Execution)

## Target

- Ubuntu laptop with Python 3.11+
- OpenCode installed/authenticated for Codex usage
- Optional SSH access for Pi dispatch testing

## Setup

```bash
cp .env.example .env
./scripts/init_dev.sh
./scripts/db_init.sh
./scripts/healthcheck.sh
```

## Environment Notes

Set or confirm in `.env`:

- `ZHC_TASK_DB` path to SQLite database
- `ZHC_STORAGE_ROOT` path to `storage/`
- `ZHC_ROUTING_POLICY` and `ZHC_APPROVAL_POLICY`
- `ZHC_AUTONOMY_MODE` (`readonly`, `supervised`, `auto`)
- `ZHC_ENABLE_REAL_OPENCODE=1` only when real OpenCode command integration is ready

Autonomy mode behavior:

- `readonly`: create/classify tasks only, block all execution/dispatch.
- `supervised` (default): require approval for all `UBUNTU_HEAVY` tasks and all high-risk actions.
- `auto`: allow non-gated tasks to execute immediately; high-risk actions still require approval.

## Service Startup (dev mode)

```bash
python3 services/task-router/router.py route --task-type code_review --prompt "Review irrigation draft"
```

## TODO Integration Hooks

- TODO: REAL_INTEGRATION - OpenCode non-interactive command contract.
- TODO: REAL_INTEGRATION - Telegram service startup process.
