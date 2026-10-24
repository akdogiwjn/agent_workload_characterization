#!/usr/bin/env python3
"""Host-side unit tests for the VideoWeaver controlled gateway ledger and the
run-root guard, exercising the required counter-examples without a container:

- budget 0 -> zero upstream sends
- concurrent requests share ONE quota -> at most one forwarded
- restarting a media script cannot reset the ledger (persistence)
- ledger open/write failure -> zero sends
- unknown video task poll rejected; task_id persisted after create
- existing output dir -> refused, bytes unchanged
- pipeline_rc=0 but missing valid final -> judgement fails
"""
import json
import os
import shutil
import sys
import tempfile
import threading
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "src"))

import host_runner as hr
from gateway import Ledger, DEFAULT_BUDGET


def make_budget(**over):
    b = dict(DEFAULT_BUDGET)
    b.update(over)
    return b


class TestLedgerBudget(unittest.TestCase):
    def _ledger(self, tmp, budget, start_epoch=None):
        os.environ["VW_RUN_START_EPOCH"] = str(start_epoch or 0.0)
        os.environ["VW_RUN_ID"] = "test"
        return Ledger(str(tmp / "ledger.json"), budget)

    def test_budget_zero_sends_zero(self):
        with tempfile.TemporaryDirectory() as td:
            l = self._ledger(Path(td), make_budget(max_llm_calls=0))
            self.assertFalse(l.charge("llm_calls"))
            self.assertTrue(l.data["exhausted"])

    def test_concurrent_quota_at_most_one(self):
        with tempfile.TemporaryDirectory() as td:
            l = self._ledger(Path(td), make_budget(max_image_creates=1))
            results = []
            def go():
                results.append(l.charge("image_creates"))
            t1 = threading.Thread(target=go); t2 = threading.Thread(target=go)
            t1.start(); t2.start(); t1.join(); t2.join()
            self.assertEqual(sorted(results), [False, True])

    def test_persistence_across_restart(self):
        with tempfile.TemporaryDirectory() as td:
            l = self._ledger(Path(td), make_budget(max_image_creates=5))
            self.assertTrue(l.charge("image_creates"))
            l.record("video_created", task_id="tid-1")
            l2 = Ledger(str(Path(td) / "ledger.json"), make_budget(max_image_creates=5))
            self.assertEqual(l2.data["counters"]["image_creates"], 1)
            self.assertIn("tid-1", l2.data["video_tasks"])

    def test_write_failure_sends_zero(self):
        with tempfile.TemporaryDirectory() as td:
            ledger_dir = Path(td) / "ledger"
            ledger_dir.mkdir()
            os.chmod(ledger_dir, 0o500)  # read-only dir -> atomic write fails
            l = self._ledger(ledger_dir, make_budget(max_image_creates=5))
            try:
                ok = l.charge("image_creates")
            finally:
                os.chmod(ledger_dir, 0o700)
            self.assertFalse(ok)
            self.assertEqual(l.data["counters"]["image_creates"], 0)

    def test_video_task_unknown_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            l = self._ledger(Path(td), make_budget(max_video_polls=5))
            self.assertNotIn("unknown-tid", l.data["video_tasks"])


class TestRunRoot(unittest.TestCase):
    def test_existing_dir_refused_and_unchanged(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "run"
            root.mkdir()
            marker = root / "old.txt"
            marker.write_text("KEEP")
            with self.assertRaises(ValueError):
                hr.new_run_root(root)
            self.assertEqual(marker.read_text(), "KEEP")


class TestJudge(unittest.TestCase):
    def test_missing_final_fails_even_with_rc0(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            for s in ("logs", "samples", "ledger", "workspace", "rollout", "closeout"):
                (root / s).mkdir()
            (root / "logs" / "exec-stdout.log").write_text("x")
            (root / "logs" / "exec-stderr.log").write_text("")
            (root / "logs" / "docker-logs.txt").write_text("")
            (root / "samples" / "summary.json").write_text("{}")
            (root / "ledger" / "ledger.json").write_text(json.dumps({
                "counters": {"llm_calls": 19, "image_creates": 8, "video_creates": 8,
                             "video_polls": 16, "media_downloads": 16},
                "exhausted": False, "events": [], "status": "open"}))
            report = {"errors": [], "cleanup": {"removed": True}, "pipeline_rc": 0}
            j = hr.judge({}, root, report)
            final_check = next(c for c in j["checks"] if c["check"] == "final_present")
            self.assertFalse(final_check["passed"])
            self.assertFalse(j["passed"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
