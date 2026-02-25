#!/usr/bin/env python3
"""CLI-friendly SQLite task registry operations for ZHC-Nova."""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def default_db_path() -> Path:
    return Path(os.getenv("ZHC_TASK_DB", "storage/tasks/task_registry.db")).resolve()


def default_schema_path() -> Path:
    return Path(
        os.getenv("ZHC_TASK_SCHEMA", "shared/task-registry/schema.sql")
    ).resolve()


def connect(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def append_event(
    conn: sqlite3.Connection, task_id: str, event_type: str, detail: str
) -> None:
    conn.execute(
        "INSERT INTO task_events (task_id, event_type, detail, created_at) VALUES (?, ?, ?, ?)",
        (task_id, event_type, detail, utc_now()),
    )


def init_db(db_path: Path, schema_path: Path) -> None:
    if not schema_path.exists():
        raise FileNotFoundError(f"Schema not found: {schema_path}")
    sql = schema_path.read_text(encoding="utf-8")
    with connect(db_path) as conn:
        conn.executescript(sql)
        conn.commit()


def create_task(
    db_path: Path,
    task_id: str,
    task_type: str,
    prompt: str,
    route_class: str,
    status: str,
    requires_approval: bool,
    risk_level: str,
    assigned_worker: str | None,
    metadata: dict[str, Any] | None,
) -> dict[str, Any]:
    now = utc_now()
    meta_json = json.dumps(metadata or {}, separators=(",", ":"))
    with connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO tasks (
                task_id, task_type, prompt, route_class, status,
                requires_approval, risk_level, assigned_worker,
                created_at, updated_at, metadata_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                task_id,
                task_type,
                prompt,
                route_class,
                status,
                int(requires_approval),
                risk_level,
                assigned_worker,
                now,
                now,
                meta_json,
            ),
        )
        append_event(
            conn, task_id, "created", f"route={route_class}; risk={risk_level}"
        )
        conn.commit()
    return get_task(db_path, task_id)


def update_task(
    db_path: Path, task_id: str, status: str, detail: str | None
) -> dict[str, Any]:
    now = utc_now()
    with connect(db_path) as conn:
        cur = conn.execute(
            "UPDATE tasks SET status = ?, updated_at = ? WHERE task_id = ?",
            (status, now, task_id),
        )
        if cur.rowcount == 0:
            raise KeyError(f"Task not found: {task_id}")
        append_event(conn, task_id, "status_updated", detail or status)
        conn.commit()
    return get_task(db_path, task_id)


def request_approval(
    db_path: Path,
    task_id: str,
    action_category: str,
    requested_by: str,
    note: str,
) -> dict[str, Any]:
    now = utc_now()
    with connect(db_path) as conn:
        task_row = conn.execute(
            "SELECT task_id FROM tasks WHERE task_id = ?",
            (task_id,),
        ).fetchone()
        if not task_row:
            raise KeyError(f"Task not found: {task_id}")

        row = conn.execute(
            """
            SELECT id, status
            FROM approvals
            WHERE task_id = ? AND action_category = ?
            ORDER BY id DESC
            LIMIT 1
            """,
            (task_id, action_category),
        ).fetchone()

        if not row:
            conn.execute(
                """
                INSERT INTO approvals (
                    task_id, action_category, status, requested_by,
                    decision_note, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (task_id, action_category, "required", requested_by, note, now, now),
            )
            append_event(
                conn,
                task_id,
                "approval_requested",
                f"action={action_category}; by={requested_by}; note={note}",
            )
        elif row["status"] == "required":
            conn.execute(
                """
                UPDATE approvals
                SET requested_by = ?, decision_note = ?, updated_at = ?
                WHERE id = ?
                """,
                (requested_by, note, now, row["id"]),
            )
            append_event(
                conn,
                task_id,
                "approval_requested",
                f"action={action_category}; refreshed_by={requested_by}; note={note}",
            )
        else:
            append_event(
                conn,
                task_id,
                "approval_requested",
                f"action={action_category}; existing_status={row['status']}",
            )
        conn.commit()
    return get_approvals(db_path, task_id)


def decide_approval(
    db_path: Path,
    task_id: str,
    action_category: str,
    decision: str,
    decided_by: str,
    note: str,
) -> dict[str, Any]:
    now = utc_now()
    if decision not in {"approved", "rejected"}:
        raise ValueError("decision must be one of: approved, rejected")

    with connect(db_path) as conn:
        task_row = conn.execute(
            "SELECT task_id FROM tasks WHERE task_id = ?",
            (task_id,),
        ).fetchone()
        if not task_row:
            raise KeyError(f"Task not found: {task_id}")

        row = conn.execute(
            """
            SELECT id, status
            FROM approvals
            WHERE task_id = ? AND action_category = ?
            ORDER BY id DESC
            LIMIT 1
            """,
            (task_id, action_category),
        ).fetchone()

        if not row:
            conn.execute(
                """
                INSERT INTO approvals (
                    task_id, action_category, status, requested_by,
                    decided_by, decision_note, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    task_id,
                    action_category,
                    "required",
                    "auto_created",
                    None,
                    "",
                    now,
                    now,
                ),
            )
            row = conn.execute(
                """
                SELECT id, status
                FROM approvals
                WHERE task_id = ? AND action_category = ?
                ORDER BY id DESC
                LIMIT 1
                """,
                (task_id, action_category),
            ).fetchone()

        if row["status"] in {"approved", "rejected", "cancelled"}:
            if row["status"] == decision:
                append_event(
                    conn,
                    task_id,
                    "approval_decision",
                    f"action={action_category}; decision={decision}; no_op=true",
                )
                conn.commit()
                return get_approvals(db_path, task_id)
            raise ValueError(
                f"Approval already decided as {row['status']} for action {action_category}"
            )

        conn.execute(
            """
            UPDATE approvals
            SET status = ?, decided_by = ?, decision_note = ?, updated_at = ?
            WHERE id = ?
            """,
            (decision, decided_by, note, now, row["id"]),
        )
        append_event(
            conn,
            task_id,
            "approval_decision",
            f"action={action_category}; decision={decision}; by={decided_by}; note={note}",
        )
        conn.commit()

    return get_approvals(db_path, task_id)


def get_approvals(db_path: Path, task_id: str) -> dict[str, Any]:
    with connect(db_path) as conn:
        task_row = conn.execute(
            "SELECT task_id FROM tasks WHERE task_id = ?",
            (task_id,),
        ).fetchone()
        if not task_row:
            raise KeyError(f"Task not found: {task_id}")
        rows = conn.execute(
            """
            SELECT id, task_id, action_category, status, requested_by,
                   decided_by, decision_note, created_at, updated_at
            FROM approvals
            WHERE task_id = ?
            ORDER BY id ASC
            """,
            (task_id,),
        ).fetchall()
    return {"task_id": task_id, "approvals": [dict(row) for row in rows]}


def list_tasks(db_path: Path, limit: int = 20) -> list[dict[str, Any]]:
    with connect(db_path) as conn:
        rows = conn.execute(
            """
            SELECT task_id, task_type, route_class, status, requires_approval,
                   risk_level, assigned_worker, created_at, updated_at
            FROM tasks
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    return [dict(row) for row in rows]


def get_task(db_path: Path, task_id: str) -> dict[str, Any]:
    with connect(db_path) as conn:
        row = conn.execute(
            "SELECT * FROM tasks WHERE task_id = ?",
            (task_id,),
        ).fetchone()
        if not row:
            raise KeyError(f"Task not found: {task_id}")
        events = conn.execute(
            "SELECT event_type, detail, created_at FROM task_events WHERE task_id = ? ORDER BY id ASC",
            (task_id,),
        ).fetchall()
        approvals = conn.execute(
            """
            SELECT action_category, status, requested_by, decided_by,
                   decision_note, created_at, updated_at
            FROM approvals
            WHERE task_id = ?
            ORDER BY id ASC
            """,
            (task_id,),
        ).fetchall()

    task = dict(row)
    task["requires_approval"] = bool(task["requires_approval"])
    task["metadata"] = json.loads(task.pop("metadata_json") or "{}")
    task["events"] = [dict(e) for e in events]
    task["approvals"] = [dict(a) for a in approvals]
    return task


def print_out(payload: Any, as_json: bool) -> None:
    if as_json:
        print(json.dumps(payload, indent=2, sort_keys=True))
        return
    if isinstance(payload, list):
        for item in payload:
            print(
                f"{item['task_id']} {item['status']} {item['route_class']} "
                f"type={item['task_type']} risk={item['risk_level']}"
            )
        return
    print(json.dumps(payload, indent=2, sort_keys=True))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="ZHC-Nova task registry CLI")
    parser.add_argument("--db", default=str(default_db_path()), help="SQLite DB path")
    parser.add_argument(
        "--schema", default=str(default_schema_path()), help="SQL schema path"
    )
    parser.add_argument("--json", action="store_true", help="Output JSON")

    sub = parser.add_subparsers(dest="command", required=True)

    p_init = sub.add_parser("init", help="Initialize DB schema")
    p_init.set_defaults(command="init")

    p_create = sub.add_parser("create", help="Create a task")
    p_create.add_argument("--task-id", required=True)
    p_create.add_argument("--task-type", required=True)
    p_create.add_argument("--prompt", required=True)
    p_create.add_argument("--route-class", required=True)
    p_create.add_argument("--status", default="pending")
    p_create.add_argument("--requires-approval", action="store_true")
    p_create.add_argument("--risk-level", default="low")
    p_create.add_argument("--assigned-worker")
    p_create.add_argument("--metadata", default="{}", help="JSON object")

    p_update = sub.add_parser("update", help="Update task status")
    p_update.add_argument("--task-id", required=True)
    p_update.add_argument("--status", required=True)
    p_update.add_argument("--detail", default="")

    p_get = sub.add_parser("get", help="Get task details")
    p_get.add_argument("--task-id", required=True)

    p_list = sub.add_parser("list", help="List tasks")
    p_list.add_argument("--limit", type=int, default=20)

    p_approval_request = sub.add_parser(
        "approval-request", help="Create or refresh an approval request"
    )
    p_approval_request.add_argument("--task-id", required=True)
    p_approval_request.add_argument("--action-category", required=True)
    p_approval_request.add_argument("--requested-by", default="system")
    p_approval_request.add_argument("--note", default="")

    p_approval_decide = sub.add_parser(
        "approval-decide", help="Decide an approval request"
    )
    p_approval_decide.add_argument("--task-id", required=True)
    p_approval_decide.add_argument("--action-category", required=True)
    p_approval_decide.add_argument(
        "--decision", choices=["approved", "rejected"], required=True
    )
    p_approval_decide.add_argument("--decided-by", required=True)
    p_approval_decide.add_argument("--note", default="")

    p_approval_list = sub.add_parser("approval-list", help="List approvals for a task")
    p_approval_list.add_argument("--task-id", required=True)

    return parser.parse_args()


def main() -> int:
    args = parse_args()
    db_path = Path(args.db).resolve()
    schema_path = Path(args.schema).resolve()

    try:
        if args.command == "init":
            init_db(db_path, schema_path)
            print(f"Initialized DB: {db_path}")
            return 0

        if not db_path.exists():
            init_db(db_path, schema_path)

        if args.command == "create":
            try:
                metadata = json.loads(args.metadata)
            except json.JSONDecodeError as exc:
                raise ValueError(f"--metadata must be valid JSON: {exc}") from exc
            result = create_task(
                db_path=db_path,
                task_id=args.task_id,
                task_type=args.task_type,
                prompt=args.prompt,
                route_class=args.route_class,
                status=args.status,
                requires_approval=args.requires_approval,
                risk_level=args.risk_level,
                assigned_worker=args.assigned_worker,
                metadata=metadata,
            )
            print_out(result, args.json)
            return 0

        if args.command == "update":
            result = update_task(db_path, args.task_id, args.status, args.detail)
            print_out(result, args.json)
            return 0

        if args.command == "get":
            result = get_task(db_path, args.task_id)
            print_out(result, args.json)
            return 0

        if args.command == "list":
            result = list_tasks(db_path, args.limit)
            print_out(result, args.json)
            return 0

        if args.command == "approval-request":
            result = request_approval(
                db_path=db_path,
                task_id=args.task_id,
                action_category=args.action_category,
                requested_by=args.requested_by,
                note=args.note,
            )
            print_out(result, args.json)
            return 0

        if args.command == "approval-decide":
            result = decide_approval(
                db_path=db_path,
                task_id=args.task_id,
                action_category=args.action_category,
                decision=args.decision,
                decided_by=args.decided_by,
                note=args.note,
            )
            print_out(result, args.json)
            return 0

        if args.command == "approval-list":
            result = get_approvals(db_path, args.task_id)
            print_out(result, args.json)
            return 0

        raise ValueError(f"Unknown command: {args.command}")
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
