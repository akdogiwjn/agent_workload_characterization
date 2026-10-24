"""Offline report-recursion regression and Agent-side boundary extraction tests."""
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
import video_use_edit_pilot_03 as pilot  # noqa: E402
from video_use_edit_pilot_03_boundary_review import (  # noqa: E402
    analyze_boundaries, analyze_rollout_events,
)


def event(kind: str, payload: dict) -> dict:
    return {"type": kind, "payload": payload}


class ReportWriterTests(unittest.TestCase):
    def setUp(self):
        self.network_guard = patch.object(
            socket.socket, "connect", side_effect=AssertionError("network blocked"))
        self.network_guard.start()
        self.addCleanup(self.network_guard.stop)
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.old_report = pilot.runner.REPORT_ROOT
        self.old_raw = pilot.runner.RAW_ROOT
        pilot.runner.REPORT_ROOT = self.root / "reports"
        pilot.runner.RAW_ROOT = self.root / "raw"
        self.addCleanup(setattr, pilot.runner, "REPORT_ROOT", self.old_report)
        self.addCleanup(setattr, pilot.runner, "RAW_ROOT", self.old_raw)
        pilot.runner.RAW_ROOT.mkdir(parents=True)
        (pilot.runner.RAW_ROOT / "run-record.json").write_bytes(b"immutable-run-record")
        (pilot.runner.RAW_ROOT / "manifest.json").write_bytes(b"immutable-manifest")

    @staticmethod
    def report() -> dict:
        return {
            "run_id": "fixture-run",
            "phases": [{"phase": "agent", "returncode": 0}],
            "verifier": {"evaluation_status": "complete", "returncode": 0},
            "removal_verification": "removed",
            "sampler_rows": [], "resource_metrics": {}, "net_summary": {},
            "rollout_summary": {},
        }

    def test_real_report_path_calls_captured_base_once_without_recursion(self):
        base = Mock(wraps=pilot._BASE_RESOURCE_REPORT_WRITER)
        with patch.object(pilot, "_BASE_RESOURCE_REPORT_WRITER", base), \
             patch.object(pilot.runner.subprocess, "Popen") as popen, \
             patch.object(pilot.runner.subprocess, "run") as run:
            status = pilot.write_resource_report(self.report())
        base.assert_called_once()
        popen.assert_not_called()
        run.assert_not_called()
        self.assertEqual(status["report_status"], "complete")
        self.assertTrue((pilot.runner.REPORT_ROOT / "resource-curves.svg").is_file())
        self.assertTrue((pilot.runner.REPORT_ROOT / "summary.md").is_file())
        saved = json.loads((pilot.runner.REPORT_ROOT / "report-generation-status.json").read_text())
        self.assertEqual(saved["report_status"], "complete")

    def test_base_failure_is_separately_recorded_and_does_not_rewrite_raw(self):
        raw_before = {p.name: p.read_bytes() for p in pilot.runner.RAW_ROOT.iterdir()}
        base = Mock(side_effect=RuntimeError("fixture report failure"))
        with patch.object(pilot, "_BASE_RESOURCE_REPORT_WRITER", base), \
             patch.object(pilot.runner.subprocess, "Popen") as popen, \
             patch.object(pilot.runner.subprocess, "run") as run:
            status = pilot.write_resource_report(self.report())
        base.assert_called_once()
        popen.assert_not_called()
        run.assert_not_called()
        self.assertEqual(status["report_status"], "failed")
        self.assertEqual(status["error"]["type"], "RuntimeError")
        self.assertTrue(status["raw_run_record_exists"])
        self.assertTrue(status["raw_manifest_exists"])
        self.assertFalse(status["raw_modified_by_report_writer"])
        self.assertEqual(raw_before, {p.name: p.read_bytes() for p in pilot.runner.RAW_ROOT.iterdir()})


class AgentBoundaryExtractionTests(unittest.TestCase):
    def test_edl_and_cuts_mapping_matches_transcript_word_boundaries(self):
        cuts = {"cuts": [{"start_ms": 1000, "end_ms": 2000, "reason": "hesitation"}]}
        edl = {"ranges": [{"start": 0.0, "end": 1.0}, {"start": 2.0, "end": 4.0}]}
        words = [
            {"text": "Yes,", "start": 1.0, "end": 1.2, "type": "word"},
            {"text": "uh-", "start": 1.2, "end": 1.5, "type": "word"},
            {"text": "Right", "start": 2.0, "end": 2.3, "type": "word"},
        ]
        result = analyze_boundaries(cuts, edl, words)
        self.assertTrue(result["edl_matches_cuts_json"])
        self.assertEqual(result["start_boundary_word_tokens"], ["Yes,"])
        self.assertEqual(result["end_boundary_word_tokens"], ["Right"])
        self.assertTrue(result["start_frame_aligned_at_source_fps"])
        self.assertTrue(result["end_frame_aligned_at_source_fps"])
        self.assertIn("score_range_pass", result)
        self.assertIn("not read", result["score_range_pass"])

    def test_rollout_separates_protocol_and_exit_and_deduplicates_usage(self):
        events = [
            event("response_item", {"type": "function_call", "name": "exec_command",
                  "call_id": "bad", "arguments": json.dumps({"cmd": "timeline_view.py --start 1"})}),
            event("response_item", {"type": "function_call_output", "call_id": "bad",
                  "output": "Process exited with code 2"}),
            event("response_item", {"type": "function_call", "name": "exec_command",
                  "call_id": "help", "arguments": json.dumps({"cmd": "timeline_view.py --help"})}),
            event("response_item", {"type": "function_call_output", "call_id": "help",
                  "output": "usage"}),
            event("response_item", {"type": "function_call", "name": "exec_command",
                  "call_id": "good", "arguments": json.dumps({"cmd": "timeline_view.py video 1 2"})}),
            event("response_item", {"type": "function_call_output", "call_id": "good",
                  "output": "Process exited with code 0"}),
            event("response_item", {"type": "function_call", "name": "view_image",
                  "call_id": "image", "arguments": json.dumps({"path": "timeline_hesitation.png"})}),
            event("response_item", {"type": "function_call_output", "call_id": "image",
                  "output": [{"type": "input_image"}]}),
            {"type": "token_usage_record", "payload": {"response_id": "resp-a",
             "usage": {"input_tokens": 10, "cached_input_tokens": 4, "output_tokens": 2,
                       "total_tokens": 12}, "turn_token_usage": {"input_tokens": 10}}},
            {"type": "token_usage_record", "payload": {"response_id": "resp-a",
             "usage": {"input_tokens": 10, "cached_input_tokens": 4, "output_tokens": 2,
                       "total_tokens": 12}, "turn_token_usage": {"input_tokens": 20}}},
            {"type": "token_usage_record", "payload": {"response_id": "resp-b",
             "usage": {"input_tokens": 7, "cached_input_tokens": 0, "output_tokens": 3,
                       "total_tokens": 10}, "turn_token_usage": {"input_tokens": 17}}},
        ]
        result = analyze_rollout_events(events)
        self.assertEqual(result["tool_call_events"], 4)
        self.assertEqual(result["tool_return_events"], 4)
        self.assertEqual(result["protocol_error_events"], 0)
        self.assertEqual(result["exec_command_events"], 3)
        self.assertEqual(result["view_image_events"], 1)
        self.assertEqual(len(result["nonzero_command_events"]), 1)
        failure = result["nonzero_command_events"][0]
        self.assertEqual(failure["command_summary"], "invalid_named_time_flags")
        self.assertTrue(failure["recovered_by_later_same_class_success"])
        self.assertTrue(failure["recovery_image_viewed"])
        self.assertEqual(result["native_response_records"], 3)
        self.assertEqual(result["unique_response_ids"], 2)
        self.assertEqual(result["duplicate_response_id_records"], 1)
        self.assertEqual(result["per_response_usage_totals"]["input_tokens"], 17)
        self.assertEqual(result["per_response_usage_totals"]["cached_input_tokens"], 4)
        self.assertEqual(result["per_response_usage_totals"]["total_tokens"], 22)


if __name__ == "__main__":
    unittest.main()
