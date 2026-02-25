#!/usr/bin/env python3
"""Telegram long-polling control plane for ZHC-Nova."""

from __future__ import annotations

import argparse
import atexit
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def storage_root() -> Path:
    return Path(os.getenv("ZHC_STORAGE_ROOT", str(repo_root() / "storage"))).resolve()


def offset_file_path() -> Path:
    path = storage_root() / "memory" / "telegram_offset.txt"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def allowed_chat_ids() -> set[int]:
    raw = os.getenv("TELEGRAM_ALLOWED_CHAT_IDS", "").strip()
    if not raw:
        return set()
    ids: set[int] = set()
    for chunk in raw.split(","):
        val = chunk.strip()
        if not val:
            continue
        try:
            ids.add(int(val))
        except ValueError:
            continue
    return ids


@dataclass
class Config:
    token: str
    api_base: str
    timeout_seconds: int
    poll_interval_seconds: float
    allowed_ids: set[int]
    audit_log: Path
    offset_file: Path
    lock_file: Path
    require_allowlist: bool
    command_timeout_seconds: int
    rate_limit_per_minute: int
    rate_limit_burst: int
    max_backoff_seconds: float


def load_config() -> Config:
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    if not token or token.startswith("TODO_"):
        raise ValueError("TELEGRAM_BOT_TOKEN is required")

    root = storage_root()
    memory_dir = root / "memory"
    memory_dir.mkdir(parents=True, exist_ok=True)

    require_allowlist = os.getenv("TELEGRAM_REQUIRE_ALLOWLIST", "1").strip() == "1"
    parsed_allowed = allowed_chat_ids()
    if require_allowlist and not parsed_allowed:
        raise ValueError(
            "TELEGRAM_ALLOWED_CHAT_IDS is required when TELEGRAM_REQUIRE_ALLOWLIST=1"
        )

    return Config(
        token=token,
        api_base=f"https://api.telegram.org/bot{token}",
        timeout_seconds=int(os.getenv("TELEGRAM_POLL_TIMEOUT_SECONDS", "30")),
        poll_interval_seconds=float(os.getenv("TELEGRAM_POLL_INTERVAL_SECONDS", "1.0")),
        allowed_ids=parsed_allowed,
        audit_log=memory_dir / "telegram_command_audit.jsonl",
        offset_file=offset_file_path(),
        lock_file=memory_dir / "telegram_longpoll.lock",
        require_allowlist=require_allowlist,
        command_timeout_seconds=int(
            os.getenv("TELEGRAM_COMMAND_TIMEOUT_SECONDS", "45")
        ),
        rate_limit_per_minute=int(os.getenv("TELEGRAM_RATE_LIMIT_PER_MINUTE", "20")),
        rate_limit_burst=int(os.getenv("TELEGRAM_RATE_LIMIT_BURST", "5")),
        max_backoff_seconds=float(os.getenv("TELEGRAM_MAX_BACKOFF_SECONDS", "60")),
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Telegram long-polling control runtime"
    )
    parser.add_argument(
        "--show-offset",
        action="store_true",
        help="Print current offset value and exit",
    )
    parser.add_argument(
        "--reset-offset",
        action="store_true",
        help="Reset offset to zero and exit",
    )
    return parser.parse_args()


def acquire_lock(lock_path: Path) -> int:
    flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY
    try:
        fd = os.open(str(lock_path), flags)
    except FileExistsError as exc:
        raise RuntimeError(f"lock_exists: {lock_path}") from exc

    os.write(fd, str(os.getpid()).encode("utf-8"))
    os.fsync(fd)

    def _cleanup() -> None:
        try:
            os.close(fd)
        except OSError:
            pass
        try:
            lock_path.unlink(missing_ok=True)
        except OSError:
            pass

    atexit.register(_cleanup)
    return fd


def telegram_api(
    config: Config, method: str, payload: dict[str, Any]
) -> dict[str, Any]:
    url = f"{config.api_base}/{method}"
    data = urllib.parse.urlencode(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST")
    try:
        with urllib.request.urlopen(
            req, timeout=config.timeout_seconds + 5
        ) as response:
            out = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"telegram_api_error method={method}: {exc}") from exc

    if not out.get("ok"):
        raise RuntimeError(f"telegram_api_not_ok method={method}: {out}")
    return out


def send_message(config: Config, chat_id: int, text: str) -> None:
    telegram_api(
        config,
        "sendMessage",
        {
            "chat_id": str(chat_id),
            "text": text[:4000],
            "disable_web_page_preview": "true",
        },
    )


def read_offset(path: Path) -> int:
    if not path.exists():
        return 0
    try:
        return int(path.read_text(encoding="utf-8").strip() or "0")
    except ValueError:
        return 0


def write_offset(path: Path, offset: int) -> None:
    path.write_text(str(offset), encoding="utf-8")


def append_audit(path: Path, payload: dict[str, Any]) -> None:
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(payload, sort_keys=True) + "\n")


def allow_message(
    buckets: dict[int, list[float]], chat_id: int, config: Config, now_ts: float
) -> bool:
    if config.rate_limit_per_minute <= 0:
        return True
    entries = buckets.get(chat_id, [])
    cutoff = now_ts - 60.0
    entries = [ts for ts in entries if ts >= cutoff]

    minute_count = len(entries)
    if minute_count >= config.rate_limit_per_minute:
        buckets[chat_id] = entries
        return False

    burst_window = 5.0
    burst_count = len([ts for ts in entries if ts >= now_ts - burst_window])
    if config.rate_limit_burst > 0 and burst_count >= config.rate_limit_burst:
        buckets[chat_id] = entries
        return False

    entries.append(now_ts)
    buckets[chat_id] = entries
    return True


def run_json_command(cmd: list[str], timeout_seconds: int) -> dict[str, Any]:
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=max(1, timeout_seconds),
        )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(f"command_timeout after {timeout_seconds}s") from exc
    if proc.returncode != 0:
        raise RuntimeError(
            proc.stderr.strip() or proc.stdout.strip() or "command failed"
        )
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"invalid_json_output: {proc.stdout[:200]}") from exc


def router_cmd(args: list[str], timeout_seconds: int) -> dict[str, Any]:
    cmd = [sys.executable, str(repo_root() / "services/task-router/router.py"), *args]
    return run_json_command(cmd, timeout_seconds)


def registry_cmd(args: list[str], timeout_seconds: int) -> Any:
    cmd = [
        sys.executable,
        str(repo_root() / "shared/task-registry/task_registry.py"),
        "--json",
        *args,
    ]
    return run_json_command(cmd, timeout_seconds)


def user_label(message: dict[str, Any]) -> str:
    sender = message.get("from", {})
    username = sender.get("username")
    if username:
        return f"@{username}"
    return str(sender.get("id", "unknown"))


def parse_command(text: str) -> tuple[str, list[str]]:
    parts = text.strip().split()
    if not parts:
        return "", []
    cmd = parts[0].split("@", 1)[0].lower()
    return cmd, parts[1:]


def format_task_short(task: dict[str, Any]) -> str:
    return (
        f"{task.get('task_id')} | {task.get('status')} | {task.get('route_class')} | "
        f"type={task.get('task_type')} | risk={task.get('risk_level')}"
    )


def help_text() -> str:
    return (
        "ZHC-Nova commands:\n"
        "/start - show quick start\n"
        "/help - show command help\n"
        "/newtask <task_type> <prompt>\n"
        "/status <task_id>\n"
        "/list [limit]\n"
        "/approve <task_id> <action_category> [note]\n"
        "/plan <task_id> <summary>\n"
        "/review <task_id> <pass|fail> [reason_code_if_fail] [notes]\n"
        "/resume <task_id>\n"
        "/stop <task_id>\n"
        "/board"
    )


def handle_command(
    config: Config, message: dict[str, Any]
) -> tuple[str, dict[str, Any]]:
    text = str(message.get("text", ""))
    cmd, args = parse_command(text)
    actor = user_label(message)

    if cmd in {"/start", "/help"}:
        return help_text(), {"command": cmd, "ok": True}

    if cmd == "/newtask":
        if len(args) < 2:
            raise ValueError("Usage: /newtask <task_type> <prompt>")
        task_type = args[0]
        prompt = " ".join(args[1:])
        result = router_cmd(
            ["route", "--task-type", task_type, "--prompt", prompt],
            config.command_timeout_seconds,
        )
        msg = (
            f"Task: {result.get('task_id')}\n"
            f"Status: {result.get('status')}\n"
            f"Route: {result.get('route_class')}\n"
            f"Policy: {result.get('policy_status', 'n/a')} ({result.get('policy_reason', 'n/a')})"
        )
        return msg, result

    if cmd == "/status":
        if len(args) != 1:
            raise ValueError("Usage: /status <task_id>")
        task = registry_cmd(
            ["get", "--task-id", args[0]], config.command_timeout_seconds
        )
        approvals = task.get("approvals", [])
        approval_status = approvals[-1]["status"] if approvals else "none"
        msg = (
            f"{format_task_short(task)}\n"
            f"approval={approval_status}\n"
            f"events={len(task.get('events', []))}"
        )
        return msg, task

    if cmd == "/list":
        limit = 10
        if args:
            limit = max(1, min(50, int(args[0])))
        tasks = registry_cmd(
            ["list", "--limit", str(limit)], config.command_timeout_seconds
        )
        if not isinstance(tasks, list):
            raise RuntimeError("invalid list response from task registry")
        if not tasks:
            return "No tasks found", {"tasks": []}
        lines = [format_task_short(task) for task in tasks]
        return "\n".join(lines[:20]), {"tasks": tasks}

    if cmd == "/approve":
        if len(args) < 2:
            raise ValueError("Usage: /approve <task_id> <action_category> [note]")
        task_id = args[0]
        action_category = args[1]
        note = " ".join(args[2:]) if len(args) > 2 else "approved via telegram"
        result = router_cmd(
            [
                "approve",
                "--task-id",
                task_id,
                "--action-category",
                action_category,
                "--decided-by",
                actor,
                "--note",
                note,
                "--defer-dispatch",
            ],
            config.command_timeout_seconds,
        )
        return (
            f"Approved {task_id}: {result.get('message')}. Use /resume {task_id}",
            result,
        )

    if cmd == "/plan":
        if len(args) < 2:
            raise ValueError("Usage: /plan <task_id> <summary>")
        task_id = args[0]
        summary = " ".join(args[1:])
        result = router_cmd(
            [
                "record-plan",
                "--task-id",
                task_id,
                "--author",
                actor,
                "--summary",
                summary,
            ],
            config.command_timeout_seconds,
        )
        return f"Planner artifact saved for {task_id}", result

    if cmd == "/review":
        if len(args) < 2:
            raise ValueError(
                "Usage: /review <task_id> <pass|fail> [reason_code_if_fail] [notes]"
            )
        task_id = args[0]
        verdict = args[1].lower()
        reason_code = ""
        notes_start_idx = 2
        if verdict == "fail":
            if len(args) < 3:
                raise ValueError(
                    "Fail review requires reason code: policy_conflict|missing_tests|insufficient_plan|high_risk_unmitigated|artifact_incomplete|other"
                )
            reason_code = args[2].lower()
            notes_start_idx = 3
        notes = " ".join(args[notes_start_idx:]) if len(args) > notes_start_idx else ""

        if verdict == "pass":
            checklist = {
                "policy_safety": True,
                "correctness": True,
                "tests": True,
                "rollback": True,
                "approval_constraints": True,
            }
        else:
            checklist = {
                "policy_safety": reason_code
                not in {"policy_conflict", "high_risk_unmitigated"},
                "correctness": reason_code != "insufficient_plan",
                "tests": reason_code != "missing_tests",
                "rollback": reason_code != "artifact_incomplete",
                "approval_constraints": reason_code != "policy_conflict",
            }

        result = router_cmd(
            [
                "record-review",
                "--task-id",
                task_id,
                "--reviewer",
                actor,
                "--verdict",
                verdict,
                "--reason-code",
                reason_code,
                "--checklist-json",
                json.dumps(checklist),
                "--notes",
                notes,
            ],
            config.command_timeout_seconds,
        )
        if verdict == "fail":
            return (
                (
                    f"Review recorded for {task_id}: fail ({reason_code}). "
                    f"{result.get('next_action', 'Fix issues then submit /review pass.')}"
                ),
                result,
            )
        return (
            f"Review recorded for {task_id}: pass. {result.get('next_action', '')}".strip(),
            result,
        )

    if cmd == "/resume":
        if len(args) != 1:
            raise ValueError("Usage: /resume <task_id>")
        resume_timeout = max(
            config.command_timeout_seconds,
            int(os.getenv("TELEGRAM_RESUME_TIMEOUT_SECONDS", "600")),
        )
        result = router_cmd(
            ["resume", "--task-id", args[0], "--requested-by", actor],
            resume_timeout,
        )
        return (
            f"Resume {args[0]}: {result.get('status')} ({result.get('message')})",
            result,
        )

    if cmd == "/stop":
        if len(args) != 1:
            raise ValueError("Usage: /stop <task_id>")
        task = registry_cmd(
            ["get", "--task-id", args[0]], config.command_timeout_seconds
        )
        if task.get("status") in {"succeeded", "failed", "cancelled"}:
            return f"Task {args[0]} already terminal: {task.get('status')}", task
        result = registry_cmd(
            [
                "update",
                "--task-id",
                args[0],
                "--status",
                "cancelled",
                "--detail",
                f"telegram_stop_requested by={actor}",
            ],
            config.command_timeout_seconds,
        )
        return f"Task {args[0]} cancelled", result

    if cmd == "/board":
        tasks = registry_cmd(["list", "--limit", "50"], config.command_timeout_seconds)
        if not isinstance(tasks, list):
            raise RuntimeError("invalid list response from task registry")
        counts: dict[str, int] = {}
        for task in tasks:
            status = task.get("status", "unknown")
            counts[status] = counts.get(status, 0) + 1
        msg = (
            f"Board\n"
            f"running={counts.get('running', 0)} blocked={counts.get('blocked', 0)} "
            f"failed={counts.get('failed', 0)} pending={counts.get('pending', 0)}"
        )
        return msg, {"counts": counts}

    raise ValueError(
        "Unknown command. Use /newtask, /status, /list, /approve, /plan, /review, /resume, /stop, /board"
    )


def process_update(
    config: Config, update: dict[str, Any], rate_buckets: dict[int, list[float]]
) -> None:
    update_id = int(update.get("update_id", 0))
    message = update.get("message") or update.get("edited_message")
    if not isinstance(message, dict):
        return

    chat = message.get("chat", {})
    chat_id = int(chat.get("id", 0))
    text = str(message.get("text", ""))
    actor = user_label(message)

    audit_payload: dict[str, Any] = {
        "ts": utc_now(),
        "update_id": update_id,
        "chat_id": chat_id,
        "actor": actor,
        "text": text,
    }

    if not allow_message(rate_buckets, chat_id, config, time.time()):
        audit_payload["status"] = "rate_limited"
        append_audit(config.audit_log, audit_payload)
        return

    if config.allowed_ids and chat_id not in config.allowed_ids:
        audit_payload["status"] = "unauthorized"
        append_audit(config.audit_log, audit_payload)
        send_message(config, chat_id, "Unauthorized chat_id for this bot")
        return

    if not text.startswith("/"):
        audit_payload["status"] = "ignored_non_command"
        append_audit(config.audit_log, audit_payload)
        return

    try:
        response_text, result = handle_command(config, message)
        audit_payload["status"] = "ok"
        audit_payload["result"] = result
        append_audit(config.audit_log, audit_payload)
        send_message(config, chat_id, response_text)
    except Exception as exc:
        err = str(exc)
        audit_payload["status"] = (
            "command_timeout" if "command_timeout" in err else "error"
        )
        audit_payload["error"] = str(exc)
        append_audit(config.audit_log, audit_payload)
        send_message(config, chat_id, f"Error: {exc}")


def poll_loop(config: Config) -> None:
    offset = read_offset(config.offset_file)
    error_count = 0
    backoff_seconds = max(config.poll_interval_seconds, 0.2)
    rate_buckets: dict[int, list[float]] = {}
    while True:
        try:
            result = telegram_api(
                config,
                "getUpdates",
                {
                    "timeout": str(config.timeout_seconds),
                    "offset": str(offset),
                    "allowed_updates": json.dumps(["message", "edited_message"]),
                },
            )
            updates = result.get("result", [])
            for update in updates:
                process_update(config, update, rate_buckets)
                offset = int(update.get("update_id", offset)) + 1
                write_offset(config.offset_file, offset)
            error_count = 0
            backoff_seconds = max(config.poll_interval_seconds, 0.2)
        except Exception as exc:
            error_count += 1
            append_audit(
                config.audit_log,
                {
                    "ts": utc_now(),
                    "status": "poll_error",
                    "error_count": error_count,
                    "backoff_seconds": round(backoff_seconds, 2),
                    "error": str(exc),
                },
            )
            time.sleep(backoff_seconds)
            backoff_seconds = min(
                max(config.poll_interval_seconds, 0.2, backoff_seconds * 2),
                max(config.max_backoff_seconds, 1.0),
            )
            continue

        time.sleep(config.poll_interval_seconds)


def main() -> int:
    try:
        args = parse_args()

        if args.show_offset:
            print(read_offset(offset_file_path()))
            return 0

        if args.reset_offset:
            write_offset(offset_file_path(), 0)
            print("offset reset to 0")
            return 0

        config = load_config()

        acquire_lock(config.lock_file)
        append_audit(
            config.audit_log,
            {
                "ts": utc_now(),
                "status": "startup",
                "allowed_chat_ids_count": len(config.allowed_ids),
                "command_timeout_seconds": config.command_timeout_seconds,
            },
        )
        poll_loop(config)
        return 0
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
