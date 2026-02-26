#!/usr/bin/env python3
"""CP-008 chaos-lite reliability suite for ZHC-Nova.

Scenarios:
1) Duplicate Telegram update replay
2) Lease recovery after simulated restart/expiry
3) Forced transient dispatch failure with retry recovery
4) Success-then-reporting-failure replay safety
"""

from __future__ import annotations

import argparse
import json
import os
import runpy
import sqlite3
import subprocess
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
BOT_PATH = ROOT / "services/telegram-control/bot_longpoll.py"
REGISTRY_PATH = ROOT / "shared/task-registry/task_registry.py"
ROUTER_PATH = ROOT / "services/task-router/router.py"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run CP-008 chaos-lite suite")
    parser.add_argument(
        "--output",
        default=str(ROOT / "storage/memory/chaos_lite_latest.json"),
        help="JSON report output path",
    )
    parser.add_argument(
        "--env-file",
        default=str(ROOT / ".env"),
        help="Env file to load before running",
    )
    parser.add_argument("--json", action="store_true", help="Print compact JSON")
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


def run_shell(
    cmd: list[str], env: dict[str, str] | None = None, timeout: int = 120
) -> dict[str, Any]:
    proc = subprocess.run(
        cmd,
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    return {
        "returncode": proc.returncode,
        "stdout": proc.stdout.strip(),
        "stderr": proc.stderr.strip(),
    }


def run_json(
    cmd: list[str], env: dict[str, str] | None = None, timeout: int = 120
) -> dict[str, Any]:
    out = run_shell(cmd, env=env, timeout=timeout)
    if out["returncode"] != 0:
        raise RuntimeError(out["stderr"] or out["stdout"] or "command failed")
    try:
        return json.loads(out["stdout"])
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"invalid_json: {out['stdout'][:200]}") from exc


def db_path() -> Path:
    return Path(
        os.getenv("ZHC_TASK_DB", str(ROOT / "storage/tasks/task_registry.db"))
    ).resolve()


def count_tasks() -> int:
    with sqlite3.connect(db_path()) as conn:
        row = conn.execute("SELECT COUNT(*) FROM tasks").fetchone()
        return int(row[0] if row else 0)


def count_tasks_for_trace(trace_id: str) -> int:
    pattern = f'%"trace_id":"{trace_id}"%'
    with sqlite3.connect(db_path()) as conn:
        row = conn.execute(
            "SELECT COUNT(*) FROM tasks WHERE metadata_json LIKE ?",
            (pattern,),
        ).fetchone()
        return int(row[0] if row else 0)


def read_audit_entries(update_id: int) -> list[dict[str, Any]]:
    log_path = ROOT / "storage/memory/telegram_command_audit.jsonl"
    if not log_path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in log_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if int(payload.get("update_id", -1)) == update_id:
            rows.append(payload)
    return rows


def service_health() -> dict[str, Any]:
    svc = run_shell(
        [
            "systemctl",
            "--user",
            "is-active",
            "zeroclaw-gateway.service",
            "zhc-telegram-control.service",
        ],
        timeout=20,
    )
    curl = run_shell(["curl", "-sS", "http://127.0.0.1:3131/health"], timeout=20)
    payload: dict[str, Any] = {}
    if curl["returncode"] == 0 and curl["stdout"]:
        try:
            payload = json.loads(curl["stdout"])
        except json.JSONDecodeError:
            payload = {"raw": curl["stdout"]}
    states = [x for x in svc["stdout"].splitlines() if x.strip()]
    return {
        "services_ok": svc["returncode"] == 0 and all(s == "active" for s in states),
        "service_states": states,
        "gateway_ok": payload.get("status") == "ok",
        "gateway": payload,
    }


def load_bot_module() -> dict[str, Any]:
    mod = runpy.run_path(str(BOT_PATH))
    return mod


def scenario_duplicate_update_replay(base_uid: int) -> dict[str, Any]:
    mod = load_bot_module()
    cfg = mod["load_config"]()
    process_update = mod["process_update"]
    process_update.__globals__["send_message"] = lambda config, chat_id, text: None

    chat_id = sorted(cfg.allowed_ids)[0]
    update_id = base_uid + 1
    update = {
        "update_id": update_id,
        "message": {
            "chat": {"id": chat_id},
            "from": {"id": chat_id, "username": "chaos_replay"},
            "text": "/newtask ping chaos duplicate replay",
        },
    }

    trace_id = f"tg-{update_id}"

    before = count_tasks_for_trace(trace_id)
    process_update(cfg, update, rate_buckets={})
    process_update(cfg, update, rate_buckets={})
    after = count_tasks_for_trace(trace_id)

    rows = read_audit_entries(update_id)
    statuses = [str(r.get("status", "")) for r in rows]
    passed = (
        (after - before == 1)
        and ("ok" in statuses)
        and ("idempotent_replay" in statuses)
    )
    return {
        "name": "duplicate_update_replay",
        "passed": passed,
        "before_trace_tasks": before,
        "after_trace_tasks": after,
        "statuses": statuses,
        "update_id": update_id,
        "trace_id": trace_id,
    }


def scenario_restart_during_running_recovery() -> dict[str, Any]:
    reg = runpy.run_path(str(REGISTRY_PATH))
    task_id = f"task-chaos-lease-{int(time.time())}"
    reg["create_task"](
        db_path(),
        task_id,
        "code_refactor",
        "chaos lease recovery",
        "UBUNTU_HEAVY",
        "blocked",
        True,
        "medium",
        None,
        {},
    )
    reg["enqueue_dispatch_lease"](db_path(), task_id, "owner-a", 1)
    reg["claim_dispatch_lease"](db_path(), task_id, "owner-a", 1)
    time.sleep(1.2)
    reg["reconcile_dispatch_leases"](db_path(), "owner-b")
    claim = reg["claim_dispatch_lease"](db_path(), task_id, "owner-b", 120)
    lease = reg["get_dispatch_lease"](db_path(), task_id)["lease"]

    passed = (
        bool(claim.get("claimed"))
        and str(lease.get("owner_id")) == "owner-b"
        and int(lease.get("attempt_count", 0)) >= 2
    )
    return {
        "name": "restart_during_running_recovery",
        "passed": passed,
        "task_id": task_id,
        "lease": lease,
        "claim": claim,
    }


def scenario_forced_dispatch_retry() -> dict[str, Any]:
    now = int(time.time())
    tmp_dir = Path(tempfile.gettempdir())
    wrapper = tmp_dir / f"zhc_chaos_retry_cmd_{now}.sh"
    counter = tmp_dir / f"zhc_chaos_counter_{now}.txt"
    wrapper.write_text(
        "#!/usr/bin/env bash\n"
        "set -euo pipefail\n"
        f'COUNTER="{counter}"\n'
        "n=0\n"
        'if [[ -f "$COUNTER" ]]; then n=$(cat "$COUNTER"); fi\n'
        "n=$((n+1))\n"
        'printf \'%s\' "$n" > "$COUNTER"\n'
        "if [[ $n -eq 1 ]]; then\n"
        "  echo 'dispatch timeout simulated' >&2\n"
        "  exit 1\n"
        "fi\n"
        "echo READY\n"
        "exit 0\n",
        encoding="utf-8",
    )
    wrapper.chmod(0o755)

    router = runpy.run_path(str(ROUTER_PATH))
    prev_retry_max = os.environ.get("ZHC_DISPATCH_RETRY_MAX")
    prev_timeout = os.environ.get("ZHC_DISPATCH_TIMEOUT_SECONDS")
    os.environ["ZHC_DISPATCH_RETRY_MAX"] = "1"
    os.environ["ZHC_DISPATCH_TIMEOUT_SECONDS"] = "5"
    proc = router["run_command"]([str(wrapper)])
    if prev_retry_max is None:
        os.environ.pop("ZHC_DISPATCH_RETRY_MAX", None)
    else:
        os.environ["ZHC_DISPATCH_RETRY_MAX"] = prev_retry_max
    if prev_timeout is None:
        os.environ.pop("ZHC_DISPATCH_TIMEOUT_SECONDS", None)
    else:
        os.environ["ZHC_DISPATCH_TIMEOUT_SECONDS"] = prev_timeout

    attempts = 0
    if counter.exists():
        try:
            attempts = int(counter.read_text(encoding="utf-8").strip() or "0")
        except ValueError:
            attempts = 0
    passed = proc.returncode == 0 and attempts >= 2 and "READY" in str(proc.stdout)
    return {
        "name": "forced_dispatch_retry",
        "passed": passed,
        "command_returncode": int(proc.returncode),
        "stdout": str(proc.stdout).strip(),
        "stderr": str(proc.stderr).strip(),
        "wrapper_attempts": attempts,
    }


def scenario_success_then_reporting_failure(base_uid: int) -> dict[str, Any]:
    mod = load_bot_module()
    cfg = mod["load_config"]()
    process_update = mod["process_update"]

    state = {"calls": 0}

    def flaky_send_message(config: Any, chat_id: int, text: str) -> None:
        state["calls"] += 1
        if state["calls"] == 1:
            raise RuntimeError("reporting_sink_down")
        return None

    process_update.__globals__["send_message"] = flaky_send_message

    chat_id = sorted(cfg.allowed_ids)[0]
    update_id = base_uid + 2
    update = {
        "update_id": update_id,
        "message": {
            "chat": {"id": chat_id},
            "from": {"id": chat_id, "username": "chaos_report"},
            "text": "/newtask ping chaos reporting failure",
        },
    }

    trace_id = f"tg-{update_id}"

    before = count_tasks_for_trace(trace_id)
    process_update(cfg, update, rate_buckets={})
    # replay with non-failing send function
    process_update.__globals__["send_message"] = lambda config, cid, text: None
    process_update(cfg, update, rate_buckets={})
    after = count_tasks_for_trace(trace_id)

    rows = read_audit_entries(update_id)
    statuses = [str(r.get("status", "")) for r in rows]
    passed = (
        (after - before == 1)
        and ("error" in statuses)
        and ("idempotent_replay" in statuses)
    )
    return {
        "name": "success_then_reporting_failure",
        "passed": passed,
        "before_trace_tasks": before,
        "after_trace_tasks": after,
        "statuses": statuses,
        "update_id": update_id,
        "trace_id": trace_id,
    }


def main() -> int:
    args = parse_args()
    load_env_file(Path(args.env_file).resolve())

    started = time.time()
    base_uid = 920000000 + int(started) % 1000000
    scenarios: list[dict[str, Any]] = []

    pre = service_health()
    scenarios.append(scenario_duplicate_update_replay(base_uid))
    scenarios.append(scenario_restart_during_running_recovery())
    scenarios.append(scenario_forced_dispatch_retry())
    scenarios.append(scenario_success_then_reporting_failure(base_uid))
    post = service_health()

    failed = [s for s in scenarios if not s.get("passed")]
    report = {
        "ok": len(failed) == 0,
        "started_at": utc_now(),
        "duration_seconds": round(time.time() - started, 2),
        "pre_health": pre,
        "post_health": post,
        "scenarios": scenarios,
        "failed_scenarios": [s.get("name") for s in failed],
    }

    out_path = Path(args.output).resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")

    if args.json:
        print(json.dumps(report, ensure_ascii=True))
    else:
        print(json.dumps(report, indent=2, sort_keys=True))

    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
