#!/usr/bin/env python3
"""Rule-based task router for v1 Pi/Ubuntu dispatch."""

# Permanent v1 policy: OpenCode has no direct Grok/ChatGPT API or browser access.
# If routing/execution needs latest external information or non-local certainty, emit
# the exact "=== EXTERNAL QUERY NEEDED ===" block and wait for Jacob's
# "=== EXTERNAL RESPONSE ===" before continuing.

from __future__ import annotations

import argparse
import hashlib
import json
import os
import random
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


VALID_AUTONOMY_MODES = {"readonly", "supervised", "auto"}
VALID_RUNTIME_MODES = {"single_node", "multi_node"}
VALID_REVIEW_FAIL_CODES = {
    "policy_conflict",
    "missing_tests",
    "insufficient_plan",
    "high_risk_unmitigated",
    "artifact_incomplete",
    "other",
}
REVIEW_CHECKLIST_KEYS = (
    "policy_safety",
    "correctness",
    "tests",
    "rollback",
    "approval_constraints",
)

_OPENROUTER_PRICE_CACHE: dict[str, tuple[float, float] | None] = {}


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


def runtime_mode() -> str:
    mode = os.getenv("ZHC_RUNTIME_MODE", "single_node").strip().lower()
    if mode not in VALID_RUNTIME_MODES:
        allowed = ", ".join(sorted(VALID_RUNTIME_MODES))
        raise ValueError(f"Invalid ZHC_RUNTIME_MODE '{mode}'. Allowed: {allowed}")
    return mode


def dispatch_owner_id() -> str:
    configured = os.getenv("ZHC_DISPATCH_OWNER", "").strip()
    if configured:
        return configured
    return f"{socket.gethostname()}:{os.getpid()}"


def dispatch_lease_seconds() -> int:
    raw = os.getenv("ZHC_DISPATCH_LEASE_SECONDS", "120").strip()
    try:
        return max(30, int(raw))
    except ValueError:
        return 120


def dispatch_retry_max() -> int:
    raw = os.getenv("ZHC_DISPATCH_RETRY_MAX", "1").strip()
    try:
        return max(0, int(raw))
    except ValueError:
        return 1


def dispatch_retry_backoff_seconds() -> float:
    raw = os.getenv("ZHC_DISPATCH_RETRY_BACKOFF_SECONDS", "1.0").strip()
    try:
        return max(0.1, float(raw))
    except ValueError:
        return 1.0


def dispatch_retry_jitter_seconds() -> float:
    raw = os.getenv("ZHC_DISPATCH_RETRY_JITTER_SECONDS", "0.3").strip()
    try:
        return max(0.0, float(raw))
    except ValueError:
        return 0.3


def dispatch_timeout_seconds() -> int:
    raw = os.getenv("ZHC_DISPATCH_TIMEOUT_SECONDS", "900").strip()
    try:
        return max(30, int(raw))
    except ValueError:
        return 900


def payload_hash(payload: dict[str, Any]) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def is_transient_dispatch_error(error_text: str) -> bool:
    text = error_text.lower()
    markers = (
        "timed out",
        "timeout",
        "temporarily unavailable",
        "connection reset",
        "broken pipe",
        "resource temporarily unavailable",
        "too many requests",
        "service unavailable",
    )
    return any(marker in text for marker in markers)


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


def estimate_tokens(text: str) -> int:
    return max(1, (len(text) + 3) // 4)


def compact_snippet(text: str, limit: int = 140) -> str:
    clean = " ".join(text.split())
    if len(clean) <= limit:
        return clean
    return clean[: limit - 3] + "..."


def token_budget(route_class: str) -> int:
    if route_class == "UBUNTU_HEAVY":
        return int(os.getenv("ZHC_CONTEXT_TOKEN_BUDGET_HEAVY", "2400"))
    return int(os.getenv("ZHC_CONTEXT_TOKEN_BUDGET", "1200"))


def target_ratio() -> float:
    try:
        val = float(os.getenv("ZHC_CONTEXT_TARGET_RATIO", "0.7"))
    except ValueError:
        return 0.7
    return max(0.3, min(val, 1.0))


def compact_text_to_token_budget(text: str, budget: int) -> tuple[str, int, int, float]:
    input_tokens = estimate_tokens(text)
    if not text.strip():
        return text, input_tokens, input_tokens, 1.0

    effective_budget = min(budget, max(120, int(input_tokens * target_ratio())))
    lines = [line.rstrip() for line in text.splitlines()]
    if not lines:
        return text, input_tokens, input_tokens, 1.0

    essential_lines: list[str] = []
    retrieval_lines: list[str] = []
    for line in lines:
        if line.startswith("- "):
            retrieval_lines.append(compact_snippet(line, 160))
        elif line.strip():
            essential_lines.append(compact_snippet(line, 200))

    selected: list[str] = []
    for line in essential_lines:
        selected.append(line)
        if estimate_tokens("\n".join(selected)) >= effective_budget:
            break

    if retrieval_lines and estimate_tokens("\n".join(selected)) < effective_budget:
        selected.append("retrieval:")
        used = estimate_tokens("\n".join(selected))
        for line in retrieval_lines:
            test = "\n".join(selected + [line])
            next_tokens = estimate_tokens(test)
            if next_tokens > effective_budget:
                break
            selected.append(line)
            used = next_tokens

    compacted = "\n".join(selected) if selected else compact_snippet(text, 400)

    if estimate_tokens(compacted) > budget:
        trimmed = compacted[: max(80, int((budget * 4) * 0.9))]
        compacted = compact_snippet(trimmed, len(trimmed))

    out_tokens = estimate_tokens(compacted)
    ratio = round(out_tokens / max(input_tokens, 1), 4)
    return compacted, input_tokens, out_tokens, ratio


def recent_memory_snippets(
    db_path: Path, task_type: str, limit: int = 5
) -> list[dict[str, str]]:
    import sqlite3

    snippets: list[dict[str, str]] = []
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT task_id, task_type, status, prompt, metadata_json
            FROM tasks
            WHERE task_type = ?
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (task_type, limit),
        ).fetchall()
    for row in rows:
        metadata = json.loads(row["metadata_json"] or "{}")
        snippets.append(
            {
                "source": f"task:{row['task_id']}",
                "text": (
                    f"task_type={row['task_type']} status={row['status']} "
                    f"cost={metadata.get('estimated_cost_usd', 0)} prompt={compact_snippet(row['prompt'], 120)}"
                ),
            }
        )

    memory_dir = repo_root() / "storage" / "memory"
    if memory_dir.exists():
        for path in sorted(
            memory_dir.glob("*.txt"), key=lambda p: p.stat().st_mtime, reverse=True
        )[:3]:
            try:
                text = path.read_text(encoding="utf-8")
            except OSError:
                continue
            snippets.append(
                {"source": f"memory:{path.name}", "text": compact_snippet(text, 200)}
            )

    return snippets


def build_context_payload(task: dict[str, Any], db_path: Path) -> tuple[str, list[str]]:
    snippets = recent_memory_snippets(db_path, task["task_type"], limit=5)
    sources = [entry["source"] for entry in snippets]
    approvals = task.get("approvals", [])
    approval_status = approvals[-1].get("status") if approvals else "none"
    lines = [
        f"task_id={task['task_id']}",
        f"task_type={task['task_type']}",
        f"route_class={task['route_class']}",
        f"risk_level={task.get('risk_level', 'unknown')}",
        f"requires_approval={task.get('requires_approval', False)}",
        f"approval_status={approval_status}",
        f"prompt={task['prompt']}",
        "",
        "retrieval:",
    ]
    for entry in snippets:
        lines.append(f"- {entry['source']}: {entry['text']}")
    return "\n".join(lines), sources


def openrouter_model_pricing(model: str) -> tuple[float, float] | None:
    if model in _OPENROUTER_PRICE_CACHE:
        return _OPENROUTER_PRICE_CACHE[model]

    enabled = os.getenv("ZHC_COST_LOOKUP_ENABLED", "1").strip()
    api_key = os.getenv("OPENROUTER_API_KEY", "").strip()
    if enabled != "1" or not api_key:
        _OPENROUTER_PRICE_CACHE[model] = None
        return None

    timeout_ms = int(os.getenv("ZHC_COST_LOOKUP_TIMEOUT_MS", "3000"))
    req = urllib.request.Request(
        "https://openrouter.ai/api/v1/models",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Accept": "application/json",
        },
        method="GET",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout_ms / 1000) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
        _OPENROUTER_PRICE_CACHE[model] = None
        return None

    for entry in payload.get("data", []):
        if entry.get("id") != model:
            continue
        pricing = entry.get("pricing", {})
        try:
            prompt = float(pricing.get("prompt", "0") or 0)
            completion = float(pricing.get("completion", "0") or 0)
        except (TypeError, ValueError):
            _OPENROUTER_PRICE_CACHE[model] = None
            return None
        _OPENROUTER_PRICE_CACHE[model] = (prompt, completion)
        return _OPENROUTER_PRICE_CACHE[model]
    _OPENROUTER_PRICE_CACHE[model] = None
    return None


def cost_model_hint(model_hint: str) -> str:
    configured = os.getenv("ZHC_COST_MODEL_DEFAULT", "").strip()
    if configured:
        return configured
    if "/" in model_hint:
        return model_hint
    return "openai/gpt-4o-mini"


def estimate_cost(
    task_type: str,
    route_class: str,
    prompt_tokens: int,
    completion_tokens: int,
    model_hint: str,
) -> dict[str, Any]:
    pricing = openrouter_model_pricing(model_hint)
    if pricing:
        prompt_price, completion_price = pricing
        estimated = (
            (prompt_tokens * prompt_price) + (completion_tokens * completion_price)
        ) / 1_000_000
        return {
            "estimated_cost_usd": round(estimated, 6),
            "cost_source": "openrouter_api",
            "pricing_prompt_per_million": prompt_price,
            "pricing_completion_per_million": completion_price,
        }

    if route_class == "PI_LIGHT":
        fallback = (prompt_tokens + completion_tokens) * 0.0000005
    else:
        base = 0.01 if task_type in {"code_refactor", "build_fix"} else 0.006
        fallback = base + (prompt_tokens + completion_tokens) * 0.000001
    return {
        "estimated_cost_usd": round(fallback, 6),
        "cost_source": "heuristic",
    }


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
    timeout_s = dispatch_timeout_seconds()
    retry_max = dispatch_retry_max()
    backoff_s = dispatch_retry_backoff_seconds()
    jitter_s = dispatch_retry_jitter_seconds()

    attempts = max(1, retry_max + 1)
    last_proc: subprocess.CompletedProcess[str] | None = None

    for attempt in range(1, attempts + 1):
        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout_s,
            )
        except subprocess.TimeoutExpired:
            proc = subprocess.CompletedProcess(
                args=cmd,
                returncode=124,
                stdout="",
                stderr=f"dispatch_timeout after {timeout_s}s",
            )

        if proc.returncode == 0:
            return proc

        err = (proc.stderr or proc.stdout or "").strip()
        last_proc = proc
        if attempt >= attempts or not is_transient_dispatch_error(err):
            return proc

        sleep_s = backoff_s * (2 ** (attempt - 1))
        sleep_s += random.uniform(0.0, jitter_s)
        time.sleep(max(0.05, sleep_s))

    return last_proc or subprocess.CompletedProcess(cmd, 1, "", "dispatch_failed")


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
    reviewer_reason_code = ""
    checklist_complete = False

    if reviewer_present:
        try:
            payload = json.loads(reviewer_path.read_text(encoding="utf-8"))
            reviewer_verdict = str(payload.get("verdict", "missing")).lower().strip()
            reviewer_reason_code = str(payload.get("reason_code", "")).strip()
            checklist = payload.get("checklist", {})
            checklist_complete = isinstance(checklist, dict) and all(
                isinstance(checklist.get(k), bool) for k in REVIEW_CHECKLIST_KEYS
            )
            reviewer_passed = reviewer_verdict == "pass" and checklist_complete
        except json.JSONDecodeError:
            reviewer_verdict = "invalid"
            reviewer_passed = False

    gate_passed = planner_present and reviewer_present and reviewer_passed
    return {
        "planner_present": planner_present,
        "reviewer_present": reviewer_present,
        "reviewer_verdict": reviewer_verdict,
        "reviewer_reason_code": reviewer_reason_code,
        "checklist_complete": checklist_complete,
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
                "scope:",
                summary,
                "",
                "risks:",
                "- TODO: identify primary risks and mitigations",
                "",
                "test_plan:",
                "- TODO: define validation/tests",
                "",
                "rollback_plan:",
                "- TODO: define rollback procedure",
                "",
                "approval_impact:",
                "- TODO: list required approvals and checkpoints",
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
    reason_code: str,
    checklist: dict[str, bool],
    notes: str,
) -> Path:
    path = reviewer_artifact_path(task_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "reviewer": reviewer,
        "verdict": verdict,
        "reason_code": reason_code,
        "checklist": checklist,
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
    dispatch_runtime: str,
) -> tuple[str, str]:
    if mode == "readonly":
        return "blocked", "readonly_mode_execution_disabled"

    if route_class == "UBUNTU_HEAVY":
        if dispatch_runtime == "single_node":
            cmd = [
                str(repo_root() / "infra/opencode/wrappers/zrun.sh"),
                "--task-type",
                task_type,
                "--prompt",
                prompt,
                "--task-id",
                task_id,
            ]
            result = run_command(cmd)
            if result.returncode != 0:
                return "failed", f"local_run_failed: {result.stderr.strip()}"
            local_task_id = task_id
            stdout = result.stdout.strip()
            if stdout:
                local_task_id = stdout.splitlines()[-1].strip()
            return "succeeded", f"single_node_local_run task_id={local_task_id}"

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
    dispatch_runtime = runtime_mode()
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
        "runtime_mode": dispatch_runtime,
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
            "runtime_mode": dispatch_runtime,
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
            "runtime_mode": dispatch_runtime,
            "policy_status": "allowed",
            "policy_reason": "allowed",
            "review_gate": gate_status,
            "message": f"Task created and blocked pending: {', '.join(pending_reasons)}",
        }

    refreshed_task = run_registry(["get", "--task-id", task_id], db_path)
    dispatch_result = dispatch_task_if_ready(refreshed_task, mode, db_path)
    return {
        "task_id": task_id,
        "status": dispatch_result["status"],
        "route_class": route_class,
        "risk_level": risk_level,
        "approval_required": False,
        "autonomy_mode": mode,
        "runtime_mode": dispatch_runtime,
        "policy_status": "allowed",
        "policy_reason": "allowed",
        "message": dispatch_result["message"],
        "created": create_payload.get("created_at"),
    }


def dispatch_blockers(task: dict[str, Any]) -> list[str]:
    blockers: list[str] = []
    if task.get("route_class") == "UBUNTU_HEAVY":
        gate = review_gate_status(task["task_id"])
        if not gate["gate_passed"]:
            if gate["reviewer_verdict"] == "fail":
                code = gate["reviewer_reason_code"] or "unspecified"
                blockers.append(f"review_failed:{code}")
            elif gate["reviewer_verdict"] == "pass" and not gate["checklist_complete"]:
                blockers.append("review_incomplete_checklist")
            else:
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
    dispatch_runtime = runtime_mode()
    if blockers:
        hint = ""
        if any(b.startswith("review_failed:") for b in blockers):
            hint = (
                " Use /review <task_id> pass <notes> after fixing reviewer fail reason."
            )
        elif "planner_reviewer_gate" in blockers:
            hint = " Record /plan and /review artifacts before resume."
        append_task_event(
            task["task_id"],
            f"resume_blocked pending={','.join(blockers)}",
            db_path,
        )
        return {
            "task_id": task["task_id"],
            "status": "blocked",
            "autonomy_mode": mode,
            "runtime_mode": dispatch_runtime,
            "pending": blockers,
            "review_gate": review_gate_status(task["task_id"]),
            "message": f"Task remains blocked pending: {', '.join(blockers)}.{hint}",
        }

    context_payload, retrieval_sources = build_context_payload(task, db_path)
    budget = token_budget(task["route_class"])
    compacted, tokens_in, tokens_out, compression_ratio = compact_text_to_token_budget(
        context_payload,
        budget,
    )
    completion_tokens_est = max(64, int(tokens_out * 0.35))

    metadata = task.get("metadata", {})
    provider_hint = metadata.get("model_provider_hint")
    model_hint = metadata.get("model_name_hint")
    if not provider_hint or not model_hint:
        provider_hint, model_hint = model_hint_for_task(task["task_type"])

    pricing_model = cost_model_hint(model_hint)
    cost_info = estimate_cost(
        task["task_type"],
        task["route_class"],
        tokens_out,
        completion_tokens_est,
        pricing_model,
    )

    artifacts_dir = task_dir(task["task_id"]) / "artifacts"
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    context_path = artifacts_dir / "context_compacted.txt"
    context_path.write_text(compacted, encoding="utf-8")
    cost_path = artifacts_dir / "cost_estimate.json"
    cost_payload = {
        "task_id": task["task_id"],
        "provider_hint": provider_hint,
        "model_hint": model_hint,
        "pricing_model": pricing_model,
        "estimated_prompt_tokens": tokens_out,
        "estimated_completion_tokens": completion_tokens_est,
        "estimated_total_tokens": tokens_out + completion_tokens_est,
        **cost_info,
    }
    cost_path.write_text(
        json.dumps(cost_payload, indent=2, sort_keys=True), encoding="utf-8"
    )

    append_task_event(
        task["task_id"],
        f"dispatch_mode={dispatch_runtime}",
        db_path,
    )
    append_task_event(
        task["task_id"],
        (
            "context_compacted "
            f"tokens_in={tokens_in} tokens_out={tokens_out} ratio={compression_ratio} budget={budget}"
        ),
        db_path,
    )
    append_task_event(
        task["task_id"],
        (
            "cost_estimated "
            f"source={cost_info['cost_source']} total_tokens={tokens_out + completion_tokens_est} "
            f"usd={cost_info['estimated_cost_usd']}"
        ),
        db_path,
    )

    owner = dispatch_owner_id()
    lease_seconds = dispatch_lease_seconds()
    run_registry(
        [
            "lease-enqueue",
            "--task-id",
            task["task_id"],
            "--owner-id",
            owner,
            "--lease-seconds",
            str(lease_seconds),
        ],
        db_path,
    )
    claim = run_registry(
        [
            "lease-claim",
            "--task-id",
            task["task_id"],
            "--owner-id",
            owner,
            "--lease-seconds",
            str(lease_seconds),
        ],
        db_path,
    )
    if not bool(claim.get("claimed", False)):
        reason = str(claim.get("reason", "unknown"))
        append_task_event(
            task["task_id"], f"lease_claim_denied reason={reason}", db_path
        )
        return {
            "task_id": task["task_id"],
            "status": "running",
            "autonomy_mode": mode,
            "runtime_mode": dispatch_runtime,
            "pending": ["lease_held_by_other_owner"],
            "review_gate": review_gate_status(task["task_id"]),
            "message": f"Task already being dispatched by another owner ({reason})",
        }

    lease = run_registry(
        [
            "lease-get",
            "--task-id",
            task["task_id"],
        ],
        db_path,
    )
    lease_row = lease.get("lease") or {}
    attempt_count = int(lease_row.get("attempt_count", 0) or 0)
    idempo_key = f"dispatch:{task['task_id']}:{attempt_count}"
    idempo_payload_hash = payload_hash(
        {
            "task_id": task["task_id"],
            "task_type": task["task_type"],
            "prompt": task["prompt"],
            "route_class": task["route_class"],
            "mode": mode,
            "runtime_mode": dispatch_runtime,
            "owner": owner,
            "attempt_count": attempt_count,
        }
    )
    idempo_begin = run_registry(
        [
            "idempo-begin",
            "--key",
            idempo_key,
            "--scope",
            "dispatch",
            "--task-id",
            task["task_id"],
            "--payload-hash",
            idempo_payload_hash,
        ],
        db_path,
    )
    if bool(idempo_begin.get("conflict", False)):
        append_task_event(task["task_id"], "idempo_dispatch_conflict", db_path)
        return {
            "task_id": task["task_id"],
            "status": "blocked",
            "autonomy_mode": mode,
            "runtime_mode": dispatch_runtime,
            "pending": ["idempotency_conflict"],
            "review_gate": review_gate_status(task["task_id"]),
            "message": "Dispatch idempotency conflict; manual inspection required",
        }
    if bool(idempo_begin.get("exists", False)):
        existing_status = str(idempo_begin.get("status", ""))
        if existing_status == "processing":
            append_task_event(task["task_id"], "idempo_dispatch_inflight", db_path)
            return {
                "task_id": task["task_id"],
                "status": "running",
                "autonomy_mode": mode,
                "runtime_mode": dispatch_runtime,
                "pending": ["dispatch_inflight"],
                "review_gate": review_gate_status(task["task_id"]),
                "message": "Dispatch attempt already in progress",
            }
        if existing_status == "completed":
            cached = idempo_begin.get("result") or {}
            cached_status = str(cached.get("dispatch_status") or "running")
            cached_detail = str(cached.get("dispatch_detail") or "idempotent_replay")
            append_task_event(task["task_id"], "idempo_dispatch_hit", db_path)
            return {
                "task_id": task["task_id"],
                "status": cached_status,
                "autonomy_mode": mode,
                "runtime_mode": dispatch_runtime,
                "review_gate": review_gate_status(task["task_id"]),
                "message": f"Dispatch replayed from idempotency cache: {cached_detail}",
            }
    append_task_event(task["task_id"], "idempo_dispatch_miss", db_path)

    run_registry(
        [
            "update",
            "--task-id",
            task["task_id"],
            "--status",
            "queued",
            "--detail",
            "queued_for_dispatch",
        ],
        db_path,
    )

    run_registry(
        [
            "update",
            "--task-id",
            task["task_id"],
            "--status",
            "running",
            "--detail",
            "dispatch_started",
        ],
        db_path,
    )

    dispatch_started = time.perf_counter()
    dispatch_status, dispatch_detail = dispatch(
        task["route_class"],
        task["task_type"],
        task["prompt"],
        task["task_id"],
        mode,
        dispatch_runtime,
    )
    dispatch_ms = max(1, int((time.perf_counter() - dispatch_started) * 1000))

    run_registry(
        [
            "idempo-complete",
            "--key",
            idempo_key,
            "--status",
            "completed",
            "--result-json",
            json.dumps(
                {
                    "dispatch_status": dispatch_status,
                    "dispatch_detail": dispatch_detail,
                    "dispatch_duration_ms": dispatch_ms,
                },
                sort_keys=True,
            ),
        ],
        db_path,
    )

    terminal_status = dispatch_status
    if terminal_status == "canceled":
        terminal_status = "cancelled"
    if terminal_status in {"succeeded", "failed", "cancelled", "expired"}:
        run_registry(
            [
                "lease-finish",
                "--task-id",
                task["task_id"],
                "--owner-id",
                owner,
                "--result-status",
                terminal_status,
                "--last-error",
                "" if terminal_status == "succeeded" else dispatch_detail,
            ],
            db_path,
        )
    else:
        run_registry(
            [
                "lease-heartbeat",
                "--task-id",
                task["task_id"],
                "--owner-id",
                owner,
                "--lease-seconds",
                str(lease_seconds),
            ],
            db_path,
        )

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
            "estimated_prompt_tokens": tokens_out,
            "estimated_completion_tokens": completion_tokens_est,
            "estimated_total_tokens": tokens_out + completion_tokens_est,
            "estimated_cost_usd": cost_info["estimated_cost_usd"],
            "cost_source": cost_info["cost_source"],
            "context_input_tokens": tokens_in,
            "context_compacted_tokens": tokens_out,
            "compression_ratio": compression_ratio,
            "context_token_budget": budget,
            "retrieval_sources": retrieval_sources,
            "context_compacted_path": str(context_path),
            "cost_estimate_path": str(cost_path),
            "model_provider_hint": provider_hint,
            "model_name_hint": model_hint,
            "pricing_model": pricing_model,
            "last_dispatch_status": dispatch_status,
        },
        "telemetry_dispatch_resume",
    )
    append_task_event(
        task["task_id"],
        (
            "telemetry "
            f"resume_ms={dispatch_ms} est_cost={cost_info['estimated_cost_usd']} "
            f"cost_source={cost_info['cost_source']}"
        ),
        db_path,
    )
    return {
        "task_id": task["task_id"],
        "status": dispatch_status,
        "autonomy_mode": mode,
        "runtime_mode": dispatch_runtime,
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
    task_id: str,
    reviewer: str,
    verdict: str,
    reason_code: str,
    checklist_json: str,
    notes: str,
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
    reason_code_l = reason_code.strip().lower()
    if verdict_l == "fail" and reason_code_l not in VALID_REVIEW_FAIL_CODES:
        allowed = ", ".join(sorted(VALID_REVIEW_FAIL_CODES))
        raise ValueError(f"reason_code required for fail verdict. Allowed: {allowed}")
    if verdict_l == "pass":
        reason_code_l = ""

    try:
        checklist_raw = json.loads(checklist_json)
    except json.JSONDecodeError as exc:
        raise ValueError(f"checklist_json must be valid JSON: {exc}") from exc
    if not isinstance(checklist_raw, dict):
        raise ValueError("checklist_json must decode to object")

    checklist: dict[str, bool] = {}
    for key in REVIEW_CHECKLIST_KEYS:
        val = checklist_raw.get(key)
        checklist[key] = bool(val) if isinstance(val, bool) else False

    if verdict_l == "pass" and not all(checklist.values()):
        raise ValueError("pass verdict requires all checklist values to be true")

    artifact = write_reviewer_artifact(
        task_id,
        reviewer,
        verdict_l,
        reason_code_l,
        checklist,
        notes,
    )
    append_task_event(
        task_id,
        (
            f"reviewer_artifact_recorded verdict={verdict_l} "
            f"reason_code={reason_code_l or 'none'} path={artifact}"
        ),
        db_path,
    )
    return {
        "task_id": task_id,
        "artifact": str(artifact),
        "reason_code": reason_code_l,
        "review_gate": review_gate_status(task_id),
        "message": "Reviewer artifact recorded",
        "next_action": (
            "Fix issues then submit pass review"
            if verdict_l == "fail"
            else "Resume task once other gates are satisfied"
        ),
    }


def resume_task(task_id: str, requested_by: str) -> dict[str, Any]:
    mode = autonomy_mode()
    if mode == "readonly":
        raise ValueError("Cannot resume tasks while ZHC_AUTONOMY_MODE=readonly")

    db_path = Path(
        os.getenv("ZHC_TASK_DB", str(repo_root() / "storage/tasks/task_registry.db"))
    ).resolve()
    run_registry(
        [
            "lease-reconcile",
            "--owner-id",
            dispatch_owner_id(),
        ],
        db_path,
    )
    task = run_registry(["get", "--task-id", task_id], db_path)
    status = str(task.get("status", "")).strip().lower()
    if status in {"succeeded", "failed", "cancelled", "expired"}:
        append_task_event(task_id, f"resume_noop terminal_status={status}", db_path)
        return {
            "task_id": task_id,
            "status": status,
            "autonomy_mode": mode,
            "runtime_mode": runtime_mode(),
            "message": f"Task already terminal: {status}",
        }
    if status in {"running", "queued"}:
        append_task_event(task_id, f"resume_noop already_{status}", db_path)
        return {
            "task_id": task_id,
            "status": status,
            "autonomy_mode": mode,
            "runtime_mode": runtime_mode(),
            "message": f"Task already in progress: {status}",
        }
    if status != "blocked":
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
    defer_dispatch: bool = False,
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
    if defer_dispatch:
        pending = dispatch_blockers(refreshed_task)
        append_task_event(
            task_id,
            (
                "approval_decision_recorded_deferred "
                f"action={action_category} decision={decision} by={decided_by}"
            ),
            db_path,
        )
        return {
            "task_id": task_id,
            "status": "blocked",
            "action_category": action_category,
            "decision": decision,
            "autonomy_mode": mode,
            "pending": pending,
            "review_gate": review_gate_status(task_id),
            "message": "Approval recorded; use resume to execute when ready",
        }

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
    approve_parser.add_argument(
        "--defer-dispatch",
        action="store_true",
        help="Record approval only; do not dispatch until explicit resume",
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
    review_parser.add_argument("--reason-code", default="")
    review_parser.add_argument("--checklist-json", default="{}")
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
                defer_dispatch=args.defer_dispatch,
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
                reason_code=args.reason_code,
                checklist_json=args.checklist_json,
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
