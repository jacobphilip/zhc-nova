# Data Model

## SQLite Registry

Primary schema file: `shared/task-registry/schema.sql`

Tables:

- `tasks`: canonical task state and routing metadata
- `task_events`: append-only event history
- `approvals`: approval gate status and decisions
- `workers`: worker/node metadata
- `artifacts`: task artifact index

Default DB path:

- `storage/tasks/task_registry.db`

Override with `ZHC_TASK_DB`.

## File Storage Boundaries

- `storage/tasks/`: per-task artifact directories (`storage/tasks/<task_id>/`)
- `storage/memory/`: assistant memory and context artifacts
- `storage/records/`: official records (protected, no automatic v1 writes)
- `storage/vault-mirror/`: secure mirror sync staging

## Event and Status Model

- Task status lifecycle: `pending -> running -> succeeded|failed|blocked|cancelled`
- Events capture state transitions, dispatch outcomes, and approval waits
- Approvals model retains `required`, `approved`, `rejected`, `cancelled`

## Task Metadata Telemetry (v1.1)

Task `metadata` may include:

- `model_provider_hint`, `model_name_hint`
- `estimated_prompt_tokens`, `estimated_completion_tokens`, `estimated_total_tokens`
- `estimated_cost_usd`, `cost_source` (`openrouter_api` or `heuristic`)
- `context_input_tokens`, `context_compacted_tokens`, `compression_ratio`, `context_token_budget`
- `retrieval_sources` (memory/task source IDs)
- `context_compacted_path`, `cost_estimate_path`

## TODO

- TODO: REAL_INTEGRATION - immutable audit sealing for compliance finalizations.
