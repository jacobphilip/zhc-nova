#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
UNIT_SRC_DIR="$ROOT_DIR/infra/zeroclaw/systemd-user"
UNIT_DST_DIR="$HOME/.config/systemd/user"

echo "[user-services] root: $ROOT_DIR"
echo "[user-services] source: $UNIT_SRC_DIR"
echo "[user-services] destination: $UNIT_DST_DIR"

if [[ ! -d "$UNIT_SRC_DIR" ]]; then
  echo "[user-services] ERROR: source unit directory missing" >&2
  exit 1
fi

mkdir -p "$UNIT_DST_DIR"

cp "$UNIT_SRC_DIR/zeroclaw-gateway.service" "$UNIT_DST_DIR/"
cp "$UNIT_SRC_DIR/zhc-telegram-control.service" "$UNIT_DST_DIR/"

echo "[user-services] stopping manual zeroclaw gateway if running"
pkill -f "zeroclaw gateway --host 127.0.0.1 --port 3131" >/dev/null 2>&1 || true

echo "[user-services] stopping manual telegram longpoll if running"
pkill -f "services/telegram-control/bot_longpoll.py" >/dev/null 2>&1 || true
rm -f "$ROOT_DIR/storage/memory/telegram_longpoll.lock"

echo "[user-services] reloading systemd user daemon"
systemctl --user daemon-reload

echo "[user-services] enabling and starting services"
systemctl --user enable --now zeroclaw-gateway.service
systemctl --user enable --now zhc-telegram-control.service

echo "[user-services] status summary"
systemctl --user --no-pager --lines=0 status zeroclaw-gateway.service
systemctl --user --no-pager --lines=0 status zhc-telegram-control.service

echo "[user-services] done"
