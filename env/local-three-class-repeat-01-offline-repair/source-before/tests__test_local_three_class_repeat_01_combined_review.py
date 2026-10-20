import json
from pathlib import Path
import tempfile
import unittest

from scripts import local_three_class_repeat_01_combined_review as review


class CombinedReviewTests(unittest.TestCase):
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
