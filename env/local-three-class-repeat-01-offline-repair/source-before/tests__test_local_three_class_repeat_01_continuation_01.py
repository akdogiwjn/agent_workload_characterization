"""Offline continuation acceptance tests; fixtures stay under temporary roots."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import socket
import sys
import tempfile
import unittest
from unittest.mock import patch

os.environ["LITELLM_LOCAL_MODEL_COST_MAP"] = "True"
ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "scripts")]

import local_three_class_repeat_01_continuation_01_entry as entry


def tree_hashes(root: Path) -> dict[str, str]:
    return {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in root.rglob("*") if p.is_file()}


class ContinuationAcceptanceTests(unittest.TestCase):
    def test_schedule_is_26_slots_and_skips_only_existing_excel_slot(self):
        rows = entry.planned_schedule()
        self.assertEqual(len(rows), 26)
        self.assertEqual([x["sequence"] for x in rows], list(range(26)))
        self.assertEqual(len({(x["chain"], x["round"], x["task"]) for x in rows}), 26)
        office = [x for x in rows if x["chain"] == "Office"]
        self.assertEqual(len(office), 8)
        self.assertNotIn(("Office", 0, entry.TASKS["Office"][0]),
                         {(x["chain"], x["round"], x["task"]) for x in rows})
        self.assertEqual([x["task"] for x in office], [
            entry.TASKS["Office"][1], entry.TASKS["Office"][2],
            entry.TASKS["Office"][1], entry.TASKS["Office"][2], entry.TASKS["Office"][0],
            entry.TASKS["Office"][2], entry.TASKS["Office"][0], entry.TASKS["Office"][1]])

    def test_three_saved_production_shapes_pass_independent_acceptance(self):
        sources = (
            ("Office", "LOCAL-THREE-CLASS-REPEAT-01", "20261016T182559Z-09-r0-office",
             "reports/resource/LOCAL-THREE-CLASS-REPEAT-01/20261016T182559Z-09-r0-office/run-report.json"),
            ("Coding", "CODING-MEASUREMENT-VOLCANO-01", "20261016T144518Z-django16485-91776c",
             "reports/resource/CODING-MEASUREMENT-VOLCANO-01/run-report.json"),
            ("Assistant", "TOOLSANDBOX-MEASUREMENT-VOLCANO-01", "20261016T145056Z-tsbvolcano01",
             "reports/resource/TOOLSANDBOX-MEASUREMENT-VOLCANO-01/run-report.json"),
        )
        snapshots = []
        results = []
        with patch.object(socket.socket, "connect", side_effect=AssertionError("network forbidden")):
            for chain, collection, run_id, report_path in sources:
                raw = ROOT / "data/raw/generated" / collection / run_id
                snapshots.append(tree_hashes(raw))
                report = json.loads((ROOT / report_path).read_text())
                result = entry.slot_acceptance(chain, {"chain": chain, "task": "fixed", "round": 0}, report, raw)
                results.append(result)
                self.assertEqual(result["slot_status"], "executed")
                self.assertEqual(result["cleanup_status"], "confirmed")
                self.assertEqual(result["archive_status"], "verified")
                self.assertEqual(result["measurement"]["status"], "complete")
                self.assertEqual(entry.stop_policy(result), (False, False, None))
        for source, old in zip(sources, snapshots):
            raw = ROOT / "data/raw/generated" / source[1] / source[2]
            self.assertEqual(tree_hashes(raw), old)
        office = results[0]
        self.assertIn("host_agent_process", office["measurement"]["cpu_intervals"])
        self.assertTrue(office["measurement"]["network"]["network_valid_interface_interval_records"] > 0)
        self.assertIn("agent_container", results[1]["measurement"]["cpu_intervals"])
        self.assertIn("verifier_container", results[1]["measurement"]["cpu_intervals"])
        self.assertEqual(results[2]["measurement"]["network"]["network_samples"], 40)

    def test_unreadable_office_report_keeps_raw_cleanup_and_stops_only_its_chain(self):
        raw = ROOT / "data/raw/generated/LOCAL-THREE-CLASS-REPEAT-01/20261016T182559Z-09-r0-office"
        result = entry.slot_acceptance("Office", {"chain": "Office", "round": 0}, {}, raw)
        self.assertEqual(result["cleanup_status"], "confirmed")
        self.assertEqual(result["archive_status"], "verified")
        self.assertEqual(result["measurement"]["status"], "complete")
        result["infra_status"] = "unknown"
        self.assertEqual(entry.stop_policy(result), (True, False, "chain_infrastructure_failure"))
        self.assertIsNone(result["task_result"])

    def test_unconfirmed_cleanup_is_global_stop_even_when_task_reward_is_known(self):
        result = {"cleanup_status": "unconfirmed", "archive_status": "verified",
                  "infra_status": "ok", "measurement": {"status": "complete"},
                  "task_result": 1.0}
        self.assertEqual(entry.stop_policy(result), (True, True, "cleanup_unconfirmed"))

    def test_counter_quality_is_per_metric_and_does_not_fill_missing_io(self):
        rows = [
            {"scope": "agent", "t_monotonic_ns": 1_000_000_000,
             "cpu_usage_usec": 1_000_000, "io_read_bytes": 10,
             "io_write_bytes": 0,
             "read_status": {"cpuacct.usage": "ok", "io": "permission_denied"}},
            {"scope": "agent", "t_monotonic_ns": 2_000_000_000,
             "cpu_usage_usec": 2_000_000, "io_read_bytes": 20,
             "io_write_bytes": 0,
             "read_status": {"cpuacct.usage": "ok", "io": "ok"}},
        ]
        actual = entry._interval_status_from_samples(rows)
        self.assertEqual(actual["cpu"], {"candidate": 1, "valid": 1, "gaps": 0})
        self.assertEqual(actual["io_read"], {"candidate": 1, "valid": 0, "gaps": 1})
        self.assertEqual(actual["io_write"], {"candidate": 1, "valid": 0, "gaps": 1})

    def test_raw_manifest_fixture_is_temp_only_and_refuses_missing_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "payload.json").write_text("{}\n")
            row = {"path": "payload.json", "bytes": (root / "payload.json").stat().st_size,
                   "sha256": hashlib.sha256((root / "payload.json").read_bytes()).hexdigest()}
            (root / "manifest.json").write_text(json.dumps({"outputs": [row]}))
            self.assertEqual(entry.verify_raw(root, "Office")["hashes_match"], True)
            (root / "payload.json").write_text("null\n")
            with self.assertRaisesRegex(ValueError, "hash"):
                entry.verify_raw(root, "Office")


if __name__ == "__main__":
    unittest.main()
