#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="${1:-$ROOT_DIR/.env}"

echo "[zeroclaw-preflight] root: $ROOT_DIR"
echo "[zeroclaw-preflight] env: $ENV_FILE"

if [[ ! -f "$ENV_FILE" ]]; then
  echo "[zeroclaw-preflight] ERROR: env file not found: $ENV_FILE" >&2
  exit 1
fi

set -a
# shellcheck disable=SC1090
source "$ENV_FILE"
set +a

CMD="${ZHC_ZEROCLAW_GATEWAY_CMD:-}"
if [[ -z "$CMD" ]]; then
  echo "[zeroclaw-preflight] ERROR: ZHC_ZEROCLAW_GATEWAY_CMD is not set" >&2
  echo "[zeroclaw-preflight] Example:" >&2
  echo "  ZHC_ZEROCLAW_GATEWAY_CMD='zeroclaw gateway --config /opt/zhc-nova/infra/zeroclaw/config/gateway.yaml'" >&2
  exit 1
fi

BIN="${CMD%% *}"
if ! command -v "$BIN" >/dev/null 2>&1; then
  echo "[zeroclaw-preflight] ERROR: gateway binary not found in PATH: $BIN" >&2
  echo "[zeroclaw-preflight] Command configured: $CMD" >&2
  exit 1
fi

echo "[zeroclaw-preflight] gateway command configured"
echo "[zeroclaw-preflight] binary found: $(command -v "$BIN")"
echo "[zeroclaw-preflight] command: $CMD"

if [[ -f "$ROOT_DIR/infra/zeroclaw/systemd/zeroclaw-gateway.service" ]]; then
  echo "[zeroclaw-preflight] systemd unit template present"
else
  echo "[zeroclaw-preflight] ERROR: missing systemd unit template" >&2
  exit 1
fi

echo "[zeroclaw-preflight] OK"
