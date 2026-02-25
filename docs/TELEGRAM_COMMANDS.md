# Telegram Command Contract (v1)

Source of truth for service command behavior: `services/telegram-control/commands.md`

## Core Commands

- `/start`
- `/help`
- `/newtask <type> <prompt>`
- `/status <task_id>`
- `/list [limit]`
- `/approve <task_id> <action>`
- `/plan <task_id> <summary>`
- `/review <task_id> <pass|fail> [reason_code_if_fail] [notes]`
- `/resume <task_id>`
- `/stop <task_id>`
- `/board`

## Notes

- Runtime implementation: `services/telegram-control/bot_longpoll.py` (long polling).
- Command audit log: `storage/memory/telegram_command_audit.jsonl`.
- Runtime protections: allowlist enforcement, per-chat rate limiting, command timeout, exponential poll backoff.
- `/resume` uses `TELEGRAM_RESUME_TIMEOUT_SECONDS` (default 600s) to allow heavy execution windows.
- All high-risk actions require approval gate checks.
- `/approve` records approval; `/resume` performs execution.
- Rejected approvals cancel blocked tasks.
- Repeated `/resume` on already terminal/in-progress tasks is treated as a safe no-op.
- `UBUNTU_HEAVY` tasks require planner/reviewer artifacts (review verdict `pass`) before resume.
- Reviewer fail reason codes: `policy_conflict`, `missing_tests`, `insufficient_plan`, `high_risk_unmitigated`, `artifact_incomplete`, `other`.
