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
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


VALID_AUTONOMY_MODES = {"readonly", "supervised", "auto"}


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


def autonomy_mode() -> str:
    mode = os.getenv("ZHC_AUTONOMY_MODE", "supervised").strip().lower()
    if mode not in VALID_AUTONOMY_MODES:
        allowed = ", ".join(sorted(VALID_AUTONOMY_MODES))
        raise ValueError(f"Invalid ZHC_AUTONOMY_MODE '{mode}'. Allowed: {allowed}")
    return mode


def evaluate_execution_policy(
    task_type: str,
    prompt: str,
    route_class: str,
    mode: str,
    execution_policy: dict[str, Any],
) -> tuple[bool, str]:
    if mode == "readonly":
        return False, "readonly_mode"

    default_cfg = execution_policy.get("default", {})
    enforcement = str(default_cfg.get("enforcement", "strict")).lower().strip()
    env_enforcement = os.getenv("ZHC_POLICY_ENFORCEMENT", "").strip().lower()
    if env_enforcement:
        enforcement = env_enforcement
    if enforcement not in {"strict", "warn"}:
        enforcement = "strict"

    allowlists = execution_policy.get("allowlists", {})
    if route_class == "PI_LIGHT":
        allowed_task_types = {
            str(v).lower() for v in allowlists.get("pi_light_task_types", [])
        }
    else:
        allowed_task_types = {
            str(v).lower() for v in allowlists.get("ubuntu_heavy_task_types", [])
        }

    task_type_l = task_type.lower().strip()
    if allowed_task_types and task_type_l not in allowed_task_types:
        if enforcement == "strict":
            return False, "unknown_task_type"

    prompt_l = prompt.lower()
    deny_rules = execution_policy.get("deny_rules", {})
    blocked_keywords = [
        str(v).lower() for v in deny_rules.get("blocked_prompt_keywords", [])
    ]
    if any(keyword and keyword in prompt_l for keyword in blocked_keywords):
        if enforcement == "strict":
            return False, "blocked_prompt_keyword"

    blocked_paths = [str(v) for v in deny_rules.get("blocked_path_patterns", [])]
    if any(path and path in prompt for path in blocked_paths):
        if enforcement == "strict":
            return False, "blocked_path_pattern"

    return True, "allowed"


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


def merge_task_metadata(
    task_id: str, db_path: Path, patch: dict[str, Any], detail: str
) -> None:
    run_registry(
        [
            "metadata-merge",
            "--task-id",
            task_id,
            "--metadata",
            json.dumps(patch),
            "--detail",
            detail,
        ],
        db_path,
    )


def model_hint_for_task(task_type: str) -> tuple[str, str]:
    default_provider = os.getenv("ZHC_DEFAULT_PROVIDER", "openai")
    default_model = os.getenv("ZHC_DEFAULT_MODEL", "codex")
    fallback_provider = os.getenv("ZHC_FALLBACK_PROVIDER", "openrouter")
    fallback_model = os.getenv("ZHC_FALLBACK_MODEL", "planner-model")
    if task_type in {"code_review", "plan", "summary"}:
        return fallback_provider, fallback_model
    return default_provider, default_model


def estimate_cost_usd(task_type: str, duration_ms: int, route_class: str) -> float:
    if route_class == "PI_LIGHT":
        return round(max(duration_ms, 1) * 0.000002, 6)
    base = 0.01 if task_type in {"code_refactor", "build_fix"} else 0.006
    return round(base + max(duration_ms, 1) * 0.000004, 6)


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


def task_dir(task_id: str) -> Path:
    return (
        Path(os.getenv("ZHC_STORAGE_ROOT", str(repo_root() / "storage")))
        / "tasks"
        / task_id
    )


def planner_artifact_path(task_id: str) -> Path:
    return task_dir(task_id) / "artifacts" / "planner.md"


def reviewer_artifact_path(task_id: str) -> Path:
    return task_dir(task_id) / "artifacts" / "reviewer.json"


def review_gate_status(task_id: str) -> dict[str, Any]:
    planner_path = planner_artifact_path(task_id)
    reviewer_path = reviewer_artifact_path(task_id)

    planner_present = planner_path.exists()
    reviewer_present = reviewer_path.exists()
    reviewer_passed = False
    reviewer_verdict = "missing"

    if reviewer_present:
        try:
            payload = json.loads(reviewer_path.read_text(encoding="utf-8"))
            reviewer_verdict = str(payload.get("verdict", "missing")).lower().strip()
            reviewer_passed = reviewer_verdict == "pass"
        except json.JSONDecodeError:
            reviewer_verdict = "invalid"
            reviewer_passed = False

    gate_passed = planner_present and reviewer_present and reviewer_passed
    return {
        "planner_present": planner_present,
        "reviewer_present": reviewer_present,
        "reviewer_verdict": reviewer_verdict,
        "gate_passed": gate_passed,
    }


def write_planner_artifact(task_id: str, author: str, summary: str) -> Path:
    path = planner_artifact_path(task_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(
            [
                f"author: {author}",
                f"created_at: {utc_now()}",
                "",
                "plan:",
                summary,
                "",
            ]
        ),
        encoding="utf-8",
    )
    return path


def write_reviewer_artifact(
    task_id: str,
    reviewer: str,
    verdict: str,
    notes: str,
) -> Path:
    path = reviewer_artifact_path(task_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "reviewer": reviewer,
        "verdict": verdict,
        "notes": notes,
        "created_at": utc_now(),
    }
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return path


def dispatch(
    route_class: str,
    task_type: str,
    prompt: str,
    task_id: str,
    mode: str,
) -> tuple[str, str]:
    if mode == "readonly":
        return "blocked", "readonly_mode_execution_disabled"

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
    current_task_dir = task_dir(task_id)
    current_task_dir.mkdir(parents=True, exist_ok=True)
    (current_task_dir / "pi_worker_stub.log").write_text(
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
    execution_policy = load_policy(
        Path(
            os.getenv(
                "ZHC_EXECUTION_POLICY",
                str(repo_root() / "shared/policies/execution_policy.yaml"),
            )
        )
    )
    db_path = Path(
        os.getenv("ZHC_TASK_DB", str(repo_root() / "storage/tasks/task_registry.db"))
    ).resolve()

    route_class, risk_level = classify(task_type, prompt, routing_policy)
    mode = autonomy_mode()
    approval_required = requires_approval(risk_level, task_type, approval_policy)
    action_category = action_category_for_task(task_type, risk_level)

    if mode == "supervised" and route_class == "UBUNTU_HEAVY":
        approval_required = True
        if action_category == "none":
            action_category = "supervised_heavy_execution"

    task_id = f"task-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')}"
    model_provider, model_name = model_hint_for_task(task_type)
    metadata = {
        "source": "router_v1",
        "approval_required": approval_required,
        "autonomy_mode": mode,
        "model_provider_hint": model_provider,
        "model_name_hint": model_name,
        "queued_at": utc_now(),
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

    policy_allowed, policy_reason = evaluate_execution_policy(
        task_type,
        prompt,
        route_class,
        mode,
        execution_policy,
    )
    if not policy_allowed:
        run_registry(
            [
                "update",
                "--task-id",
                task_id,
                "--status",
                "blocked",
                "--detail",
                f"policy_block:{policy_reason}",
            ],
            db_path,
        )
        append_task_event(task_id, f"policy_block reason={policy_reason}", db_path)
        return {
            "task_id": task_id,
            "status": "blocked",
            "route_class": route_class,
            "risk_level": risk_level,
            "approval_required": False,
            "autonomy_mode": mode,
            "policy_status": "blocked",
            "policy_reason": policy_reason,
            "message": f"Task blocked by execution policy: {policy_reason}",
            "created": create_payload.get("created_at"),
        }

    append_task_event(task_id, "policy_allow", db_path)

    gate_required = route_class == "UBUNTU_HEAVY"
    gate_status = review_gate_status(task_id)

    pending_reasons: list[str] = []
    if gate_required and not gate_status["gate_passed"]:
        pending_reasons.append("planner_reviewer_gate")
        append_task_event(task_id, "review_gate_pending", db_path)

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
        pending_reasons.append("human_approval")
        append_task_event(task_id, "approval_required before execution", db_path)

    if pending_reasons:
        block_detail = "awaiting_" + "_and_".join(pending_reasons)
        run_registry(
            [
                "update",
                "--task-id",
                task_id,
                "--status",
                "blocked",
                "--detail",
                block_detail,
            ],
            db_path,
        )
        return {
            "task_id": task_id,
            "status": "blocked",
            "route_class": route_class,
            "risk_level": risk_level,
            "approval_required": approval_required,
            "action_category": action_category if approval_required else "none",
            "autonomy_mode": mode,
            "policy_status": "allowed",
            "policy_reason": "allowed",
            "review_gate": gate_status,
            "message": f"Task created and blocked pending: {', '.join(pending_reasons)}",
        }

    dispatch_started = time.perf_counter()
    dispatch_status, dispatch_detail = dispatch(
        route_class, task_type, prompt, task_id, mode
    )
    dispatch_ms = max(1, int((time.perf_counter() - dispatch_started) * 1000))
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
    merge_task_metadata(
        task_id,
        db_path,
        {
            "dispatch_duration_ms": dispatch_ms,
            "estimated_cost_usd": estimate_cost_usd(
                task_type, dispatch_ms, route_class
            ),
            "last_dispatch_status": dispatch_status,
        },
        "telemetry_dispatch_route",
    )
    append_task_event(
        task_id,
        f"telemetry route_ms={dispatch_ms} est_cost={estimate_cost_usd(task_type, dispatch_ms, route_class)}",
        db_path,
    )

    return {
        "task_id": task_id,
        "status": dispatch_status,
        "route_class": route_class,
        "risk_level": risk_level,
        "approval_required": False,
        "autonomy_mode": mode,
        "policy_status": "allowed",
        "policy_reason": "allowed",
        "message": dispatch_detail,
        "created": create_payload.get("created_at"),
    }


def dispatch_blockers(task: dict[str, Any]) -> list[str]:
    blockers: list[str] = []
    if task.get("route_class") == "UBUNTU_HEAVY":
        gate = review_gate_status(task["task_id"])
        if not gate["gate_passed"]:
            blockers.append("planner_reviewer_gate")

    if task.get("requires_approval"):
        approvals = task.get("approvals", [])
        approved = any(a.get("status") == "approved" for a in approvals)
        if not approved:
            blockers.append("human_approval")
    return blockers


def dispatch_task_if_ready(
    task: dict[str, Any], mode: str, db_path: Path
) -> dict[str, Any]:
    blockers = dispatch_blockers(task)
    if blockers:
        append_task_event(
            task["task_id"],
            f"resume_blocked pending={','.join(blockers)}",
            db_path,
        )
        return {
            "task_id": task["task_id"],
            "status": "blocked",
            "autonomy_mode": mode,
            "pending": blockers,
            "review_gate": review_gate_status(task["task_id"]),
            "message": f"Task remains blocked pending: {', '.join(blockers)}",
        }

    dispatch_started = time.perf_counter()
    dispatch_status, dispatch_detail = dispatch(
        task["route_class"], task["task_type"], task["prompt"], task["task_id"], mode
    )
    dispatch_ms = max(1, int((time.perf_counter() - dispatch_started) * 1000))
    run_registry(
        [
            "update",
            "--task-id",
            task["task_id"],
            "--status",
            dispatch_status,
            "--detail",
            dispatch_detail,
        ],
        db_path,
    )
    append_task_event(
        task["task_id"],
        f"dispatched_after_gates status={dispatch_status} detail={dispatch_detail}",
        db_path,
    )
    merge_task_metadata(
        task["task_id"],
        db_path,
        {
            "dispatch_duration_ms": dispatch_ms,
            "estimated_cost_usd": estimate_cost_usd(
                task["task_type"], dispatch_ms, task["route_class"]
            ),
            "last_dispatch_status": dispatch_status,
        },
        "telemetry_dispatch_resume",
    )
    append_task_event(
        task["task_id"],
        (
            "telemetry "
            f"resume_ms={dispatch_ms} est_cost={estimate_cost_usd(task['task_type'], dispatch_ms, task['route_class'])}"
        ),
        db_path,
    )
    return {
        "task_id": task["task_id"],
        "status": dispatch_status,
        "autonomy_mode": mode,
        "message": dispatch_detail,
    }


def record_plan(task_id: str, author: str, summary: str) -> dict[str, Any]:
    db_path = Path(
        os.getenv("ZHC_TASK_DB", str(repo_root() / "storage/tasks/task_registry.db"))
    ).resolve()
    task = run_registry(["get", "--task-id", task_id], db_path)
    if task.get("route_class") != "UBUNTU_HEAVY":
        raise ValueError("Planner artifact is only required for UBUNTU_HEAVY tasks")
    artifact = write_planner_artifact(task_id, author, summary)
    append_task_event(task_id, f"planner_artifact_recorded path={artifact}", db_path)
    return {
        "task_id": task_id,
        "artifact": str(artifact),
        "review_gate": review_gate_status(task_id),
        "message": "Planner artifact recorded",
    }


def record_review(
    task_id: str, reviewer: str, verdict: str, notes: str
) -> dict[str, Any]:
    db_path = Path(
        os.getenv("ZHC_TASK_DB", str(repo_root() / "storage/tasks/task_registry.db"))
    ).resolve()
    task = run_registry(["get", "--task-id", task_id], db_path)
    if task.get("route_class") != "UBUNTU_HEAVY":
        raise ValueError("Reviewer artifact is only required for UBUNTU_HEAVY tasks")
    verdict_l = verdict.strip().lower()
    if verdict_l not in {"pass", "fail"}:
        raise ValueError("verdict must be one of: pass, fail")
    artifact = write_reviewer_artifact(task_id, reviewer, verdict_l, notes)
    append_task_event(
        task_id,
        f"reviewer_artifact_recorded verdict={verdict_l} path={artifact}",
        db_path,
    )
    return {
        "task_id": task_id,
        "artifact": str(artifact),
        "review_gate": review_gate_status(task_id),
        "message": "Reviewer artifact recorded",
    }


def resume_task(task_id: str, requested_by: str) -> dict[str, Any]:
    mode = autonomy_mode()
    if mode == "readonly":
        raise ValueError("Cannot resume tasks while ZHC_AUTONOMY_MODE=readonly")

    db_path = Path(
        os.getenv("ZHC_TASK_DB", str(repo_root() / "storage/tasks/task_registry.db"))
    ).resolve()
    task = run_registry(["get", "--task-id", task_id], db_path)
    if task.get("status") != "blocked":
        raise ValueError(f"Task {task_id} must be blocked before resume")

    result = dispatch_task_if_ready(task, mode, db_path)
    append_task_event(task_id, f"resume_requested by={requested_by}", db_path)
    return result


def approve_task(
    task_id: str,
    action_category: str,
    decided_by: str,
    note: str,
    decision: str,
) -> dict[str, Any]:
    mode = autonomy_mode()
    if mode == "readonly":
        raise ValueError("Cannot approve/resume tasks while ZHC_AUTONOMY_MODE=readonly")

    db_path = Path(
        os.getenv("ZHC_TASK_DB", str(repo_root() / "storage/tasks/task_registry.db"))
    ).resolve()

    task = run_registry(["get", "--task-id", task_id], db_path)
    if task.get("status") != "blocked":
        raise ValueError(f"Task {task_id} must be blocked before approval decision")
    if not task.get("approvals"):
        raise ValueError(
            f"Task {task_id} is blocked by policy/runtime state and cannot be resumed by approval"
        )

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

    refreshed_task = run_registry(["get", "--task-id", task_id], db_path)
    dispatch_result = dispatch_task_if_ready(refreshed_task, mode, db_path)
    append_task_event(
        task_id,
        (
            "approval_decision_processed "
            f"action={action_category} decision={decision} by={decided_by}"
        ),
        db_path,
    )

    return {
        "task_id": task_id,
        "status": dispatch_result["status"],
        "action_category": action_category,
        "decision": decision,
        "autonomy_mode": mode,
        "pending": dispatch_result.get("pending", []),
        "review_gate": dispatch_result.get("review_gate"),
        "message": dispatch_result["message"],
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

    plan_parser = sub.add_parser(
        "record-plan", help="Record planner artifact for heavy task"
    )
    plan_parser.add_argument("--task-id", required=True)
    plan_parser.add_argument("--author", required=True)
    plan_parser.add_argument("--summary", required=True)

    review_parser = sub.add_parser(
        "record-review", help="Record reviewer artifact and verdict for heavy task"
    )
    review_parser.add_argument("--task-id", required=True)
    review_parser.add_argument("--reviewer", required=True)
    review_parser.add_argument("--verdict", choices=["pass", "fail"], required=True)
    review_parser.add_argument("--notes", default="")

    resume_parser = sub.add_parser(
        "resume", help="Resume blocked task once all gates are satisfied"
    )
    resume_parser.add_argument("--task-id", required=True)
    resume_parser.add_argument("--requested-by", required=True)

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
        execution_policy = load_policy(
            Path(
                os.getenv(
                    "ZHC_EXECUTION_POLICY",
                    str(repo_root() / "shared/policies/execution_policy.yaml"),
                )
            )
        )

        if args.command == "classify":
            mode = autonomy_mode()
            route_class, risk_level = classify(
                args.task_type, args.prompt, routing_policy
            )
            approval_required = requires_approval(
                risk_level, args.task_type, approval_policy
            )
            if mode == "supervised" and route_class == "UBUNTU_HEAVY":
                approval_required = True
            policy_allowed, policy_reason = evaluate_execution_policy(
                args.task_type,
                args.prompt,
                route_class,
                mode,
                execution_policy,
            )
            out = {
                "route_class": route_class,
                "risk_level": risk_level,
                "approval_required": approval_required,
                "autonomy_mode": mode,
                "policy_status": "allowed" if policy_allowed else "blocked",
                "policy_reason": policy_reason,
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

        if args.command == "record-plan":
            result = record_plan(args.task_id, args.author, args.summary)
            print(json.dumps(result, indent=2, sort_keys=True))
            return 0

        if args.command == "record-review":
            result = record_review(
                task_id=args.task_id,
                reviewer=args.reviewer,
                verdict=args.verdict,
                notes=args.notes,
            )
            print(json.dumps(result, indent=2, sort_keys=True))
            return 0

        if args.command == "resume":
            result = resume_task(args.task_id, args.requested_by)
            print(json.dumps(result, indent=2, sort_keys=True))
            return 0

        raise ValueError("Unknown command")
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
