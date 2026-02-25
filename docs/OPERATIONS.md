# Operations Guide

## Daily Flow (v1)

1. Receive command (Telegram contract or CLI simulation).
2. Route task via `services/task-router/router.py`.
3. Monitor task status/events in task registry.
4. Review artifacts in `storage/tasks/<task_id>/`.
5. Approve gated actions before execution continues.

## Common Commands

```bash
# Initialize database
./scripts/db_init.sh

# Create and route task
python3 services/task-router/router.py route --task-type code_refactor --prompt "Refactor parser"

# List tasks
python3 shared/task-registry/task_registry.py list --limit 20

# Get task
python3 shared/task-registry/task_registry.py get --task-id <task_id>

# Run health checks
./scripts/healthcheck.sh
```

## Logs and Artifacts

- Task logs/artifacts: `storage/tasks/<task_id>/`
- Runtime stdout/stderr: systemd journal (when enabled)

## Recovery

- If DB missing/corrupt: backup file, recreate with `./scripts/db_init.sh`.
- If dispatch fails: verify SSH key + `ZHC_UBUNTU_HOST` + remote path.
- If task stuck in pending/running: append event and mark terminal state manually via CLI update.
