#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage: zbrowser_safe.sh --task-type browser_pilot --prompt PROMPT --task-id ID

Runs a constrained browser automation pilot workflow with strict safety defaults.
EOF
}

TASK_TYPE=""
PROMPT=""
TASK_ID=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --task-type)
      TASK_TYPE="$2"
      shift 2
      ;;
    --prompt)
      PROMPT="$2"
      shift 2
      ;;
    --task-id)
      TASK_ID="$2"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown arg: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

if [[ "$TASK_TYPE" != "browser_pilot" || -z "$PROMPT" || -z "$TASK_ID" ]]; then
  echo "ERROR: --task-type browser_pilot, --prompt, and --task-id are required" >&2
  exit 2
fi

STORAGE_ROOT="${ZHC_STORAGE_ROOT:-storage}"
TASK_DIR="${STORAGE_ROOT}/tasks/${TASK_ID}"
mkdir -p "$TASK_DIR"

ALLOWED_DOMAINS="${ZHC_BROWSER_ALLOWED_DOMAINS:-example.com}"
MAX_OUTPUT="${ZHC_BROWSER_MAX_OUTPUT:-50000}"
CONFIRM_ACTIONS="${ZHC_BROWSER_CONFIRM_ACTIONS:-eval,download}"
ENABLE_BROWSER_PILOT="${ZHC_ENABLE_BROWSER_PILOT:-0}"

if [[ -z "${ALLOWED_DOMAINS}" ]]; then
  echo "ERROR: ZHC_BROWSER_ALLOWED_DOMAINS must be set for browser_pilot" >&2
  exit 1
fi

if [[ "$ENABLE_BROWSER_PILOT" != "1" ]]; then
  {
    echo "[SKIP] browser_pilot disabled (set ZHC_ENABLE_BROWSER_PILOT=1 to enable)"
    echo "[STUB] browser_pilot task recorded safely without execution"
    echo "[STUB] prompt=${PROMPT}"
  } >"$TASK_DIR/stdout.log"
  : >"$TASK_DIR/stderr.log"
  echo "$TASK_ID"
  exit 0
fi

if ! command -v agent-browser >/dev/null 2>&1; then
  {
    echo "[SKIP] agent-browser not installed"
    echo "[STUB] browser_pilot task recorded safely without execution"
    echo "[STUB] prompt=${PROMPT}"
  } >"$TASK_DIR/stdout.log"
  : >"$TASK_DIR/stderr.log"
  echo "$TASK_ID"
  exit 0
fi

SESSION_NAME="browser-pilot-${TASK_ID}"

set +e
agent-browser \
  --session-name "$SESSION_NAME" \
  --allowed-domains "$ALLOWED_DOMAINS" \
  --confirm-actions "$CONFIRM_ACTIONS" \
  --max-output "$MAX_OUTPUT" \
  --json \
  snapshot >"$TASK_DIR/stdout.log" 2>"$TASK_DIR/stderr.log"
EXIT_CODE=$?
set -e

if [[ $EXIT_CODE -ne 0 ]]; then
  exit $EXIT_CODE
fi

echo "$TASK_ID"
exit 0
