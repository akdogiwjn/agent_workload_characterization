"""RUN-02-R1 A-stage offline checks; no Docker or real permissions."""

import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from agent_workload_characterization.runners import run_02_entry as core
from agent_workload_characterization.runners import run_02_r1_entry as r1


class Run02R1Tests(unittest.TestCase):
    def test_parent_failure_files_are_unchanged_and_identity_is_bound(self):
        expected = {
            "APPROVAL.txt": "cf744bf09ac4ba334cf0010dd0be0afdd7859c84046a763bb869f7ef26becd9a",
            "ATTEMPT_STARTED.json": "8279e463198d9130496e3f5f43b0aad1d7fa6e42a9e9cfee0a9581f34fa8b437",
            "PREFLIGHT_DIAGNOSTIC.json": "ed911efcc6a74cf8f8245b7c47ba6c44e51651bb50b21d8a52ee8bf428db2bdc",
        }
        paths = {
            "APPROVAL.txt": r1.OLD_APPROVAL,
            "ATTEMPT_STARTED.json": r1.OLD_MARKER,
            "PREFLIGHT_DIAGNOSTIC.json": r1.OLD_PREFLIGHT,
        }
        for name, path in paths.items():
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(),
                             expected[name])
        with mock.patch.object(core, "MINI_VENV_PY", Path(__file__)), \
             mock.patch.object(core, "EVAL_VENV_PY", Path(__file__)), \
             mock.patch("agent_workload_characterization.runners.mini_agent_adapter.MiniSweAgentHarness.load_bundled_config",
                        return_value={"agent": {}, "model": {"model_kwargs": {}},
                                      "environment": {}}), \
             mock.patch.object(core, "_read_catalog", return_value={
                 "budget_proposal": {"model_requests": 1, "steps": 1,
                 "output_tokens_per_request": 1, "agent_wall_min": 1,
                 "verifier_wall_min": 1, "total_wall_min": 1,
                 "run_dir_threshold_gib": 1},
                 "collection_id": "RUN-02", "execution_authorized": False}), \
             mock.patch.object(core, "_record", return_value={
                 "instance_id": "django__django-16485", "problem_statement": "x",
                 "log_parser": "x", "eval_type": "x"}):
            plan = r1.build_plan()
        self.assertEqual(plan["identity"]["attempt_label"], "RUN-02-R1")
        self.assertEqual(plan["authorization"]["user_approval"], "pending")
        self.assertEqual(plan["authorization"]["tool_execution_permission"], "pending")
        self.assertNotEqual(plan["identity"]["r1_paths"]["approval"],
                            str(r1.OLD_APPROVAL))

    def test_r1_registration_is_atomic_and_single_use(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            marker = root / "reports/resource/RUN-02/retries/R1/ATTEMPT_STARTED.json"
            marker.parent.mkdir(parents=True)
            with mock.patch.object(core, "ATTEMPT_MARKER_PATH", marker):
                core._claim_attempt({"attempt_label": "RUN-02-R1"}, root)
                with self.assertRaises(core.Run02EntryError):
                    core._claim_attempt({"attempt_label": "RUN-02-R1"}, root)
            self.assertEqual(json.loads(marker.read_text())["status"], "started")

    def test_old_approval_path_cannot_authorize_r1(self):
        self.assertNotEqual(core.APPROVAL_PATH, r1.R1_APPROVAL)
        self.assertNotEqual(r1.OLD_APPROVAL, r1.R1_APPROVAL)
        # R1 may already have a separately approved/failed record; the
        # isolation contract is the fixed namespace, not nonexistence.

    def test_preflight_classifies_safe_error_categories(self):
        cases = [
            ("permission denied", "socket_access_denied"),
            ("Cannot connect to the Docker daemon", "daemon_unavailable"),
            ("manifest unknown: image not found", "image_not_found"),
            ("unexpected backend failure", "unknown"),
        ]
        for stderr, category in cases:
            with self.subTest(category=category):
                context = SimpleNamespace(returncode=0, stdout="default", stderr="")
                inspect = SimpleNamespace(returncode=1, stdout="", stderr=stderr)
                with mock.patch.object(core.subprocess, "run",
                                       side_effect=[context, inspect]):
                    with self.assertRaisesRegex(core.Run02PreflightError,
                                                f"category={category}"):
                        core._docker_preflight(60.0)

    def test_preflight_success_is_only_synthetic_and_no_extra_runner_call(self):
        context = SimpleNamespace(returncode=0, stdout="default", stderr="")
        inspect = SimpleNamespace(returncode=0, stdout="sha256:x arm64 linux", stderr="")
        with mock.patch.object(core.subprocess, "run",
                               side_effect=[context, inspect]) as run:
            result = core._docker_preflight(60.0)
        self.assertEqual(result["architecture"], "arm64")
        self.assertEqual(run.call_count, 2)

    def test_permission_and_missing_exceptions_are_not_timeout(self):
        for error, category in ((PermissionError("denied"), "socket_access_denied"),
                                (FileNotFoundError("docker"), "unknown")):
            with self.subTest(category=category):
                with mock.patch.object(core.subprocess, "run", side_effect=error):
                    with self.assertRaisesRegex(core.Run02PreflightError,
                                                f"category={category}"):
                        core._docker_preflight(60.0)

    def _r1_paths(self, root):
        state = root / "reports/resource/RUN-02/retries/R1"
        state.mkdir(parents=True)
        return state, state / "APPROVAL.txt", state / "ATTEMPT_STARTED.json", state / "PREFLIGHT.json"

    def _fake_outcome(self, root):
        run_dir = root / "data/raw/generated/RUN-02/fake-run"
        run_dir.mkdir(parents=True)
        return SimpleNamespace(
            run_id="fake-run", run_dir=str(run_dir), execution_status="ok",
            evaluation_status="ok", archive_status="ok", cleanup_status="ok",
            cleanup_errors=[], resolved=False, budget_usage={})

    def test_r1_actual_entry_rejects_old_approval_without_runner_call(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            _, approval, marker, preflight = self._r1_paths(root)
            approval.write_text(json.dumps({"checklist_identity": {"old": True},
                                            "approved_by": "test",
                                            "approved_at_utc": "now"}))
            runner = SimpleNamespace(project_root=root, credentials=None)
            runner.run = mock.Mock(return_value=self._fake_outcome(root))
            identity = {"attempt_label": "RUN-02-R1"}
            with mock.patch.object(r1, "R1_APPROVAL", approval), \
                 mock.patch.object(r1, "R1_MARKER", marker), \
                 mock.patch.object(r1, "R1_PREFLIGHT", preflight), \
                 mock.patch.object(core, "build_run02_runner",
                                   return_value=(runner, identity)):
                rc = r1.main(["--execute", "--i-approve-the-run-02-r1"])
            self.assertEqual(rc, 3)
            runner.run.assert_not_called()
            self.assertFalse(marker.exists())

    def test_r1_actual_entry_allows_one_call_then_rejects_repeat(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            _, approval, marker, preflight = self._r1_paths(root)
            identity = {"attempt_label": "RUN-02-R1"}
            approval.write_text(json.dumps({"checklist_identity": identity,
                                            "approved_by": "test",
                                            "approved_at_utc": "now"}))
            runner = SimpleNamespace(project_root=root, credentials=None)
            runner.run = mock.Mock(return_value=self._fake_outcome(root))
            with mock.patch.object(r1, "R1_APPROVAL", approval), \
                 mock.patch.object(r1, "R1_MARKER", marker), \
                 mock.patch.object(r1, "R1_PREFLIGHT", preflight), \
                 mock.patch.object(core, "build_run02_runner",
                                   return_value=(runner, identity)), \
                 mock.patch.object(core, "_docker_preflight",
                                   return_value={"context": "default"}), \
                 mock.patch.object(core, "_credentials", return_value={}), \
                 mock.patch("agent_workload_characterization.analyzers.run_02_analysis.write_run_02_report",
                            return_value={"status": "complete"}):
                self.assertEqual(r1.main([
                    "--execute", "--i-approve-the-run-02-r1"]), 0)
                self.assertEqual(r1.main([
                    "--execute", "--i-approve-the-run-02-r1"]), 3)
            runner.run.assert_called_once()

    def test_r1_actual_entry_records_preflight_failure_without_runner_call(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            _, approval, marker, preflight = self._r1_paths(root)
            identity = {"attempt_label": "RUN-02-R1"}
            approval.write_text(json.dumps({"checklist_identity": identity,
                                            "approved_by": "test",
                                            "approved_at_utc": "now"}))
            runner = SimpleNamespace(project_root=root, credentials=None)
            runner.run = mock.Mock(return_value=self._fake_outcome(root))
            with mock.patch.object(r1, "R1_APPROVAL", approval), \
                 mock.patch.object(r1, "R1_MARKER", marker), \
                 mock.patch.object(r1, "R1_PREFLIGHT", preflight), \
                 mock.patch.object(core, "build_run02_runner",
                                   return_value=(runner, identity)), \
                 mock.patch.object(core, "_docker_preflight",
                                   side_effect=core.Run02PreflightError(
                                       "RUN-02 preflight category=socket_access_denied")):
                self.assertEqual(r1.main([
                    "--execute", "--i-approve-the-run-02-r1"]), 4)
            runner.run.assert_not_called()
            self.assertEqual(json.loads(preflight.read_text())["status"], "failed")
            self.assertEqual(json.loads(marker.read_text())["status"], "failed")


if __name__ == "__main__":
    unittest.main()
