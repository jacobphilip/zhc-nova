#!/usr/bin/env python3
"""Fast control-plane smoke test for ZHC-Nova.

Runs a short, deterministic sequence (typically 2-6 minutes) that validates:
- service health pre/post
- approve is record-only (no dispatch side effects)
- resume performs execution
- duplicate approve/resume safety behavior
"""

from __future__ import annotations

import argparse
import json
import os
import runpy
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
AUDIT_LOG = ROOT / "storage/memory/telegram_command_audit.jsonl"
REGISTRY = ROOT / "shared/task-registry/task_registry.py"
BOT_PATH = ROOT / "services/telegram-control/bot_longpoll.py"


@dataclass
class StepResult:
    command: str
    update_id: int
    status: str
    error: str | None
    result: dict[str, Any] | None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Fast control-plane smoke test")
    parser.add_argument(
        "--mode",
        choices=["simulation", "full"],
        default="full",
        help="simulation skips service health checks",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print only JSON summary",
    )
    parser.add_argument(
        "--output",
        default="",
        help="Optional path to write JSON summary",
    )
    parser.add_argument(
        "--env-file",
        default=str(ROOT / ".env"),
        help="Env file to load before running tests",
    )
    parser.add_argument(
        "--real-exec",
        action="store_true",
        help="Use real heavy execution path (default uses fast stub mode)",
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
        if not key:
            continue
        value = value.strip()
        if (value.startswith('"') and value.endswith('"')) or (
            value.startswith("'") and value.endswith("'")
        ):
            value = value[1:-1]
        os.environ.setdefault(key, value)


def run_shell(command: list[str], timeout: int = 20) -> tuple[int, str, str]:
    proc = subprocess.run(
        command,
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    return proc.returncode, proc.stdout.strip(), proc.stderr.strip()


def service_health() -> dict[str, Any]:
    code, out, err = run_shell(
        [
            "systemctl",
            "--user",
            "is-active",
            "zeroclaw-gateway.service",
            "zhc-telegram-control.service",
        ],
        timeout=20,
    )
    states = [s.strip() for s in out.splitlines() if s.strip()]
    services_ok = code == 0 and len(states) == 2 and all(s == "active" for s in states)

    code2, out2, err2 = run_shell(
        ["curl", "-sS", "http://127.0.0.1:3131/health"], timeout=20
    )
    health_payload: dict[str, Any] = {}
    if code2 == 0 and out2:
        try:
            health_payload = json.loads(out2)
        except json.JSONDecodeError:
            health_payload = {"raw": out2}

    gateway_ok = bool(health_payload.get("status") == "ok")

    return {
        "services_ok": services_ok,
        "service_states": states,
        "services_error": err,
        "gateway_ok": gateway_ok,
        "gateway_health": health_payload,
        "gateway_error": err2,
    }


def read_audit_by_update(update_id: int) -> dict[str, Any] | None:
    if not AUDIT_LOG.exists():
        return None
    match: dict[str, Any] | None = None
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


def get_task(task_id: str) -> dict[str, Any]:
    code, out, err = run_shell(
        ["python3", str(REGISTRY), "--json", "get", "--task-id", task_id], timeout=30
    )
    if code != 0:
        raise RuntimeError(f"registry_get_failed: {err or out}")
    return json.loads(out)


def count_dispatch_events(task: dict[str, Any]) -> int:
    count = 0
    for ev in task.get("events", []):
        detail = str(ev.get("detail", ""))
        if detail.startswith("single_node_local_run"):
            count += 1
    return count


def run_sequence(real_exec: bool) -> dict[str, Any]:
    if not real_exec:
        os.environ["ZHC_ENABLE_REAL_OPENCODE"] = "0"

    mod = runpy.run_path(str(BOT_PATH))
    load_config = mod["load_config"]
    process_update = mod["process_update"]

    # never send real Telegram replies during harness run
    mod["send_message"] = lambda config, chat_id, text: None

    cfg = load_config()
    if not cfg.allowed_ids:
        raise RuntimeError("No TELEGRAM_ALLOWED_CHAT_IDS configured")
    # Disable the per-chat limiter so the harness can fire commands in a tight loop.
    cfg.rate_limit_per_minute = 0
    cfg.rate_limit_burst = 0

    chat_id = sorted(cfg.allowed_ids)[0]
    now = int(time.time())
    update_id = 910000000 + (now % 1000000)
    rate_buckets: dict[int, list[float]] = {}
    steps: list[StepResult] = []

    def run_cmd(text: str) -> StepResult:
        nonlocal update_id
        update_id += 1
        update = {
            "update_id": update_id,
            "message": {
                "chat": {"id": chat_id},
                "from": {"id": chat_id, "username": "fast_smoke"},
                "text": text,
            },
        }
        process_update(cfg, update, rate_buckets)
        audit = read_audit_by_update(update_id) or {}
        step = StepResult(
            command=text,
            update_id=update_id,
            status=str(audit.get("status", "missing")),
            error=audit.get("error"),
            result=audit.get("result")
            if isinstance(audit.get("result"), dict)
            else None,
        )
        steps.append(step)
        return step

    suffix = f"fast-{now}"
    create = run_cmd(f"/newtask code_refactor fast smoke {suffix}")
    task_id = (create.result or {}).get("task_id", "")
    action = (create.result or {}).get("action_category", "supervised_heavy_execution")
    if not task_id:
        raise RuntimeError("Failed to create heavy smoke task")

    run_cmd(f"/plan {task_id} fast smoke plan")
    run_cmd(f"/review {task_id} pass fast smoke review")

    before_approve = get_task(task_id)
    dispatch_before_approve = count_dispatch_events(before_approve)
    approve1 = run_cmd(f"/approve {task_id} {action} fast smoke approve one")
    after_approve1 = get_task(task_id)
    dispatch_after_approve1 = count_dispatch_events(after_approve1)
    approve2 = run_cmd(f"/approve {task_id} {action} fast smoke approve duplicate")
    after_approve2 = get_task(task_id)
    dispatch_after_approve2 = count_dispatch_events(after_approve2)

    resume1 = run_cmd(f"/resume {task_id}")
    after_resume1 = get_task(task_id)
    dispatch_after_resume1 = count_dispatch_events(after_resume1)
    resume2 = run_cmd(f"/resume {task_id}")
    after_resume2 = get_task(task_id)
    dispatch_after_resume2 = count_dispatch_events(after_resume2)

    approve_record_only_ok = (
        approve1.status == "ok"
        and approve2.status == "ok"
        and dispatch_after_approve1 == dispatch_before_approve
        and dispatch_after_approve2 == dispatch_before_approve
        and after_approve2.get("status") == "blocked"
    )

    resume_executes_ok = (
        resume1.status == "ok"
        and after_resume1.get("status") == "succeeded"
        and dispatch_after_resume1 >= dispatch_before_approve + 1
    )

    duplicate_resume_safe = (
        dispatch_after_resume2 == dispatch_after_resume1
        and (resume2.status in {"ok", "error"})
        and after_resume2.get("status") == "succeeded"
    )

    duplicate_execution_detected = dispatch_after_resume2 > dispatch_after_resume1

    command_timeout_count = sum(
        1
        for s in steps
        if s.status == "command_timeout" or (s.error and "command_timeout" in s.error)
    )

    return {
        "chat_id": chat_id,
        "task_id": task_id,
        "steps": [
            {
                "command": s.command,
                "update_id": s.update_id,
                "status": s.status,
                "error": s.error,
            }
            for s in steps
        ],
        "checks": {
            "approve_record_only": approve_record_only_ok,
            "resume_executes": resume_executes_ok,
            "duplicate_resume_safe": duplicate_resume_safe,
            "duplicate_execution_detected": duplicate_execution_detected,
        },
        "dispatch_event_counts": {
            "before_approve": dispatch_before_approve,
            "after_approve_1": dispatch_after_approve1,
            "after_approve_2": dispatch_after_approve2,
            "after_resume_1": dispatch_after_resume1,
            "after_resume_2": dispatch_after_resume2,
        },
        "final_task_status": after_resume2.get("status"),
        "timeouts": command_timeout_count,
        "approve_messages": {
            "first": (approve1.result or {}).get("message"),
            "second": (approve2.result or {}).get("message"),
        },
        "resume_statuses": {
            "first": resume1.status,
            "second": resume2.status,
            "second_error": resume2.error,
        },
    }


def main() -> int:
    args = parse_args()
    load_env_file(Path(args.env_file).resolve())
    started = time.time()
    pre = {} if args.mode == "simulation" else service_health()
    sequence = run_sequence(args.real_exec)
    post = {} if args.mode == "simulation" else service_health()
    duration = round(time.time() - started, 2)

    checks = sequence["checks"]
    passed = all(
        [
            checks["approve_record_only"],
            checks["resume_executes"],
            checks["duplicate_resume_safe"],
            not checks["duplicate_execution_detected"],
            sequence["timeouts"] == 0,
            sequence["final_task_status"] == "succeeded",
            (args.mode == "simulation")
            or (
                pre.get("services_ok")
                and pre.get("gateway_ok")
                and post.get("services_ok")
                and post.get("gateway_ok")
            ),
        ]
    )

    summary = {
        "ok": passed,
        "mode": args.mode,
        "real_exec": args.real_exec,
        "duration_seconds": duration,
        "service_health_pre": pre,
        "service_health_post": post,
        "result": sequence,
    }

    if args.output:
        out_path = Path(args.output).resolve()
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(
            json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8"
        )

    if args.json:
        print(json.dumps(summary, ensure_ascii=True))
    else:
        print(json.dumps(summary, indent=2, sort_keys=True))

    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
