#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import runpy
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REGISTRY_PATH = ROOT / "shared/task-registry/task_registry.py"
BOT_PATH = ROOT / "services/telegram-control/bot_longpoll.py"


class IdempotencyPathTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.tmp_path = Path(self.tmp.name)
        self.db = self.tmp_path / "task_registry.db"
        self.storage = self.tmp_path / "storage"
        self.storage.mkdir(parents=True, exist_ok=True)

        self.registry = runpy.run_path(str(REGISTRY_PATH))
        self.registry["init_db"](self.db, ROOT / "shared/task-registry/schema.sql")

        self._env_backup = dict(os.environ)
        os.environ["ZHC_TASK_DB"] = str(self.db)
        os.environ["ZHC_STORAGE_ROOT"] = str(self.storage)
        os.environ["TELEGRAM_BOT_TOKEN"] = "test-token"
        os.environ["TELEGRAM_ALLOWED_CHAT_IDS"] = "12345"
        os.environ["TELEGRAM_REQUIRE_ALLOWLIST"] = "1"

    def tearDown(self) -> None:
        os.environ.clear()
        os.environ.update(self._env_backup)
        self.tmp.cleanup()

    def test_registry_idempo_replay_and_conflict(self) -> None:
        begin1 = self.registry["begin_idempotency"](
            self.db,
            "tg_update:42",
            "telegram_command",
            "hash-a",
            None,
        )
        self.assertFalse(begin1["exists"])

        self.registry["complete_idempotency"](
            self.db,
            "tg_update:42",
            "completed",
            json.dumps({"status": "ok"}),
        )

        begin2 = self.registry["begin_idempotency"](
            self.db,
            "tg_update:42",
            "telegram_command",
            "hash-a",
            None,
        )
        self.assertTrue(begin2["exists"])
        self.assertFalse(begin2["conflict"])
        self.assertEqual(begin2["status"], "completed")
        self.assertEqual(begin2["result"], {"status": "ok"})

        begin3 = self.registry["begin_idempotency"](
            self.db,
            "tg_update:42",
            "telegram_command",
            "hash-b",
            None,
        )
        self.assertTrue(begin3["conflict"])
        self.assertEqual(begin3["status"], "conflict")

    def test_telegram_duplicate_update_executes_once(self) -> None:
        mod = runpy.run_path(str(BOT_PATH))
        cfg = mod["load_config"]()
        process_update = mod["process_update"]

        calls = {"count": 0}

        def fake_handle_command(config, message, trace_id=""):
            calls["count"] += 1
            return "ok", {"ok": True, "message": message.get("text", "")}

        process_update.__globals__["handle_command"] = fake_handle_command
        process_update.__globals__["send_message"] = lambda config, chat_id, text: None

        update = {
            "update_id": 777,
            "message": {
                "chat": {"id": 12345},
                "from": {"id": 12345, "username": "idempo"},
                "text": "/start",
            },
        }

        process_update(cfg, update, rate_buckets={})
        process_update(cfg, update, rate_buckets={})

        self.assertEqual(calls["count"], 1)

        lines = cfg.audit_log.read_text(encoding="utf-8").splitlines()
        payloads = [json.loads(line) for line in lines if line.strip()]
        statuses = [p.get("status") for p in payloads if p.get("update_id") == 777]
        self.assertIn("ok", statuses)
        self.assertIn("idempotent_replay", statuses)


if __name__ == "__main__":
    unittest.main()
