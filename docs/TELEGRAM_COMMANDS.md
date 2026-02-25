# Telegram Command Contract (v1)

Source of truth for service command behavior: `services/telegram-control/commands.md`

## Core Commands

- `/newtask <type> <prompt>`
- `/status <task_id>`
- `/list [limit]`
- `/approve <task_id> <action>`
- `/plan <task_id> <summary>`
- `/review <task_id> <pass|fail> [notes]`
- `/resume <task_id>`
- `/stop <task_id>`
- `/board`

## Notes

- Runtime implementation: `services/telegram-control/bot_longpoll.py` (long polling).
- Command audit log: `storage/memory/telegram_command_audit.jsonl`.
- Runtime protections: allowlist enforcement, per-chat rate limiting, command timeout, exponential poll backoff.
- All high-risk actions require approval gate checks.
- Approved actions resume blocked tasks; rejected actions cancel blocked tasks.
- `UBUNTU_HEAVY` tasks require planner/reviewer artifacts (review verdict `pass`) before resume.
