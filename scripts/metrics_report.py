#!/usr/bin/env python3
"""Generate closed-loop operational metrics for ZHC-Nova."""

from __future__ import annotations

import argparse
import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from statistics import median
from typing import Any


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def parse_ts(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def percentile(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    if len(values) == 1:
        return values[0]
    sorted_vals = sorted(values)
    idx = int(round((len(sorted_vals) - 1) * p))
    idx = max(0, min(idx, len(sorted_vals) - 1))
    return sorted_vals[idx]


def default_db_path() -> Path:
    return Path("storage/tasks/task_registry.db").resolve()


def default_audit_log_path() -> Path:
    return Path("storage/memory/telegram_command_audit.jsonl").resolve()


@dataclass
class Window:
    start: datetime
    end: datetime


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate closed-loop metrics report")
    parser.add_argument("--db", default=str(default_db_path()), help="SQLite DB path")
    parser.add_argument(
        "--audit-log",
        default=str(default_audit_log_path()),
        help="Telegram command audit log path",
    )
    parser.add_argument("--days", type=int, default=7, help="Window size in days")
    parser.add_argument(
        "--limit-tasks",
        type=int,
        default=500,
        help="Max tasks to include from window",
    )
    parser.add_argument("--iteration", default="latest", help="Iteration label")
    parser.add_argument("--output-md", required=True, help="Markdown output path")
    parser.add_argument("--output-json", required=True, help="JSON output path")
    return parser.parse_args()


def connect(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def fetch_tasks(
    conn: sqlite3.Connection, window: Window, limit: int
) -> list[sqlite3.Row]:
    return conn.execute(
        """
        SELECT task_id, task_type, route_class, status, risk_level, created_at, updated_at, metadata_json
        FROM tasks
        WHERE created_at >= ? AND created_at <= ?
        ORDER BY created_at DESC
        LIMIT ?
        """,
        (window.start.isoformat(), window.end.isoformat(), limit),
    ).fetchall()


def fetch_policy_block_events(
    conn: sqlite3.Connection, window: Window
) -> list[sqlite3.Row]:
    return conn.execute(
        """
        SELECT detail
        FROM task_events
        WHERE created_at >= ? AND created_at <= ?
          AND event_type = 'router'
          AND detail LIKE 'policy_block reason=%'
        ORDER BY created_at DESC
        """,
        (window.start.isoformat(), window.end.isoformat()),
    ).fetchall()


def fetch_approvals(conn: sqlite3.Connection, window: Window) -> list[sqlite3.Row]:
    return conn.execute(
        """
        SELECT task_id, status, created_at, updated_at
        FROM approvals
        WHERE created_at >= ? AND created_at <= ?
        ORDER BY created_at DESC
        """,
        (window.start.isoformat(), window.end.isoformat()),
    ).fetchall()


def fetch_review_events(conn: sqlite3.Connection, window: Window) -> list[sqlite3.Row]:
    return conn.execute(
        """
        SELECT task_id, detail, created_at
        FROM task_events
        WHERE created_at >= ? AND created_at <= ?
          AND event_type = 'router'
          AND (
              detail = 'review_gate_pending'
              OR detail LIKE 'reviewer_artifact_recorded verdict=%'
          )
        ORDER BY created_at ASC
        """,
        (window.start.isoformat(), window.end.isoformat()),
    ).fetchall()


def parse_policy_reason(detail: str) -> str:
    prefix = "policy_block reason="
    if not detail.startswith(prefix):
        return "unknown"
    return detail[len(prefix) :].strip() or "unknown"


def load_telegram_audit(path: Path, window: Window) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        ts = parse_ts(str(payload.get("ts", "")))
        if not ts:
            continue
        if ts < window.start or ts > window.end:
            continue
        rows.append(payload)
    return rows


def summarize(
    tasks: list[sqlite3.Row],
    policy_events: list[sqlite3.Row],
    approvals: list[sqlite3.Row],
    review_events: list[sqlite3.Row],
    telegram_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    status_counts: dict[str, int] = {}
    route_counts: dict[str, int] = {}
    risk_counts: dict[str, int] = {}

    dispatch_ms_values: list[float] = []
    total_cost = 0.0
    total_tokens = 0
    compression_ratios: list[float] = []
    cost_source_counts: dict[str, int] = {
        "openrouter_api": 0,
        "heuristic": 0,
        "unknown": 0,
    }

    heavy_task_count = 0
    heavy_gate_pass = 0
    heavy_gate_missing = 0
    heavy_gate_fail = 0
    review_reason_counts: dict[str, int] = {}
    review_schema_complete_count = 0
    review_fail_then_pass_count = 0

    for row in tasks:
        status = str(row["status"])
        route = str(row["route_class"])
        risk = str(row["risk_level"])
        status_counts[status] = status_counts.get(status, 0) + 1
        route_counts[route] = route_counts.get(route, 0) + 1
        risk_counts[risk] = risk_counts.get(risk, 0) + 1

        metadata = json.loads(row["metadata_json"] or "{}")
        dispatch_ms = float(metadata.get("dispatch_duration_ms", 0) or 0)
        if dispatch_ms > 0:
            dispatch_ms_values.append(dispatch_ms)
        total_cost += float(metadata.get("estimated_cost_usd", 0.0) or 0.0)
        total_tokens += int(metadata.get("estimated_total_tokens", 0) or 0)
        ratio = float(metadata.get("compression_ratio", 0.0) or 0.0)
        if ratio > 0:
            compression_ratios.append(ratio)

        cost_source = str(metadata.get("cost_source", "unknown") or "unknown")
        if cost_source not in cost_source_counts:
            cost_source = "unknown"
        cost_source_counts[cost_source] += 1

        if route == "UBUNTU_HEAVY":
            heavy_task_count += 1
            review_path = (
                Path("storage/tasks") / str(row["task_id"]) / "artifacts/reviewer.json"
            )
            reviewer_status = "missing"
            if review_path.exists():
                try:
                    payload = json.loads(review_path.read_text(encoding="utf-8"))
                    reviewer_status = (
                        str(payload.get("verdict", "missing")).lower().strip()
                    )
                    reason_code = str(payload.get("reason_code", "") or "")
                    if reason_code:
                        review_reason_counts[reason_code] = (
                            review_reason_counts.get(reason_code, 0) + 1
                        )
                    checklist = payload.get("checklist", {})
                    if isinstance(checklist, dict) and all(
                        isinstance(checklist.get(k), bool)
                        for k in (
                            "policy_safety",
                            "correctness",
                            "tests",
                            "rollback",
                            "approval_constraints",
                        )
                    ):
                        review_schema_complete_count += 1
                except json.JSONDecodeError:
                    reviewer_status = "invalid"
            if reviewer_status == "pass":
                heavy_gate_pass += 1
            elif reviewer_status == "fail":
                heavy_gate_fail += 1
            else:
                heavy_gate_missing += 1

    policy_reason_counts: dict[str, int] = {}
    for row in policy_events:
        reason = parse_policy_reason(str(row["detail"]))
        policy_reason_counts[reason] = policy_reason_counts.get(reason, 0) + 1

    approval_status_counts: dict[str, int] = {}
    approval_latency_minutes: list[float] = []
    for row in approvals:
        status = str(row["status"])
        approval_status_counts[status] = approval_status_counts.get(status, 0) + 1
        if status in {"approved", "rejected"}:
            start = parse_ts(str(row["created_at"]))
            end = parse_ts(str(row["updated_at"]))
            if start and end and end >= start:
                approval_latency_minutes.append((end - start).total_seconds() / 60.0)

    pending_ts: dict[str, datetime] = {}
    gate_latency_minutes: list[float] = []
    review_timeline: dict[str, list[str]] = {}
    for row in review_events:
        task_id = str(row["task_id"])
        detail = str(row["detail"])
        ts = parse_ts(str(row["created_at"]))
        if not ts:
            continue
        if detail.startswith("reviewer_artifact_recorded verdict="):
            if "verdict=fail" in detail:
                review_timeline.setdefault(task_id, []).append("fail")
            elif "verdict=pass" in detail:
                review_timeline.setdefault(task_id, []).append("pass")
        if detail == "review_gate_pending":
            pending_ts[task_id] = ts
            continue
        if (
            detail.startswith("reviewer_artifact_recorded verdict=pass")
            and task_id in pending_ts
        ):
            start = pending_ts[task_id]
            if ts >= start:
                gate_latency_minutes.append((ts - start).total_seconds() / 60.0)

    for timeline in review_timeline.values():
        if (
            "fail" in timeline
            and "pass" in timeline
            and timeline.index("fail") < timeline.index("pass")
        ):
            review_fail_then_pass_count += 1

    command_counts: dict[str, int] = {}
    command_status_counts: dict[str, dict[str, int]] = {}
    telegram_status_counts: dict[str, int] = {}
    for row in telegram_rows:
        status = str(row.get("status", "unknown"))
        telegram_status_counts[status] = telegram_status_counts.get(status, 0) + 1
        text = str(row.get("text", "")).strip()
        if text.startswith("/"):
            cmd = text.split()[0].split("@", 1)[0].lower()
            command_counts[cmd] = command_counts.get(cmd, 0) + 1
            cmd_bucket = command_status_counts.setdefault(cmd, {})
            cmd_bucket[status] = cmd_bucket.get(status, 0) + 1

    telegram_total = len(telegram_rows)
    telegram_error = telegram_status_counts.get("error", 0)
    telegram_timeout = telegram_status_counts.get("command_timeout", 0)
    poll_error_count = telegram_status_counts.get("poll_error", 0)
    telegram_ok = telegram_status_counts.get("ok", 0)

    return {
        "task_flow": {
            "task_count": len(tasks),
            "status_counts": status_counts,
            "route_counts": route_counts,
            "risk_counts": risk_counts,
        },
        "policy": {
            "policy_block_count": len(policy_events),
            "policy_reason_counts": policy_reason_counts,
        },
        "approvals": {
            "approval_status_counts": approval_status_counts,
            "median_approval_latency_minutes": round(
                median(approval_latency_minutes), 2
            )
            if approval_latency_minutes
            else 0,
            "p90_approval_latency_minutes": round(
                percentile(approval_latency_minutes, 0.90), 2
            )
            if approval_latency_minutes
            else 0,
        },
        "review_gate": {
            "heavy_task_count": heavy_task_count,
            "gate_pass_count": heavy_gate_pass,
            "gate_fail_count": heavy_gate_fail,
            "gate_missing_count": heavy_gate_missing,
            "review_reason_counts": review_reason_counts,
            "review_schema_complete_count": review_schema_complete_count,
            "review_schema_complete_rate": round(
                review_schema_complete_count / heavy_task_count, 4
            )
            if heavy_task_count
            else 0,
            "fail_then_pass_count": review_fail_then_pass_count,
            "gate_pass_rate": round(heavy_gate_pass / heavy_task_count, 4)
            if heavy_task_count
            else 0,
            "median_gate_latency_minutes": round(median(gate_latency_minutes), 2)
            if gate_latency_minutes
            else 0,
            "p90_gate_latency_minutes": round(percentile(gate_latency_minutes, 0.90), 2)
            if gate_latency_minutes
            else 0,
        },
        "telemetry": {
            "avg_dispatch_duration_ms": round(
                sum(dispatch_ms_values) / len(dispatch_ms_values), 2
            )
            if dispatch_ms_values
            else 0,
            "p90_dispatch_duration_ms": round(percentile(dispatch_ms_values, 0.90), 2)
            if dispatch_ms_values
            else 0,
            "avg_estimated_tokens": round(total_tokens / len(tasks), 2) if tasks else 0,
            "total_estimated_tokens": total_tokens,
            "total_estimated_cost_usd": round(total_cost, 6),
            "avg_estimated_cost_usd": round(total_cost / len(tasks), 6) if tasks else 0,
            "avg_compression_ratio": round(
                sum(compression_ratios) / len(compression_ratios), 4
            )
            if compression_ratios
            else 0,
            "cost_source_counts": cost_source_counts,
        },
        "telegram": {
            "command_count": sum(command_counts.values()),
            "command_counts": command_counts,
            "command_status_counts": command_status_counts,
            "status_counts": telegram_status_counts,
            "success_rate": round(telegram_ok / telegram_total, 4)
            if telegram_total
            else 0,
            "error_rate": round((telegram_error + telegram_timeout) / telegram_total, 4)
            if telegram_total
            else 0,
            "unauthorized_count": telegram_status_counts.get("unauthorized", 0),
            "poll_error_count": poll_error_count,
            "command_timeout_count": telegram_timeout,
        },
    }


def recommendations(summary: dict[str, Any]) -> list[str]:
    out: list[str] = []
    policy_blocks = summary["policy"]["policy_block_count"]
    if policy_blocks > 0:
        out.append(
            "Tune execution policy allowlists/keywords to reduce unnecessary policy blocks."
        )

    review_pass_rate = float(summary["review_gate"]["gate_pass_rate"])
    if summary["review_gate"]["heavy_task_count"] > 0 and review_pass_rate < 0.8:
        out.append(
            "Improve planner/reviewer quality: increase gate pass rate above 80%."
        )

    if float(summary["review_gate"]["review_schema_complete_rate"]) < 0.9:
        out.append(
            "Enforce complete reviewer checklist schema on all heavy-task reviews."
        )

    if float(summary["telegram"]["error_rate"]) > 0.1:
        out.append(
            "Reduce Telegram command error rate with stricter input validation/help hints."
        )

    if int(summary["telegram"]["poll_error_count"]) > 0:
        out.append(
            "Stabilize Telegram polling loop and restart behavior to reduce poll errors."
        )

    openrouter_count = int(
        summary["telemetry"]["cost_source_counts"].get("openrouter_api", 0)
    )
    heuristic_count = int(
        summary["telemetry"]["cost_source_counts"].get("heuristic", 0)
    )
    if openrouter_count == 0:
        out.append(
            "Enable OpenRouter pricing enrichment to improve cost signal quality."
        )
    elif heuristic_count > openrouter_count:
        out.append(
            "Increase OpenRouter-enriched pricing coverage; heuristic pricing still dominates."
        )

    if float(summary["telemetry"]["avg_compression_ratio"]) >= 0.9:
        out.append(
            "Improve context compaction effectiveness (target lower average compression ratio)."
        )

    if not out:
        out.append(
            "Maintain current controls and continue per-iteration metrics/audit cadence."
        )
    return out[:5]


def render_markdown(
    iteration: str, window: Window, summary: dict[str, Any], actions: list[str]
) -> str:
    lines: list[str] = []
    lines.append(f"# ZHC-Nova Metrics Report - {iteration}")
    lines.append("")
    lines.append(f"- Generated: {utc_now().isoformat()}")
    lines.append(f"- Window: {window.start.isoformat()} -> {window.end.isoformat()}")
    lines.append("")

    flow = summary["task_flow"]
    policy = summary["policy"]
    approvals = summary["approvals"]
    gate = summary["review_gate"]
    telemetry = summary["telemetry"]
    telegram = summary["telegram"]

    lines.append("## KPI Summary")
    lines.append("")
    lines.append(f"- Tasks: {flow['task_count']} (status: {flow['status_counts']})")
    lines.append(
        f"- Policy blocks: {policy['policy_block_count']} ({policy['policy_reason_counts']})"
    )
    lines.append(
        f"- Approval latency: median={approvals['median_approval_latency_minutes']}m p90={approvals['p90_approval_latency_minutes']}m"
    )
    lines.append(
        "- Review gate: "
        f"pass_rate={gate['gate_pass_rate']} pass={gate['gate_pass_count']} fail={gate['gate_fail_count']} "
        f"missing={gate['gate_missing_count']} schema_complete_rate={gate['review_schema_complete_rate']} "
        f"fail_then_pass={gate['fail_then_pass_count']}"
    )
    lines.append(
        f"- Telemetry: avg_dispatch_ms={telemetry['avg_dispatch_duration_ms']} total_cost_usd={telemetry['total_estimated_cost_usd']} total_tokens={telemetry['total_estimated_tokens']}"
    )
    lines.append(
        "- Telegram: "
        f"success_rate={telegram['success_rate']} error_rate={telegram['error_rate']} "
        f"unauthorized={telegram['unauthorized_count']} poll_errors={telegram['poll_error_count']} "
        f"timeouts={telegram['command_timeout_count']}"
    )
    lines.append("")

    lines.append("## Top 5 Next Actions")
    lines.append("")
    for action in actions:
        lines.append(f"- {action}")
    lines.append("")
    return "\n".join(lines) + "\n"


def main() -> int:
    args = parse_args()
    db_path = Path(args.db).resolve()
    audit_log_path = Path(args.audit_log).resolve()
    output_md = Path(args.output_md).resolve()
    output_json = Path(args.output_json).resolve()

    end = utc_now()
    start = end - timedelta(days=max(1, args.days))
    window = Window(start=start, end=end)

    with connect(db_path) as conn:
        tasks = fetch_tasks(conn, window, args.limit_tasks)
        policy_events = fetch_policy_block_events(conn, window)
        approvals = fetch_approvals(conn, window)
        review_events = fetch_review_events(conn, window)

    telegram_rows = load_telegram_audit(audit_log_path, window)
    summary = summarize(tasks, policy_events, approvals, review_events, telegram_rows)
    actions = recommendations(summary)

    payload = {
        "generated_at": utc_now().isoformat(),
        "iteration": args.iteration,
        "window": {"start": window.start.isoformat(), "end": window.end.isoformat()},
        "summary": summary,
        "actions": actions,
    }

    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_md.parent.mkdir(parents=True, exist_ok=True)
    output_json.write_text(
        json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8"
    )
    output_md.write_text(
        render_markdown(args.iteration, window, summary, actions), encoding="utf-8"
    )

    print(f"Wrote metrics json: {output_json}")
    print(f"Wrote metrics md: {output_md}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
