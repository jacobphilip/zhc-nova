# CP-007 Draft: Minimal Ops Status Surface

This draft defines the implementation for CP-007 (`/ops` status surface) in v1.2.

## Objective

- Provide one command that answers: "Is the system healthy right now?"
- Keep implementation minimal, local-first, and backed by existing task/lease/idempotency data.

## Scope

- Add `/ops` command to Telegram runtime (`services/telegram-control/bot_longpoll.py`).
- Add registry support query for compact ops summary (`shared/task-registry/task_registry.py`).
- Add a CLI equivalent for shell-based usage (`task_registry.py --json ops-summary`).

Out of scope:

- New UI/dashboard pages
- Prometheus/Grafana integration
- Multi-node aggregation

## Proposed `/ops` Output

Human-readable Telegram response:

```text
OPS
tasks: blocked=<n> running=<n> queued=<n> failed_24h=<n>
leases: active=<n> stale=<n>
idempotency(24h): replay=<n> conflict=<n>
timeouts(24h): command=<n> dispatch=<n>
status: healthy|degraded
```

## Data Sources

- Task statuses from `tasks` table (`blocked`, `running`, `queued`, `failed`).
- Lease health from `task_dispatch_lease`:
  - active: `lease_status IN ('queued','running')`
  - stale: active where `lease_expires_at < now`
- Idempotency from `idempotency_keys`:
  - replay count: entries reused with `exists=true` behavior (track from router events or audit)
  - conflict count: `status='conflict'` in 24h window
- Timeout/retry signals:
  - command timeout: `telegram_command_audit.jsonl` entries with `status='command_timeout'`
  - dispatch timeout: task events containing `dispatch_timeout` in 24h window

## Registry CLI Additions

- New command:

```bash
python3 shared/task-registry/task_registry.py --json ops-summary --hours 24
```

- JSON response schema:

```json
{
  "window_hours": 24,
  "tasks": {
    "blocked": 0,
    "running": 0,
    "queued": 0,
    "failed_window": 0
  },
  "leases": {
    "active": 0,
    "stale": 0
  },
  "idempotency": {
    "conflict_window": 0,
    "dispatch_keys_window": 0,
    "telegram_keys_window": 0
  },
  "timeouts": {
    "dispatch_window": 0
  },
  "status": "healthy",
  "reasons": []
}
```

`status` logic (minimal):

- `degraded` if any of:
  - stale leases > 0
  - running tasks > 0 with stale leases > 0
  - idempotency conflicts in window > 0
  - dispatch timeouts in window > 0
- else `healthy`

## Telegram Command Addition

- Add `/ops` in `handle_command`.
- `/ops` executes `ops-summary` and formats concise output.
- Keep response bounded to a few lines for mobile readability.

## Tests

- Add `tests/test_ops_summary.py` covering:
  - healthy baseline
  - stale lease -> degraded
  - idempotency conflict -> degraded
  - dispatch timeout marker -> degraded
- Extend command-level tests (if present) for `/ops` format sanity.

## Acceptance Criteria

- Operator can run `/ops` and determine health in <10 seconds.
- Stale lease and conflict conditions are surfaced without log diving.
- `ops-summary` command returns stable JSON for automation.
- `make test-control` and `make smoke-fast` remain green.

## Rollout Steps

1. Implement `ops-summary` in task registry CLI.
2. Add `/ops` command in Telegram runtime.
3. Add tests and docs examples.
4. Validate with smoke + targeted degraded-state fixture tests.
