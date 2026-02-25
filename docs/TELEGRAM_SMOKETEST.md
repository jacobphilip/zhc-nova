# Telegram Runtime Smoke Test

Run this checklist after deploy/restart of Telegram runtime.

## Preconditions

- `zhc-telegram-control.service` is active
- `.env` has valid `TELEGRAM_BOT_TOKEN` and `TELEGRAM_ALLOWED_CHAT_IDS`
- Task DB initialized

## Command Sequence

1. `/newtask ping smoke check`
2. `/list 5`
3. `/status <task_id_from_step_1>`
4. `/newtask code_refactor smoke heavy`
5. `/approve <heavy_task_id> supervised_heavy_execution approved`
6. `/plan <heavy_task_id> smoke test plan`
7. `/review <heavy_task_id> fail missing_tests add tests first`
8. `/resume <heavy_task_id>` (expect blocked with review_failed reason)
9. `/review <heavy_task_id> pass smoke review`
10. `/resume <heavy_task_id>`
11. `/board`
12. `/stop <task_id_if_non-terminal>`

## Verify

- Bot replies to each command without crash/restart loops.
- `storage/memory/telegram_command_audit.jsonl` contains `ok` records.
- Unauthorized chat IDs are logged as `unauthorized` and do not execute commands.
- `python3 shared/task-registry/task_registry.py --json telemetry --limit 10` shows updated telemetry.
