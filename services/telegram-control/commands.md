# Telegram Control Commands (v1 runtime)

Runtime entrypoint: `services/telegram-control/bot_longpoll.py`

Audit log path: `storage/memory/telegram_command_audit.jsonl`

## /newtask

`/newtask <task_type> <prompt>`

- Creates a task and routes it.
- Returns: `task_id`, route, status, approval requirement.

Example:

```text
/newtask code_refactor Refactor weather ingestion worker for reliability
```

## /status

`/status <task_id>`

- Returns current task status and recent events.

## /list

`/list [limit]`

- Lists recent tasks with status and route class.

## /approve

`/approve <task_id> <action_category> [note]`

- Records human approval decision for gated actions.
- If planner/reviewer gate is already satisfied, resumes blocked task execution when approved.
- If planner/reviewer gate is not satisfied, keeps task blocked until review artifacts are recorded.
- If rejected, task is deterministically cancelled.

## /plan

`/plan <task_id> <summary>`

- Records planner artifact for `UBUNTU_HEAVY` tasks.

## /review

`/review <task_id> <pass|fail> [notes]`

- Records reviewer artifact and verdict for `UBUNTU_HEAVY` tasks.
- `pass` is required before heavy task can resume.

## /resume

`/resume <task_id>`

- Attempts to resume blocked task after approvals and review gate are satisfied.

## /stop

`/stop <task_id>`

- Requests stop/cancel for active task.
- TODO: REAL_INTEGRATION - propagate stop to remote workers.

## /board

`/board`

- Returns lightweight operational board summary:
  - running tasks
  - blocked tasks
  - failed tasks (recent)

## Safety Contract

Any command that triggers high-risk action remains blocked until explicit human approval.
