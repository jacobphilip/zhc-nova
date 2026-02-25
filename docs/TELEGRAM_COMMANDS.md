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

- v1 defines contract and responses; bot runtime integration is TODO.
- All high-risk actions require approval gate checks.
- Approved actions resume blocked tasks; rejected actions cancel blocked tasks.
- `UBUNTU_HEAVY` tasks require planner/reviewer artifacts (review verdict `pass`) before resume.
