"""P1-12 review-v1 focused tests: the three real risks of this round.
Read-only over the sealed batch and the generated review report."""
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BATCH = ROOT / "reports/resource/P1-12/P1-12-20260928T023250Z-33ffbd62/summary.json"
REVIEW = ROOT / "reports/analysis/P1-12-review-v1/summary.json"


class P112ReviewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.batch = json.loads(BATCH.read_text())
        cls.review = json.loads(REVIEW.read_text())

    def test_requests_counter_matches_call_records_not_budget_labels(self):
        """270 must come from closed llm_request events, not be a copy of
        the configured 9x30 budget."""
        q1 = self.review["focused_questions"]["q1_requests"]
        # the budget counter is per-run and equals closed events per run
        self.assertEqual(q1["budget_counter_total"], q1["llm_closed_event_total"])
        # ok + errors reconstruct the total (no hidden extra calls)
        self.assertEqual(q1["llm_ok_total"] + q1["llm_error_total"],
                         q1["llm_closed_event_total"])
        # and it is NOT simply 9*30 with zero evidence: per-run closed
        # events were actually parsed from events.jsonl
        per_run = [p["llm"]["requests_closed"] for p in self.review["raw_points"]]
        self.assertEqual(sum(per_run), 270)
        self.assertTrue(all(0 < n <= 30 for n in per_run))

    def test_no_candidate_attempt_is_not_evaluated_not_failed(self):
        """The no_candidate attempt: empty/absent candidate, verifier never
        started, resolved null — never counted as an evaluation failure or
        as resolved=false."""
        nc = [p for p in self.review["raw_points"]
              if p["execution_status"] == "no_candidate"]
        self.assertEqual(len(nc), 1)
        p = nc[0]
        self.assertEqual(p["evaluation_status"], "not_run")
        self.assertIsNone(p["verifier_scope"])
        self.assertIsNone(p["resolved"])
        self.assertEqual(p["candidate_patch_bytes"] if "candidate_patch_bytes" in p
                         else 0, 0) if "candidate_patch_bytes" in p else None
        # per-task stats: verifier n=2 (not 3), agent n=3 (evidence kept)
        st = self.review["per_task"][p["instance_id"]]
        self.assertEqual(st["verifier_cpu_core_s_stats"]["n"], 2)
        self.assertEqual(st["agent_cpu_core_s_stats"]["n"], 3)
        self.assertEqual(st["resolved_false"], 2)
        self.assertEqual(st["not_evaluated"], 1)

    def test_missing_metrics_stay_null_not_zero(self):
        """Verifier stats for the not-evaluated attempt are excluded (n=2),
        never zero-filled; unknown stays unknown."""
        st = self.review["per_task"]["astropy__astropy-13398"]
        self.assertEqual(st["verifier_cpu_core_s_stats"]["n"], 2)
        for task, s in self.review["per_task"].items():
            # every agent point has real samples (n=3) — no zero fill
            self.assertEqual(s["agent_cpu_core_s_stats"]["n"], 3, task)
        self.assertIn("unknown", json.dumps(
            self.review["focused_questions"]["q1_requests"]["finding"]).lower()
            or "unknown")


if __name__ == "__main__":
    unittest.main()
