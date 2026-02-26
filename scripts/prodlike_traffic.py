#!/usr/bin/env python3
"""Generate production-like synthetic operator traffic.

This script drives Telegram command handling locally (without network sends)
to produce realistic command/audit patterns for reliability scoring when no
real operator traffic exists yet.
"""

from __future__ import annotations

import argparse
import json
import os
import runpy
import time
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
BOT_PATH = ROOT / "services/telegram-control/bot_longpoll.py"
AUDIT_LOG = ROOT / "storage/memory/telegram_command_audit.jsonl"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate production-like traffic")
    parser.add_argument(
        "--cycles", type=int, default=12, help="Number of traffic cycles"
    )
    parser.add_argument(
        "--sleep-seconds",
        type=float,
        default=0.2,
        help="Pause between cycles",
    )
    parser.add_argument(
        "--heavy-every",
        type=int,
        default=6,
        help="Run one heavy gated flow every N cycles",
    )
    parser.add_argument(
        "--output",
        default=str(ROOT / "storage/memory/prodlike_traffic_latest.json"),
        help="Output JSON summary path",
    )
    parser.add_argument(
        "--env-file",
        default=str(ROOT / ".env"),
        help="Env file to load",
    )
    parser.add_argument(
        "--real-exec",
        action="store_true",
        help="Use real heavy execution path (default uses stub mode)",
    )
    return parser.parse_args()


def load_env_file(path: Path) -> None:
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if not key:
            continue
        if (value.startswith('"') and value.endswith('"')) or (
            value.startswith("'") and value.endswith("'")
        ):
            value = value[1:-1]
        os.environ.setdefault(key, value)


def read_audit(update_id: int) -> dict[str, Any] | None:
    if not AUDIT_LOG.exists():
        return None
    match = None
    for line in AUDIT_LOG.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if int(row.get("update_id", 0)) == update_id:
            match = row
    return match


def main() -> int:
    args = parse_args()
    load_env_file(Path(args.env_file).resolve())

    mod = runpy.run_path(str(BOT_PATH))
    cfg = mod["load_config"]()
    process_update = mod["process_update"]
    process_update.__globals__["send_message"] = lambda config, chat_id, text: None

    if not cfg.allowed_ids:
        raise RuntimeError("No TELEGRAM_ALLOWED_CHAT_IDS configured")

    if not args.real_exec:
        os.environ["ZHC_ENABLE_REAL_OPENCODE"] = "0"

    # Keep generator deterministic and resilient to local rate limits.
    cfg.rate_limit_per_minute = 0
    cfg.rate_limit_burst = 0

    chat_id = sorted(cfg.allowed_ids)[0]
    update_id = 930000000 + (int(time.time()) % 1000000)
    rate_buckets: dict[int, list[float]] = {}

    status_counts: dict[str, int] = {}
    command_count = 0
    heavy_runs = 0

    def run_cmd(text: str) -> dict[str, Any]:
        nonlocal update_id, command_count
        command_count += 1
        update_id += 1
        update = {
            "update_id": update_id,
            "traffic_class": "synthetic_prodlike",
            "message": {
                "chat": {"id": chat_id},
                "from": {"id": chat_id, "username": "prodlike_runner"},
                "text": text,
            },
        }
        process_update(cfg, update, rate_buckets)
        audit = read_audit(update_id) or {}
        status = str(audit.get("status", "missing"))
        status_counts[status] = status_counts.get(status, 0) + 1
        return audit

    started = time.time()
    for cycle in range(1, max(1, args.cycles) + 1):
        run_cmd("/ops")
        run_cmd("/board")
        ping = run_cmd(f"/newtask ping prodlike-cycle-{cycle}")
        ping_task = (ping.get("result") or {}).get("task_id", "")
        if ping_task:
            run_cmd(f"/status {ping_task}")

        if args.heavy_every > 0 and cycle % args.heavy_every == 0:
            heavy_runs += 1
            heavy = run_cmd(f"/newtask code_refactor prodlike heavy cycle {cycle}")
            result = heavy.get("result") or {}
            task_id = str(result.get("task_id", ""))
            action = str(result.get("action_category", "supervised_heavy_execution"))
            if task_id:
                run_cmd(f"/plan {task_id} prodlike plan cycle {cycle}")
                run_cmd(f"/review {task_id} pass prodlike review cycle {cycle}")
                run_cmd(f"/approve {task_id} {action} prodlike approve cycle {cycle}")
                run_cmd(f"/resume {task_id}")
                run_cmd(f"/status {task_id}")

        time.sleep(max(0.0, args.sleep_seconds))

    summary = {
        "ok": True,
        "traffic_class": "synthetic_prodlike",
        "duration_seconds": round(time.time() - started, 2),
        "cycles": int(args.cycles),
        "heavy_runs": heavy_runs,
        "commands_sent": command_count,
        "status_counts": status_counts,
        "last_update_id": update_id,
    }

    out_path = Path(args.output).resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
