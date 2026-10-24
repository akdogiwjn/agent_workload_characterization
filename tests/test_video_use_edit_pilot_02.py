"""Offline regression coverage for the PILOT-02 interpreter repair wiring."""
from __future__ import annotations

import socket
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "scripts"), str(ROOT / "src")]
import video_use_edit_pilot_02 as pilot  # noqa: E402


class InterpreterWiringTests(unittest.TestCase):
    def setUp(self):
        self.network_guard = patch.object(socket.socket, "connect",
                                          side_effect=AssertionError("network disabled in unit tests"))
        self.network_guard.start()
        self.addCleanup(self.network_guard.stop)

    def test_image_restores_path_after_login_profile_and_keeps_ordinary_env(self):
        dockerfile = (ROOT / "env/video/video-use/codex-bailian-integration-02/Dockerfile").read_text()
        self.assertIn('ENV PATH="/opt/video-use-venv/bin:${PATH}"', dockerfile)
        self.assertIn("/etc/profile", dockerfile)
        self.assertIn('export PATH="/opt/video-use-venv/bin:$PATH"', dockerfile)

    def test_production_transcription_uses_bare_python3_from_skill_directory(self):
        source = Path(pilot.runner.__file__).read_text()
        self.assertIn('cd /opt/video-use && python3 helpers/transcribe.py', source)
        runtime = (ROOT / "src/agent_workload_characterization/runners/container_runtime.py").read_text()
        self.assertIn('"bash", "-lc", command', runtime)

    def test_codex_tools_shell_is_login_shell_equivalent_only(self):
        runtime = (ROOT / "src/agent_workload_characterization/runners/container_runtime.py").read_text()
        self.assertIn('"bash", "-lc", command', runtime)
        # No Codex session is launched by this offline test; the shell boundary
        # is the same, but the live tool invocation remains unverified here.

    def test_asr_failure_does_not_start_agent_or_verifier(self):
        source = Path(pilot.runner.__file__).read_text()
        self.assertIn('"phase": "official_elevenlabs_transcribe"', source)
        self.assertIn('"agent_not_started_after_pre_agent_failure"', source)
        failed_report = {"phases": [{"phase": "official_elevenlabs_transcribe", "returncode": 1}]}
        with patch.object(pilot.runner, "run_verifier") as verifier:
            result = pilot.runner.verifier_after_agent(failed_report)
        verifier.assert_not_called()
        self.assertEqual(result["status"], "not_started")
        self.assertNotIn("agent", [p["phase"] for p in failed_report["phases"]])

    def test_unit_test_network_guard_is_active(self):
        with self.assertRaisesRegex(AssertionError, "network disabled"):
            socket.socket.connect(None, ("192.0.2.1", 9))

    def test_exception_path_exports_partial_evidence_and_removes_container(self):
        source = Path(pilot.runner.__file__).read_text()
        self.assertIn('"partial_export"', source)
        self.assertIn('finally:', source)
        self.assertIn('runtime.stop(handle)', source)
        self.assertIn('runtime.verify_removal(handle)', source)

    def test_pilot02_identity_is_independent_and_not_an_attempt(self):
        self.assertEqual(pilot.TASK, "VIDEO-USE-EDIT-PILOT-02")
        self.assertEqual(pilot.RUN_ID, "20261021T0937Z-video-use-edit-02")
        self.assertNotEqual(pilot.runner._IDENTITY_FILE,
                            ROOT / "env/video/video-use/VIDEO-USE-EDIT-PILOT-01/frozen-identity.json")
        self.assertFalse(pilot.runner.RAW_ROOT.exists())

    def test_old_prepared_monotonic_does_not_reduce_invocation_budget(self):
        with tempfile.TemporaryDirectory() as td:
            identity = Path(td) / "frozen-identity.json"
            identity.write_text('{"prepared_at_monotonic_ns": 1}')
            pilot.IDENTITY = identity
            pilot.runner.PROCESS_START_NS = 1
            fresh_start = 8_000_000_000_000
            with patch.object(pilot.time, "monotonic_ns",
                              side_effect=[fresh_start, fresh_start + 500]), \
                    patch.object(pilot.runner, "main",
                                 side_effect=lambda: pilot.runner.elapsed_s()) as shared:
                elapsed_at_shared_entry = pilot.main()
            shared.assert_called_once_with()
            self.assertEqual(pilot.runner.PROCESS_START_NS, fresh_start)
            self.assertLess(elapsed_at_shared_entry, 0.001)

    def test_invalid_or_cross_boot_saved_clock_is_ignored_and_shared_runner_called(self):
        with tempfile.TemporaryDirectory() as td:
            identity = Path(td) / "frozen-identity.json"
            identity.write_text('{"prepared_at_monotonic_ns": "not-a-clock"}')
            pilot.IDENTITY = identity
            pilot.runner.PROCESS_START_NS = -10**30
            fresh_start = 123456789
            with patch.object(pilot.time, "monotonic_ns", return_value=fresh_start), \
                    patch.object(pilot.runner, "main",
                                 side_effect=lambda: pilot.runner.PROCESS_START_NS) as shared:
                result = pilot.main()
            shared.assert_called_once_with()
            self.assertEqual(result, fresh_start)


if __name__ == "__main__":
    unittest.main()
