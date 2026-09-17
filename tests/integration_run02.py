"""RUN-02 A-stage real-mini offline observability integration.

Uses the existing RUN-01 integration fixture and harness, but exercises the
new RUN-02 derived reader over the sealed mini tool/host files.  The fake
transport blocks real HTTP and the fake environment never calls Docker.
"""

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from agent_workload_characterization.analyzers.run_02_analysis import (
    summarize_run_02,
)
from agent_workload_characterization.runners.coding_pilot import BudgetLimits
from agent_workload_characterization.runners.container_runtime import (
    FakeContainerRuntime,
)
from agent_workload_characterization.runners.mini_agent_adapter import (
    AgentTask,
)

from tests.integration_run01 import (  # noqa: E402
    CANDIDATE, FAKE_ENV, GIT_DIFF_CMD, GREP_CMD, MINI_CFG, MiniThroughputTestBase,
    SUBMIT_CMD, _tool_call,
)
from agent_workload_characterization.collectors.semantic_recorder import (
    FakeClock, SemanticRecorder,
)
from agent_workload_characterization.runners.coding_pilot import FakeVerifier
from agent_workload_characterization.runners import run_02_entry
from agent_workload_characterization.runners import run_02_r2_entry


class Run02MiniObservabilityTests(MiniThroughputTestBase):
    def test_real_mini_archives_hook_host_and_derived_views(self):
        bad_cmd = "python repro.py"
        env_script = {
            bad_cmd: {"returncode": 1, "output": "boom"},
            GREP_CMD: {"returncode": 0, "output": "found"},
            SUBMIT_CMD: FAKE_ENV[SUBMIT_CMD],
        }
        harness = self._harness(
            [_tool_call(bad_cmd), _tool_call(GREP_CMD),
             _tool_call(SUBMIT_CMD)], env_script=env_script)
        task, budget, recorder, runtime, container = self._context(harness)
        result = harness.run(task, budget, recorder, runtime, container,
                             None, self.run_dir)
        self.assertEqual(result.status, "ok")
        recorder.seal()
        (self.run_dir / "samples.json").write_text(json.dumps({
            "scopes": {}, "evidence": {}, "collector": {},
        }), encoding="utf-8")
        (self.run_dir / "metadata.json").write_text(json.dumps({
            "run_id": "r02-it", "attempt_id": "r02-it-a1",
            "task_id": "django__django-16485", "source_type": "synthetic",
            "execution_status": "ok", "evaluation_status": "not_run",
            "budget_usage": budget.usage_dict(),
        }), encoding="utf-8")
        derived = summarize_run_02(self.run_dir)
        self.assertEqual(derived["collection"], "RUN-02")
        self.assertEqual(derived["tool_events"]["n_open"], 3)
        self.assertEqual(derived["tool_events"]["n_closed"], 2)
        self.assertEqual(derived["tool_events"]["n_error"], 1)
        self.assertTrue(derived["tool_events"]["safe_command_views_only"])
        self.assertTrue(derived["host_process"]["identity_present"])
        self.assertEqual(len(derived["tool_timeline"]["records"]), 3)

    def test_entry_runner_archive_and_report_complete_chain(self):
        """Exercise RUN-02 entry approval -> runner -> archive -> report.

        All external boundaries are replaced with FakeContainerRuntime and
        fake transport/environment; the mini subprocess itself remains real.
        """
        with tempfile.TemporaryDirectory() as td:
            project = Path(td)
            (project / "data/raw/generated").mkdir(parents=True)
            (project / "reports/resource/RUN-02").mkdir(parents=True)
            runtime = FakeContainerRuntime(FakeClock())
            runtime.execute_script["git -c core.fileMode=false diff"] = {
                "returncode": 0, "output": CANDIDATE}
            harness = self._harness(
                [_tool_call(GREP_CMD), _tool_call(SUBMIT_CMD)],
                env_script=FAKE_ENV)
            verifier = FakeVerifier(FakeClock(), {"resolved": False})
            runner, identity = run_02_entry.build_run02_runner(
                authorized=True, runtime=runtime, harness=harness,
                verifier=verifier, project_root=project)
            state_dir = project / "reports/resource/RUN-02"
            approval = state_dir / "APPROVAL.txt"
            approval.write_text(json.dumps({
                "checklist_identity": identity,
                "approved_by": "offline-test",
                "approved_at_utc": "2026-09-14T00:00:00Z",
            }), encoding="utf-8")
            marker = state_dir / "ATTEMPT_STARTED.json"
            with mock.patch.object(run_02_entry, "APPROVAL_PATH", approval), \
                 mock.patch.object(run_02_entry, "ATTEMPT_MARKER_PATH", marker), \
                 mock.patch.object(run_02_entry, "_docker_preflight",
                                   return_value={"context": "default"}), \
                 mock.patch.object(run_02_entry, "_credentials",
                                   return_value={"OPENAI_API_BASE": "fake",
                                                 "OPENAI_API_KEY": "fake"}), \
                 mock.patch.object(run_02_entry, "build_run02_runner",
                                   return_value=(runner, identity)):
                result = run_02_entry.execute_run02()
            self.assertEqual(result["archive_status"], "ok")
            self.assertEqual(result["report_status"], "complete")
            self.assertEqual(result["cleanup_status"], "ok")
            report = Path(result["report_dir"])
            summary = json.loads((report / "summary.json").read_text())
            self.assertEqual(summary["status"], "complete")
            self.assertGreater(summary["tool_timeline"]["coverage"][
                "n_valid_durations"], 0)
            self.assertEqual(len(runtime.started), 2)
            self.assertEqual(runtime.started[0].pull, "never")
            self.assertEqual(runtime.started[0].network, "none")
            self.assertEqual(runtime.active_at_start[1], [])
            self.assertEqual(len(runtime.stop_calls), 2)
            self.assertTrue(all(timeout > 60.0 for timeout in runtime.stop_calls))
            with self.assertRaises(run_02_entry.Run02EntryError):
                run_02_entry.execute_run02()

    def test_r2_entry_real_credential_route_to_real_mini_archive_report(self):
        """R2 entry owns the full fake-config -> real mini chain.

        Docker and HTTP remain blocked by the fake runtime/transport, but the
        entry calls the real loader and the installed mini subprocess rather
        than replacing either with a credentials mock.
        """
        with tempfile.TemporaryDirectory() as td:
            project = Path(td)
            (project / "data/raw/generated").mkdir(parents=True)
            (project / "reports/resource/RUN-02/retries/R2").mkdir(parents=True)
            config = project / "synthetic-opencode.json"
            config.write_text(json.dumps({"provider": {"火山AI网关": {
                "options": {"baseURL": "https://gateway.invalid/v1",
                            "apiKey": "{env:VOLCANO_API_KEY}"},
                "models": {"deepseek-v4-flash": {"name": "deepseek-v4-flash"}}
            }}}), encoding="utf-8")
            runtime = FakeContainerRuntime(FakeClock())
            runtime.execute_script[GIT_DIFF_CMD] = {
                "returncode": 0, "output": CANDIDATE}
            harness = self._harness([_tool_call(GREP_CMD),
                                    _tool_call(SUBMIT_CMD)], env_script=FAKE_ENV)
            harness.payload_extras["_fake_transport"]["assert_credentials"] = True
            verifier = FakeVerifier(FakeClock(), {"resolved": False})
            with mock.patch.object(run_02_r2_entry.smoke_launcher,
                                   "DEFAULT_CONFIG", config), \
                 mock.patch.dict(os.environ, {"VOLCANO_API_KEY": "fake-secret",
                                              "HTTP_PROXY": "http://unapproved.invalid"},
                                 clear=False), \
                 run_02_r2_entry._r2_configuration():
                runner, identity = run_02_entry.build_run02_runner(
                    authorized=True, runtime=runtime, harness=harness,
                    verifier=verifier, project_root=project)
            approval = project / "reports/resource/RUN-02/retries/R2/APPROVAL.txt"
            approval.write_text(json.dumps({
                "checklist_identity": identity,
                "approved_by": "offline-test",
                "approved_at_utc": "2026-09-14T00:00:00Z",
            }), encoding="utf-8")
            marker = approval.with_name("ATTEMPT_STARTED.json")
            preflight = approval.with_name("PREFLIGHT.json")
            with mock.patch.object(run_02_r2_entry, "R2_APPROVAL", approval), \
                 mock.patch.object(run_02_r2_entry, "R2_MARKER", marker), \
                 mock.patch.object(run_02_r2_entry, "R2_PREFLIGHT", preflight), \
                 mock.patch.object(run_02_entry, "build_run02_runner",
                                   return_value=(runner, identity)), \
                 mock.patch.object(run_02_entry, "_docker_preflight",
                                   return_value={"context": "default"}), \
                 mock.patch.object(run_02_r2_entry.smoke_launcher,
                                   "DEFAULT_CONFIG", config), \
                 mock.patch.dict(os.environ, {"VOLCANO_API_KEY": "fake-secret",
                                              "HTTP_PROXY": "http://unapproved.invalid"},
                                 clear=False):
                result = run_02_r2_entry.main([
                    "--execute", "--i-approve-the-run-02-r2"])
            self.assertEqual(result, 0)
            self.assertEqual(runner.credentials["OPENAI_API_BASE"],
                             "https://gateway.invalid/v1")
            self.assertEqual(runner.credentials["OPENAI_API_KEY"], "fake-secret")
            self.assertEqual(Path(result if False else marker).read_text().count(
                "fake-secret"), 0)
            self.assertEqual(json.loads(marker.read_text())["status"], "finished")
            reports = [p for p in (project / "reports/resource/RUN-02").iterdir()
                       if p.is_dir() and p.name != "retries"]
            self.assertEqual(len(reports), 1)
            report = reports[0]
            self.assertTrue((report / "summary.json").is_file())
            self.assertEqual(json.loads((report / "summary.json").read_text())["status"],
                             "complete")
            self.assertNotIn("fake-secret", "".join(
                path.read_text(encoding="utf-8")
                for path in report.rglob("*") if path.is_file()))

    def test_missing_observability_files_are_not_normal(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            # Reuse the minimal fixture shape from the unit test but omit the
            # two new raw observation files.
            (root / "events.jsonl").write_text("", encoding="utf-8")
            (root / "samples.json").write_text(
                json.dumps({"scopes": {}, "evidence": {}, "collector": {}}),
                encoding="utf-8")
            (root / "metadata.json").write_text(json.dumps({
                "run_id": "x", "attempt_id": "x-a1", "task_id": "django__django-16485",
                "source_type": "synthetic", "execution_status": "ok",
                "evaluation_status": "not_run", "budget_usage": {}}),
                encoding="utf-8")
            (root / "mini_trajectory.json").write_text(
                json.dumps({"messages": [], "info": {}}), encoding="utf-8")
            (root / "mini_status.jsonl").write_text("", encoding="utf-8")
            out = summarize_run_02(root)
            self.assertNotEqual(out["status"], "complete")
            self.assertIn("mini_tool_events.jsonl", out["missing_required_files"])


if __name__ == "__main__":
    unittest.main()
