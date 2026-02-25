#!/usr/bin/env python3
"""Rule-based task router for v1 Pi/Ubuntu dispatch."""

# Permanent v1 policy: OpenCode has no direct Grok/ChatGPT API or browser access.
# If routing/execution needs latest external information or non-local certainty, emit
# the exact "=== EXTERNAL QUERY NEEDED ===" block and wait for Jacob's
# "=== EXTERNAL RESPONSE ===" before continuing.

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def load_policy(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    raw = path.read_text(encoding="utf-8").strip()
    if not raw:
        return {}
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        # TODO: REAL_INTEGRATION - replace with strict YAML parsing dependency.
        return {}


def classify(
    task_type: str, prompt: str, routing_policy: dict[str, Any]
) -> tuple[str, str]:
    task_type_l = task_type.lower().strip()
    prompt_l = prompt.lower()

    default_cfg = routing_policy.get("default", {})
    route_class = default_cfg.get("route_class", "PI_LIGHT")
    risk_level = default_cfg.get("risk_level", "low")

    overrides = routing_policy.get("task_type_overrides", {})
    if task_type_l in overrides:
        cfg = overrides[task_type_l]
        route_class = cfg.get("route_class", route_class)
        risk_level = cfg.get("risk_level", risk_level)

    rules = routing_policy.get("keyword_rules", {})
    heavy_keywords = [k.lower() for k in rules.get("ubuntu_heavy", [])]
    high_risk_keywords = [k.lower() for k in rules.get("high_risk", [])]

    if any(word in prompt_l for word in heavy_keywords):
        route_class = "UBUNTU_HEAVY"

    if any(word in prompt_l for word in high_risk_keywords):
        risk_level = "high"

    return route_class, risk_level


def requires_approval(
    risk_level: str, task_type: str, approval_policy: dict[str, Any]
) -> bool:
    if risk_level == "high":
        return True

    gates = approval_policy.get("gates", {})
    gate_by_task_type = {
        "deploy": "deploy_restart",
        "delete": "delete_files",
        "scheduler_change": "scheduler_change",
        "compliance_finalize": "compliance_finalize",
        "customer_outbound": "customer_outbound",
    }
    gate_name = gate_by_task_type.get(task_type.lower())
    if not gate_name:
        return False

    return bool(gates.get(gate_name, {}).get("require_human_approval", False))


def action_category_for_task(task_type: str, risk_level: str) -> str:
    gate_by_task_type = {
        "deploy": "deploy_restart",
        "delete": "delete_files",
        "scheduler_change": "scheduler_change",
        "compliance_finalize": "compliance_finalize",
        "customer_outbound": "customer_outbound",
    }
    task_type_l = task_type.lower().strip()
    if task_type_l in gate_by_task_type:
        return gate_by_task_type[task_type_l]
    if risk_level == "high":
        return "manual_review"
    return "none"


def run_registry(args: list[str], db_path: Path) -> dict[str, Any]:
    cmd = [
        sys.executable,
        str(repo_root() / "shared/task-registry/task_registry.py"),
        "--db",
        str(db_path),
        "--json",
        *args,
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or "registry command failed")
    return json.loads(proc.stdout)


def append_task_event(task_id: str, detail: str, db_path: Path) -> None:
    import sqlite3

    db_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "INSERT INTO task_events (task_id, event_type, detail, created_at) VALUES (?, ?, ?, ?)",
            (task_id, "router", detail, utc_now()),
        )
        conn.commit()


def run_command(cmd: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, capture_output=True, text=True)


def dispatch(
    route_class: str, task_type: str, prompt: str, task_id: str
) -> tuple[str, str]:
    if route_class == "UBUNTU_HEAVY":
        cmd = [
            str(repo_root() / "infra/opencode/wrappers/zdispatch.sh"),
            "--task-type",
            task_type,
            "--prompt",
            prompt,
        ]
        result = run_command(cmd)
        if result.returncode != 0:
            return "failed", f"dispatch_failed: {result.stderr.strip()}"
        remote_task_id = result.stdout.strip() or task_id
        return "running", f"dispatched_to_ubuntu task_id={remote_task_id}"

    # PI_LIGHT local stub execution
    task_dir = (
        Path(os.getenv("ZHC_STORAGE_ROOT", str(repo_root() / "storage")))
        / "tasks"
        / task_id
    )
    task_dir.mkdir(parents=True, exist_ok=True)
    (task_dir / "pi_worker_stub.log").write_text(
        "[STUB] PI_LIGHT worker executed\n"
        "TODO: REAL_INTEGRATION - bind actual Pi worker runtime\n",
        encoding="utf-8",
    )
    return "succeeded", "pi_light_stub_executed"


def route_task(task_type: str, prompt: str) -> dict[str, Any]:
    routing_policy = load_policy(
        Path(
            os.getenv(
                "ZHC_ROUTING_POLICY", str(repo_root() / "shared/policies/routing.yaml")
            )
        )
    )
    approval_policy = load_policy(
        Path(
            os.getenv(
                "ZHC_APPROVAL_POLICY",
                str(repo_root() / "shared/policies/approvals.yaml"),
            )
        )
    )
    db_path = Path(
        os.getenv("ZHC_TASK_DB", str(repo_root() / "storage/tasks/task_registry.db"))
    ).resolve()

    route_class, risk_level = classify(task_type, prompt, routing_policy)
    approval_required = requires_approval(risk_level, task_type, approval_policy)
    action_category = action_category_for_task(task_type, risk_level)

    task_id = f"task-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
    metadata = {
        "source": "router_v1",
        "approval_required": approval_required,
    }

    create_payload = run_registry(
        [
            "create",
            "--task-id",
            task_id,
            "--task-type",
            task_type,
            "--prompt",
            prompt,
            "--route-class",
            route_class,
            "--risk-level",
            risk_level,
            "--metadata",
            json.dumps(metadata),
        ]
        + (["--requires-approval"] if approval_required else []),
        db_path,
    )

    append_task_event(
        task_id, f"classification route={route_class} risk={risk_level}", db_path
    )

    if approval_required:
        run_registry(
            [
                "approval-request",
                "--task-id",
                task_id,
                "--action-category",
                action_category,
                "--requested-by",
                "router_v1",
                "--note",
                "created_by_router_block",
            ],
            db_path,
        )
        run_registry(
            [
                "update",
                "--task-id",
                task_id,
                "--status",
                "blocked",
                "--detail",
                "awaiting_human_approval",
            ],
            db_path,
        )
        append_task_event(task_id, "approval_required before execution", db_path)
        return {
            "task_id": task_id,
            "status": "blocked",
            "route_class": route_class,
            "risk_level": risk_level,
            "approval_required": True,
            "action_category": action_category,
            "message": "Task created and blocked pending approval",
        }

    dispatch_status, dispatch_detail = dispatch(route_class, task_type, prompt, task_id)
    run_registry(
        [
            "update",
            "--task-id",
            task_id,
            "--status",
            dispatch_status,
            "--detail",
            dispatch_detail,
        ],
        db_path,
    )
    append_task_event(task_id, dispatch_detail, db_path)

    return {
        "task_id": task_id,
        "status": dispatch_status,
        "route_class": route_class,
        "risk_level": risk_level,
        "approval_required": False,
        "message": dispatch_detail,
        "created": create_payload.get("created_at"),
    }


def approve_task(
    task_id: str,
    action_category: str,
    decided_by: str,
    note: str,
    decision: str,
) -> dict[str, Any]:
    db_path = Path(
        os.getenv("ZHC_TASK_DB", str(repo_root() / "storage/tasks/task_registry.db"))
    ).resolve()

    task = run_registry(["get", "--task-id", task_id], db_path)
    if task.get("status") != "blocked":
        raise ValueError(f"Task {task_id} must be blocked before approval decision")

    run_registry(
        [
            "approval-decide",
            "--task-id",
            task_id,
            "--action-category",
            action_category,
            "--decision",
            decision,
            "--decided-by",
            decided_by,
            "--note",
            note,
        ],
        db_path,
    )

    if decision == "rejected":
        run_registry(
            [
                "update",
                "--task-id",
                task_id,
                "--status",
                "cancelled",
                "--detail",
                f"approval_rejected action={action_category}",
            ],
            db_path,
        )
        append_task_event(
            task_id,
            f"approval_rejected action={action_category} by={decided_by}",
            db_path,
        )
        return {
            "task_id": task_id,
            "status": "cancelled",
            "action_category": action_category,
            "decision": decision,
            "message": "Task cancelled due to rejected approval",
        }

    dispatch_status, dispatch_detail = dispatch(
        task["route_class"], task["task_type"], task["prompt"], task_id
    )
    run_registry(
        [
            "update",
            "--task-id",
            task_id,
            "--status",
            dispatch_status,
            "--detail",
            dispatch_detail,
        ],
        db_path,
    )
    append_task_event(
        task_id,
        (
            "resumed_after_approval "
            f"action={action_category} decision={decision} by={decided_by}; {dispatch_detail}"
        ),
        db_path,
    )

    return {
        "task_id": task_id,
        "status": dispatch_status,
        "action_category": action_category,
        "decision": decision,
        "message": dispatch_detail,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="ZHC-Nova task router")
    sub = parser.add_subparsers(dest="command", required=True)

    route_parser = sub.add_parser("route", help="Classify and dispatch a task")
    route_parser.add_argument("--task-type", required=True)
    route_parser.add_argument("--prompt", required=True)

    classify_parser = sub.add_parser("classify", help="Classify task without dispatch")
    classify_parser.add_argument("--task-type", required=True)
    classify_parser.add_argument("--prompt", required=True)

    approve_parser = sub.add_parser(
        "approve", help="Record approval decision and resume blocked task"
    )
    approve_parser.add_argument("--task-id", required=True)
    approve_parser.add_argument("--action-category", required=True)
    approve_parser.add_argument("--decided-by", required=True)
    approve_parser.add_argument("--note", default="")
    approve_parser.add_argument(
        "--decision", choices=["approved", "rejected"], default="approved"
    )

    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        routing_policy = load_policy(
            Path(
                os.getenv(
                    "ZHC_ROUTING_POLICY",
                    str(repo_root() / "shared/policies/routing.yaml"),
                )
            )
        )
        approval_policy = load_policy(
            Path(
                os.getenv(
                    "ZHC_APPROVAL_POLICY",
                    str(repo_root() / "shared/policies/approvals.yaml"),
                )
            )
        )

        if args.command == "classify":
            route_class, risk_level = classify(
                args.task_type, args.prompt, routing_policy
            )
            out = {
                "route_class": route_class,
                "risk_level": risk_level,
                "approval_required": requires_approval(
                    risk_level, args.task_type, approval_policy
                ),
            }
            print(json.dumps(out, indent=2, sort_keys=True))
            return 0

        if args.command == "route":
            result = route_task(args.task_type, args.prompt)
            print(json.dumps(result, indent=2, sort_keys=True))
            return 0

        if args.command == "approve":
            result = approve_task(
                task_id=args.task_id,
                action_category=args.action_category,
                decided_by=args.decided_by,
                note=args.note,
                decision=args.decision,
            )
            print(json.dumps(result, indent=2, sort_keys=True))
            return 0

        raise ValueError("Unknown command")
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
