# Operations Guide

## Reference Repositories

- ZeroClaw: https://github.com/openagen/zeroclaw
- OpenCode: https://github.com/anomalyco/opencode
- ZHC philosophy (Brian Roemmele): https://x.com/BrianRoemmele
- Agent Swarm: The One-Person Dev Team Setup: https://x.com/elvissun/status/2025920521871716562?s=20

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

# Approve and resume a blocked task
python3 services/task-router/router.py approve --task-id <task_id> --action-category deploy_restart --decided-by jacob --note "approved"

# Record planner/reviewer artifacts for UBUNTU_HEAVY task
python3 services/task-router/router.py record-plan --task-id <task_id> --author planner --summary "Plan steps and risks"
python3 services/task-router/router.py record-review --task-id <task_id> --reviewer reviewer --verdict pass --checklist-json '{"policy_safety":true,"correctness":true,"tests":true,"rollback":true,"approval_constraints":true}' --notes "Looks safe"

# Fail review with taxonomy reason code
python3 services/task-router/router.py record-review --task-id <task_id> --reviewer reviewer --verdict fail --reason-code missing_tests --checklist-json '{"policy_safety":true,"correctness":true,"tests":false,"rollback":true,"approval_constraints":true}' --notes "Add test coverage first"

# Resume blocked task after gates are satisfied
python3 services/task-router/router.py resume --task-id <task_id> --requested-by jacob

# List tasks
python3 shared/task-registry/task_registry.py list --limit 20

# Compact ops health summary (last 24h)
python3 shared/task-registry/task_registry.py --json ops-summary --hours 24

# Telemetry summary (cost/latency estimates)
python3 shared/task-registry/task_registry.py --json telemetry --limit 20

# Closed-loop metrics report
python3 scripts/metrics_report.py --days 7 --iteration latest --output-json docs/audits/metrics/latest_metrics.json --output-md docs/audits/metrics/latest_metrics.md

# Chaos-lite reliability suite (CP-008)
python3 scripts/chaos_lite.py --output storage/memory/chaos_lite_latest.json

# Production-like traffic generator (for pre-production KPI windows)
python3 scripts/prodlike_traffic.py --output storage/memory/prodlike_traffic_latest.json

# Install recurring prodlike traffic timer (systemd --user)
./scripts/install_prodlike_timer.sh

# Rollback drill (HEAD~1 smoke validation in temporary worktree)
./scripts/rollback_drill.sh

# Get task
python3 shared/task-registry/task_registry.py get --task-id <task_id>

# Run health checks
./scripts/healthcheck.sh

# Run Telegram long-polling control plane
python3 services/telegram-control/bot_longpoll.py

# ZeroClaw gateway preflight
./scripts/zeroclaw_preflight.sh

# Telegram service logs (systemd)
journalctl -u zhc-telegram-control.service -n 200 --no-pager

# ZeroClaw gateway logs (systemd)
journalctl -u zeroclaw-gateway.service -n 200 --no-pager
```

## Autonomy Modes

- `readonly`: tasks can be created/classified but execution is blocked.
- `supervised` (default): all `UBUNTU_HEAVY` tasks require approval before dispatch; high-risk tasks remain gated.
- `auto`: non-gated tasks execute immediately; high-risk tasks still require approval.

Mode override examples:

```bash
ZHC_AUTONOMY_MODE=readonly python3 services/task-router/router.py route --task-type ping --prompt "status check"
ZHC_AUTONOMY_MODE=supervised python3 services/task-router/router.py route --task-type code_refactor --prompt "refactor parser"
ZHC_AUTONOMY_MODE=auto python3 services/task-router/router.py route --task-type ping --prompt "status check"
```

## Runtime Modes

- `single_node` (default): `UBUNTU_HEAVY` tasks run locally through `infra/opencode/wrappers/zrun.sh`.
- `multi_node`: `UBUNTU_HEAVY` tasks dispatch over SSH through `infra/opencode/wrappers/zdispatch.sh`.

Examples:

```bash
ZHC_RUNTIME_MODE=single_node python3 services/task-router/router.py route --task-type code_refactor --prompt "single node"
ZHC_RUNTIME_MODE=multi_node python3 services/task-router/router.py route --task-type code_refactor --prompt "multi node"
```

## Execution Policy

- Policy source: `shared/policies/execution_policy.yaml` (or `ZHC_EXECUTION_POLICY`).
- `strict` mode blocks execution before approval/dispatch when policy fails.
- Blocked tasks return `policy_status=blocked` and `policy_reason=<code>`.

Inspect blocked reason and events:

```bash
python3 shared/task-registry/task_registry.py --json get --task-id <task_id>
```

## Heavy Task Gate

- Every `UBUNTU_HEAVY` task is blocked until both artifacts exist:
  - `storage/tasks/<task_id>/artifacts/planner.md`
  - `storage/tasks/<task_id>/artifacts/reviewer.json` with verdict `pass` and complete checklist
- High-risk tasks may require both human approval and planner/reviewer gate before dispatch.

## Telemetry

- Router writes per-task telemetry into metadata (`dispatch_duration_ms`, `estimated_cost_usd`, model hints).
- Router also writes context compaction + token estimates and cost artifacts.
- View rollup with `python3 shared/task-registry/task_registry.py --json telemetry --limit 20`.
- For OpenRouter price enrichment, set `OPENROUTER_API_KEY` and keep `ZHC_COST_LOOKUP_ENABLED=1`.
- Verify enrichment with `python3 scripts/metrics_report.py ...` and check `cost_source_counts.openrouter_api`.

OpenRouter enrichment quick check:

```bash
OPENROUTER_API_KEY=<real_key> make metrics
python3 - <<'PY'
import json
from pathlib import Path
payload = json.loads(Path('docs/audits/metrics/latest_metrics.json').read_text())
print(payload['summary']['telemetry']['cost_source_counts'])
PY
```

Inspect artifacts for one task:

```bash
python3 shared/task-registry/task_registry.py --json get --task-id <task_id>
python3 shared/task-registry/task_registry.py --json events --task-id <task_id> --limit 200
python3 shared/task-registry/task_registry.py --json trace-events --trace-id <trace_id> --limit 500
ls storage/tasks/<task_id>/artifacts
python3 shared/task-registry/task_registry.py --json lease-get --task-id <task_id>
```

## Logs and Artifacts

- Task logs/artifacts: `storage/tasks/<task_id>/`
- Telegram command audit: `storage/memory/telegram_command_audit.jsonl`
- Telegram offset file: `storage/memory/telegram_offset.txt`
- Dispatch lease record: `task_dispatch_lease` (query via `lease-get` / `lease-list`)
- Idempotency record: `idempotency_keys` (query via `idempo-get` / `idempo-list`)
- Runtime stdout/stderr: systemd journal (when enabled)

## Timeout And Retry Matrix

- Telegram poll: `TELEGRAM_POLL_TIMEOUT_SECONDS`, backoff to `TELEGRAM_MAX_BACKOFF_SECONDS` on poll errors.
- Telegram API calls (`sendMessage` etc.): `TELEGRAM_API_CALL_TIMEOUT_SECONDS`.
- Router/registry command calls from Telegram: `TELEGRAM_COMMAND_TIMEOUT_SECONDS` with retries controlled by `TELEGRAM_COMMAND_RETRY_MAX`, `TELEGRAM_COMMAND_RETRY_BACKOFF_SECONDS`, and `TELEGRAM_COMMAND_RETRY_JITTER_SECONDS`.
- Heavy resume from Telegram: `TELEGRAM_RESUME_TIMEOUT_SECONDS` (separate from normal command timeout).
- Dispatch wrapper execution: `ZHC_DISPATCH_TIMEOUT_SECONDS` with retries controlled by `ZHC_DISPATCH_RETRY_MAX`, `ZHC_DISPATCH_RETRY_BACKOFF_SECONDS`, and `ZHC_DISPATCH_RETRY_JITTER_SECONDS`.

## Recovery

- If DB missing/corrupt: backup file, recreate with `./scripts/db_init.sh`.
- If dispatch fails: verify SSH key + `ZHC_UBUNTU_HOST` + remote path.
- If task stuck in pending/running: append event and mark terminal state manually via CLI update.
- If Telegram bot not responding:
  - user service mode: `systemctl --user restart zhc-telegram-control.service`
  - system service mode: `sudo systemctl restart zhc-telegram-control.service`
  - inspect logs (user): `journalctl --user-unit zhc-telegram-control.service -n 200 --no-pager`
  - inspect logs (system): `journalctl -u zhc-telegram-control.service -n 200 --no-pager`
- If ZeroClaw gateway not responding:
  - user service mode: `systemctl --user restart zeroclaw-gateway.service`
  - system service mode: `sudo systemctl restart zeroclaw-gateway.service`
  - inspect logs (user): `journalctl --user-unit zeroclaw-gateway.service -n 200 --no-pager`
  - inspect logs (system): `journalctl -u zeroclaw-gateway.service -n 200 --no-pager`
- If offset appears stuck or replaying:
  - `python3 services/telegram-control/bot_longpoll.py --show-offset`
  - `python3 services/telegram-control/bot_longpoll.py --reset-offset`
- If service fails with `lock_exists` and no active bot process:
  - remove stale lock: `rm storage/memory/telegram_longpoll.lock`
  - restart (user): `systemctl --user restart zhc-telegram-control.service`
  - restart (system): `sudo systemctl restart zhc-telegram-control.service`
- If `/resume` times out in Telegram:
  - verify current state: `/status <task_id>`
  - if task is still `blocked`, run `/resume <task_id>` once more
  - for persistent timeouts, increase `TELEGRAM_RESUME_TIMEOUT_SECONDS` and restart telegram service

## Telegram Smoke Test

- Run `docs/TELEGRAM_SMOKETEST.md` after deploy/restart.
- Fast harness (2-6 minutes):

```bash
python3 scripts/smoke_fast_control_plane.py --mode full --json --output storage/memory/fast_smoke_latest.json
```

- Pass condition: JSON output contains `"ok": true`.
- Default harness mode forces stubbed heavy execution (`ZHC_ENABLE_REAL_OPENCODE=0`) for speed.
- Use `--real-exec` to exercise real heavy execution path.

```bash
python3 scripts/smoke_fast_control_plane.py --mode full --real-exec --json
```

## Chaos-Lite Reliability Suite

- Run CP-008 scenarios:

```bash
make chaos-lite
```

- Report output: `storage/memory/chaos_lite_latest.json`
- Pass condition: report contains `"ok": true` and no failed scenarios.

## Production-Like Traffic Window

- Generate realistic operator-like command flow when no real operator traffic exists yet:

```bash
make prodlike-traffic
```

- Report output: `storage/memory/prodlike_traffic_latest.json`
- Audit rows are tagged `traffic_class=synthetic_prodlike`.

Recurring timer install:

```bash
make prodlike-timer-install
systemctl --user list-timers --all | grep zhc-prodlike-traffic
```

## Rollback Drill (CP-009)

- Validate rollback readiness by running smoke in an isolated `HEAD~1` worktree.

```bash
make rollback-drill
```

- Report output: `storage/memory/rollback_drill_latest.json`
- Pass condition: `rollback_validation_ok=true` and `smoke_exit_code=0`.

## Browser Pilot (Safe Wrapper)

- `browser_pilot` is routed as `UBUNTU_HEAVY` and approval-gated via `browser_sensitive`.
- Runtime is single-node only; multi-node dispatch is blocked.
- Wrapper path: `infra/browser/wrappers/zbrowser_safe.sh`
- Default behavior is safe stub mode, even if `agent-browser` exists.

Enable real browser pilot execution only when intentionally testing:

```bash
export ZHC_ENABLE_BROWSER_PILOT=1
export ZHC_BROWSER_ALLOWED_DOMAINS=example.com
```

## Ubuntu Single-Node Alive Checklist

- Telegram bot running and responding to `/start`, `/help`, `/newtask`, `/board`.
- Heavy task flow enforces approval + planner/reviewer gates.
- Heavy task resume executes local wrapper path in `single_node` mode.
- Artifacts present in `storage/tasks/<task_id>/artifacts/`.

## External Brain Fallback

- Jacob has real-time access to Grok Super (xAI) and ChatGPT Plus (GPT-4o).
- OpenCode has zero direct API/browser access in v1 and must never pretend otherwise.
- If latest information, advanced creative/strategic reasoning, complex code review/architecture advice, or anything uncertain is needed, agents must stop and emit this exact block:

=== EXTERNAL QUERY NEEDED ===
TARGET: Grok OR GPT
QUERY:
[paste the full prompt/question you want me to send to Grok or ChatGPT]
CONTEXT (current task & why we need this):
• bullet 1
• bullet 2
=== END QUERY ===

- Wait for Jacob to reply in this format:

=== EXTERNAL RESPONSE ===
[answer from Grok or GPT]

- Resume exactly where execution paused, incorporating the returned answer.

## Iteration Audit Loop

- Run the repeatable audit process documented in `docs/AUDIT_PROCESS.md` at each milestone.
- Keep current rolling artifacts in `docs/audits/latest_scores.json` and `docs/audits/latest_report.md`.
- Archive milestone outputs as dated files in `docs/audits/`.

Audit commands:

```bash
# update docs/audits/latest_scores.json, then
make audit

# or generate a dated report
python3 scripts/audit_score.py \
  --scores docs/audits/2026-02-25-v1_1_scores.json \
  --output docs/audits/2026-02-25-v1_1_report.md \
  --iteration 2026-02-25-v1.1
```
