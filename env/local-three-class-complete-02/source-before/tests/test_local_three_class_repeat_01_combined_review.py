import json
from pathlib import Path
import tempfile
import unittest

from scripts import local_three_class_repeat_01_combined_review as review


class CombinedReviewTests(unittest.TestCase):
    @staticmethod
    def coding_run(run_id, cpu):
        return {"chain": "Coding", "task": review.TASKS["Coding"][1],
                "profile_stratum": "continuation_frozen_profile", "run_id": run_id,
                "task_result": True, "attempt_wall_s": 10, "behavior": {}, "phases": [],
                "disk": {"task_workspace": "unknown", "container": {}, "host": {"paths": []}},
                "scopes": [{"scope": run_id + "-agent-sandbox", "scope_kind": "agent_container",
                            "metric_quality": {"cpu": {"observed_valid_delta_sum": cpu}},
                            "memory_sampled_peak_bytes": 1024}]}

    def test_cpu_aggregates_by_role_not_unique_run_scope(self):
        runs = [self.coding_run("run-a", 32.247294), self.coding_run("run-b", 28.459129)]
        rows = review._task_stats(runs, [])
        cpu = next(x for x in rows if x["metric"] == "observed_cpu_s::agent_container")
        self.assertEqual(cpu["n"], 2)
        self.assertAlmostEqual(cpu["median"], 30.3532115)
        self.assertAlmostEqual(cpu["iqr"], 1.8940825)
        self.assertFalse(any("run-a" in r["metric"] or "run-b" in r["metric"] for r in rows))
        # Host and verifier observations are not added to Agent CPU.
        runs[0]["scopes"].append({"scope": "verifier-a", "scope_kind": "verifier_container",
                                 "metric_quality": {"cpu": {"observed_valid_delta_sum": 7}}})
        metrics = review._metrics_for(runs[0])
        self.assertEqual(metrics["observed_cpu_s::agent_container"], 32.247294)
        self.assertEqual(metrics["observed_cpu_s::verifier_container"], 7)
        runs[0]["scopes"].append(dict(runs[0]["scopes"][0]))
        with self.assertRaisesRegex(ValueError, "duplicate resource role"):
            review._metrics_for(runs[0])

    def test_verifier_reassessment_preserves_archived_partial(self):
        run = self.coding_run("run-a", 10)
        archived = {"status": "partial", "gaps": ["verifier_container_cpu_intervals_missing", "verifier_workspace_footprint_partial"]}
        run["acceptance"] = {"measurement": archived}
        report = {"execution_status": "no_candidate", "evaluation_status": "not_run"}
        events = [{"kind": "verifier", "attrs": {"status": "not_run"}}]
        review._reassess_verifier(run, report, events)
        self.assertEqual(run["measurement_reassessment"]["verifier"], "not_applicable")
        self.assertEqual(run["measurement_reassessment"]["status"], "complete")
        self.assertEqual(archived["status"], "partial")
        self.assertEqual(len(archived["gaps"]), 2)
        events.append({"kind": "container", "attrs": {"scope": "verifier", "action": "start"}})
        review._reassess_verifier(run, report, events)
        self.assertEqual(run["measurement_reassessment"]["status"], "partial")

    def test_primary_plot_selects_agent_role_not_host_or_verifier(self):
        metrics = {"observed_cpu_s::host_mini_child": {"median": 99},
                   "observed_cpu_s::agent_container": {"median": 5},
                   "observed_cpu_s::verifier_container": {"median": 7}}
        self.assertEqual(review._primary_metric(metrics, "Coding", "observed_cpu_s"), {"median": 5})

    def test_quantiles_use_linear_n_minus_one_definition(self):
        stats = review.distribution([1.0, 3.0])
        self.assertEqual(stats["median"], 2.0)
        self.assertEqual(stats["q1"], 1.5)
        self.assertEqual(stats["q3"], 2.5)
        self.assertEqual(stats["iqr"], 1.0)
        self.assertEqual(stats["n"], 2)

    def test_route_resolution_detects_missing_per_run_route(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "scripts/docops_word_resource_01_entry.py"
            source.parent.mkdir(parents=True)
            source.write_text(
                "API_BASE = 'https://api.deepseek.com/v1'\n"
                "api_base=route.get('api_base', API_BASE)\n", encoding="utf-8")
            digest = review.hashlib.sha256(source.read_bytes()).hexdigest()
            tasks = {task: [{"max_steps": 40} for _ in range(3)]
                     for task in review.TASKS["Office"]}
            frozen = {"identity": {"components": {"Office": {
                "model": {"route": {"provider": "火山AI网关", "api_base": "https://gateway.invalid/v1"}},
                "run_configs_by_task_round": tasks,
                "code_and_runtime_files": [{"path": "scripts/docops_word_resource_01_entry.py",
                                             "sha256": digest}]}}}}
            rows = [{"chain": "Office", "task": review.TASKS["Office"][1], "round": 0,
                     "slot_status": "executed"}]
            audit = review._route_profile(review.AuditInputs(root), frozen, rows)
            self.assertTrue(audit["new_office_route_mismatch_confirmed"])
            self.assertEqual(rows[0]["execution_profile_status"], "route_config_mismatch")
            self.assertEqual(audit["production_default_api_base"], "https://api.deepseek.com/v1")

    def test_office_error_text_is_removed_and_profile_excluded(self):
        record = {"chain": "Office", "execution_profile_status": "route_config_mismatch",
                  "behavior": {"tools": [{"error": "credential fragment must not escape"}],
                               "actual_http_attempts": 1, "actual_bill": 0,
                               "response_models": {"None": 1}}}
        review._strip_sensitive_result(record)
        encoded = json.dumps(record)
        self.assertNotIn("credential fragment", encoded)
        self.assertNotIn("None\"", encoded)
        self.assertFalse(record["task_protocol_valid_for_frozen_route"])
        self.assertIsNone(record["behavior"]["actual_http_attempts"])
        self.assertEqual(record["behavior"]["response_model_unknown_count"], 1)

    def test_not_executed_slots_never_become_zero_observations(self):
        slots = [{"chain": "Coding", "task": review.TASKS["Coding"][1],
                  "slot_status": "not_executed"}]
        rows = review._task_stats([], slots)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["n"], 0)
        self.assertEqual(rows[0]["raw_points"], [])
        self.assertIsNone(rows[0]["median"])
        self.assertFalse(rows[0]["eligible_as_frozen_profile_summary"])


if __name__ == "__main__":
    unittest.main()
