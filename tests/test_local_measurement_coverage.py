import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from scripts.local_measurement_coverage import (
    _metric_interval_coverage, _rate_coverage, _stats,
    _unique_office_container_id, _verify_raw)


class LocalMeasurementCoverageTests(unittest.TestCase):
    def test_raw_manifest_file_set_and_hashes_are_checked(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run = root / "run"
            run.mkdir()
            payload = b'{"sample":1}\n'
            (run / "samples.json").write_bytes(payload)
            manifest = {"outputs": [{"path": "samples.json", "bytes": len(payload),
                                      "sha256": hashlib.sha256(payload).hexdigest()}]}
            (run / "manifest.json").write_text(json.dumps(manifest))
            inputs = {}
            _, files = _verify_raw(root, run, inputs)
            self.assertEqual(files, ["samples.json"])
            self.assertEqual(set(inputs), {"run/manifest.json", "run/samples.json"})
            (run / "samples.json").write_bytes(b"tampered")
            with self.assertRaises(ValueError):
                _verify_raw(root, run, {})

    def test_missing_and_zero_values_remain_distinct(self):
        result = _stats([{"counter": 0}, {"counter": None}, {}], ("counter",))
        self.assertEqual(result, {"valid_points": 1, "missing_or_invalid_points": 2,
                                  "observed_zero_points": 1})

    def test_office_container_identity_requires_one_saved_run_identity(self):
        self.assertEqual(_unique_office_container_id({"events": [
            {"phase": "container_identified", "container_id": "sha256like-id"}]}),
            "sha256like-id")
        self.assertIsNone(_unique_office_container_id({"events": [
            {"phase": "container_identified", "container_id": "a"},
            {"phase": "container_identified", "container_id": "b"}]}))
        self.assertIsNone(_unique_office_container_id({"events": []}))

    def test_rate_coverage_is_derived_from_per_run_valid_and_gap_counts(self):
        report = _rate_coverage([
            {"resources": {"cpu": {"pairs": 4, "valid": 3, "gaps": 1}}},
            {"resources": {"io": {"pairs": 2, "valid": 0, "gaps": 2}}}], ())
        self.assertEqual(report, {"pairs": 6, "valid_intervals": 3,
                                  "gap_intervals": 3, "status": "derivable_with_gaps"})

    def test_io_validity_changes_do_not_change_cpu_coverage(self):
        run = {"collection": "DOCOPS-OFFICE-REPEAT-02", "run_id": "r1",
               "scopes": {"agent_container": {
                   "derivable_cgroup_rates": {
                       "cpu": {"pairs": 4, "valid": 4, "gaps": 0},
                       "io_read": {"pairs": 4, "valid": 3, "gaps": 1},
                       "io_write": {"pairs": 4, "valid": 2, "gaps": 2}},
                   "derivable_host_process_rates": {}}}}
        before = _metric_interval_coverage([run])
        run["scopes"]["agent_container"]["derivable_cgroup_rates"]["io_read"] = {
            "pairs": 4, "valid": 0, "gaps": 4}
        after = _metric_interval_coverage([run])
        before_cpu = before["DOCOPS-OFFICE-REPEAT-02"]["cgroup.cpu"]
        after_cpu = after["DOCOPS-OFFICE-REPEAT-02"]["cgroup.cpu"]
        self.assertEqual(before_cpu, after_cpu)
        self.assertEqual(after["DOCOPS-OFFICE-REPEAT-02"]["cgroup.io_read"][
            "valid_intervals"], 0)

    def test_absent_coding_proc_io_is_not_reported_as_zero_measurement(self):
        run = {"collection": "P1-12-CODING-REPEAT-01", "run_id": "c1",
               "scopes": {}, "host_process": {"cpu_and_proc_io_rate_intervals": {
                   "cpu": {"pairs": 2, "valid": 2, "gaps": 0}}}}
        coverage = _metric_interval_coverage([run])["P1-12-CODING-REPEAT-01"]
        for name in ("proc_rchar", "proc_wchar", "proc_read_bytes", "proc_write_bytes"):
            item = coverage["host_process." + name]
            self.assertEqual(item["observation_status"], "not_recorded")
            self.assertEqual(item["candidate_intervals"], 0)
            self.assertEqual(item["runs"][0]["observation_status"], "not_recorded")


if __name__ == "__main__":
    unittest.main()
