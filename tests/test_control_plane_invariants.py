#!/usr/bin/env python3
from __future__ import annotations

import os
import runpy
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REGISTRY_PATH = ROOT / "shared/task-registry/task_registry.py"
ROUTER_PATH = ROOT / "services/task-router/router.py"


class ControlPlaneInvariantTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.tmp_path = Path(self.tmp.name)
        self.db = self.tmp_path / "task_registry.db"
        self.schema = ROOT / "shared/task-registry/schema.sql"
        self.storage = self.tmp_path / "storage"
        self.storage.mkdir(parents=True, exist_ok=True)

        self.registry = runpy.run_path(str(REGISTRY_PATH))
        self.router = runpy.run_path(str(ROUTER_PATH))

        self.registry["init_db"](self.db, self.schema)

        self._env_backup = dict(os.environ)
        os.environ["ZHC_TASK_DB"] = str(self.db)
        os.environ["ZHC_STORAGE_ROOT"] = str(self.storage)
        os.environ["ZHC_RUNTIME_MODE"] = "single_node"
        os.environ["ZHC_AUTONOMY_MODE"] = "supervised"

    def tearDown(self) -> None:
        os.environ.clear()
        os.environ.update(self._env_backup)
        self.tmp.cleanup()

    def _create_task(
        self, task_id: str, status: str, route_class: str = "UBUNTU_HEAVY"
    ) -> None:
        self.registry["create_task"](
            self.db,
            task_id,
            "code_refactor",
            "invariant test",
            route_class,
            status,
            True,
            "medium",
            None,
            {},
        )

    def test_status_transition_enforced(self) -> None:
        task_id = "task-transition-1"
        self._create_task(task_id, "pending", route_class="PI_LIGHT")

        updated = self.registry["update_task"](self.db, task_id, "blocked", "test")
        self.assertEqual(updated["status"], "blocked")

        with self.assertRaises(ValueError):
            self.registry["update_task"](self.db, task_id, "pending", "invalid")

        done = self.registry["update_task"](self.db, task_id, "succeeded", "done")
        self.assertEqual(done["status"], "succeeded")

        with self.assertRaises(ValueError):
            self.registry["update_task"](self.db, task_id, "blocked", "reopen")

    def test_approve_defer_is_record_only(self) -> None:
        task_id = "task-approve-defer-1"
        self._create_task(task_id, "blocked")
        self.registry["request_approval"](
            self.db,
            task_id,
            "supervised_heavy_execution",
            "tester",
            "need approval",
        )

        result = self.router["approve_task"](
            task_id=task_id,
            action_category="supervised_heavy_execution",
            decided_by="@tester",
            note="approved",
            decision="approved",
            defer_dispatch=True,
        )

        self.assertEqual(result["status"], "blocked")
        self.assertIn("Approval recorded", result["message"])

        task = self.registry["get_task"](self.db, task_id)
        dispatch_events = [
            e
            for e in task["events"]
            if str(e.get("detail", "")).startswith("single_node_local_run")
        ]
        self.assertEqual(len(dispatch_events), 0)

    def test_resume_on_terminal_is_noop(self) -> None:
        task_id = "task-resume-noop-1"
        self._create_task(task_id, "succeeded")

        result = self.router["resume_task"](task_id=task_id, requested_by="@tester")
        self.assertEqual(result["status"], "succeeded")
        self.assertIn("already terminal", result["message"])


if __name__ == "__main__":
    unittest.main()
