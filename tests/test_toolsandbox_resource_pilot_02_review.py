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
import toolsandbox_resource_pilot_02_review as review


def _digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _put(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(value, bytes):
        path.write_bytes(value)
    else:
        path.write_text(json.dumps(value, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")


def _line(path: Path, rows) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row, sort_keys=True) + "\n" for row in rows), encoding="utf-8")


def _refresh_manifests(root: Path) -> None:
    raw = root / review.RAW_REL
    raw_manifest_path = raw / "manifest.json"
    files = []
    for path in sorted(p for p in raw.rglob("*") if p.is_file() and p != raw_manifest_path):
        data = path.read_bytes()
        files.append({"path": path.relative_to(raw).as_posix(), "bytes": len(data), "sha256": _digest(data)})
    _put(raw_manifest_path, {"schema": "toolsandbox-pilot-run-manifest-v1", "identity_sha256": review.IDENTITY,
                             "run_id": review.RUN_ID, "files": files})
    report = root / review.REPORT_REL
    (report / "run-report.json").write_text((report / "run-report.json").read_text(), encoding="utf-8")
    outer_inputs = [root / review.REPORT_REL / "APPROVAL.json", root / review.ENV_REL / "plan-identity.json",
                    root / review.ENV_REL / "frozen-identity.json", raw_manifest_path]
    outer_outputs = [report / "run-report.json"]
    def records(paths):
        return [{"path": p.relative_to(root).as_posix(), "bytes": p.stat().st_size,
                 "sha256": _digest(p.read_bytes())} for p in paths]
    _put(report / "manifest.json", {"identity_sha256": review.IDENTITY, "run_id": review.RUN_ID,
                                    "inputs": records(outer_inputs), "outputs": records(outer_outputs)})


def _fixture(root: Path, *, extra_request: bool = False) -> Path:
    for rel in (review.ENV_REL / "plan-identity.json", review.ENV_REL / "frozen-identity.json",
                review.ENV_REL / "source-manifest.json", review.TASK_SOURCE_REL, review.EVALUATOR_SOURCE_REL,
                review.EXEC_ENV_SOURCE_REL, review.SCENARIO_BASE_SOURCE_REL, review.WORKER_REL,
                review.HOST_READER_REL, Path("scripts/toolsandbox_resource_pilot_02_review.py")):
        src = ROOT / rel
        target = root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, target)
    report = root / review.REPORT_REL
    raw = root / review.RAW_REL
    _put(report / "APPROVAL.json", {"identity_sha256": review.IDENTITY, "user_approval": "approved"})
    _put(raw / "ATTEMPT_STARTED.json", {"identity_sha256": review.IDENTITY, "run_id": review.RUN_ID})
    _put(raw / "ATTEMPT_COMPLETED.json", {"identity_sha256": review.IDENTITY, "run_id": review.RUN_ID})
    (raw / "official/trajectories" / review.TASK).mkdir(parents=True, exist_ok=True)

    reqs = [
        ("req-a", "agent", 1_100_000_000, 1_400_000_000, "deepseek-v4-flash", "deepseek-flash"),
        ("req-u", "user", 1_300_000_000, 1_600_000_000, "deepseek-v4-flash", "deepseek-flash"),
    ]
    if extra_request:
        reqs.append(("req-extra", "agent", 1_700_000_000, 1_800_000_000, "deepseek-v4-flash", "deepseek-flash"))
    events = [{"event_id": "root", "kind": "run", "status": "open", "t_monotonic_ns": 900_000_000,
               "attrs": {"run_id": review.RUN_ID}}]
    for request_id, role, start, end, model, response_model in reqs:
        eid = "event-" + request_id
        events.extend([
            {"event_id": eid, "kind": "llm_request", "status": "open", "t_monotonic_ns": start,
             "attrs": {"request_id": request_id, "role": role, "model": model}},
            {"event_id": eid, "kind": "llm_request", "status": "closed", "t_monotonic_ns": end,
             "attrs": {"response_model": response_model, "transport_attempt_count": 1,
                       "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2,
                                 "completion_tokens_details": {"reasoning_tokens": 0}}}},
        ])
    tool_id = "tool-1"
    events.extend([
        {"event_id": tool_id, "kind": "tool_call", "status": "open", "t_monotonic_ns": 1_350_000_000,
         "attrs": {"role": "agent", "tool_name": "search_contacts", "request_event_id": "req-a"}},
        {"event_id": tool_id, "kind": "tool_call", "status": "closed", "t_monotonic_ns": 1_500_000_000,
         "attrs": {"ok": True, "result_bytes": 2}},
        {"event_id": "batch-1", "kind": "tool_batch", "status": "open", "t_monotonic_ns": 1_300_000_000,
         "attrs": {"batch_index": 1, "tool_names": ["search_contacts"], "call_ids": ["native-call-1"]}},
        {"event_id": "batch-1", "kind": "tool_batch", "status": "closed", "t_monotonic_ns": 1_600_000_000,
         "attrs": {"planned_orderings": 1, "executed_orderings": 1,
                   "resource_before": {"cpu_ticks": 20, "process_io": {}},
                   "resource_after": {"cpu_ticks": 30, "process_io": {}}}},
    ])
    _line(raw / "events.jsonl", events)
    _line(raw / "samples.jsonl", [
        {"pid": 22, "starttime_ticks": 4, "t_monotonic_ns": 900_000_000, "cpu_ticks": 10,
         "user_ticks": 9, "system_ticks": 1, "rss_bytes": 100, "threads": 2,
         "process_io": {"rchar": 1, "wchar": 2, "read_bytes": 0, "write_bytes": 0},
         "read_status": {"stat": "ok", "io": "ok", "status": "ok"}},
        {"pid": 22, "starttime_ticks": 4, "t_monotonic_ns": 1_900_000_000, "cpu_ticks": 110,
         "user_ticks": 99, "system_ticks": 11, "rss_bytes": 0, "threads": 3,
         "process_io": {"rchar": 11, "wchar": 22, "read_bytes": 0, "write_bytes": 0},
         "read_status": {"stat": "ok", "io": "ok", "status": "ok"}},
    ])
    phase_rows = []
    values = [("worker_start", 900_000_000, 10), ("imports_begin", 920_000_000, 12),
              ("imports_end", 950_000_000, 15), ("play_begin", 1_000_000_000, 20),
              ("system_setup_exec", 1_010_000_000, 21), ("play_end", 2_000_000_000, 110),
              ("evaluate_begin", 2_010_000_000, 111), ("evaluate_end", 2_100_000_000, 120),
              ("worker_end", 2_200_000_000, 130)]
    for name, t, ticks in values:
        row = {"phase": name, "t_monotonic_ns": t, "cpu_ticks": ticks, "user_ticks": ticks-1,
               "system_ticks": 1, "rss_bytes": 100, "pid": 22, "starttime_ticks": 4,
               "threads": 2, "read_status": {"stat": "ok", "io": "ok", "status": "ok"},
               "process_io": {"rchar": ticks, "wchar": ticks, "read_bytes": 0, "write_bytes": 0}}
        if name == "play_begin": row["phase_start_ns"] = t
        if name == "play_end": row["phase_end_ns"] = t
        if name == "evaluate_begin": row["phase_start_ns"] = t
        if name == "evaluate_end": row["phase_end_ns"] = t
        phase_rows.append(row)
    _line(raw / "boundaries.jsonl", phase_rows)
    _put(raw / "result.json", {"run_id": review.RUN_ID,"scenario_name":review.TASK,
        "transport": {"request_model_label": "deepseek-v4-flash"},
        "retry": {"sdk_max_retries": 0},
        "counts": {"agent_logical_calls": 1, "user_logical_calls": 1},
        "stop": {"conversation_active": False, "user_end_conversation_executed": True,
                 "reason": "user_end_conversation"},
        "evaluation": {"similarity": 0.9, "milestone_mapping": {"0": [1,1.0], "1": [2,1.0],
                     "2": [3,1.0], "3": [4,0.6]}}})
    rr = report / "run-report.json"
    _put(rr, {"run_id": review.RUN_ID, "identity_sha256": review.IDENTITY, "exit_code": 0,
              "worker_exit_code": 0, "wall_s": 2.3, "deadline_timeout": None,
              "evaluation_status": "completed", "cleanup": {"wait_reaped": True,
              "original_process_gone": True, "sampler_stopped": True},"archive_verification":{"valid":True,"errors":[]},
              "evaluation": {"similarity": 0.9, "milestone_mapping": {"0": [1,1.0], "1": [2,1.0],
                              "2": [3,1.0], "3": [4,0.6]}}})
    traj = raw / "official/trajectories" / review.TASK
    _put(traj / "conversation.json", [{"role": "system", "content": ""}, {"role": "assistant", "content": ""}])
    _put(traj / "execution_context.json", {"_dbs": {"SANDBOX": [], "SETTING": [], "CONTACT": [], "MESSAGING": [], "REMINDER": []}})
    (traj / "pretty_print.txt").write_text("fixture summary\n", encoding="utf-8")
    _put(raw / "job.json", {"run_id":review.RUN_ID,"scenario_name":review.TASK})
    (raw / "worker.stderr").write_text("", encoding="utf-8")
    (raw / "worker.stdout").write_text("", encoding="utf-8")
    _refresh_manifests(root)
    return root


class Pilot02ReviewTests(unittest.TestCase):
    def test_full_entry_reports_calls_setup_and_time_partition(self):
        with tempfile.TemporaryDirectory() as td:
            root = _fixture(Path(td))
            out = root / "reports/analysis/review"
            result = review.run(root=root, output_dir=out)
            summary = result["summary"]
            calls = summary["behavior"]["tool_calls"]
            self.assertEqual(calls["system_setup_exec_count"], 1)
            self.assertEqual(calls["by_role"], {"agent": 1, "user": 0})
            self.assertEqual(calls["tool_batch_count"], 1)
            self.assertTrue(calls["all_tool_returns_saved"])
            self.assertEqual(summary["behavior"]["logical_requests"]["agent"], 1)
            self.assertEqual(summary["behavior"]["logical_requests"]["user"], 1)
            partition = summary["time"]["play_request_batch_partition"]
            self.assertAlmostEqual(partition["overlap_s"], 0.3)
            self.assertAlmostEqual(partition["window_s"], sum(partition[k] for k in
                ("request_only_s", "batch_only_s", "overlap_s", "uncovered_s")))
            manifest = json.loads((out / "manifest.json").read_text())
            self.assertEqual(manifest["outputs"], result["manifest"]["outputs"])
            self.assertFalse(any(item["path"].endswith("manifest.json") for item in manifest["outputs"]))

    def test_saved_event_id_pairing_and_anomalies(self):
        events = [
            {"event_id": "a", "kind": "x", "status": "open", "t_monotonic_ns": 1},
            {"event_id": "a", "kind": "x", "status": "open", "t_monotonic_ns": 2},
            {"event_id": "orphan", "kind": "x", "status": "closed", "t_monotonic_ns": 3},
        ]
        spans, quality = review._pair_spans(events)
        self.assertEqual(spans, [])
        self.assertEqual(quality["duplicate_open"], ["a"])
        self.assertEqual(quality["orphan_terminal"], ["orphan"])
        self.assertEqual(len(quality["unclosed"]), 1)

    def test_partition_union_overlap_and_uncovered_conserve(self):
        window = (1_000_000_000, 2_000_000_000)
        partition = review._partition(window,
            [(1_100_000_000,1_400_000_000),(1_200_000_000,1_300_000_000)],
            [(1_300_000_000,1_600_000_000)])
        self.assertAlmostEqual(partition["request_only_s"], 0.2)
        self.assertAlmostEqual(partition["overlap_s"], 0.1)
        self.assertAlmostEqual(partition["batch_only_s"], 0.2)
        self.assertAlmostEqual(partition["uncovered_s"], 0.5)
        self.assertAlmostEqual(partition["residual_s"], 0)

    def test_cpu_units_reset_gap_and_true_zero(self):
        def sample(t, cpu, rss, status="ok"):
            return {"t_monotonic_ns": t, "cpu_ticks": cpu, "user_ticks": cpu, "system_ticks": 0,
                    "rss_bytes": rss, "threads": 2, "process_io": {},
                    "read_status": {"stat": status, "io": "ok", "status": "ok"}}
        samples=[sample(1_000_000_000,10,7),sample(2_000_000_000,110,0),
                 sample(3_000_000_000,210,9,"missing"),sample(4_000_000_000,150,8),
                 sample(5_000_000_000,100,9),sample(6_000_000_000,200,9)]
        got=review._sample_resources(samples,[],[],100)
        self.assertEqual(got["cpu_ticks_delta"],200)
        self.assertEqual(got["cpu_s_using_current_clk_tck"],2)
        self.assertEqual(got["rss_peak_bytes"],9)
        self.assertEqual(got["counter_regression_intervals"],[4])
        self.assertIn(2,got["invalid_cpu_sample_indices"])
        self.assertIsNone(got["proc_io_delta_bytes"]["rchar"])

    def test_input_hash_mismatch_is_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            root=_fixture(Path(td))
            with (root/review.RAW_REL/"events.jsonl").open("a") as f: f.write("{}\n")
            with self.assertRaisesRegex(ValueError,"raw hash mismatch"):
                review.analyze(root)

    def test_input_change_changes_analysis_output(self):
        with tempfile.TemporaryDirectory() as td:
            root=_fixture(Path(td))
            first=review.run(root,root/"reports/analysis/first")["summary"]["behavior"]["logical_requests"]["total"]
            root2=Path(td)/"second"
            _fixture(root2,extra_request=True)
            second=review.run(root2,root2/"reports/analysis/second")["summary"]["behavior"]["logical_requests"]["total"]
            self.assertEqual(first,2)
            self.assertEqual(second,3)


if __name__ == "__main__":
    unittest.main()
