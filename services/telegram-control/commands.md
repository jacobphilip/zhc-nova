# Telegram Control Commands (v1 contract)

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

- Records human approval for gated actions.
- TODO: REAL_INTEGRATION - update approvals table + resume blocked execution.

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
