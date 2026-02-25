#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DB_PATH="${ZHC_TASK_DB:-$ROOT_DIR/storage/tasks/task_registry.db}"

echo "[healthcheck] root: $ROOT_DIR"

if ! command -v python3 >/dev/null 2>&1; then
  echo "[healthcheck] ERROR: python3 not found" >&2
  exit 1
fi

for dir in "$ROOT_DIR/storage/tasks" "$ROOT_DIR/storage/memory" "$ROOT_DIR/storage/records" "$ROOT_DIR/storage/vault-mirror"; do
  if [[ ! -d "$dir" ]]; then
    echo "[healthcheck] ERROR: missing dir $dir" >&2
    exit 1
  fi
done

if [[ ! -f "$DB_PATH" ]]; then
  echo "[healthcheck] WARN: DB missing at $DB_PATH (run scripts/db_init.sh)"
else
  python3 "$ROOT_DIR/shared/task-registry/task_registry.py" --db "$DB_PATH" list --limit 1 >/dev/null
  echo "[healthcheck] DB query ok"
fi

if [[ ! -x "$ROOT_DIR/infra/opencode/wrappers/zrun.sh" ]]; then
  echo "[healthcheck] ERROR: zrun.sh not executable" >&2
  exit 1
fi

if [[ ! -x "$ROOT_DIR/infra/opencode/wrappers/zdispatch.sh" ]]; then
  echo "[healthcheck] ERROR: zdispatch.sh not executable" >&2
  exit 1
fi

echo "[healthcheck] OK"
