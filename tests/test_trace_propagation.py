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


class TracePropagationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.tmp_path = Path(self.tmp.name)
        self.db = self.tmp_path / "task_registry.db"
        self.storage = self.tmp_path / "storage"
        self.storage.mkdir(parents=True, exist_ok=True)

        self.registry = runpy.run_path(str(REGISTRY_PATH))
        self.router = runpy.run_path(str(ROUTER_PATH))
        self.registry["init_db"](self.db, ROOT / "shared/task-registry/schema.sql")

        self._env_backup = dict(os.environ)
        os.environ["ZHC_TASK_DB"] = str(self.db)
        os.environ["ZHC_STORAGE_ROOT"] = str(self.storage)
        os.environ["ZHC_RUNTIME_MODE"] = "single_node"
        os.environ["ZHC_AUTONOMY_MODE"] = "supervised"
        os.environ["ZHC_ENABLE_REAL_OPENCODE"] = "0"

    def tearDown(self) -> None:
        os.environ.clear()
        os.environ.update(self._env_backup)
        self.tmp.cleanup()

    def test_trace_saved_in_task_and_events(self) -> None:
        trace_id = "tg-123456"
        routed = self.router["route_task"]("code_refactor", "trace smoke", trace_id)
        task_id = routed["task_id"]

        task = self.registry["get_task"](self.db, task_id)
        self.assertEqual(task.get("metadata", {}).get("trace_id"), trace_id)

        events = self.registry["trace_events"](self.db, trace_id, 50)
        self.assertTrue(
            any(e.get("task_id") == task_id for e in events.get("events", []))
        )


if __name__ == "__main__":
    unittest.main()
