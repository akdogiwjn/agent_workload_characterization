"""CPU-02 offline integration tests for the real official grading chain.

Run with the pinned evaluator venv interpreter (swebench installed):

    PYTHONPATH=src .venvs/swebench-eval-02e7a74/bin/python \
        -m unittest tests.integration_cpu_02 -v

Pure offline: the CPU-02 entry's grade_eval over the FIXED local record
with synthetic Django-format test logs. No containers, no docker, no
network, no model. The default offline suite never imports swebench; this
is the explicit entry validating the real parsing chain used by CPU-02.
"""
import json
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RECORD_PATH = (ROOT / "data/raw/public/swebench_verified/"
               "78f471bf655a3137b2e8a75af1501690ec009ec3/"
               "django__django-16485/record.json")
CANDIDATE_PATH = (ROOT / "data/raw/generated/RUN-02/20260915T012427Z-2d75aa/"
                  "candidate.patch")
RECORD_SHA = ("762de270d1ce06ab23104a35322098178624865c886d7b0ddadf9044d8fe"
              "c46a")


def load_record() -> dict:
    import hashlib
    raw = RECORD_PATH.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == RECORD_SHA, "record hash drift"
    return json.loads(raw)


class GradeEvalTests(unittest.TestCase):
    """grade_eval through the official make_test_spec + get_eval_report:
    resolved=true, resolved=false and no-marker outcomes stay distinct."""

    START = ">>>>> Start Test Output"
    END = ">>>>> End Test Output"

    def test_registered_eval_script_identity_from_pinned_evaluator(self):
        from agent_workload_characterization.runners import cpu_02_entry as entry
        generated, metadata = entry._load_generated_eval_script(load_record())
        self.assertEqual(len(generated.encode()), 1453)
        self.assertEqual(metadata['original_sha256'],
                         entry.EVAL_SCRIPT_ORIGINAL_SHA256)
        self.assertEqual(metadata['generated_sha256'],
                         entry.EVAL_SCRIPT_GENERATED_SHA256)
        self.assertEqual(metadata['difference_id'],
                         'record_eval_script_plus_exit_code_v1')

    def _grade(self, log_text: str) -> dict:
        from agent_workload_characterization.runners.cpu_02_entry import grade_eval
        record = load_record()
        candidate = CANDIDATE_PATH.read_text()
        return grade_eval(log_text, record, candidate,
                          model_name="cpu-02-integration-test")

    def test_resolved_true(self):
        record = load_record()
        lines = [f"{t} ... ok" for t in record["FAIL_TO_PASS"]]
        lines += [f"{t} ... ok" for t in record["PASS_TO_PASS"]]
        result = self._grade(f"{self.START}\n" + "\n".join(lines)
                             + f"\n{self.END}\n")
        self.assertEqual(result["status"], "ok")
        self.assertTrue(result["resolved"])
        self.assertFalse(result["infra_failure"])

    def test_resolved_false(self):
        record = load_record()
        lines = [f"{t} ... FAILED" for t in record["FAIL_TO_PASS"]]
        lines += [f"{t} ... ok" for t in record["PASS_TO_PASS"]]
        result = self._grade(f"{self.START}\n" + "\n".join(lines)
                             + f"\n{self.END}\n")
        self.assertEqual(result["status"], "ok")
        self.assertFalse(result["resolved"])

    def test_no_markers_is_tests_not_run(self):
        result = self._grade("some random output\n")
        self.assertEqual(result["status"], "tests_not_run")
        self.assertIsNone(result["resolved"])

    def test_empty_log_is_tests_not_run(self):
        result = self._grade("")
        self.assertEqual(result["status"], "tests_not_run")
        self.assertIsNone(result["resolved"])


if __name__ == "__main__":
    unittest.main()
