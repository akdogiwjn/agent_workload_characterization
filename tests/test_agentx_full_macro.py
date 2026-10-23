"""Identity, clock, cap-boundary and frozen-input checks for the new analysis."""
import contextlib
import json
import os
from pathlib import Path
import tempfile
import unittest

from scripts.agentx_full_macro import (
    compare_signatures, distribution, file_record, flatten, scan,
    scoped_intervals, validate_declared, write_report,
)


def request(t=0, inp=10, out=1):
    return {"type": "s", "t": t, "model": "m", "in": inp, "out": out,
            "hash_ids": [], "api_time": 1, "ttft": None}


def trace(tid, requests):
    return {"id": tid, "block_size": 64, "hash_id_scope": "local", "requests": requests}


class AgentXFullTests(unittest.TestCase):
    def test_nested_groups_not_requests_and_native_scopes_retained(self):
        raw = trace("x", [request(), {"type": "subagent", "agent_id": "a", "requests": [
            request(), {"type": "subagent", "agent_id": "b", "requests": [request()]}]}])
        scopes, groups, errors = flatten(raw)
        self.assertEqual(set(scopes), {(), ("a",), ("a", "b")})
        self.assertEqual(sum(map(len, scopes.values())), 3)
        self.assertEqual(len(groups), 2)
        self.assertEqual(errors, [])

    def test_clock_union_handles_nested_overlap(self):
        events = [{"t": 0, "api_time": 10}, {"t": 1, "api_time": 1}, {"t": 2, "api_time": 5}]
        result = scoped_intervals(events)
        self.assertEqual(result["union_s"], 10)
        self.assertEqual(result["overlap_excess_s"], 6)
        self.assertIsNone(scoped_intervals([])["union_s"])

    def test_multiset_matching_does_not_pair_ambiguous_timestamps(self):
        key = ((), "payload")
        result = compare_signatures({"x": {key: [2, 5, 8]}}, {"x": {key: [0, 3]}})
        self.assertEqual(result["matched_payloads"], 2)
        self.assertEqual(result["full_only_payloads"], 1)
        self.assertEqual(result["capped_only_payloads"], 0)
        row = result["per_trace"][0]
        self.assertEqual(row["unique_payload_timestamp_pairs"], 0)
        self.assertEqual(row["ambiguous_pairs_unassigned"], 2)
        self.assertFalse(row["uniform_session_offset"])

    def test_distribution_keeps_zero_but_excludes_missing_and_bool(self):
        result = distribution([0, 2, 4, None, True, float("nan")])
        self.assertEqual(result["n"], 3)
        self.assertEqual(result["median"], 2)
        self.assertEqual(result["iqr"], 2)
        self.assertEqual(result["missing_or_invalid"], 3)

    def test_cap_boundary_parser_errors_and_no_cross_session_time_union(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "traces.jsonl"
            path.write_text("\n".join([
                json.dumps(trace("a", [request(inp=255999, out=1)])),
                json.dumps(trace("b", [request(inp=256000, out=1)])),
                "malformed JSON",
                json.dumps(trace("c", [{"type": "unknown"}])),
            ]) + "\n")
            summary, rows, _, _ = scan(path)
            self.assertEqual(summary["trace_count"], 3)
            self.assertEqual(summary["total_model_request_count"], 2)
            self.assertEqual(summary["requests_at_256k_input_plus_output"], 1)
            self.assertEqual(summary["requests_above_256k_input_plus_output"], 1)
            self.assertEqual(summary["main_stream_observed_span_s"]["n"], 2)
            self.assertEqual(summary["main_stream_observed_span_s"]["median"], 1)
            self.assertEqual(len(summary["errors"]), 2)
            self.assertNotIn("scope_time", summary)
            self.assertEqual(rows[0]["request_distributions"]["ttft"]["n"], 0)

    def test_source_stats_mismatch_is_explicit(self):
        checks = validate_declared({"trace_count": 1}, {"traces": 2})
        self.assertFalse(checks[0]["matches"])

    @contextlib.contextmanager
    def fixture(self):
        with tempfile.TemporaryDirectory() as tmp:
            old = Path.cwd()
            os.chdir(tmp)
            try:
                full, cap = Path("raw/full"), Path("raw/cap")
                full.mkdir(parents=True)
                cap.mkdir(parents=True)
                keep = request(t=10)
                group = {"type": "subagent", "agent_id": "a", "tool_use_count": None,
                         "status": "completed", "requests": [request(t=12, inp=256000), request(t=14)]}
                (full / "traces.jsonl").write_text(json.dumps(trace("x", [keep, group])) + "\n")
                cap_group = {**group, "requests": [{**request(t=14), "t": 4}]}
                (cap / "traces.jsonl").write_text(json.dumps(trace("x", [{**keep, "t": 0}, cap_group])) + "\n")
                for root, count in ((full, 3), (cap, 2)):
                    (root / "README.md").write_text("test-only fixture")
                    (root / "stats.txt").write_text(f"traces: 1\ntotal_model_requests: {count}\n")
                manifest = Path("reports/analysis/AGENTX-APPLIED-MACRO-v1/manifest.json")
                manifest.parent.mkdir(parents=True)
                manifest.write_text(json.dumps({"inputs": [file_record(cap / "traces.jsonl")]}))
                acq = Path("acquisition.json")
                acq.write_text(json.dumps({"dataset_id": "test/fixture", "revision": "test-revision",
                                          "files": [file_record(p) for p in full.iterdir()]}))
                Path("tests").mkdir()
                Path("tests/test_agentx_full_macro.py").write_text("test-only source identity")
                yield full / "traces.jsonl", cap / "traces.jsonl", acq, Path("report")
            finally:
                os.chdir(old)

    def test_end_to_end_subset_and_uniform_shift_and_no_overwrite(self):
        with self.fixture() as (full, cap, acq, out):
            summary = write_report(full, cap, acq, out, plots=False)
            self.assertEqual(summary["status"], "PASS")
            self.assertTrue(summary["cap_rule_count_matches"])
            self.assertEqual(summary["comparison"]["matched_payloads"], 2)
            self.assertEqual(summary["comparison"]["capped_only_payloads"], 0)
            self.assertEqual(summary["comparison"]["sessions_with_nonzero_offset"], 1)
            self.assertEqual(summary["full"]["group_nonnull_fields"].get("tool_use_count", 0), 0)
            self.assertEqual(summary["full"]["same_stream_prefix"]["adjacent_comparisons"], 1)
            self.assertEqual(summary["capped_256k"]["same_stream_prefix"]["adjacent_comparisons"], 0)
            self.assertEqual(len((out / "per_trace.jsonl").read_text().splitlines()), 2)
            manifest = json.loads((out / "manifest.json").read_text())
            for entry in manifest["outputs"]:
                self.assertEqual(file_record(entry["path"]), entry)
            with self.assertRaises(FileExistsError):
                write_report(full, cap, acq, out, plots=False)

    def test_changed_frozen_input_is_rejected_before_output(self):
        with self.fixture() as (full, cap, acq, out):
            full.write_text("{}\n")
            with self.assertRaisesRegex(ValueError, "acquisition evidence mismatch"):
                write_report(full, cap, acq, out, plots=False)
            self.assertFalse(out.exists())


if __name__ == "__main__":
    unittest.main()
