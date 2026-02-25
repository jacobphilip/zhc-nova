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
- `ZHC_EXECUTION_POLICY` and `ZHC_POLICY_ENFORCEMENT`
- `ZHC_RUNTIME_MODE` (`single_node` recommended first, `multi_node` for Pi->Ubuntu dispatch)
- `ZHC_AUTONOMY_MODE` (`readonly`, `supervised`, `auto`)
- `ZHC_CONTEXT_TOKEN_BUDGET` and `ZHC_CONTEXT_TOKEN_BUDGET_HEAVY`
- `ZHC_CONTEXT_TARGET_RATIO`
- `ZHC_COST_LOOKUP_ENABLED`, `ZHC_COST_LOOKUP_TIMEOUT_MS`, `ZHC_COST_MODEL_DEFAULT`, `OPENROUTER_API_KEY`
- `ZHC_ENABLE_REAL_OPENCODE=1` only when real OpenCode command integration is ready

## Single-Node Mode (recommended first)

Set:

- `ZHC_RUNTIME_MODE=single_node`

In single-node mode, `UBUNTU_HEAVY` tasks run locally via `infra/opencode/wrappers/zrun.sh`.
`ZHC_UBUNTU_HOST` and `ZHC_REMOTE_REPO` are not required in this mode.

Local heavy-flow check:

```bash
python3 services/task-router/router.py route --task-type code_refactor --prompt "single node heavy test"
# then use approve/plan/review/resume flow via CLI or Telegram
```

If `ZHC_ENABLE_REAL_OPENCODE=0`, wrapper execution is stubbed but end-to-end routing and gating should still complete.

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
