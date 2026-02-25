#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage: zdispatch.sh --task-type TYPE --prompt PROMPT [--repo PATH] [--worktree PATH]

Dispatches a heavy task from Pi to Ubuntu over SSH and returns task ID.
TODO: REAL_INTEGRATION - integrate with ZeroClaw dispatch/auth lifecycle.
EOF
}

TASK_TYPE=""
PROMPT=""
REPO_PATH=""
WORKTREE_PATH=""

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

AUTONOMY_MODE="${ZHC_AUTONOMY_MODE:-supervised}"
if [[ "$AUTONOMY_MODE" != "readonly" && "$AUTONOMY_MODE" != "supervised" && "$AUTONOMY_MODE" != "auto" ]]; then
  echo "ERROR: Invalid ZHC_AUTONOMY_MODE '$AUTONOMY_MODE' (allowed: readonly|supervised|auto)" >&2
  exit 2
fi

if [[ "$AUTONOMY_MODE" == "readonly" ]]; then
  echo "ERROR: dispatch blocked by ZHC_AUTONOMY_MODE=readonly" >&2
  exit 1
fi

UBUNTU_HOST="${ZHC_UBUNTU_HOST:-}"
REMOTE_REPO="${ZHC_REMOTE_REPO:-}"

if [[ -z "$UBUNTU_HOST" || -z "$REMOTE_REPO" || "$UBUNTU_HOST" == "TODO_REAL_HOST" ]]; then
  echo "ERROR: Set ZHC_UBUNTU_HOST and ZHC_REMOTE_REPO in environment" >&2
  exit 1
fi

TASK_ID="task-$(date -u +%Y%m%dT%H%M%SZ)-$RANDOM"

PROMPT_B64=$(printf '%s' "$PROMPT" | base64 -w 0)
REPO_B64=$(printf '%s' "$REPO_PATH" | base64 -w 0)
WORKTREE_B64=$(printf '%s' "$WORKTREE_PATH" | base64 -w 0)

REMOTE_CMD="set -euo pipefail; \
mkdir -p '$REMOTE_REPO/storage/tasks/$TASK_ID'; \
ZHC_AUTONOMY_MODE='$AUTONOMY_MODE'; \
PROMPT=\$(printf '%s' '$PROMPT_B64' | base64 -d); \
REPO=\$(printf '%s' '$REPO_B64' | base64 -d); \
WORKTREE=\$(printf '%s' '$WORKTREE_B64' | base64 -d); \
'$REMOTE_REPO/infra/opencode/wrappers/zrun.sh' --task-type '$TASK_TYPE' --prompt \"\$PROMPT\" --repo \"\$REPO\" --worktree \"\$WORKTREE\" --task-id '$TASK_ID'"

if ! ssh "$UBUNTU_HOST" "$REMOTE_CMD" >/dev/null 2>&1; then
  echo "ERROR: remote dispatch failed for $TASK_ID" >&2
  exit 1
fi

echo "$TASK_ID"
