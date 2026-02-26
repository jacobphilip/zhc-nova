#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
UNIT_SRC_DIR="$ROOT_DIR/infra/zeroclaw/systemd-user"
UNIT_DST_DIR="$HOME/.config/systemd/user"

mkdir -p "$UNIT_DST_DIR"
cp "$UNIT_SRC_DIR/zhc-prodlike-traffic.service" "$UNIT_DST_DIR/"
cp "$UNIT_SRC_DIR/zhc-prodlike-traffic.timer" "$UNIT_DST_DIR/"

systemctl --user daemon-reload
systemctl --user enable --now zhc-prodlike-traffic.timer
systemctl --user start zhc-prodlike-traffic.service

systemctl --user --no-pager --lines=0 status zhc-prodlike-traffic.timer
echo "prodlike timer installed and started"
