#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

mkdir -p "$ROOT_DIR/storage/tasks" "$ROOT_DIR/storage/memory" "$ROOT_DIR/storage/records" "$ROOT_DIR/storage/vault-mirror"

echo "Pi runtime bootstrap stub complete"
echo "TODO: REAL_INTEGRATION - install/enable systemd units and Telegram runtime"
