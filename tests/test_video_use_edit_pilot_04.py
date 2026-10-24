"""Offline PILOT-04 production-wiring regressions; no model/API/container."""
from __future__ import annotations

import json
import socket
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "scripts"), str(ROOT / "src")]
import video_use_edit_pilot_04 as pilot  # noqa: E402


class Pilot04PolicyAndReportTests(unittest.TestCase):
    def setUp(self):
        self.net = patch.object(socket.socket, "connect",
                                side_effect=AssertionError("network blocked"))
        self.net.start()
        self.addCleanup(self.net.stop)
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.old_report = pilot.REPORT_ROOT
        self.old_raw = pilot.RAW_ROOT
        self.old_runner_report = pilot.runner.REPORT_ROOT
        self.old_runner_raw = pilot.runner.RAW_ROOT
        pilot.REPORT_ROOT = Path(self.temp.name) / "report"
        pilot.RAW_ROOT = Path(self.temp.name) / "raw"
        pilot.runner.REPORT_ROOT = pilot.REPORT_ROOT
        pilot.runner.RAW_ROOT = pilot.RAW_ROOT
        pilot.RAW_ROOT.mkdir()
        (pilot.RAW_ROOT / "run-record.json").write_bytes(b"raw-run")
        (pilot.RAW_ROOT / "manifest.json").write_bytes(b"raw-manifest")
        self.addCleanup(setattr, pilot, "REPORT_ROOT", self.old_report)
        self.addCleanup(setattr, pilot, "RAW_ROOT", self.old_raw)
        self.addCleanup(setattr, pilot.runner, "REPORT_ROOT", self.old_runner_report)
        self.addCleanup(setattr, pilot.runner, "RAW_ROOT", self.old_runner_raw)

    def test_policy_is_bound_to_the_production_runner_prompt(self):
        prompt = " ".join(pilot.runner.starter_instruction().split())
        for requirement in (
            "timestamps as candidate locations",
            "conversational acknowledgements",
            "smallest cut",
            "Assess the proposed before and after boundaries separately",
            "cuts.json and the EDL synchronized",
            "audio semantic judgment not verified",
            "repeated blind edits",
            "boundary-notes.md",
        ):
            self.assertIn(requirement, prompt)
        self.assertNotIn("25.160", prompt)
        self.assertNotIn("27.240", prompt)
        self.assertNotIn("PILOT-03", prompt)
        self.assertEqual(pilot.runner.starter_instruction, pilot.starter_instruction)

    def test_report_uses_captured_base_once_and_writes_p4_summary(self):
        report = {"run_id": pilot.RUN_ID, "sampler_rows": [],
                  "phases": [{"phase": "agent", "returncode": 0}],
                  "verifier": {"evaluation_status": "complete", "returncode": 0},
                  "removal_verification": "removed", "resource_metrics": {},
                  "net_summary": {}, "rollout_summary": {}}
        base = Mock(wraps=pilot.pilot03._BASE_RESOURCE_REPORT_WRITER)
        with patch.object(pilot.pilot03, "_BASE_RESOURCE_REPORT_WRITER", base), \
             patch.object(pilot.runner.subprocess, "Popen") as popen, \
             patch.object(pilot.runner.subprocess, "run") as run:
            status = pilot.write_resource_report(report)
        base.assert_called_once_with(report)
        popen.assert_not_called()
        run.assert_not_called()
        self.assertEqual(status["report_status"], "complete")
        summary = (pilot.REPORT_ROOT / "summary.md").read_text()
        self.assertIn("VIDEO-USE-EDIT-PILOT-04", summary)
        self.assertNotIn("VIDEO-USE-EDIT-PILOT-03 执行报告", summary)

    def test_report_error_is_separate_and_leaves_raw_unchanged(self):
        before = {p.name: p.read_bytes() for p in pilot.RAW_ROOT.iterdir()}
        base = Mock(side_effect=RuntimeError("offline report fixture error"))
        with patch.object(pilot.pilot03, "_BASE_RESOURCE_REPORT_WRITER", base):
            status = pilot.write_resource_report({"run_id": pilot.RUN_ID, "phases": [],
                                                  "verifier": {}, "sampler_rows": []})
        base.assert_called_once()
        self.assertEqual(status["report_status"], "failed")
        saved = json.loads((pilot.REPORT_ROOT / "report-generation-status.json").read_text())
        self.assertEqual(saved["error"]["type"], "RuntimeError")
        self.assertEqual(before, {p.name: p.read_bytes() for p in pilot.RAW_ROOT.iterdir()})

    def test_execution_clock_uses_current_entry_origin(self):
        with patch.object(pilot, "ENTRY_START_NS", 987654321):
            pilot.runner.PROCESS_START_NS = 123
            pilot.reset_execution_clock()
        self.assertEqual(pilot.runner.PROCESS_START_NS, 987654321)

    def test_plan_binds_fixed_route_budgets_and_dedicated_verifier(self):
        plan = pilot.plan_data({"inspect": f"{pilot.IMAGE_ID} arm64 linux",
                                "codex_version": "codex-cli 0.163.0"})
        self.assertEqual(plan["image"]["id"], pilot.IMAGE_ID)
        self.assertEqual(plan["model_route"]["model"], "qwen3.7-plus")
        self.assertEqual(plan["model_route"]["wire_api"], "responses")
        self.assertEqual(plan["asr"]["model"], "scribe_v1")
        self.assertEqual(plan["budgets_s"], {"total": 2700, "agent_max": 1800,
                                               "verifier_max": 600, "cleanup_reserve": 300})
        self.assertEqual(plan["verifier"]["python"], str(pilot.pilot03.VERIFIER_PYTHON))


if __name__ == "__main__":
    unittest.main()
