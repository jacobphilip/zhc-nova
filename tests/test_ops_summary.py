#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import runpy
import sqlite3
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REGISTRY_PATH = ROOT / "shared/task-registry/task_registry.py"


class OpsSummaryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.tmp_path = Path(self.tmp.name)
        self.db = self.tmp_path / "task_registry.db"
        self.storage = self.tmp_path / "storage"
        (self.storage / "memory").mkdir(parents=True, exist_ok=True)

        self.registry = runpy.run_path(str(REGISTRY_PATH))
        self.registry["init_db"](self.db, ROOT / "shared/task-registry/schema.sql")

        self._env_backup = dict(os.environ)
        os.environ["ZHC_STORAGE_ROOT"] = str(self.storage)

    def tearDown(self) -> None:
        os.environ.clear()
        os.environ.update(self._env_backup)
        self.tmp.cleanup()

    def _create_task(self, task_id: str, status: str = "blocked") -> None:
        self.registry["create_task"](
            self.db,
            task_id,
            "code_refactor",
            "ops summary test",
            "UBUNTU_HEAVY",
            status,
            True,
            "medium",
            None,
            {},
        )

    def test_ops_summary_healthy_baseline(self) -> None:
        self._create_task("task-ops-healthy", "blocked")
        summary = self.registry["ops_summary"](self.db, 24)
        self.assertEqual(summary["status"], "healthy")
        self.assertEqual(summary["leases"]["stale"], 0)
        self.assertEqual(summary["idempotency"]["conflict_window"], 0)

    def test_ops_summary_degraded_on_stale_lease(self) -> None:
        task_id = "task-ops-stale"
        self._create_task(task_id, "running")
        self.registry["enqueue_dispatch_lease"](self.db, task_id, "owner-a", 120)
        self.registry["claim_dispatch_lease"](self.db, task_id, "owner-a", 120)

        with sqlite3.connect(self.db) as conn:
            conn.execute(
                "UPDATE task_dispatch_lease SET lease_expires_at = '2000-01-01T00:00:00+00:00' WHERE task_id = ?",
                (task_id,),
            )
            conn.commit()

        summary = self.registry["ops_summary"](self.db, 24)
        self.assertEqual(summary["status"], "degraded")
        self.assertGreater(summary["leases"]["stale"], 0)
        self.assertIn("stale_lease_present", summary["reasons"])

    def test_ops_summary_degraded_on_idempotency_conflict(self) -> None:
        self.registry["begin_idempotency"](
            self.db,
            "tg_update:9001",
            "telegram_command",
            "hash-a",
            None,
        )
        self.registry["begin_idempotency"](
            self.db,
            "tg_update:9001",
            "telegram_command",
            "hash-b",
            None,
        )

        summary = self.registry["ops_summary"](self.db, 24)
        self.assertEqual(summary["status"], "degraded")
        self.assertGreater(summary["idempotency"]["conflict_window"], 0)
        self.assertIn("idempotency_conflicts_detected", summary["reasons"])

    def test_ops_summary_degraded_on_dispatch_timeout_event(self) -> None:
        self._create_task("task-ops-timeout", "failed")
        with sqlite3.connect(self.db) as conn:
            conn.execute(
                "INSERT INTO task_events (task_id, event_type, detail, created_at) VALUES (?, 'router', ?, ?)",
                (
                    "task-ops-timeout",
                    "dispatch_timeout after 900s",
                    self.registry["utc_now"](),
                ),
            )
            conn.commit()

        audit_path = self.storage / "memory" / "telegram_command_audit.jsonl"
        audit_path.write_text(
            json.dumps({"ts": self.registry["utc_now"](), "status": "command_timeout"})
            + "\n",
            encoding="utf-8",
        )

        summary = self.registry["ops_summary"](self.db, 24)
        self.assertEqual(summary["status"], "degraded")
        self.assertGreater(summary["timeouts"]["dispatch_window"], 0)
        self.assertGreater(summary["timeouts"]["command_window"], 0)


if __name__ == "__main__":
    unittest.main()
