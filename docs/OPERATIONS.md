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
