import io
import json
import tempfile
import unittest
from contextlib import nullcontext
from pathlib import Path
from unittest import mock

from agent_workload_characterization.runners import p1_12_repeat_entry as entry
from agent_workload_characterization.runners import p1_12_entry as base
from agent_workload_characterization.runners.coding_pilot import FakeVerifier
from agent_workload_characterization.runners.container_runtime import FakeContainerRuntime
from agent_workload_characterization.runners.mini_agent_adapter import FakeAgentHarness
from agent_workload_characterization.collectors.semantic_recorder import FakeClock


class RepeatEntryTests(unittest.TestCase):
    def test_plan_is_independent_and_deterministic(self):
        plan = entry.build_plan()
        self.assertEqual(plan["collection"], "P1-12-CODING-REPEAT-01")
        self.assertEqual(len(plan["identity"]["design"]["order"]), 9)
        self.assertEqual(
            [x["instance_id"] for x in plan["identity"]["design"]["order"]].count(
                "django__django-16485"), 3)
        self.assertIn("--i-approve-the-p1-12-coding-repeat-01", plan["command"])
        self.assertIn("CODING-REPEAT-01", plan["identity"]["report_root"])
        self.assertEqual(plan["authorization"]["user_approval"], "pending")

    def test_plan_has_no_external_side_effects_and_old_flag_is_rejected(self):
        # The actual plan may compute hashes, but must not assemble production
        # factories or read credentials.
        with mock.patch.object(base, "production_factories", side_effect=AssertionError), \
             mock.patch.object(base, "resolve_credentials", side_effect=AssertionError), \
             mock.patch("sys.stdout", new_callable=io.StringIO):
            self.assertEqual(entry.main([]), 0)
        with self.assertRaises(SystemExit):
            entry.main(["--execute", "--i-approve-the-p1-12-b"])

    def test_existing_attempt_namespace_is_rejected_without_runtime(self):
        parent = entry.base.PROJECT_ROOT / "reports/resource/P1-12/repeats"
        parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=parent) as td:
            state = Path(td)
            paths = {"STATE_ROOT": state, "APPROVAL": state / "APPROVAL.json",
                     "ATTEMPT": state / "ATTEMPT_STARTED.json",
                     "PREFLIGHT": state / "PREFLIGHT.json"}
            paths["STATE_ROOT"].mkdir(parents=True, exist_ok=True)
            paths["ATTEMPT"].write_text("{}")
            with mock.patch.multiple(entry, **paths), \
                 mock.patch.object(base, "production_factories", side_effect=AssertionError):
                with mock.patch("sys.stdout", new_callable=io.StringIO):
                    self.assertEqual(entry.main(["--execute",
                        "--i-approve-the-p1-12-coding-repeat-01"]), 3)

    def test_actual_entry_uses_shared_batch_runner_with_fake_boundaries(self):
        clock = FakeClock()
        def runtime_factory():
            return FakeContainerRuntime(clock)
        script = {"steps": [{"model": {"usage": {"prompt_tokens": 1,
                                      "completion_tokens": 1,
                                      "total_tokens": 2}},
                              "tools": [{"command": "true",
                                         "category": "Synthetic"}]}],
                  "final": {"status": "ok", "candidate_patch": "diff --git a/x b/x\n"}}
        def harness_factory(image):
            return FakeAgentHarness(clock, script)
        def verifier_factory():
            return FakeVerifier(clock, {"status": "ok", "resolved": False})
        parent = entry.base.PROJECT_ROOT / "reports/resource/P1-12/repeats"
        parent.mkdir(parents=True, exist_ok=True)
        formal_report_root = entry.base.PROJECT_ROOT / "reports/resource/P1-12/repeats/CODING-REPEAT-01"
        formal_raw_root = entry.base.PROJECT_ROOT / "data/raw/generated/P1-12-CODING-REPEAT-01"
        before_report = {p.relative_to(formal_report_root): p.read_bytes()
                         for p in formal_report_root.rglob("*") if p.is_file()}
        before_raw = {p.relative_to(formal_raw_root): p.read_bytes()
                      for p in formal_raw_root.rglob("*") if p.is_file()}
        with tempfile.TemporaryDirectory(dir=parent) as td, \
             tempfile.TemporaryDirectory() as raw_td:
            state = Path(td) / "namespace"
            raw_project = Path(raw_td)
            (raw_project / "data/raw/generated").mkdir(parents=True)
            paths = {"STATE_ROOT": state, "APPROVAL": state / "APPROVAL.json",
                     "ATTEMPT": state / "ATTEMPT_STARTED.json",
                     "PREFLIGHT": state / "PREFLIGHT.json"}
            with mock.patch.multiple(entry, **paths), \
                 mock.patch.object(entry, "RAW_PROJECT_ROOT", raw_project), \
                 mock.patch.object(base, "preflight_checks", return_value={"status": "READY"}), \
                 mock.patch.object(base, "docker_image_preflight", return_value={"status": "READY"}), \
                 mock.patch.object(base, "resolve_credentials", return_value={"synthetic": "only"}), \
                 mock.patch.object(base, "production_factories", return_value=(runtime_factory, harness_factory, verifier_factory)), \
                 mock.patch("agent_workload_characterization.runners.g1_02_entry.local_docker_environment", return_value=nullcontext()):
                with mock.patch("sys.stdout", new_callable=io.StringIO):
                    self.assertEqual(entry.main(["--execute",
                        "--i-approve-the-p1-12-coding-repeat-01"]), 0)
            self.assertTrue((state / "APPROVAL.json").is_file())
            self.assertTrue((state / "ATTEMPT_STARTED.json").is_file())
            result = json.loads((state / "batch" / "summary.json").read_text())
            self.assertEqual(result["status"], "complete")
            self.assertEqual(len(result["attempts"]), 9)
            self.assertTrue(all(a["status"] == "executed" for a in result["attempts"]))
            self.assertEqual(json.loads((state / "ATTEMPT_STARTED.json").read_text())["status"], "completed")
            raw_files = {p.relative_to(raw_project / "data/raw/generated")
                         for p in (raw_project / "data/raw/generated").rglob("*") if p.is_file()}
            self.assertTrue(raw_files)
            self.assertTrue(all(str(p).startswith(entry.COLLECTION + "/") for p in raw_files))
            self.assertEqual({p.relative_to(formal_report_root): p.read_bytes()
                              for p in formal_report_root.rglob("*") if p.is_file()}, before_report)
            self.assertEqual({p.relative_to(formal_raw_root): p.read_bytes()
                              for p in formal_raw_root.rglob("*") if p.is_file()}, before_raw)
        self.assertFalse(any((Path(raw_td) / "data/raw/generated").rglob("*")))


if __name__ == "__main__":
    unittest.main()
