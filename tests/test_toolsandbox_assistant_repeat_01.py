"""Offline end-to-end preparation and fake batch regressions.

Run with the ToolSandbox pilot interpreter and PYTHONPATH=src:scripts. All
approval, report, attempt, and raw files are confined to TemporaryDirectory.
"""
from __future__ import annotations

import hashlib
import json
import shutil
import sys
import tempfile
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "scripts"), str(ROOT / "src"), str(ROOT / "tests")]

import toolsandbox_assistant_repeat_01_entry as batch
import toolsandbox_resource_pilot_01_entry as shared
import test_toolsandbox_resource_pilot_01 as pilot01_tests


def file_hash(path: Path) -> tuple[int, str]:
    data = path.read_bytes()
    return len(data), hashlib.sha256(data).hexdigest()


def write_approval(root: Path, identity_sha256: str) -> None:
    approval_path = root / batch.PROFILE.report_rel / "APPROVAL.json"
    approval_path.parent.mkdir(parents=True, exist_ok=True)
    approval_path.write_text(json.dumps({
        "schema": "toolsandbox-pilot-approval-v1",
        "collection": batch.PROFILE.collection,
        "user_approval": "approved",
        "identity_sha256": identity_sha256,
        "accept_unknown_cost_no_hard_cap": True,
    }) + "\n")


def fake_transport(task: str, round_index: int, position: int, *, block_s: float = 0) -> dict:
    if task == batch.TASKS[0]:
        # Reuse the already passing PILOT-01 fake script for this exact task.
        transport = pilot01_tests.fake_transport(pilot01_tests.standard_agent_script())
        if block_s:
            transport["script"]["agent"][0]["sleep_s"] = block_s
        return transport
    tool = "get_current_timestamp"
    return {"kind": "fake", "model_name": "offline-request-label",
            "script": {
                "agent": [
                    {"tool_calls": [{"id": f"agent-{round_index}-{position}", "type": "function",
                                     "function": {"name": tool, "arguments": "{}"}}],
                     "model": "offline-agent-response"},
                ] + [{"content": "Offline fixture response.",
                      "model": "offline-agent-response"} for _ in range(19)],
                "user": [{"content": "I do not have additional information.",
                          "model": "offline-user-response"} for _ in range(20)],
            }}


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


class AssistantRepeatBatchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory()
        cls.root = Path(cls._tmp.name)
        source_origin = ROOT / shared.PILOT_01_PROFILE.source_copy_rel
        source_manifest = ROOT / shared.PILOT_01_PROFILE.env_rel / "source-manifest.json"
        shutil.copytree(source_origin, cls.root / shared.PILOT_01_PROFILE.source_copy_rel)
        dest_manifest = cls.root / shared.PILOT_01_PROFILE.env_rel / "source-manifest.json"
        dest_manifest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source_manifest, dest_manifest)
        batch.prepare_source(cls.root)
        cls.frozen_plan = batch.freeze(cls.root)
        before = sorted(str(p.relative_to(cls.root)) for p in cls.root.rglob("*"))
        cls.unapproved_plan = batch.plan_mode(cls.root)
        after = sorted(str(p.relative_to(cls.root)) for p in cls.root.rglob("*"))
        cls.plan_mode_was_read_only = before == after
        write_approval(cls.root, cls.frozen_plan["identity_sha256"])
        cls.plan = batch.plan_mode(cls.root)

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def setUp(self):
        for rel in (batch.PROFILE.raw_rel, batch.PROFILE.report_rel):
            path = self.root / rel
            if path.exists():
                shutil.rmtree(path)
        write_approval(self.root, self.plan["identity_sha256"])

    def test_identity_plan_is_fixed_and_plan_mode_is_read_only(self):
        self.assertTrue(self.plan_mode_was_read_only)
        self.assertTrue(self.unapproved_plan["identity_matches_frozen"])
        self.assertTrue(self.unapproved_plan["ready_for_approval"])
        self.assertFalse(self.unapproved_plan["ready_for_execution"])
        self.assertTrue(self.plan["ready_for_execution"])
        self.assertEqual(self.plan["identity"]["batch"]["run_count"], 9)
        self.assertEqual(self.plan["identity"]["batch"]["max_logical_model_calls"], 360)
        self.assertEqual([x["name"] for x in self.plan["identity"]["scenario"]["tasks"]],
                         list(batch.TASKS))
        b_facts = self.plan["identity"]["scenario"]["tasks"][1]
        self.assertTrue(any("tomorrow 5PM" in row["content"]
                            for row in b_facts["task_messages"]))
        self.assertEqual(batch.PILOT_01_PROFILE.collection, "TOOLSANDBOX-RESOURCE-PILOT-01")
        self.assertNotEqual(batch.PROFILE.approval_flag, shared.PILOT_02_PROFILE.approval_flag)

    def test_nine_fake_runs_use_fixed_order_fresh_worker_state_and_final_manifests(self):
            root = self.root
            plan = self.plan
            protected_source_before = file_hash(ROOT / shared.PILOT_01_PROFILE.env_rel /
                                                "source-manifest.json")
            provider_calls = []

            def provider(task, round_index, position):
                provider_calls.append((round_index, task, position))
                return fake_transport(task, round_index, position)

            rc = batch.execute_batch(root, plan, transport_provider=provider,
                                     budgets_override={"total_wall_s": 180,
                                                       "cleanup_reserve_s": 10,
                                                       "play_s": 100,
                                                       "evaluate_s": 120,
                                                       "max_messages": 30},
                                     batch_budget_override={"total_wall_s": 2600,
                                                            "cleanup_reserve_s": 80})
            expected = [(r, task, p) for r, tasks in enumerate(batch.ROUND_SCHEDULE)
                        for p, task in enumerate(tasks)]
            report_root = root / batch.PROFILE.report_rel
            summary = json.loads((report_root / "batch-summary.json").read_text())
            worker_stderr = []
            for rows in summary["per_task"].values():
                for row in rows["runs"]:
                    stderr_path = root / batch.PROFILE.raw_rel / row["run_id"] / "worker.stderr"
                    if stderr_path.is_file():
                        worker_stderr.append(stderr_path.read_text()[-3000:])
            self.assertEqual(rc, 0, json.dumps({
                "stop_reason": summary["stop_reason"],
                "executed": summary["executed"],
                "runs": [{"run_id": p["run_id"], "task": p["task"],
                          "exit_code": p["exit_code"], "termination": p["termination"],
                          "worker_failure": p.get("worker_failure"),
                          "cleanup": p["cleanup"], "archive": p["archive_verification"],
                          "within_total_budget": p.get("within_total_budget")}
                         for rows in summary["per_task"].values() for p in rows["runs"]],
                "worker_stderr_tail": worker_stderr,
            }))
            self.assertEqual(provider_calls, expected)
            self.assertEqual(summary["executed"], 9)
            self.assertEqual(summary["not_executed_count"], 0)
            self.assertTrue(summary["execution_occurred"])
            all_run_ids = []
            for round_index, tasks in enumerate(batch.ROUND_SCHEDULE):
                for position, task in enumerate(tasks):
                    matching = [p for p in summary["per_task"][task]["runs"]
                                if p["round"] == round_index]
                    self.assertEqual(len(matching), 1)
                    point = matching[0]
                    run_id = point["run_id"]
                    all_run_ids.append(run_id)
                    raw = root / batch.PROFILE.raw_rel / run_id
                    report_path = report_root / "runs" / f"{run_id}.json"
                    report = json.loads(report_path.read_text())
                    self.assertEqual(report["scenario"], task)
                    self.assertEqual(report["run_metadata"]["sequence_index"],
                                     round_index * 3 + position)
                    self.assertEqual(report["worker_result"]["scenario_name"], task)
                    self.assertEqual(report["cleanup"]["wait_reaped"], True)
                    self.assertEqual(report["cleanup"]["original_process_gone"], True)
                    self.assertTrue(point["runtime_environment_present"])
                    env = json.loads((raw / "environment.json").read_text())
                    for field in ("python_executable", "pid", "starttime_ticks", "sc_clk_tck",
                                  "sc_page_size", "online_cpu_count", "worker_cpu_affinity",
                                  "cgroup_limits"):
                        self.assertIn(field, env)
                    context = json.loads((raw / "scenario_context.json").read_text())
                    self.assertEqual(context["scenario_name"], task)
                    self.assertIn("initialization_started_utc", context)
                    self.assertTrue(context["evaluation_milestone_targets"])
                    self.assertTrue(shared.verify_run_archive(raw)[0])
                    raw_manifest = json.loads((raw / 'manifest.json').read_text())
                    self.assertIn('supplemental_measurements.json',
                                  {row['path'] for row in raw_manifest['outputs']})
                    supplement = json.loads((raw / 'supplemental_measurements.json').read_text())
                    self.assertEqual(supplement['network']['scope_kind'],
                                     'network_namespace_shared')
                    self.assertEqual(supplement['task_workspace']['status'], 'not_applicable')
                    self.assertEqual(supplement['disk_footprint']['paths'][0]['role'],
                                     'attempt_output')
                    self.assertEqual(report['host_sampling']['resource_intervals'][0]
                                     ['metrics']['cpu']['unit'], 'cpu_seconds')
                    events = read_jsonl(raw / "events.jsonl")
                    roots = [e for e in events if e["kind"] == "run"]
                    opened = next(e for e in roots if e["status"] == "open")
                    closed = next(e for e in roots if e["status"] == "closed")
                    self.assertEqual(opened["event_id"], closed["event_id"])
                    self.assertEqual(opened["attrs"]["task_id"], task)
                    self.assertGreaterEqual(point["logical_requests"]["agent"], 2)
                    self.assertLessEqual(point["logical_requests"]["agent"], 20)
                    self.assertGreaterEqual(point["logical_requests"]["user"], 1)
                    self.assertLessEqual(point["logical_requests"]["user"], 20)
                    if task == batch.TASKS[0]:
                        self.assertIsNotNone(point["evaluation"])
                    elif point["evaluation"] is None:
                        self.assertEqual(report["worker_exit_code"], 3)
            self.assertEqual(len(set(all_run_ids)), 9)
            self.assertEqual(file_hash(ROOT / shared.PILOT_01_PROFILE.env_rel /
                                       "source-manifest.json"), protected_source_before)
            outer = json.loads((report_root / "manifest.json").read_text())
            self.assertFalse(outer["manifest_self_hash"])
            self.assertEqual(len(outer["raw_run_manifests"]), 9)
            self.assertEqual(len(outer["outputs"]), len({x["path"] for x in outer["outputs"]}))
            for item in outer["outputs"] + outer["raw_run_manifests"]:
                path = root / item["path"]
                self.assertEqual(file_hash(path), (item["bytes"], item["sha256"]))

    def test_blocked_play_stops_batch_preserves_right_censored_root_and_marks_remaining(self):
            root = self.root
            plan = self.plan
            calls = []

            def provider(task, round_index, position):
                calls.append(task)
                return fake_transport(task, round_index, position, block_s=2)

            rc = batch.execute_batch(root, plan, transport_provider=provider,
                                     budgets_override={"total_wall_s": 20,
                                                       "cleanup_reserve_s": 2,
                                                       "play_s": .2,
                                                       "evaluate_s": 5},
                                     batch_budget_override={"total_wall_s": 40,
                                                            "cleanup_reserve_s": 2})
            self.assertEqual(rc, 4)
            self.assertEqual(len(calls), 1)
            report_root = root / batch.PROFILE.report_rel
            summary = json.loads((report_root / "batch-summary.json").read_text())
            self.assertEqual(summary["executed"], 1)
            self.assertEqual(summary["not_executed_count"], 8)
            point = next(iter(summary["per_task"].values()))["runs"]
            timed = next(p for row in summary["per_task"].values() for p in row["runs"])
            raw = root / batch.PROFILE.raw_rel / timed["run_id"]
            report = json.loads((report_root / "runs" / f"{timed['run_id']}.json").read_text())
            self.assertTrue(report["killed_by_deadline"])
            self.assertTrue(report["cleanup"]["wait_reaped"])
            self.assertTrue(report["cleanup"]["original_process_gone"])
            events = read_jsonl(raw / "events.jsonl")
            run_events = [e for e in events if e["kind"] == "run"]
            self.assertEqual([e["status"] for e in run_events], ["open"])
            self.assertTrue(shared.verify_run_archive(raw)[0])
            self.assertEqual(len(json.loads((report_root / "manifest.json").read_text())[
                "raw_run_manifests"]), 1)

    def test_elapsed_batch_work_window_refuses_to_start_any_run(self):
            root = self.root
            plan = self.plan
            rc = batch.execute_batch(root, plan,
                                     started_monotonic_ns=time.monotonic_ns() - 10_000_000_000,
                                     budgets_override={"total_wall_s": 2, "cleanup_reserve_s": .2},
                                     batch_budget_override={"total_wall_s": 5,
                                                            "cleanup_reserve_s": 1})
            self.assertEqual(rc, 4)
            summary = json.loads((root / batch.PROFILE.report_rel /
                                  "batch-summary.json").read_text())
            self.assertEqual(summary["executed"], 0)
            self.assertEqual(summary["not_executed_count"], 9)
            self.assertEqual(list((root / batch.PROFILE.raw_rel).iterdir()), [])

    def test_old_collection_flag_is_rejected_without_creating_run_output(self):
            root = self.root
            with self.assertRaises(SystemExit) as raised:
                batch.main(["--execute", shared.PILOT_02_PROFILE.approval_flag], root=root)
            self.assertEqual(raised.exception.code, 2)
            self.assertFalse((root / batch.PROFILE.raw_rel).exists())


if __name__ == "__main__":
    unittest.main(verbosity=2)
