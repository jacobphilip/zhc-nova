#!/usr/bin/env python3
"""CLI-friendly SQLite task registry operations for ZHC-Nova."""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


VALID_TASK_STATUSES = {
    "requested",
    "pending",
    "approved",
    "queued",
    "running",
    "blocked",
    "succeeded",
    "failed",
    "cancelled",
    "canceled",
    "expired",
}

TERMINAL_STATUSES = {"succeeded", "failed", "cancelled", "canceled", "expired"}

ALLOWED_STATUS_TRANSITIONS: dict[str, set[str]] = {
    "requested": {"approved", "queued", "running", "blocked", "cancelled", "failed"},
    "pending": {"approved", "queued", "running", "blocked", "cancelled", "failed"},
    "approved": {"queued", "running", "blocked", "cancelled", "failed"},
    "queued": {"queued", "running", "blocked", "cancelled", "failed", "expired"},
    "running": {"running", "succeeded", "failed", "blocked", "cancelled", "expired"},
    "blocked": {
        "approved",
        "queued",
        "running",
        "succeeded",
        "failed",
        "cancelled",
        "expired",
    },
    "succeeded": {"succeeded"},
    "failed": {"failed"},
    "cancelled": {"cancelled"},
    "canceled": {"canceled"},
    "expired": {"expired"},
}

ACTIVE_LEASE_STATUSES = {"queued", "running"}
DEFAULT_LEASE_SECONDS = 120


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def utc_now_dt() -> datetime:
    return datetime.now(timezone.utc)


def parse_ts(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


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
    db_path: Path,
    task_id: str,
    status: str,
    detail: str | None,
    force: bool = False,
) -> dict[str, Any]:
    now = utc_now()
    next_status = status.strip().lower()
    if next_status not in VALID_TASK_STATUSES:
        raise ValueError(f"Invalid status: {status}")

    with connect(db_path) as conn:
        row = conn.execute(
            "SELECT status FROM tasks WHERE task_id = ?",
            (task_id,),
        ).fetchone()
        if not row:
            raise KeyError(f"Task not found: {task_id}")

        current_status = str(row["status"]).strip().lower()
        if current_status == "canceled":
            current_status = "cancelled"
        if next_status == "canceled":
            next_status = "cancelled"

        if not force:
            allowed = ALLOWED_STATUS_TRANSITIONS.get(current_status)
            if allowed is None:
                raise ValueError(
                    f"Unknown current status '{current_status}' for task {task_id}; use --force to override"
                )
            if next_status not in allowed:
                raise ValueError(
                    f"Invalid status transition for {task_id}: {current_status} -> {next_status}"
                )

        cur = conn.execute(
            "UPDATE tasks SET status = ?, updated_at = ? WHERE task_id = ?",
            (next_status, now, task_id),
        )
        if cur.rowcount == 0:
            raise KeyError(f"Task not found: {task_id}")
        append_event(conn, task_id, "status_updated", detail or next_status)
        conn.commit()
    return get_task(db_path, task_id)


def merge_task_metadata(
    db_path: Path, task_id: str, metadata_patch: dict[str, Any], detail: str
) -> dict[str, Any]:
    now = utc_now()
    with connect(db_path) as conn:
        row = conn.execute(
            "SELECT metadata_json FROM tasks WHERE task_id = ?",
            (task_id,),
        ).fetchone()
        if not row:
            raise KeyError(f"Task not found: {task_id}")

        current = json.loads(row["metadata_json"] or "{}")
        if not isinstance(current, dict):
            current = {}
        current.update(metadata_patch)

        conn.execute(
            "UPDATE tasks SET metadata_json = ?, updated_at = ? WHERE task_id = ?",
            (json.dumps(current, separators=(",", ":")), now, task_id),
        )
        append_event(conn, task_id, "metadata_updated", detail)
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


def ensure_task_exists(conn: sqlite3.Connection, task_id: str) -> None:
    row = conn.execute(
        "SELECT task_id FROM tasks WHERE task_id = ?", (task_id,)
    ).fetchone()
    if not row:
        raise KeyError(f"Task not found: {task_id}")


def get_dispatch_lease(db_path: Path, task_id: str) -> dict[str, Any]:
    with connect(db_path) as conn:
        ensure_task_exists(conn, task_id)
        row = conn.execute(
            """
            SELECT task_id, owner_id, lease_status, attempt_count, lease_expires_at,
                   heartbeat_at, last_error, created_at, updated_at
            FROM task_dispatch_lease
            WHERE task_id = ?
            """,
            (task_id,),
        ).fetchone()
    return {"task_id": task_id, "lease": dict(row) if row else None}


def list_dispatch_leases(
    db_path: Path, status: str | None = None, limit: int = 50
) -> dict[str, Any]:
    query = (
        "SELECT task_id, owner_id, lease_status, attempt_count, lease_expires_at, "
        "heartbeat_at, last_error, created_at, updated_at "
        "FROM task_dispatch_lease"
    )
    params: list[Any] = []
    if status:
        query += " WHERE lease_status = ?"
        params.append(status)
    query += " ORDER BY updated_at DESC LIMIT ?"
    params.append(limit)
    with connect(db_path) as conn:
        rows = conn.execute(query, tuple(params)).fetchall()
    return {"leases": [dict(row) for row in rows], "limit": limit, "status": status}


def enqueue_dispatch_lease(
    db_path: Path,
    task_id: str,
    owner_id: str,
    lease_seconds: int = DEFAULT_LEASE_SECONDS,
) -> dict[str, Any]:
    now_dt = utc_now_dt()
    now = now_dt.isoformat()
    expires = (now_dt + timedelta(seconds=max(1, lease_seconds))).isoformat()
    with connect(db_path) as conn:
        ensure_task_exists(conn, task_id)
        row = conn.execute(
            """
            SELECT owner_id, lease_status, attempt_count, lease_expires_at
            FROM task_dispatch_lease
            WHERE task_id = ?
            """,
            (task_id,),
        ).fetchone()
        if not row:
            conn.execute(
                """
                INSERT INTO task_dispatch_lease (
                    task_id, owner_id, lease_status, attempt_count,
                    lease_expires_at, heartbeat_at, last_error, created_at, updated_at
                ) VALUES (?, ?, 'queued', 0, ?, ?, '', ?, ?)
                """,
                (task_id, owner_id, expires, now, now, now),
            )
            append_event(conn, task_id, "lease", f"enqueue owner={owner_id}")
        else:
            status = str(row["lease_status"])
            current_exp = parse_ts(str(row["lease_expires_at"]))
            expired = not current_exp or current_exp <= now_dt
            if status in {"succeeded", "failed", "cancelled", "expired"} or expired:
                conn.execute(
                    """
                    UPDATE task_dispatch_lease
                    SET owner_id = ?, lease_status = 'queued', lease_expires_at = ?,
                        heartbeat_at = ?, updated_at = ?
                    WHERE task_id = ?
                    """,
                    (owner_id, expires, now, now, task_id),
                )
                append_event(conn, task_id, "lease", f"enqueue_reset owner={owner_id}")
            else:
                append_event(
                    conn,
                    task_id,
                    "lease",
                    (f"enqueue_noop owner={row['owner_id']} status={status}"),
                )
        conn.commit()
    return get_dispatch_lease(db_path, task_id)


def claim_dispatch_lease(
    db_path: Path,
    task_id: str,
    owner_id: str,
    lease_seconds: int = DEFAULT_LEASE_SECONDS,
) -> dict[str, Any]:
    now_dt = utc_now_dt()
    now = now_dt.isoformat()
    expires = (now_dt + timedelta(seconds=max(1, lease_seconds))).isoformat()
    with connect(db_path) as conn:
        ensure_task_exists(conn, task_id)
        row = conn.execute(
            """
            SELECT owner_id, lease_status, attempt_count, lease_expires_at
            FROM task_dispatch_lease
            WHERE task_id = ?
            """,
            (task_id,),
        ).fetchone()
        if not row:
            conn.execute(
                """
                INSERT INTO task_dispatch_lease (
                    task_id, owner_id, lease_status, attempt_count,
                    lease_expires_at, heartbeat_at, last_error, created_at, updated_at
                ) VALUES (?, ?, 'running', 1, ?, ?, '', ?, ?)
                """,
                (task_id, owner_id, expires, now, now, now),
            )
            append_event(
                conn, task_id, "lease", f"claim_new owner={owner_id} attempts=1"
            )
            conn.commit()
            return {"task_id": task_id, "claimed": True, "reason": "created"}

        status = str(row["lease_status"])
        current_owner = str(row["owner_id"])
        attempt_count = int(row["attempt_count"] or 0)
        current_exp = parse_ts(str(row["lease_expires_at"]))
        expired = not current_exp or current_exp <= now_dt

        if status == "running" and not expired and current_owner != owner_id:
            append_event(
                conn,
                task_id,
                "lease",
                f"claim_denied owner={owner_id} held_by={current_owner}",
            )
            conn.commit()
            return {
                "task_id": task_id,
                "claimed": False,
                "reason": "held_by_other_owner",
                "held_by": current_owner,
            }

        if status == "running" and not expired and current_owner == owner_id:
            conn.execute(
                """
                UPDATE task_dispatch_lease
                SET lease_expires_at = ?, heartbeat_at = ?, updated_at = ?
                WHERE task_id = ?
                """,
                (expires, now, now, task_id),
            )
            append_event(conn, task_id, "lease", f"claim_refresh owner={owner_id}")
            conn.commit()
            return {"task_id": task_id, "claimed": True, "reason": "refreshed"}

        next_attempt = attempt_count + 1
        conn.execute(
            """
            UPDATE task_dispatch_lease
            SET owner_id = ?, lease_status = 'running', attempt_count = ?,
                lease_expires_at = ?, heartbeat_at = ?, updated_at = ?
            WHERE task_id = ?
            """,
            (owner_id, next_attempt, expires, now, now, task_id),
        )
        append_event(
            conn,
            task_id,
            "lease",
            f"claim owner={owner_id} attempts={next_attempt}",
        )
        conn.commit()
    return {"task_id": task_id, "claimed": True, "reason": "claimed"}


def heartbeat_dispatch_lease(
    db_path: Path,
    task_id: str,
    owner_id: str,
    lease_seconds: int = DEFAULT_LEASE_SECONDS,
) -> dict[str, Any]:
    now_dt = utc_now_dt()
    now = now_dt.isoformat()
    expires = (now_dt + timedelta(seconds=max(1, lease_seconds))).isoformat()
    with connect(db_path) as conn:
        ensure_task_exists(conn, task_id)
        row = conn.execute(
            "SELECT owner_id, lease_status FROM task_dispatch_lease WHERE task_id = ?",
            (task_id,),
        ).fetchone()
        if not row:
            raise ValueError(f"No lease exists for task {task_id}")
        if str(row["owner_id"]) != owner_id:
            raise ValueError(f"Lease owner mismatch for task {task_id}")
        if str(row["lease_status"]) != "running":
            raise ValueError(f"Lease is not running for task {task_id}")
        conn.execute(
            """
            UPDATE task_dispatch_lease
            SET lease_expires_at = ?, heartbeat_at = ?, updated_at = ?
            WHERE task_id = ?
            """,
            (expires, now, now, task_id),
        )
        append_event(conn, task_id, "lease", f"heartbeat owner={owner_id}")
        conn.commit()
    return get_dispatch_lease(db_path, task_id)


def finish_dispatch_lease(
    db_path: Path,
    task_id: str,
    owner_id: str,
    result_status: str,
    last_error: str,
) -> dict[str, Any]:
    terminal = result_status.strip().lower()
    if terminal == "canceled":
        terminal = "cancelled"
    if terminal not in {"succeeded", "failed", "cancelled", "expired"}:
        raise ValueError(
            "result_status must be one of: succeeded, failed, cancelled, expired"
        )
    now = utc_now()
    with connect(db_path) as conn:
        ensure_task_exists(conn, task_id)
        row = conn.execute(
            "SELECT owner_id FROM task_dispatch_lease WHERE task_id = ?",
            (task_id,),
        ).fetchone()
        if not row:
            raise ValueError(f"No lease exists for task {task_id}")
        if str(row["owner_id"]) != owner_id:
            raise ValueError(f"Lease owner mismatch for task {task_id}")
        conn.execute(
            """
            UPDATE task_dispatch_lease
            SET lease_status = ?, lease_expires_at = ?, heartbeat_at = ?,
                last_error = ?, updated_at = ?
            WHERE task_id = ?
            """,
            (terminal, now, now, last_error, now, task_id),
        )
        append_event(
            conn,
            task_id,
            "lease",
            f"finish owner={owner_id} status={terminal}",
        )
        conn.commit()
    return get_dispatch_lease(db_path, task_id)


def reconcile_dispatch_leases(db_path: Path, owner_id: str) -> dict[str, Any]:
    now_dt = utc_now_dt()
    now = now_dt.isoformat()
    reconciled = 0
    with connect(db_path) as conn:
        rows = conn.execute(
            """
            SELECT task_id, lease_status, lease_expires_at
            FROM task_dispatch_lease
            WHERE lease_status IN ('queued', 'running')
            """
        ).fetchall()
        for row in rows:
            exp = parse_ts(str(row["lease_expires_at"]))
            if exp and exp > now_dt:
                continue
            task_id = str(row["task_id"])
            conn.execute(
                """
                UPDATE task_dispatch_lease
                SET owner_id = ?, lease_status = 'queued', last_error = ?, updated_at = ?
                WHERE task_id = ?
                """,
                (owner_id, "lease_expired_reconciled", now, task_id),
            )
            append_event(
                conn, task_id, "lease", f"reconcile_expired new_owner={owner_id}"
            )
            reconciled += 1
        conn.commit()
    return {"owner_id": owner_id, "reconciled": reconciled, "at": now}


def begin_idempotency(
    db_path: Path,
    key: str,
    scope: str,
    payload_hash: str,
    task_id: str | None,
) -> dict[str, Any]:
    now = utc_now()
    with connect(db_path) as conn:
        row = conn.execute(
            """
            SELECT key, scope, task_id, payload_hash, status, result_json, created_at, updated_at
            FROM idempotency_keys
            WHERE key = ?
            """,
            (key,),
        ).fetchone()

        if not row:
            conn.execute(
                """
                INSERT INTO idempotency_keys (
                    key, scope, task_id, payload_hash, status, result_json, created_at, updated_at
                ) VALUES (?, ?, ?, ?, 'processing', '', ?, ?)
                """,
                (key, scope, task_id, payload_hash, now, now),
            )
            conn.commit()
            return {
                "key": key,
                "scope": scope,
                "exists": False,
                "conflict": False,
                "status": "processing",
                "result": None,
            }

        existing_hash = str(row["payload_hash"])
        result_obj = None
        result_json = str(row["result_json"] or "")
        if result_json:
            try:
                result_obj = json.loads(result_json)
            except json.JSONDecodeError:
                result_obj = {"raw": result_json}

        if existing_hash != payload_hash:
            conn.execute(
                "UPDATE idempotency_keys SET status = 'conflict', updated_at = ? WHERE key = ?",
                (now, key),
            )
            conn.commit()
            return {
                "key": key,
                "scope": str(row["scope"]),
                "exists": True,
                "conflict": True,
                "status": "conflict",
                "result": result_obj,
            }

        return {
            "key": key,
            "scope": str(row["scope"]),
            "exists": True,
            "conflict": False,
            "status": str(row["status"]),
            "result": result_obj,
        }


def complete_idempotency(
    db_path: Path,
    key: str,
    status: str,
    result_json: str,
) -> dict[str, Any]:
    next_status = status.strip().lower()
    if next_status not in {"processing", "completed", "conflict"}:
        raise ValueError("status must be one of: processing, completed, conflict")
    now = utc_now()
    with connect(db_path) as conn:
        row = conn.execute(
            "SELECT key FROM idempotency_keys WHERE key = ?",
            (key,),
        ).fetchone()
        if not row:
            raise KeyError(f"Idempotency key not found: {key}")

        conn.execute(
            """
            UPDATE idempotency_keys
            SET status = ?, result_json = ?, updated_at = ?
            WHERE key = ?
            """,
            (next_status, result_json, now, key),
        )
        conn.commit()
    return get_idempotency(db_path, key)


def get_idempotency(db_path: Path, key: str) -> dict[str, Any]:
    with connect(db_path) as conn:
        row = conn.execute(
            """
            SELECT key, scope, task_id, payload_hash, status, result_json, created_at, updated_at
            FROM idempotency_keys
            WHERE key = ?
            """,
            (key,),
        ).fetchone()
    if not row:
        raise KeyError(f"Idempotency key not found: {key}")
    payload = dict(row)
    raw_result = str(payload.get("result_json") or "")
    if raw_result:
        try:
            payload["result"] = json.loads(raw_result)
        except json.JSONDecodeError:
            payload["result"] = {"raw": raw_result}
    else:
        payload["result"] = None
    return payload


def list_idempotency(
    db_path: Path,
    scope: str,
    limit: int,
) -> dict[str, Any]:
    with connect(db_path) as conn:
        rows = conn.execute(
            """
            SELECT key, scope, task_id, payload_hash, status, created_at, updated_at
            FROM idempotency_keys
            WHERE scope = ?
            ORDER BY updated_at DESC
            LIMIT ?
            """,
            (scope, limit),
        ).fetchall()
    return {"scope": scope, "limit": limit, "keys": [dict(row) for row in rows]}


def list_events(db_path: Path, task_id: str, limit: int = 200) -> dict[str, Any]:
    with connect(db_path) as conn:
        ensure_task_exists(conn, task_id)
        rows = conn.execute(
            """
            SELECT event_type, detail, created_at
            FROM task_events
            WHERE task_id = ?
            ORDER BY id DESC
            LIMIT ?
            """,
            (task_id, limit),
        ).fetchall()
    events = [dict(row) for row in rows]
    events.reverse()
    return {"task_id": task_id, "limit": limit, "events": events}


def trace_events(db_path: Path, trace_id: str, limit: int = 500) -> dict[str, Any]:
    pattern = f'"trace_id": "{trace_id}"'
    with connect(db_path) as conn:
        rows = conn.execute(
            """
            SELECT task_id, event_type, detail, created_at
            FROM task_events
            WHERE detail LIKE ?
            ORDER BY id DESC
            LIMIT ?
            """,
            (f"%{pattern}%", limit),
        ).fetchall()
    events = [dict(row) for row in rows]
    events.reverse()
    return {"trace_id": trace_id, "limit": limit, "events": events}


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


def telemetry_summary(db_path: Path, limit: int = 20) -> dict[str, Any]:
    with connect(db_path) as conn:
        rows = conn.execute(
            """
            SELECT task_id, task_type, route_class, status, metadata_json, created_at
            FROM tasks
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()

    tasks: list[dict[str, Any]] = []
    total_estimated_cost = 0.0
    total_dispatch_ms = 0
    counted_dispatch = 0
    total_prompt_tokens = 0
    total_completion_tokens = 0
    total_input_tokens = 0
    total_compacted_tokens = 0
    total_ratio = 0.0
    counted_ratio = 0
    cost_source_counts = {"openrouter_api": 0, "heuristic": 0, "unknown": 0}
    for row in rows:
        metadata = json.loads(row["metadata_json"] or "{}")
        dispatch_ms = int(metadata.get("dispatch_duration_ms", 0) or 0)
        est_cost = float(metadata.get("estimated_cost_usd", 0.0) or 0.0)
        est_prompt_tokens = int(metadata.get("estimated_prompt_tokens", 0) or 0)
        est_completion_tokens = int(metadata.get("estimated_completion_tokens", 0) or 0)
        context_input_tokens = int(metadata.get("context_input_tokens", 0) or 0)
        context_compacted_tokens = int(metadata.get("context_compacted_tokens", 0) or 0)
        compression_ratio = float(metadata.get("compression_ratio", 0.0) or 0.0)
        cost_source = str(metadata.get("cost_source", "unknown") or "unknown")
        if cost_source not in cost_source_counts:
            cost_source = "unknown"
        if dispatch_ms > 0:
            total_dispatch_ms += dispatch_ms
            counted_dispatch += 1
        total_prompt_tokens += est_prompt_tokens
        total_completion_tokens += est_completion_tokens
        total_input_tokens += context_input_tokens
        total_compacted_tokens += context_compacted_tokens
        if compression_ratio > 0:
            total_ratio += compression_ratio
            counted_ratio += 1
        cost_source_counts[cost_source] += 1
        total_estimated_cost += est_cost
        tasks.append(
            {
                "task_id": row["task_id"],
                "task_type": row["task_type"],
                "route_class": row["route_class"],
                "status": row["status"],
                "dispatch_duration_ms": dispatch_ms,
                "estimated_prompt_tokens": est_prompt_tokens,
                "estimated_completion_tokens": est_completion_tokens,
                "estimated_total_tokens": est_prompt_tokens + est_completion_tokens,
                "compression_ratio": round(compression_ratio, 4),
                "estimated_cost_usd": round(est_cost, 6),
                "cost_source": cost_source,
                "model_provider_hint": metadata.get("model_provider_hint", ""),
                "model_name_hint": metadata.get("model_name_hint", ""),
            }
        )

    avg_dispatch_ms = (
        int(total_dispatch_ms / counted_dispatch) if counted_dispatch else 0
    )
    return {
        "limit": limit,
        "task_count": len(tasks),
        "avg_dispatch_duration_ms": avg_dispatch_ms,
        "avg_compression_ratio": round(total_ratio / counted_ratio, 4)
        if counted_ratio
        else 0,
        "total_estimated_prompt_tokens": total_prompt_tokens,
        "total_estimated_completion_tokens": total_completion_tokens,
        "total_estimated_tokens": total_prompt_tokens + total_completion_tokens,
        "total_context_input_tokens": total_input_tokens,
        "total_context_compacted_tokens": total_compacted_tokens,
        "total_estimated_cost_usd": round(total_estimated_cost, 6),
        "cost_source_counts": cost_source_counts,
        "tasks": tasks,
    }


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
        lease = conn.execute(
            """
            SELECT task_id, owner_id, lease_status, attempt_count, lease_expires_at,
                   heartbeat_at, last_error, created_at, updated_at
            FROM task_dispatch_lease
            WHERE task_id = ?
            """,
            (task_id,),
        ).fetchone()

    task = dict(row)
    task["requires_approval"] = bool(task["requires_approval"])
    task["metadata"] = json.loads(task.pop("metadata_json") or "{}")
    task["events"] = [dict(e) for e in events]
    task["approvals"] = [dict(a) for a in approvals]
    task["dispatch_lease"] = dict(lease) if lease else None
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
    p_update.add_argument(
        "--force",
        action="store_true",
        help="Allow transition override (for controlled recovery)",
    )

    p_get = sub.add_parser("get", help="Get task details")
    p_get.add_argument("--task-id", required=True)

    p_list = sub.add_parser("list", help="List tasks")
    p_list.add_argument("--limit", type=int, default=20)

    p_telemetry = sub.add_parser("telemetry", help="Summarize task telemetry")
    p_telemetry.add_argument("--limit", type=int, default=20)

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

    p_metadata_merge = sub.add_parser(
        "metadata-merge", help="Merge metadata JSON into a task"
    )
    p_metadata_merge.add_argument("--task-id", required=True)
    p_metadata_merge.add_argument("--metadata", required=True, help="JSON object")
    p_metadata_merge.add_argument("--detail", default="metadata_merge")

    p_lease_enqueue = sub.add_parser(
        "lease-enqueue", help="Create/refresh queued lease"
    )
    p_lease_enqueue.add_argument("--task-id", required=True)
    p_lease_enqueue.add_argument("--owner-id", required=True)
    p_lease_enqueue.add_argument(
        "--lease-seconds", type=int, default=DEFAULT_LEASE_SECONDS
    )

    p_lease_claim = sub.add_parser("lease-claim", help="Claim lease for dispatch owner")
    p_lease_claim.add_argument("--task-id", required=True)
    p_lease_claim.add_argument("--owner-id", required=True)
    p_lease_claim.add_argument(
        "--lease-seconds", type=int, default=DEFAULT_LEASE_SECONDS
    )

    p_lease_heartbeat = sub.add_parser(
        "lease-heartbeat", help="Heartbeat running lease"
    )
    p_lease_heartbeat.add_argument("--task-id", required=True)
    p_lease_heartbeat.add_argument("--owner-id", required=True)
    p_lease_heartbeat.add_argument(
        "--lease-seconds", type=int, default=DEFAULT_LEASE_SECONDS
    )

    p_lease_finish = sub.add_parser(
        "lease-finish", help="Finish lease with terminal status"
    )
    p_lease_finish.add_argument("--task-id", required=True)
    p_lease_finish.add_argument("--owner-id", required=True)
    p_lease_finish.add_argument("--result-status", required=True)
    p_lease_finish.add_argument("--last-error", default="")

    p_lease_reconcile = sub.add_parser(
        "lease-reconcile", help="Reconcile expired active leases"
    )
    p_lease_reconcile.add_argument("--owner-id", required=True)

    p_lease_get = sub.add_parser("lease-get", help="Get dispatch lease for a task")
    p_lease_get.add_argument("--task-id", required=True)

    p_lease_list = sub.add_parser("lease-list", help="List dispatch leases")
    p_lease_list.add_argument("--status", default="")
    p_lease_list.add_argument("--limit", type=int, default=50)

    p_idempo_begin = sub.add_parser("idempo-begin", help="Begin/check idempotency key")
    p_idempo_begin.add_argument("--key", required=True)
    p_idempo_begin.add_argument("--scope", required=True)
    p_idempo_begin.add_argument("--payload-hash", required=True)
    p_idempo_begin.add_argument("--task-id", default="")

    p_idempo_complete = sub.add_parser(
        "idempo-complete", help="Complete idempotency key"
    )
    p_idempo_complete.add_argument("--key", required=True)
    p_idempo_complete.add_argument(
        "--status", default="completed", choices=["processing", "completed", "conflict"]
    )
    p_idempo_complete.add_argument("--result-json", default="{}")

    p_idempo_get = sub.add_parser("idempo-get", help="Get idempotency key")
    p_idempo_get.add_argument("--key", required=True)

    p_idempo_list = sub.add_parser("idempo-list", help="List idempotency keys by scope")
    p_idempo_list.add_argument("--scope", required=True)
    p_idempo_list.add_argument("--limit", type=int, default=100)

    p_events = sub.add_parser("events", help="List events for a task")
    p_events.add_argument("--task-id", required=True)
    p_events.add_argument("--limit", type=int, default=200)

    p_trace_events = sub.add_parser("trace-events", help="Find events by trace_id")
    p_trace_events.add_argument("--trace-id", required=True)
    p_trace_events.add_argument("--limit", type=int, default=500)

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
            result = update_task(
                db_path,
                args.task_id,
                args.status,
                args.detail,
                force=args.force,
            )
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

        if args.command == "telemetry":
            result = telemetry_summary(db_path, args.limit)
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

        if args.command == "metadata-merge":
            try:
                metadata_patch = json.loads(args.metadata)
            except json.JSONDecodeError as exc:
                raise ValueError(f"--metadata must be valid JSON: {exc}") from exc
            if not isinstance(metadata_patch, dict):
                raise ValueError("--metadata must decode to a JSON object")
            result = merge_task_metadata(
                db_path=db_path,
                task_id=args.task_id,
                metadata_patch=metadata_patch,
                detail=args.detail,
            )
            print_out(result, args.json)
            return 0

        if args.command == "lease-enqueue":
            result = enqueue_dispatch_lease(
                db_path,
                args.task_id,
                args.owner_id,
                args.lease_seconds,
            )
            print_out(result, args.json)
            return 0

        if args.command == "lease-claim":
            result = claim_dispatch_lease(
                db_path,
                args.task_id,
                args.owner_id,
                args.lease_seconds,
            )
            print_out(result, args.json)
            return 0

        if args.command == "lease-heartbeat":
            result = heartbeat_dispatch_lease(
                db_path,
                args.task_id,
                args.owner_id,
                args.lease_seconds,
            )
            print_out(result, args.json)
            return 0

        if args.command == "lease-finish":
            result = finish_dispatch_lease(
                db_path,
                args.task_id,
                args.owner_id,
                args.result_status,
                args.last_error,
            )
            print_out(result, args.json)
            return 0

        if args.command == "lease-reconcile":
            result = reconcile_dispatch_leases(db_path, args.owner_id)
            print_out(result, args.json)
            return 0

        if args.command == "lease-get":
            result = get_dispatch_lease(db_path, args.task_id)
            print_out(result, args.json)
            return 0

        if args.command == "lease-list":
            status = args.status.strip().lower() or None
            result = list_dispatch_leases(db_path, status, args.limit)
            print_out(result, args.json)
            return 0

        if args.command == "idempo-begin":
            result = begin_idempotency(
                db_path,
                args.key,
                args.scope,
                args.payload_hash,
                args.task_id.strip() or None,
            )
            print_out(result, args.json)
            return 0

        if args.command == "idempo-complete":
            # validate JSON early
            try:
                json.loads(args.result_json)
            except json.JSONDecodeError as exc:
                raise ValueError(f"--result-json must be valid JSON: {exc}") from exc
            result = complete_idempotency(
                db_path,
                args.key,
                args.status,
                args.result_json,
            )
            print_out(result, args.json)
            return 0

        if args.command == "idempo-get":
            result = get_idempotency(db_path, args.key)
            print_out(result, args.json)
            return 0

        if args.command == "idempo-list":
            result = list_idempotency(db_path, args.scope, args.limit)
            print_out(result, args.json)
            return 0

        if args.command == "events":
            result = list_events(db_path, args.task_id, args.limit)
            print_out(result, args.json)
            return 0

        if args.command == "trace-events":
            result = trace_events(db_path, args.trace_id, args.limit)
            print_out(result, args.json)
            return 0

        raise ValueError(f"Unknown command: {args.command}")
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
