#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

mkdir -p "$ROOT_DIR/storage/tasks" "$ROOT_DIR/storage/memory" "$ROOT_DIR/storage/records" "$ROOT_DIR/storage/vault-mirror"

if [[ ! -f "$ROOT_DIR/.env" && -f "$ROOT_DIR/.env.example" ]]; then
  cp "$ROOT_DIR/.env.example" "$ROOT_DIR/.env"
  echo "Created .env from .env.example"
fi

if command -v python3 >/dev/null 2>&1; then
  PY_VER=$(python3 -c 'import sys; print(".".join(map(str, sys.version_info[:3])))')
  echo "Python found: $PY_VER"
else
  echo "ERROR: python3 not found" >&2
  exit 1
fi

echo "Dev init complete"
