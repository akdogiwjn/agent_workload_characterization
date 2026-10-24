"""Offline P3 renderer/verifier wiring and classification regressions."""
from __future__ import annotations

import json
import hashlib
import socket
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "scripts"), str(ROOT / "src"),
               str(ROOT / "env/video/video-use/VIDEO-USE-EDIT-PILOT-03/verifier")]
import video_use_edit_pilot_03 as pilot  # noqa: E402
import entry as verifier_entry  # noqa: E402


class OfflineWiringTests(unittest.TestCase):
    def setUp(self):
        self.block_network = patch.object(
            socket.socket, "connect",
            side_effect=AssertionError("network disabled in mock tests"))
        self.block_network.start()
        self.addCleanup(self.block_network.stop)

    def test_registered_skill_and_production_image_overlay_are_same_files(self):
        dockerfile = (pilot.PLAN_ROOT / "Dockerfile").read_text()
        self.assertIn("COPY overlay/helpers/render.py /opt/video-use/helpers/render.py", dockerfile)
        self.assertIn("COPY overlay/helpers/timeline_view.py /opt/video-use/helpers/timeline_view.py", dockerfile)
        self.assertIn("COPY overlay/SKILL.md /opt/video-use/SKILL.md", dockerfile)
        self.assertIn("/root/.codex/skills/video-use", dockerfile)

    def test_prompt_uses_generic_candidate_search_without_prior_run_context(self):
        prompt = pilot.starter_instruction()
        self.assertIn("candidate regions", prompt)
        self.assertIn("--preserve-source-spec", prompt)
        self.assertIn("determine", prompt)
        self.assertNotIn("PILOT-02", prompt)
        self.assertNotIn("reward", prompt.lower())
        self.assertNotIn("golden", prompt.lower())
        self.assertNotIn("25.16", prompt)
        self.assertNotIn("27.26", prompt)

    def test_rollout_counters_separate_protocol_events_and_nonzero_exit(self):
        events = [
            {"type": "response_item", "payload": {"type": "function_call",
             "name": "exec_command", "call_id": "c1", "arguments": "{\"cmd\":\"render\"}"}},
            {"type": "response_item", "payload": {"type": "function_call_output",
             "call_id": "c1", "output": "Process exited with code 1"}},
            {"type": "response_item", "payload": {"type": "function_call",
             "name": "view_image", "call_id": "c2", "arguments": "{}"}},
            {"type": "response_item", "payload": {"type": "function_call_output",
             "call_id": "c2", "output": [{"type": "input_image", "image_url": "test"}]}},
            {"type": "response_item", "payload": {"type": "function_call_error",
             "call_id": "c3", "error": "protocol"}},
        ]
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "rollout-test.jsonl"
            path.write_text("\n".join(json.dumps({"type": e["type"], "payload": e["payload"]})
                                        for e in events))
            result = pilot.rollout_summary(Path(td))
        self.assertEqual(result["protocol_tool_call_events"], 2)
        self.assertEqual(result["protocol_tool_return_events"], 2)
        self.assertEqual(result["protocol_error_events"], 1)
        self.assertEqual(result["exec_command_tool_events"], 1)
        self.assertEqual(result["observed_nonzero_process_exit_events"], 1)

    def test_asr_pre_agent_failure_skips_agent_and_verifier(self):
        report = {"phases": [{"phase": "official_elevenlabs_transcribe",
                              "returncode": 1}]}
        with patch.object(pilot.runner.subprocess, "Popen") as popen:
            result = pilot.isolated_run_verifier(report)
        popen.assert_not_called()
        self.assertEqual(result["status"], "not_started")
        self.assertEqual(result["reason"], "agent_not_started")

    def test_missing_submission_does_not_start_judge(self):
        with tempfile.TemporaryDirectory() as td:
            previous = pilot.runner.RAW_ROOT
            pilot.runner.RAW_ROOT = Path(td)
            self.addCleanup(setattr, pilot.runner, "RAW_ROOT", previous)
            report = {"phases": [{"phase": "agent", "returncode": 1}]}
            with patch.object(pilot.runner.subprocess, "Popen") as popen:
                result = pilot.isolated_run_verifier(report)
            popen.assert_not_called()
            self.assertEqual(result["status"], "not_started_missing_submission")
            self.assertEqual(result["checks"]["audio_xcorr"], "not_evaluated")

    def test_shared_exception_path_stops_container_and_archives_partial_record(self):
        source = Path(pilot.runner.__file__).read_text()
        failure = source.index("except BaseException as e:")
        finalizer = source.index("finally:", failure)
        archive = source.index('write_json(RAW_ROOT / "run-record.json", report)', finalizer)
        manifest = source.index("emit_manifest(RAW_ROOT)", archive)
        path = source[failure:manifest]
        self.assertIn("runtime.stop(handle)", path)
        self.assertIn("runtime.verify_removal(handle)", path)
        self.assertIn('write_json(RAW_ROOT / "run-record.json", report)', source[finalizer:])
        self.assertIn("emit_manifest(RAW_ROOT)", source[archive:])


class VerifierClassificationTests(unittest.TestCase):
    def test_ssim_exception_is_evaluation_error_not_quality_failure(self):
        emitted = {"reward": 0.0, "details": {"reason": "ssim sampling failed: No module named skimage"}}
        result = verifier_entry.classify_result(0, emitted, {"audio": "required"}, True)
        self.assertEqual(result["evaluation_status"], "evaluation_error")
        self.assertFalse(result["evaluation_complete"])
        self.assertIsNone(result["task_score"])
        self.assertEqual(result["checks"]["audio_xcorr"], "unknown")

    def test_complete_zero_score_remains_a_completed_task_result(self):
        emitted = {"reward": 0.0, "details": {
            "reason": "honesty gate failed: ssim=0.4", "per_cut": [],
            "duration_pass": True, "duration_diff_s": 0.01, "ssim": 0.4,
            "audio_xcorr": 0.95}}
        result = verifier_entry.classify_result(0, emitted, {"audio": "required"}, True)
        self.assertEqual(result["evaluation_status"], "complete")
        self.assertEqual(result["task_score"], 0.0)
        self.assertEqual(result["checks"]["audio_xcorr"], "evaluated")

    def test_audio_skip_is_not_reported_as_audio_failure(self):
        emitted = {"reward": 1.0, "details": {
            "reason": "passed 1/1 cuts", "per_cut": [{}], "duration_pass": True,
            "duration_diff_s": 0.0, "ssim": 1.0, "audio_xcorr": None}}
        result = verifier_entry.classify_result(0, emitted, {"audio": "skip"}, True)
        self.assertEqual(result["evaluation_status"], "complete")
        self.assertEqual(result["checks"]["audio_xcorr"], "not_evaluated")

    def test_wrong_interpreter_refuses_to_launch_official_judge(self):
        with tempfile.TemporaryDirectory() as td:
            judge = Path(td) / "judge.py"
            judge.write_text("pass\n")
            status = Path(td) / "status.json"
            args = type("Args", (), {
                "expected_venv": td + "/expected", "status_json": str(status),
                "judge": str(judge),
                "judge_sha256": hashlib.sha256(judge.read_bytes()).hexdigest(),
            })()
            with patch.object(verifier_entry, "_versions", return_value={}), \
                    patch.object(verifier_entry.subprocess, "Popen") as popen:
                code, result = verifier_entry.run(args)
            popen.assert_not_called()
            self.assertEqual(code, 20)
            self.assertEqual(result["evaluation_status"], "evaluation_error")
            self.assertIsNone(result["task_score"])


if __name__ == "__main__":
    unittest.main()
