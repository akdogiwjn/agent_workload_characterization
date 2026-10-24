#!/usr/bin/env python3
"""Host-side offline regression for the audit-fixed runner (no docker, no
network). Covers the strict report evaluation counterexamples required by
the audit round:

- report missing -> fail
- report corrupt JSON -> fail
- report not an object / no checks -> fail
- required check missing -> fail
- required check failed -> fail
- failures list non-empty -> fail
- a fully valid report -> ok

Also asserts that the runner's REQUIRED_CHECKS list stays in sync with the
check names the in-container driver actually emits (static source scan), so
a renamed check cannot silently fall out of the strict gate.
"""
from __future__ import annotations

import json
import re
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from vimax_bailian_runner import evaluate_report, REQUIRED_CHECKS  # noqa: E402


def _valid_report() -> dict:
    checks = {name: {"ok": True, "detail": ""} for name in REQUIRED_CHECKS}
    return {"checks": checks, "failures": [], "wall_s": 1.0}


class EvaluateReportTest(unittest.TestCase):
    def test_missing_report_fails(self):
        ok, problems, parsed = evaluate_report(None)
        self.assertFalse(ok)
        self.assertIn("validation report missing", problems)
        self.assertIsNone(parsed)

    def test_corrupt_report_fails(self):
        ok, problems, _ = evaluate_report('{"checks": [BROKEN')
        self.assertFalse(ok)
        self.assertTrue(any("corrupt" in p for p in problems))

    def test_non_object_report_fails(self):
        ok, problems, _ = evaluate_report('[1, 2, 3]')
        self.assertFalse(ok)

    def test_empty_checks_fails(self):
        ok, problems, _ = evaluate_report(json.dumps({"checks": {}}))
        self.assertFalse(ok)
        self.assertTrue(any("no checks" in p for p in problems))

    def test_missing_required_check_fails(self):
        report = _valid_report()
        report["checks"].pop("agent_render_ok")
        ok, problems, _ = evaluate_report(json.dumps(report))
        self.assertFalse(ok)
        self.assertTrue(any("required check missing: agent_render_ok"
                            in p for p in problems))

    def test_failed_required_check_fails(self):
        report = _valid_report()
        report["checks"]["media_full_decode"] = {"ok": False, "detail": "x"}
        ok, problems, _ = evaluate_report(json.dumps(report))
        self.assertFalse(ok)
        self.assertTrue(any("required check failed: media_full_decode"
                            in p for p in problems))

    def test_nonempty_failures_fails(self):
        report = _valid_report()
        report["failures"] = ["something"]
        ok, problems, _ = evaluate_report(json.dumps(report))
        self.assertFalse(ok)
        self.assertTrue(any("failures list non-empty" in p for p in problems))

    def test_valid_report_passes(self):
        ok, problems, _ = evaluate_report(json.dumps(_valid_report()))
        self.assertTrue(ok, problems)
        self.assertEqual(problems, [])

    def test_preflight_counterexample_is_critical(self):
        report = _valid_report()
        report["checks"]["preflight_medium_variation_rejected_with_zero_sends"] = {
            "ok": False, "detail": "sent anyway"}
        ok, problems, _ = evaluate_report(json.dumps(report))
        self.assertFalse(ok)
        self.assertTrue(any("critical check failed" in p for p in problems))


class CheckNameSyncTest(unittest.TestCase):
    def test_required_checks_exist_in_driver_source(self):
        driver = (HERE / "offline_validation.py").read_text(encoding="utf-8")
        emitted = set(re.findall(r'check\(\s*"([A-Za-z0-9_]+)"', driver))
        # dynamically generated names: check(f"env_dep_{mod}") over the
        # module tuple in stage_environment
        if 'check(f"env_dep_{mod}"' in driver:
            mods = re.search(r'for mod in \(([^)]+)\):', driver)
            if mods:
                for mod in re.findall(r'"([A-Za-z0-9_]+)"', mods.group(1)):
                    emitted.add(f"env_dep_{mod}")
        missing = [name for name in REQUIRED_CHECKS if name not in emitted]
        self.assertEqual(
            missing, [],
            f"REQUIRED_CHECKS names not emitted by offline_validation: "
            f"{missing} (strict gate would always fail)")


if __name__ == "__main__":
    unittest.main(verbosity=2)
