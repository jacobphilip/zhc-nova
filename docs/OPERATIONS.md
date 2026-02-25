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
python3 services/task-router/router.py record-review --task-id <task_id> --reviewer reviewer --verdict pass --notes "Looks safe"

# Resume blocked task after gates are satisfied
python3 services/task-router/router.py resume --task-id <task_id> --requested-by jacob

# List tasks
python3 shared/task-registry/task_registry.py list --limit 20

# Telemetry summary (cost/latency estimates)
python3 shared/task-registry/task_registry.py --json telemetry --limit 20

# Closed-loop metrics report
python3 scripts/metrics_report.py --days 7 --iteration latest --output-json docs/audits/metrics/latest_metrics.json --output-md docs/audits/metrics/latest_metrics.md

# Get task
python3 shared/task-registry/task_registry.py get --task-id <task_id>

# Run health checks
./scripts/healthcheck.sh

# Run Telegram long-polling control plane
python3 services/telegram-control/bot_longpoll.py
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
  - `storage/tasks/<task_id>/artifacts/reviewer.json` with verdict `pass`
- High-risk tasks may require both human approval and planner/reviewer gate before dispatch.

## Telemetry

- Router writes per-task telemetry into metadata (`dispatch_duration_ms`, `estimated_cost_usd`, model hints).
- Router also writes context compaction + token estimates and cost artifacts.
- View rollup with `python3 shared/task-registry/task_registry.py --json telemetry --limit 20`.

Inspect artifacts for one task:

```bash
python3 shared/task-registry/task_registry.py --json get --task-id <task_id>
ls storage/tasks/<task_id>/artifacts
```

## Logs and Artifacts

- Task logs/artifacts: `storage/tasks/<task_id>/`
- Telegram command audit: `storage/memory/telegram_command_audit.jsonl`
- Runtime stdout/stderr: systemd journal (when enabled)

## Recovery

- If DB missing/corrupt: backup file, recreate with `./scripts/db_init.sh`.
- If dispatch fails: verify SSH key + `ZHC_UBUNTU_HOST` + remote path.
- If task stuck in pending/running: append event and mark terminal state manually via CLI update.

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
