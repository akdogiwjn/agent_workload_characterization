"""RUN-02 A-stage offline checks; no Docker, network, model, or credentials."""

import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from agent_workload_characterization.analyzers.run_02_analysis import summarize_run_02
from agent_workload_characterization.runners import run_02_entry
from agent_workload_characterization.runners.report_writer import guard_resource_report


class Run02AStageTests(unittest.TestCase):
    def _plan_patches(self):
        catalog = {"budget_proposal": {
            "model_requests": 3, "steps": 3,
            "output_tokens_per_request": 64,
            "agent_wall_min": 1, "verifier_wall_min": 1,
            "total_wall_min": 2, "run_dir_threshold_gib": 1}}
        record = {"instance_id": "django__django-16485",
                  "problem_statement": "synthetic problem",
                  "log_parser": "fake", "eval_type": "fake",
                  "base_commit": "base"}
        cfg = {"agent": {}, "model": {"model_kwargs": {}},
               "environment": {}}
        return catalog, record, cfg

    def _offline_plan(self):
        catalog, record, cfg = self._plan_patches()
        with mock.patch.object(run_02_entry, "_read_catalog",
                               return_value=catalog), \
             mock.patch.object(run_02_entry, "_record", return_value=record), \
             mock.patch.object(run_02_entry, "MINI_VENV_PY", Path(__file__)), \
             mock.patch.object(run_02_entry, "EVAL_VENV_PY", Path(__file__)), \
             mock.patch("agent_workload_characterization.runners.mini_agent_adapter.MiniSweAgentHarness.load_bundled_config",
                        return_value=cfg):
            return run_02_entry.build_plan()

    def test_plan_is_independent_and_side_effect_free(self):
        plan = self._offline_plan()
        self.assertEqual(plan["collection"], "RUN-02")
        self.assertEqual(plan["authorization"]["user_approval"], "pending")
        self.assertFalse(plan["side_effects"]["docker"])
        self.assertFalse(plan["side_effects"]["network"])
        self.assertFalse(plan["side_effects"]["credentials_read"])
        self.assertIn("run_02_entry", plan["entry"]["execute_command"])
        self.assertNotIn("RUN-01-C", json.dumps(plan))

    def test_catalog_and_record_identity_are_pinned(self):
        self.assertEqual(
            hashlib.sha256(run_02_entry.CATALOG_PATH.read_bytes()).hexdigest(),
            run_02_entry.CATALOG_SHA256)
        self.assertEqual(self._offline_plan()["record_instance_id"],
                         "django__django-16485")

    def test_identity_contains_catalog_and_complete_code_hashes(self):
        plan = self._offline_plan()
        identity = plan["identity"]
        self.assertEqual(identity["catalog_sha256"], run_02_entry.CATALOG_SHA256)
        self.assertIn("runners/run_02_entry.py", identity["code_sha256"])
        self.assertEqual(len(identity["code_sha256"]["runners/run_02_entry.py"]), 64)

    def test_attempt_registration_is_single_use(self):
        identity = {"collection": "RUN-02", "code_sha256": {"x": "y"}}
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            marker = root / "reports/resource/RUN-02/ATTEMPT_STARTED.json"
            marker.parent.mkdir(parents=True)
            with mock.patch.object(run_02_entry, "PROJECT_ROOT", root), \
                 mock.patch.object(run_02_entry, "ATTEMPT_MARKER_PATH", marker):
                run_02_entry._claim_attempt(identity)
                with self.assertRaises(run_02_entry.Run02EntryError):
                    run_02_entry._claim_attempt(identity)

    def test_infra_or_archive_failure_returns_nonzero(self):
        failed = {"execution_status": "infra_failure",
                  "archive_status": "failed", "report_status": "partial"}
        with mock.patch.object(run_02_entry, "execute_run02", return_value=failed):
            self.assertEqual(run_02_entry.main([
                "--execute", "--i-approve-the-run-02"]), 5)

    def test_verifier_infrastructure_failure_is_nonzero_but_unresolved_is_not(self):
        with mock.patch.object(run_02_entry, "execute_run02", return_value={
                "execution_status": "ok", "evaluation_status": "infra_failure",
                "cleanup_status": "ok", "archive_status": "ok",
                "report_status": "complete"}):
            self.assertEqual(run_02_entry.main([
                "--execute", "--i-approve-the-run-02"]), 5)
        with mock.patch.object(run_02_entry, "execute_run02", return_value={
                "execution_status": "ok", "evaluation_status": "ok",
                "resolved": False, "cleanup_status": "ok",
                "archive_status": "ok", "report_status": "complete"}):
            self.assertEqual(run_02_entry.main([
                "--execute", "--i-approve-the-run-02"]), 0)

    def test_preflight_rejects_non_default_context_without_docker_side_effects(self):
        class Result:
            returncode = 0
            stdout = "remote\n"
        with mock.patch.object(run_02_entry.subprocess, "run",
                               return_value=Result()) as run:
            with self.assertRaises(run_02_entry.Run02PreflightError):
                run_02_entry._docker_preflight(60.0)
        self.assertEqual(run.call_args.args[0], ["docker", "context", "show"])
        self.assertEqual(run_02_entry.TARGET_IMAGE.split("@", 1)[1],
                         "sha256:19d403c243c2857e7cb9cf5af8ce3f1cb6d87be91c5254e1de00040e6db3b7d2")

    def test_derived_reader_requires_archived_observability_files(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "events.jsonl").write_text("", encoding="utf-8")
            (root / "samples.json").write_text(
                json.dumps({"scopes": {}, "evidence": {}, "collector": {}}),
                encoding="utf-8")
            (root / "metadata.json").write_text(json.dumps({
                "run_id": "run02-test", "attempt_id": "run02-test-a1",
                "task_id": "django__django-16485", "source_type": "synthetic",
                "execution_status": "ok", "evaluation_status": "not_run",
                "budget_usage": {},}), encoding="utf-8")
            (root / "mini_tool_events.jsonl").write_text(
                json.dumps({"event": "open", "event_id": "x", "seq": 1,
                            "command_view": {"sha256": "x", "length": 1}}) + "\n",
                encoding="utf-8")
            (root / "mini_trajectory.json").write_text(
                json.dumps({"messages": [], "info": {}}), encoding="utf-8")
            (root / "mini_status.jsonl").write_text("", encoding="utf-8")
            (root / "host_process.jsonl").write_text(json.dumps({
                "identity": {"pid": 1, "starttime_ticks": 2},
                "units": {"clk_tck": 100, "page_size": 4096},
                "records": [], "summary": {}}), encoding="utf-8")
            out = summarize_run_02(root)
            self.assertEqual(out["collection"], "RUN-02")
            self.assertTrue(out["host_process"]["identity_present"])
            self.assertTrue(out["tool_events"]["safe_command_views_only"])
            self.assertEqual(out["status"], "partial")
            self.assertTrue(out["observation_quality"]["tool_complete"])

    def test_empty_or_invalid_observation_cannot_be_complete(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            for name, value in {
                "events.jsonl": "", "samples.json": json.dumps({}),
                "metadata.json": json.dumps({"execution_status": "ok"}),
                "mini_tool_events.jsonl": "",
                "mini_trajectory.json": json.dumps({"messages": []}),
                "mini_status.jsonl": "",
                "host_process.jsonl": json.dumps({}),
            }.items():
                (root / name).write_text(value, encoding="utf-8")
            out = summarize_run_02(root)
            self.assertEqual(out["status"], "partial")
            self.assertFalse(out["host_process"]["identity_present"])

    def test_resource_report_guard_rejects_symlinked_parent(self):
        with tempfile.TemporaryDirectory() as td, tempfile.TemporaryDirectory() as outside:
            root = Path(td)
            (root / "reports").symlink_to(Path(outside), target_is_directory=True)
            with self.assertRaises(ValueError):
                guard_resource_report(root, root / "reports/resource/RUN-02/one")


if __name__ == "__main__":
    unittest.main()
