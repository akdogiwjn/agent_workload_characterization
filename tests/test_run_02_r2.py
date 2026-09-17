"""RUN-02-R2 A-stage offline tests; no Docker, network, or real secret."""

import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from agent_workload_characterization.runners import run_02_entry as core
from agent_workload_characterization.runners import run_02_r2_entry as r2


class Run02R2Tests(unittest.TestCase):
    def _paths(self, root):
        state = root / "reports/resource/RUN-02/retries/R2"
        state.mkdir(parents=True)
        return state, state / "APPROVAL.txt", state / "ATTEMPT_STARTED.json", state / "PREFLIGHT.json"

    def _fake_outcome(self, root):
        run_dir = root / "data/raw/generated/RUN-02/fake-run"
        run_dir.mkdir(parents=True)
        return SimpleNamespace(run_id="fake-run", run_dir=str(run_dir),
                               execution_status="ok", evaluation_status="ok",
                               archive_status="ok", cleanup_status="ok",
                               cleanup_errors=[], resolved=False,
                               budget_usage={})

    def _approval(self, path, identity):
        path.write_text(json.dumps({"checklist_identity": identity,
                                    "approved_by": "test",
                                    "approved_at_utc": "now"}))

    def test_plan_is_fixed_and_side_effect_free(self):
        with mock.patch.object(core, "MINI_VENV_PY", Path(__file__)), \
             mock.patch.object(core, "EVAL_VENV_PY", Path(__file__)), \
             mock.patch.object(core, "_read_catalog", return_value={
                 "budget_proposal": {"model_requests": 1, "steps": 1,
                 "output_tokens_per_request": 1, "agent_wall_min": 1,
                 "verifier_wall_min": 1, "total_wall_min": 1,
                 "run_dir_threshold_gib": 1}, "collection_id": "RUN-02",
                 "execution_authorized": False}), \
             mock.patch.object(core, "_record", return_value={
                 "instance_id": "django__django-16485", "problem_statement": "x",
                 "log_parser": "x", "eval_type": "x"}), \
             mock.patch("agent_workload_characterization.runners.mini_agent_adapter.MiniSweAgentHarness.load_bundled_config",
                        return_value={"agent": {}, "model": {"model_kwargs": {}},
                                      "environment": {}}):
            plan = r2.build_plan()
        self.assertEqual(plan["attempt_label"], "RUN-02-R2")
        self.assertEqual(plan["authorization"]["user_approval"], "pending")
        self.assertFalse(plan["side_effects"]["r2_created"])
        self.assertIn("-u HTTP_PROXY", plan["entry"]["execute_command"])

    def test_credential_reference_maps_through_actual_r2_entry_child(self):
        with tempfile.TemporaryDirectory() as td:
            config = Path(td) / "config.json"
            config.write_text(json.dumps({"provider": {"火山AI网关": {
                "options": {"baseURL": "https://gateway.invalid/v1",
                            "apiKey": "{env:VOLCANO_API_KEY}"},
                "models": {"deepseek-v4-flash": {"name": "deepseek-v4-flash"}}
            }}}))
            original_proxy = os.environ.get("HTTP_PROXY")
            with mock.patch.object(r2.smoke_launcher, "DEFAULT_CONFIG", config), \
                 mock.patch.dict(os.environ, {"VOLCANO_API_KEY": "fake-secret",
                                              "HTTP_PROXY": "http://unapproved.invalid"}, clear=False), \
                 r2._r2_configuration():
                creds = r2._r2_credentials()
                env = {"PATH": "/usr/bin:/bin", **creds}
                child = subprocess.run(
                    ["/usr/bin/python3", "-c",
                     "import json,os; print(json.dumps({'base':bool(os.getenv('OPENAI_API_BASE')), 'key':bool(os.getenv('OPENAI_API_KEY')), 'proxy':any(os.getenv(k) for k in ('HTTP_PROXY','HTTPS_PROXY','ALL_PROXY','http_proxy','https_proxy','all_proxy'))}))"],
                    env=env, capture_output=True, text=True, check=True)
            self.assertEqual(json.loads(child.stdout),
                             {"base": True, "key": True, "proxy": False})
            self.assertEqual(os.environ.get("HTTP_PROXY"), original_proxy)

    def test_old_approval_isolation_and_preflight_failure_call_r2_entry(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            _, approval, marker, preflight = self._paths(root)
            identity = {"attempt_label": "RUN-02-R2"}
            self._approval(approval, {"attempt_label": "RUN-02-R1"})
            runner = SimpleNamespace(project_root=root, credentials=None)
            runner.run = mock.Mock(return_value=self._fake_outcome(root))
            with mock.patch.object(r2, "R2_APPROVAL", approval), \
                 mock.patch.object(r2, "R2_MARKER", marker), \
                 mock.patch.object(r2, "R2_PREFLIGHT", preflight), \
                 mock.patch.object(core, "build_run02_runner", return_value=(runner, identity)):
                self.assertEqual(r2.main(["--execute", "--i-approve-the-run-02-r2"]), 3)
            runner.run.assert_not_called()
            self.assertFalse(marker.exists())

            self._approval(approval, identity)
            with mock.patch.object(r2, "R2_APPROVAL", approval), \
                 mock.patch.object(r2, "R2_MARKER", marker), \
                 mock.patch.object(r2, "R2_PREFLIGHT", preflight), \
                 mock.patch.object(core, "build_run02_runner", return_value=(runner, identity)), \
                 mock.patch.object(core, "_docker_preflight", side_effect=core.Run02PreflightError("category=unknown")):
                self.assertEqual(r2.main(["--execute", "--i-approve-the-run-02-r2"]), 4)
            runner.run.assert_not_called()
            self.assertEqual(json.loads(preflight.read_text())["status"], "failed")
            self.assertEqual(json.loads(marker.read_text())["status"], "failed")

    def test_one_r2_call_only_and_parent_proxy_is_local_to_entry(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            _, approval, marker, preflight = self._paths(root)
            identity = {"attempt_label": "RUN-02-R2"}
            self._approval(approval, identity)
            runner = SimpleNamespace(project_root=root, credentials=None)
            runner.run = mock.Mock(return_value=self._fake_outcome(root))
            with mock.patch.object(r2, "R2_APPROVAL", approval), \
                 mock.patch.object(r2, "R2_MARKER", marker), \
                 mock.patch.object(r2, "R2_PREFLIGHT", preflight), \
                 mock.patch.object(core, "build_run02_runner", return_value=(runner, identity)), \
                 mock.patch.object(core, "_docker_preflight", return_value={"context": "default"}), \
                 mock.patch.object(r2, "_r2_credentials", return_value={"OPENAI_API_BASE": "https://x", "OPENAI_API_KEY": "fake"}), \
                 mock.patch("agent_workload_characterization.analyzers.run_02_analysis.write_run_02_report", return_value={"status": "complete"}), \
                 mock.patch.dict(os.environ, {"HTTP_PROXY": "http://unapproved.invalid"}, clear=False):
                self.assertEqual(r2.main(["--execute", "--i-approve-the-run-02-r2"]), 0)
                self.assertEqual(r2.main(["--execute", "--i-approve-the-run-02-r2"]), 3)
            runner.run.assert_called_once()
            self.assertEqual(runner.credentials["OPENAI_API_KEY"], "fake")

    def test_credential_failures_consume_r2_marker_without_runner(self):
        for config_value, env_present in ((None, True),
                                          ("{env:OTHER_KEY}", True),
                                          ("{env:VOLCANO_API_KEY}", False)):
            with self.subTest(config_value=config_value), tempfile.TemporaryDirectory() as td:
                root = Path(td)
                _, approval, marker, preflight = self._paths(root)
                identity = {"attempt_label": "RUN-02-R2"}
                options = {"baseURL": "https://gateway.invalid/v1"}
                if config_value is not None:
                    options["apiKey"] = config_value
                config = Path(td) / "config.json"
                config.write_text(json.dumps({"provider": {"火山AI网关": {
                    "options": options,
                    "models": {"deepseek-v4-flash": {"name": "deepseek-v4-flash"}}
                }}}))
                self._approval(approval, identity)
                runner = SimpleNamespace(project_root=root, credentials=None)
                runner.run = mock.Mock(return_value=self._fake_outcome(root))
                with mock.patch.object(r2, "R2_APPROVAL", approval), \
                     mock.patch.object(r2, "R2_MARKER", marker), \
                     mock.patch.object(r2, "R2_PREFLIGHT", preflight), \
                     mock.patch.object(r2.smoke_launcher, "DEFAULT_CONFIG", config), \
                     mock.patch.dict(os.environ, {"VOLCANO_API_KEY": "fake-secret"}, clear=False), \
                     mock.patch.object(core, "build_run02_runner", return_value=(runner, identity)), \
                     mock.patch.object(core, "_docker_preflight", return_value={"context": "default"}):
                    if not env_present:
                        os.environ.pop("VOLCANO_API_KEY", None)
                    self.assertEqual(r2.main(["--execute", "--i-approve-the-run-02-r2"]), 3)
                runner.run.assert_not_called()
                marker_data = json.loads(marker.read_text())
                self.assertEqual(marker_data["status"], "failed")
                self.assertTrue(marker_data["error"].startswith("credentials:"))
                self.assertNotIn("fake-secret", marker.read_text())


if __name__ == "__main__":
    unittest.main()
