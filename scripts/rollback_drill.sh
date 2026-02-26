#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
REPORT_PATH="$ROOT_DIR/storage/memory/rollback_drill_latest.json"

HEAD_COMMIT="$(git -C "$ROOT_DIR" rev-parse HEAD)"
PREV_COMMIT="$(git -C "$ROOT_DIR" rev-parse HEAD~1)"

WORKTREE_DIR="/tmp/zhc-rollback-drill-$(date +%s)"
mkdir -p "$(dirname "$REPORT_PATH")"

cleanup() {
  git -C "$ROOT_DIR" worktree remove --force "$WORKTREE_DIR" >/dev/null 2>&1 || true
  rm -rf "$WORKTREE_DIR" >/dev/null 2>&1 || true
}
trap cleanup EXIT

git -C "$ROOT_DIR" worktree add --detach "$WORKTREE_DIR" "$PREV_COMMIT" >/dev/null

set +e
SMOKE_OUTPUT="$(python3 "$WORKTREE_DIR/scripts/smoke_fast_control_plane.py" --mode simulation --json 2>&1)"
SMOKE_CODE=$?
set -e

if [[ $SMOKE_CODE -eq 0 ]]; then
  ROLLBACK_OK=true
else
  ROLLBACK_OK=false
fi

export ZHC_ROLLBACK_TIMESTAMP="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
export ZHC_ROLLBACK_HEAD="$HEAD_COMMIT"
export ZHC_ROLLBACK_TARGET="$PREV_COMMIT"
export ZHC_ROLLBACK_OK="$ROLLBACK_OK"
export ZHC_ROLLBACK_SMOKE_CODE="$SMOKE_CODE"
export ZHC_ROLLBACK_SMOKE_OUTPUT="$SMOKE_OUTPUT"
export ZHC_ROLLBACK_REPORT_PATH="$REPORT_PATH"

python3 - <<'PY'
import json
import os
from pathlib import Path

report = {
    "timestamp": os.environ["ZHC_ROLLBACK_TIMESTAMP"],
    "head_commit": os.environ["ZHC_ROLLBACK_HEAD"],
    "rollback_target_commit": os.environ["ZHC_ROLLBACK_TARGET"],
    "rollback_validation_ok": os.environ["ZHC_ROLLBACK_OK"].lower() == "true",
    "smoke_exit_code": int(os.environ["ZHC_ROLLBACK_SMOKE_CODE"]),
    "smoke_output": os.environ["ZHC_ROLLBACK_SMOKE_OUTPUT"],
}
Path(os.environ["ZHC_ROLLBACK_REPORT_PATH"]).write_text(
    json.dumps(report, indent=2, sort_keys=True), encoding="utf-8"
)
PY

echo "rollback drill report written to $REPORT_PATH"
