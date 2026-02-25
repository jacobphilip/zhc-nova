#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

DB_PATH="${ZHC_TASK_DB:-$ROOT_DIR/storage/tasks/task_registry.db}"
SCHEMA_PATH="${ZHC_TASK_SCHEMA:-$ROOT_DIR/shared/task-registry/schema.sql}"

python3 "$ROOT_DIR/shared/task-registry/task_registry.py" --db "$DB_PATH" --schema "$SCHEMA_PATH" init

echo "DB initialized at $DB_PATH"
