#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage: zrun.sh --task-type TYPE --prompt PROMPT [--repo PATH] [--worktree PATH] [--task-id ID]

Runs a routed OpenCode job wrapper and writes artifacts to storage/tasks/<task_id>/.

TODO: REAL_INTEGRATION - replace stub invocation with final OpenCode non-interactive contract.
EOF
}

TASK_TYPE=""
PROMPT=""
REPO_PATH=""
WORKTREE_PATH=""
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
    --repo)
      REPO_PATH="$2"
      shift 2
      ;;
    --worktree)
      WORKTREE_PATH="$2"
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

if [[ -z "$TASK_TYPE" || -z "$PROMPT" ]]; then
  echo "ERROR: --task-type and --prompt are required" >&2
  exit 2
fi

if [[ -z "$TASK_ID" ]]; then
  TASK_ID="task-$(date -u +%Y%m%dT%H%M%SZ)-$RANDOM"
fi

STORAGE_ROOT="${ZHC_STORAGE_ROOT:-storage}"
TASK_DIR="${STORAGE_ROOT}/tasks/${TASK_ID}"
mkdir -p "$TASK_DIR"

AUTONOMY_MODE="${ZHC_AUTONOMY_MODE:-supervised}"
if [[ "$AUTONOMY_MODE" != "readonly" && "$AUTONOMY_MODE" != "supervised" && "$AUTONOMY_MODE" != "auto" ]]; then
  echo "ERROR: Invalid ZHC_AUTONOMY_MODE '$AUTONOMY_MODE' (allowed: readonly|supervised|auto)" >&2
  exit 2
fi

if [[ "$AUTONOMY_MODE" == "readonly" ]]; then
  echo "ERROR: execution blocked by ZHC_AUTONOMY_MODE=readonly" >&2
  exit 1
fi

BLOCKED_KEYWORDS="${ZHC_BLOCKED_PROMPT_KEYWORDS:-rm -rf|drop database|truncate table|git push --force|force push|delete all}"
IFS='|' read -r -a KEYWORDS <<< "$BLOCKED_KEYWORDS"
for keyword in "${KEYWORDS[@]}"; do
  if [[ -n "$keyword" ]] && grep -Fqi -- "$keyword" <<< "$PROMPT"; then
    echo "ERROR: execution blocked by wrapper policy keyword: $keyword" >&2
    exit 1
  fi
done

PROVIDER="${ZHC_DEFAULT_PROVIDER:-openai}"
MODEL="${ZHC_DEFAULT_MODEL:-codex}"

case "$TASK_TYPE" in
  code_review|plan|summary)
    PROVIDER="${ZHC_FALLBACK_PROVIDER:-openrouter}"
    MODEL="${ZHC_FALLBACK_MODEL:-reviewer-model}"
    ;;
esac

RUN_LOG="$TASK_DIR/run.log"
STDOUT_LOG="$TASK_DIR/stdout.log"
STDERR_LOG="$TASK_DIR/stderr.log"
META_JSON="$TASK_DIR/meta.json"

{
  echo "task_id=$TASK_ID"
  echo "task_type=$TASK_TYPE"
  echo "provider=$PROVIDER"
  echo "model=$MODEL"
  echo "autonomy_mode=$AUTONOMY_MODE"
  echo "repo=${REPO_PATH:-unset}"
  echo "worktree=${WORKTREE_PATH:-unset}"
  echo "created_at=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
} >> "$RUN_LOG"

cat > "$META_JSON" <<EOF
{
  "task_id": "$TASK_ID",
  "task_type": "$TASK_TYPE",
  "provider": "$PROVIDER",
  "model": "$MODEL",
  "repo": "${REPO_PATH}",
  "worktree": "${WORKTREE_PATH}",
  "status": "running"
}
EOF

if [[ "${ZHC_ENABLE_REAL_OPENCODE:-0}" == "1" ]]; then
  if ! command -v opencode >/dev/null 2>&1; then
    echo "ERROR: opencode command not found" | tee -a "$RUN_LOG" >&2
    exit 1
  fi

  # Uses non-interactive one-shot execution path.
  set +e
  if [[ -n "$REPO_PATH" ]]; then
    opencode run --print-logs --model "$PROVIDER/$MODEL" "$PROMPT" "$REPO_PATH" >"$STDOUT_LOG" 2>"$STDERR_LOG"
  else
    opencode run --print-logs --model "$PROVIDER/$MODEL" "$PROMPT" >"$STDOUT_LOG" 2>"$STDERR_LOG"
  fi
  EXIT_CODE=$?
  set -e
else
  {
    echo "[STUB] OpenCode execution disabled"
    echo "[STUB] Prompt: $PROMPT"
    echo "[STUB] TODO: REAL_INTEGRATION"
  } >"$STDOUT_LOG"
  : >"$STDERR_LOG"
  EXIT_CODE=0
fi

if [[ $EXIT_CODE -eq 0 ]]; then
  STATUS="succeeded"
else
  STATUS="failed"
fi

cat > "$META_JSON" <<EOF
{
  "task_id": "$TASK_ID",
  "task_type": "$TASK_TYPE",
  "provider": "$PROVIDER",
  "model": "$MODEL",
  "repo": "${REPO_PATH}",
  "worktree": "${WORKTREE_PATH}",
  "status": "$STATUS",
  "exit_code": $EXIT_CODE
}
EOF

echo "status=$STATUS exit_code=$EXIT_CODE" >> "$RUN_LOG"
echo "$TASK_ID"
exit "$EXIT_CODE"
