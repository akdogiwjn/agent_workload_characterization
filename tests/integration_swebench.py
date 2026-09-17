"""RUN-01 gate B offline integration tests for the swebench evaluator path.

Run with the gate-B evaluator venv interpreter (swebench package installed):

    PYTHONPATH=src .venvs/swebench-eval-02e7a74/bin/python \
        -m unittest tests.integration_swebench -v

Pure offline: make_test_spec + get_eval_report over the FIXED local record
with synthetic test logs. No containers, no docker, no network, no model.
The default project suite never imports swebench; this file is the explicit
entry that validates the real parsing chain used by SwebenchVerifierRunner.
"""

import json
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RECORD_PATH = (ROOT / "data/raw/public/swebench_verified/"
               "78f471bf655a3137b2e8a75af1501690ec009ec3/"
               "django__django-16485/record.json")
RECORD_SHA = ("762de270d1ce06ab23104a35322098178624865c886d7b0ddadf9044d8fe"
              "c46a")


def load_record() -> dict:
    import hashlib
    raw = RECORD_PATH.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == RECORD_SHA, "record hash drift"
    return json.loads(raw)


class MakeTestSpecTests(unittest.TestCase):
    def test_spec_from_fixed_record(self):
        from swebench.harness.utils import make_test_spec
        spec = make_test_spec(load_record())
        self.assertEqual(spec.instance_id, "django__django-16485")
        self.assertEqual(spec.repo, "django/django")
        self.assertEqual(spec.version, "5.0")
        self.assertEqual(spec.log_parser, "parse_log_django")
        self.assertEqual(spec.eval_type, "pass_and_fail")
        self.assertEqual(len(spec.FAIL_TO_PASS), 1)
        self.assertEqual(len(spec.PASS_TO_PASS), 9)
        self.assertIn("39f83765e12b0e5d260b7939fc3fe281d879b279",
                      spec.eval_script)
        self.assertIn("test_floatformat.py", spec.eval_script)


class GradingChainTests(unittest.TestCase):
    """get_eval_report over synthetic Django-format logs (the official
    parse_log_django path used by SwebenchVerifierRunner).

    The official get_logs_eval only parses the slice between the
    ">>>>> Start/End Test Output" markers that the eval script emits, so
    the synthetic logs reproduce that exact framing."""

    START = ">>>>> Start Test Output"
    END = ">>>>> End Test Output"

    def _log(self, f2p_status: str, p2p_status: str) -> str:
        record = load_record()
        lines = [f"{t} ... {f2p_status}" for t in record["FAIL_TO_PASS"]]
        lines += [f"{t} ... {p2p_status}" for t in record["PASS_TO_PASS"]]
        return f"{self.START}\n" + "\n".join(lines) + f"\n{self.END}\n"

    def _grade(self, log_text: str) -> dict:
        from swebench.harness.utils import make_test_spec
        from swebench.harness.grading import get_eval_report
        record = load_record()
        spec = make_test_spec(record)
        with tempfile.TemporaryDirectory() as tmp:
            log_path = Path(tmp) / "test_output.txt"
            log_path.write_text(log_text, encoding="utf-8")
            prediction = {"instance_id": record["instance_id"],
                          "model_name_or_path": "offline-integration-test",
                          "model_patch": "--- a/f.py\n+++ b/f.py\n"}
            report = get_eval_report(test_spec=spec, prediction=prediction,
                                     test_log_path=str(log_path),
                                     include_tests_status=True)
        return report[record["instance_id"]]

    def test_all_pass_resolves(self):
        report = self._grade(self._log("ok", "ok"))
        self.assertTrue(report["resolved"])
        self.assertFalse(report["infra_failure"])
        self.assertTrue(report["patch_successfully_applied"])
        f2p = report["tests_status"]["FAIL_TO_PASS"]
        self.assertEqual(len(f2p["success"]), 1)
        self.assertEqual(f2p["failure"], [])

    def test_f2p_fail_not_resolved(self):
        report = self._grade(self._log("FAIL", "ok"))
        self.assertFalse(report["resolved"])
        self.assertFalse(report["infra_failure"])

    def test_p2p_regression_not_resolved(self):
        report = self._grade(self._log("ok", "FAIL"))
        self.assertFalse(report["resolved"])

    def test_suite_not_run_keeps_unresolved(self):
        # log WITHOUT the start/end markers: the official chain treats it as
        # an unparseable/never-ran suite — resolved stays False, and our
        # verifier maps this shape to tests_not_run (never silently True)
        report = self._grade("some unrelated stdout noise\n")
        self.assertFalse(report["resolved"])


if __name__ == "__main__":
    unittest.main()
