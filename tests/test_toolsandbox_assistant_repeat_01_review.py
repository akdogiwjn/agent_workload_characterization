"""Offline tests for the ToolSandbox Assistant Repeat-01 review."""
from __future__ import annotations

import hashlib
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import toolsandbox_assistant_repeat_01_review as review


def copy_file(source: Path, root: Path, rel: Path) -> None:
    target = root / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, target)


def make_fixture(root: Path) -> None:
    for rel in (review.REPORT_REL, review.RAW_REL, review.ENV_REL):
        shutil.copytree(ROOT / rel, root / rel)
    for rel in review.ANALYSIS_CODE:
        copy_file(ROOT / rel, root, rel)
    for rel in review.STATIC_SOURCES:
        copy_file(ROOT / review.STATIC_SOURCE_ROOT / rel, root, review.STATIC_SOURCE_ROOT / rel)


def sample(t: int, cpu: int | None, *, stat: str = "ok", rss: int | None = 0) -> dict:
    return {"t_monotonic_ns": t, "cpu_ticks": cpu, "user_ticks": cpu, "system_ticks": 0,
            "rss_bytes": rss, "threads": 1,
            "read_status": {"stat": stat, "io": "ok", "status": "ok"},
            "process_io": {"rchar": t, "wchar": t, "read_bytes": t, "write_bytes": t}}


class AssistantRepeatReviewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source_protected = {}
        for rel in (review.REPORT_REL, review.RAW_REL, review.ENV_REL):
            for path in (ROOT / rel).rglob("*"):
                if path.is_file():
                    data = path.read_bytes()
                    cls.source_protected[path] = (len(data), hashlib.sha256(data).hexdigest())

    def test_real_three_by_three_fixture_generates_review(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            make_fixture(root)
            output = root / review.OUTPUT_REL
            result = review.run(root, output)
            summary = result["summary"]
            self.assertEqual(len(result["per_run"]), 9)
            self.assertEqual(summary["integrity"]["batch_executed"], 9)
            self.assertEqual(summary["behavior"]["logical_requests"],
                             {"agent": 52, "user": 13, "total": 65})
            self.assertEqual(summary["behavior"]["agent_tool_calls"], 48)
            self.assertEqual(summary["behavior"]["user_end_conversation_calls"], 9)
            self.assertEqual(summary["behavior"]["tool_batches"], 48)
            self.assertEqual(summary["behavior"]["system_setup_exec"], 9)
            self.assertEqual(summary["behavior"]["batch_ordering_executions_excluding_system_setup"], 59)
            self.assertEqual(summary["behavior"]["wrapper_execution_count_including_system_setup"], 68)
            self.assertEqual(summary["resources"]["sample_count"], 396)
            self.assertEqual(summary["behavior"]["tool_call_error_count"], 2)
            self.assertTrue(summary["integrity"]["all_run_counter_cleanup_archive_checks_pass"])
            self.assertEqual(summary["infrastructure"]["runs_with_saved_clean_exit_cleanup_and_archive"], 9)
            self.assertEqual([error["error_class"] for error in summary["behavior"]["tool_errors"]],
                             ["ConnectionError", "ValueError"])
            self.assertTrue(all(row["behavior"]["tool_calls"]["all_returns_saved"]
                                for row in result["per_run"]))
            self.assertTrue(all(row["behavior"]["termination"]["run_root_open_close"]["closed"]
                                for row in result["per_run"]))
            self.assertEqual(summary["per_task"]["C"]["n_runs"], 3)
            self.assertEqual(summary["per_task"]["C"]["metrics"]["attempt_wall_s"]["n"], 3)
            self.assertTrue((output / "summary.md").is_file())
            self.assertEqual(len(review.read_jsonl(output / "per_run.jsonl")), 9)
            manifest = review.read_json(output / "manifest.json")
            self.assertFalse(manifest["manifest_self_hash"])
            self.assertEqual(len(manifest["outputs"]), 3)
            self.assertTrue(all(not Path(item["path"]).is_absolute() for item in manifest["inputs"] +
                                manifest["analysis_code"] + manifest["outputs"]))
            self.assertFalse(any("api_key" in json.dumps(item).lower() for item in manifest["inputs"] +
                                 manifest["analysis_code"] + manifest["outputs"]))
            self.assertTrue(all(review._record_matches(root, entry, "test output")
                                for entry in manifest["outputs"]))
            self.assertEqual(summary["integrity"]["batch_manifest_sha256"],
                             review.sha256((root / review.REPORT_REL / "manifest.json").read_bytes()))

    def test_raw_hash_mismatch_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            make_fixture(root)
            events = root / review.RAW_REL / "20261012T135428Z-r0-a-tsbassistant01" / "events.jsonl"
            events.write_bytes(events.read_bytes() + b"\n")
            with self.assertRaisesRegex(ValueError, "hash mismatch"):
                review.run(root, root / "out")
            self.assertFalse((root / "out").exists())

    def test_span_pairing_keeps_duplicate_orphan_and_missing_ids_visible(self):
        events = [
            {"kind": "tool_call", "status": "open", "event_id": "dup", "t_monotonic_ns": 1},
            {"kind": "tool_call", "status": "open", "event_id": "dup", "t_monotonic_ns": 2},
            {"kind": "tool_call", "status": "closed", "event_id": "dup", "t_monotonic_ns": 3},
            {"kind": "llm_request", "status": "closed", "event_id": "orphan", "t_monotonic_ns": 4},
            {"kind": "tool_call", "status": "open", "event_id": "", "t_monotonic_ns": 5},
        ]
        spans, quality = review._spans(events)
        self.assertEqual(spans, [])
        self.assertEqual(quality["duplicate_open_ids"][0]["count"], 2)
        self.assertEqual(len(quality["orphan_terminals"]), 1)
        self.assertEqual(len(quality["missing_id_events"]), 1)

    def test_union_overlap_and_partition_conserve_observation_window(self):
        result = review._partition((0, 10_000_000_000),
                                   [(1_000_000_000, 5_000_000_000), (4_000_000_000, 7_000_000_000)],
                                   [(3_000_000_000, 6_000_000_000)])
        self.assertAlmostEqual(result["request_only_s"], 3)
        self.assertAlmostEqual(result["batch_only_s"], 0)
        self.assertAlmostEqual(result["overlap_s"], 3)
        self.assertAlmostEqual(result["uncovered_s"], 4)
        self.assertAlmostEqual(result["residual_s"], 0)

    def test_runtime_clk_tck_and_missing_or_regressed_samples(self):
        valid = review._sample_metrics([sample(0, 10), sample(1_000_000_000, 110)], {}, [], 100)
        self.assertEqual(valid["cpu_ticks_delta"], 100)
        self.assertEqual(valid["process_cpu_s"], 1.0)
        invalid = review._sample_metrics([
            sample(0, 10), sample(1_000_000_000, None),
            sample(2_000_000_000, 50), sample(3_000_000_000, 40),
        ], {}, [], 100)
        self.assertEqual(invalid["valid_cpu_intervals"], 0)
        self.assertIsNone(invalid["cpu_ticks_delta"])
        self.assertIsNone(invalid["process_cpu_s"])
        self.assertEqual(invalid["rss_sampled_peak_bytes"], 0)
        self.assertEqual(len(invalid["invalid_cpu_or_status_intervals"]), 2)
        self.assertEqual(len(invalid["cpu_counter_regression_intervals"]), 1)

    def test_phase_cpu_uses_boundary_ticks_and_runtime_clk_tck(self):
        def edge(t: int, ticks: int) -> dict:
            return {"phase": "x", "t_monotonic_ns": t, "cpu_ticks": ticks,
                    "user_ticks": ticks - 1, "system_ticks": 1,
                    "read_status": {"stat": "ok"}}
        boundaries = {
            "worker_start": edge(0, 100), "play_begin": edge(2_000_000_000, 200),
            "imports_begin": edge(100, 101), "imports_end": edge(1_000_000_100, 151),
            "play_end": edge(4_000_000_000, 300), "evaluate_begin": edge(4_000_000_000, 300),
            "evaluate_end": edge(5_000_000_000, 350), "worker_end": edge(6_000_000_000, 400),
        }
        result = review._phase_metrics(boundaries, 100)
        self.assertEqual(result["phases"]["setup"]["process_cpu_s"], 1.0)
        self.assertEqual(result["phases"]["imports"]["process_cpu_s"], .5)
        self.assertEqual(result["phases"]["evaluator"]["process_cpu_s"], .5)
        self.assertEqual(result["phase_cpu_conservation_residual_ticks"], 0)

    def test_project_history_hashes_are_unchanged(self):
        for path, expected in self.source_protected.items():
            data = path.read_bytes()
            self.assertEqual((len(data), hashlib.sha256(data).hexdigest()), expected, str(path))


if __name__ == "__main__":
    unittest.main()
