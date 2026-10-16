import io
import json
import tempfile
import unittest
from contextlib import nullcontext, redirect_stdout
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from agent_workload_characterization.runners import p1_12_single_entry as entry


class SingleEntryOfflineTests(unittest.TestCase):
    def test_plan_is_one_task_and_zero_side_effects(self):
        before = set(Path(entry.base.PROJECT_ROOT).glob(
            "reports/resource/P1-12/revalidations/FINISH-02/*"))
        out = io.StringIO()
        with redirect_stdout(out):
            self.assertEqual(entry.main([]), 0)
        plan = json.loads(out.getvalue())
        self.assertEqual(plan["task"], "django__django-16485")
        self.assertEqual(plan["scope"], "one attempt; no retry; no nine-attempt batch")
        self.assertEqual(plan["identity"]["model"]["provider"], "deepseek-official")
        self.assertEqual(plan["identity"]["model"]["model_key"], "deepseek-flash")
        self.assertEqual(plan["limits"]["max_model_requests"], 30)
        after = set(Path(entry.base.PROJECT_ROOT).glob(
            "reports/resource/P1-12/revalidations/FINISH-02/*"))
        self.assertEqual(before, after)

    def test_both_flags_are_required(self):
        self.assertEqual(entry.main(["--execute"]), 2)

    def test_execute_command_uses_registered_evaluator_interpreter(self):
        self.assertTrue(entry.COMMAND.startswith(
            "PYTHONPATH=src " + str(entry.base.EVAL_VENV_PY)))
        self.assertIn("finish-02", entry.COMMAND)
        self.assertIn("--i-approve-the-p1-12-django-finish-02", entry.COMMAND)

    def test_finish_01_approval_flag_is_rejected(self):
        with self.assertRaises(SystemExit) as cm:
            entry.main(["--execute",
                        "--i-approve-the-p1-12-django-finish-01"])
        self.assertEqual(cm.exception.code, 2)

    def test_plan_identity_is_finish_02_only(self):
        out = io.StringIO()
        with redirect_stdout(out):
            self.assertEqual(entry.main([]), 0)
        plan = json.loads(out.getvalue())
        ident = plan["identity"]
        self.assertEqual(plan["collection"], "P1-12-FINISH-02")
        self.assertEqual(ident["collection"], "P1-12-FINISH-02")
        self.assertTrue(ident["approval_path"].endswith("FINISH-02/APPROVAL.json"))
        self.assertTrue(ident["attempt_path"].endswith("FINISH-02/ATTEMPT_STARTED.json"))
        self.assertTrue(ident["report_path"].endswith("FINISH-02"))
        self.assertNotIn("FINISH-01", json.dumps(plan))

    def test_fake_success_stays_in_temporary_finish_02_namespace(self):
        old_root = entry.base.PROJECT_ROOT / "reports/resource/P1-12/revalidations/FINISH-01"
        old_files = {p: p.read_bytes() for p in old_root.glob("*") if p.is_file()}
        finish02_root = entry.base.PROJECT_ROOT / "reports/resource/P1-12/revalidations/FINISH-02"
        finish02_files = {p: p.read_bytes() for p in finish02_root.glob("*") if p.is_file()}
        with tempfile.TemporaryDirectory(
                dir=entry.base.PROJECT_ROOT / "reports/resource/P1-12/revalidations") as td, \
             tempfile.TemporaryDirectory() as raw_td:
            state = Path(td) / "FINISH-02"
            paths = {
                "STATE_ROOT": state,
                "APPROVAL": state / "APPROVAL.json",
                "ATTEMPT": state / "ATTEMPT_STARTED.json",
                "PREFLIGHT": state / "PREFLIGHT.json",
                "SUMMARY": state / "SUMMARY.json",
                "MANIFEST": state / "MANIFEST.json",
            }
            raw = Path(raw_td)
            (raw / "mini_trajectory.json").write_text(
                json.dumps({"info": {"model_stats": {"api_calls": 1},
                            "exit_status": "Submitted", "submission": "patch"}}))
            outcome = SimpleNamespace(
                run_id="synthetic-finish-02", attempt_id="synthetic-finish-02-a1",
                execution_status="ok", evaluation_status="ok", resolved=False,
                archive_status="ok", cleanup_status="ok", cleanup_errors=[],
                budget_usage={}, run_dir=str(raw))
            class FakeRunner:
                def run(self):
                    return outcome
            def fake_factories():
                return (lambda: object(), lambda image: object(),
                        lambda: object())
            with mock.patch.object(entry, "STATE_ROOT", paths["STATE_ROOT"]), \
                 mock.patch.object(entry, "APPROVAL", paths["APPROVAL"]), \
                 mock.patch.object(entry, "ATTEMPT", paths["ATTEMPT"]), \
                 mock.patch.object(entry, "PREFLIGHT", paths["PREFLIGHT"]), \
                 mock.patch.object(entry, "SUMMARY", paths["SUMMARY"]), \
                 mock.patch.object(entry, "MANIFEST", paths["MANIFEST"]), \
                 mock.patch.object(entry.sys, "executable", str(entry.base.EVAL_VENV_PY)), \
                 mock.patch.object(entry.base, "preflight_checks", return_value={"status": "READY"}), \
                 mock.patch.object(entry.base, "docker_image_preflight", return_value={"status": "READY"}), \
                 mock.patch.object(entry.base, "resolve_credentials", return_value={"safe": "synthetic"}), \
                 mock.patch.object(entry.base, "production_factories", side_effect=fake_factories), \
                 mock.patch.object(entry.base, "build_task_runner", return_value=FakeRunner()), \
                 mock.patch("agent_workload_characterization.runners.g1_02_entry.local_docker_environment", return_value=nullcontext()):
                rc = entry.main(["--execute",
                    "--i-approve-the-p1-12-django-finish-02"])
                self.assertEqual(rc, 0)
                self.assertTrue(paths["APPROVAL"].is_file())
                self.assertTrue(paths["ATTEMPT"].is_file())
                self.assertTrue(paths["SUMMARY"].is_file())
                self.assertTrue(paths["MANIFEST"].is_file())
            self.assertEqual({p: p.read_bytes() for p in old_root.glob("*") if p.is_file()}, old_files)
            self.assertEqual({p: p.read_bytes() for p in finish02_root.glob("*") if p.is_file()}, finish02_files)


if __name__ == "__main__":
    unittest.main()
