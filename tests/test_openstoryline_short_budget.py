from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
import os
import sys
import types
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "env/video/openstoryline/OPENSTORYLINE-ENV-01/source"
sys.path.insert(0, str(SOURCE / "src"))
sys.path.insert(0, str(ROOT / "env/video/openstoryline/edit-pilot-02/runtime"))
from short_task_budget import begin_deadline
from open_storyline.confirmation_flow import continue_with_confirmation

# The request-ledger regression exercises only its local JSONL/count logic.
# The real callback superclass is supplied by the pinned container runtime;
# keep this host test dependency-free while loading the production module.
langchain_core = types.ModuleType("langchain_core")
callbacks = types.ModuleType("langchain_core.callbacks")
callbacks.BaseCallbackHandler = type("BaseCallbackHandler", (), {})
langchain_core.callbacks = callbacks
sys.modules.setdefault("langchain_core", langchain_core)
sys.modules.setdefault("langchain_core.callbacks", callbacks)
from open_storyline.mcp import request_ledger


class FreshShortTaskBudgetTests(unittest.TestCase):
    def test_old_run_record_cannot_shift_new_deadline(self):
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, "old-run-start.json").write_text('{"started_monotonic_ns": 1}')
            window = begin_deadline(1800, monotonic=lambda: 1234.5)
            self.assertEqual(window.started_monotonic, 1234.5)
            self.assertEqual(window.deadline_monotonic, 3034.5)
            self.assertEqual(window.remaining(now=1234.5), 1800)

    def test_cleanup_reserve_is_inside_new_wall_window(self):
        window = begin_deadline(1800, monotonic=lambda: 100.0)
        execution_deadline = window.execution_deadline(60)
        self.assertEqual(execution_deadline, 1840.0)
        self.assertEqual(window.remaining(now=execution_deadline), 60.0)

    def test_invalid_or_exhaustive_cleanup_reserve_fails_closed(self):
        window = begin_deadline(1800, monotonic=lambda: 100.0)
        with self.assertRaises(ValueError):
            window.execution_deadline(-1)
        with self.assertRaises(ValueError):
            window.execution_deadline(1800)

    def test_old_ledger_is_unchanged_and_new_ledger_starts_at_zero(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            old = root / "short-03" / "model-requests.jsonl"
            old.parent.mkdir()
            original = b'{"event":"request_started","request_id":"old"}\n'
            old.write_bytes(original)
            new = root / "short-04" / "output"
            new.mkdir(parents=True)
            with patch.dict(os.environ, {
                "OPENSTORYLINE_TRACE_DIR": str(new),
                "OPENSTORYLINE_MAX_LOGICAL_REQUESTS": "40",
                "OPENSTORYLINE_MAX_OBSERVED_TOKENS_SOFT_THRESHOLD": "500000",
                "OPENSTORYLINE_MAX_OUTPUT_TOKENS_PER_REQUEST": "8192",
            }, clear=False):
                self.assertFalse((new / "model-requests.jsonl").exists())
                attempt = request_ledger.begin_request(
                    phase="test", model="offline", output_token_limit=8192)
                request_ledger.finish_request(attempt, status="completed",
                                              usage={"total_tokens": 1})
            self.assertEqual(old.read_bytes(), original)
            rows = [line for line in (new / "model-requests.jsonl").read_bytes().splitlines()
                    if line]
            import json
            events = [json.loads(row) for row in rows]
            self.assertEqual(sum(row.get("event") == "request_started" for row in events), 1)
            self.assertEqual(sum(row.get("event") == "request_finished" for row in events), 1)
            self.assertEqual(old.read_bytes(), original)

    def test_same_session_confirmation_keeps_deadline_and_request_ledger(self):
        window = begin_deadline(1800, monotonic=lambda: 100.0)
        messages = [{"type": "human", "content": "edit"}]
        reply = {"type": "ai", "content": "continue"}
        continued = continue_with_confirmation(messages, reply)
        self.assertEqual(continued, [*messages, reply])
        self.assertEqual(window.deadline_monotonic, 1900.0)
        self.assertEqual(window.remaining(now=150.0), 1750.0)

    def test_production_short_entry_uses_fresh_budget_without_old_debits(self):
        runner = ROOT / "env/video/openstoryline/edit-pilot-02/preparation/real-native-short-04/run_short_task.py"
        source = runner.read_text(encoding="utf-8")
        self.assertIn("window = begin_deadline(1800)", source)
        self.assertIn('"max_logical_requests": 40', source)
        self.assertIn('"max_observed_tokens_soft_threshold": 500_000', source)
        self.assertIn('"max_output_tokens_per_request": 8192', source)
        self.assertNotIn('real-native-short-02/run-start.json', source)
        self.assertNotIn("previous_start", source)


if __name__ == "__main__":
    unittest.main()
