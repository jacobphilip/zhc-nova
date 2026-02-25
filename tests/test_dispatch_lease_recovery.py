#!/usr/bin/env python3
from __future__ import annotations

import runpy
import tempfile
import time
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REGISTRY_PATH = ROOT / "shared/task-registry/task_registry.py"


class DispatchLeaseRecoveryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.tmp_path = Path(self.tmp.name)
        self.db = self.tmp_path / "task_registry.db"
        self.schema = ROOT / "shared/task-registry/schema.sql"

        self.registry = runpy.run_path(str(REGISTRY_PATH))
        self.registry["init_db"](self.db, self.schema)

        self.task_id = "task-lease-1"
        self.registry["create_task"](
            self.db,
            self.task_id,
            "code_refactor",
            "lease recovery test",
            "UBUNTU_HEAVY",
            "blocked",
            True,
            "medium",
            None,
            {},
        )

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_claim_denied_for_active_other_owner(self) -> None:
        self.registry["enqueue_dispatch_lease"](self.db, self.task_id, "owner-a", 120)
        claim_a = self.registry["claim_dispatch_lease"](
            self.db, self.task_id, "owner-a", 120
        )
        self.assertTrue(claim_a["claimed"])

        claim_b = self.registry["claim_dispatch_lease"](
            self.db, self.task_id, "owner-b", 120
        )
        self.assertFalse(claim_b["claimed"])
        self.assertEqual(claim_b["reason"], "held_by_other_owner")

    def test_expired_running_lease_reclaims_with_attempt_increment(self) -> None:
        self.registry["enqueue_dispatch_lease"](self.db, self.task_id, "owner-a", 1)
        first = self.registry["claim_dispatch_lease"](
            self.db, self.task_id, "owner-a", 1
        )
        self.assertTrue(first["claimed"])

        time.sleep(1.2)
        self.registry["reconcile_dispatch_leases"](self.db, "owner-b")
        second = self.registry["claim_dispatch_lease"](
            self.db, self.task_id, "owner-b", 120
        )
        self.assertTrue(second["claimed"])

        lease = self.registry["get_dispatch_lease"](self.db, self.task_id)["lease"]
        self.assertEqual(lease["owner_id"], "owner-b")
        self.assertEqual(lease["lease_status"], "running")
        self.assertEqual(int(lease["attempt_count"]), 2)

    def test_finish_records_terminal_and_last_error(self) -> None:
        self.registry["enqueue_dispatch_lease"](self.db, self.task_id, "owner-a", 120)
        self.registry["claim_dispatch_lease"](self.db, self.task_id, "owner-a", 120)
        self.registry["finish_dispatch_lease"](
            self.db,
            self.task_id,
            "owner-a",
            "failed",
            "simulated_failure",
        )

        lease = self.registry["get_dispatch_lease"](self.db, self.task_id)["lease"]
        self.assertEqual(lease["lease_status"], "failed")
        self.assertEqual(lease["last_error"], "simulated_failure")
        self.assertEqual(int(lease["attempt_count"]), 1)


if __name__ == "__main__":
    unittest.main()
