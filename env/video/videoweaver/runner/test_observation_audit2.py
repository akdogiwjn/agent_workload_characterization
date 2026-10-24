#!/usr/bin/env python3
"""Observation audit-2 counterexample tests (no containers, no credentials).

A complete normal judge fixture (real final.mp4, logs, ledger, summary, valid
resource stream, boundaries, stream_state, quality) is built once; each damage
case copies it and breaks exactly one item to prove that item flips the
measurement-acceptance result (never relying on 'missing final')."""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "gateway"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from agent_workload_characterization.collectors.resource_sampler import CounterSnapshot, ScopeSamples
from agent_workload_characterization.collectors.execution_measurement import (
    assess_resource_quality, validate_resource_stream, read_resource_stream)
import host_runner as hr

N = 64
SCOPE = "videoweaver"
KIND = "agent_container"
RS = {"cpuacct.usage": "ok_ns_converted_to_usec",
      "memory.usage_in_bytes": "ok", "io.stat": "ok_summed_devices"}


def make_rows(n=N, scope=SCOPE, kind=KIND, corrupt_at=None):
    rows = []
    for i in range(n):
        r = {"schema": "resource-stream-v1", "scope": scope, "scope_kind": kind,
             "t_monotonic_ns": i * 10 ** 9, "cpu_usage_usec": 1000 + i * 1000,
             "mem_current_bytes": 1000 + i, "mem_peak_bytes": None,
             "io_read_bytes": 100 + i, "io_write_bytes": 50 + i,
             "read_status": dict(RS)}
        if corrupt_at is not None and i == corrupt_at["i"]:
            r.update(corrupt_at["fields"])
        rows.append(r)
    return rows


def make_bounds(bstart=None, bend=None):
    return {
        "boundary_start": bstart if bstart is not None else {
            "scope": SCOPE, "scope_kind": KIND, "t_monotonic_ns": 0,
            "cpu_usage_usec": 1000, "mem_current_bytes": 1000,
            "io_read_bytes": 100, "io_write_bytes": 50, "read_status": dict(RS)},
        "boundary_end": bend if bend is not None else {
            "scope": SCOPE, "scope_kind": KIND, "t_monotonic_ns": (N - 1) * 10 ** 9,
            "cpu_usage_usec": 1000 + (N - 1) * 1000, "mem_current_bytes": 1000 + (N - 1),
            "io_read_bytes": 100 + (N - 1), "io_write_bytes": 50 + (N - 1),
            "read_status": dict(RS)},
    }


def make_quality(stream_rows=None, bstart=None, bend=None):
    q = assess_resource_quality(
        stream_rows=stream_rows or make_rows(),
        boundary_start=_mk(bstart) if bstart else _mk_boundary_start(),
        boundary_end=_mk(bend) if bend else _mk_boundary_end(),
        expected_scope=SCOPE, expected_scope_kind=KIND)
    return q


def _mk(d):
    return CounterSnapshot(scope=d["scope"], scope_kind=d["scope_kind"],
                           t_monotonic_ns=d["t_monotonic_ns"],
                           cpu_usage_usec=d.get("cpu_usage_usec"),
                           mem_current_bytes=d.get("mem_current_bytes"),
                           mem_peak_bytes=d.get("mem_peak_bytes"),
                           io_read_bytes=d.get("io_read_bytes"),
                           io_write_bytes=d.get("io_write_bytes"),
                           read_status=d.get("read_status") or {})


def _mk_boundary_start():
    d = make_bounds()["boundary_start"]
    return _mk(d)


def _mk_boundary_end():
    d = make_bounds()["boundary_end"]
    return _mk(d)


def base_fixture(td: Path) -> Path:
    """Complete normal run dir; every non-target check passes."""
    root = Path(td)
    for sub in ("logs", "samples", "ledger", "workspace", "rollout", "closeout"):
        (root / sub).mkdir(parents=True, exist_ok=True)
    (root / "logs" / "exec-stdout.log").write_text("x")
    (root / "logs" / "exec-stderr.log").write_text("")
    (root / "logs" / "docker-logs.txt").write_text("")
    (root / "ledger" / "ledger.json").write_text(json.dumps({
        "counters": {"llm_calls": 3, "image_creates": 0, "video_creates": 0,
                     "video_polls": 0, "media_downloads": 0},
        "exhausted": False, "events": [], "status": "open"}))
    rows = make_rows()
    (root / "samples" / "resource-stream.jsonl").write_text(
        "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows))
    (root / "samples" / "boundaries.json").write_text(json.dumps(make_bounds()))
    (root / "samples" / "summary.json").write_text(json.dumps({"n_samples": N}))
    # real final video so final/ffprobe/clips checks pass
    out = root / "closeout" / "merge-agent-output"
    out.mkdir(parents=True, exist_ok=True)
    final = out / "final.mp4"
    subprocess.run(["ffmpeg", "-y", "-v", "error",
                    "-f", "lavfi", "-i", "color=c=#808080:s=1280x720:r=30:d=40",
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", "-an", str(final)], check=True)
    return root


def damage_copy(src: Path, *, stream=None, stream_state=None, bounds=None,
                summary_n=None):
    td = tempfile.mkdtemp(prefix="vwfx-")
    dst = Path(td)
    for name in ("logs", "samples", "ledger", "workspace", "rollout", "closeout"):
        shutil.copytree(src / name, dst / name)
    if stream is not None:
        (dst / "samples" / "resource-stream.jsonl").write_text(stream)
    if bounds is not None:
        (dst / "samples" / "boundaries.json").write_text(json.dumps(bounds))
    if summary_n is not None:
        (dst / "samples" / "summary.json").write_text(json.dumps({"n_samples": summary_n}))
    return dst


def run_judge(root):
    report = {
        "errors": [],
        "cleanup": {"removed": True},
        "measurement_quality": make_quality(),
        "stream_state": {"rows_written": N, "rows_received": N, "rows_buffered": 0,
                         "lost_undelivered": 0, "error": None},
        "resource_samples": {"n_samples": N},
    }
    return hr.judge({"judge_media": {"image_creates": 0, "video_creates": 0,
                                     "media_downloads": 0}}, root, report)


class TestJudgeContract(unittest.TestCase):
    def setUp(self):
        self._td = tempfile.mkdtemp(prefix="vw-base-")
        self.base = base_fixture(Path(self._td))

    def tearDown(self):
        shutil.rmtree(self._td, ignore_errors=True)

    def _check(self, root, name):
        j = run_judge(root)
        return next(c for c in j["checks"] if c["check"] == name)

    def test_normal_fixture_stream_checks_pass(self):
        j = run_judge(self.base)
        for name in ("stream_validated", "stream_metrics_valid", "stream_schema_scope",
                     "stream_rows_consistent", "quality_recomputed"):
            c = next(c for c in j["checks"] if c["check"] == name)
            self.assertTrue(c["passed"], name)

    def test_single_empty_line_but_declared_64(self):
        root = damage_copy(self.base, stream="{}\n", summary_n=N)
        c = self._check(root, "stream_validated")
        self.assertFalse(c["passed"])
        rc = self._check(root, "stream_rows_consistent")
        self.assertFalse(rc["passed"])

    def test_scope_replaced_in_one_row(self):
        rows = make_rows(corrupt_at={"i": 3, "fields": {"scope": "other"}})
        root = damage_copy(self.base, stream="".join(json.dumps(r) + "\n" for r in rows))
        c = self._check(root, "stream_schema_scope")
        self.assertFalse(c["passed"])
        self.assertIn("other", c["detail"])

    def test_negative_counter_value(self):
        rows = make_rows(corrupt_at={"i": 5, "fields": {"cpu_usage_usec": -1}})
        root = damage_copy(self.base, stream="".join(json.dumps(r) + "\n" for r in rows))
        mc = self._check(root, "stream_metrics_valid")
        self.assertFalse(mc["passed"])
        rc = self._check(root, "stream_rows_consistent")
        self.assertFalse(rc["passed"])  # valid rows 63 != declared 64

    def test_bool_value(self):
        rows = make_rows(corrupt_at={"i": 5, "fields": {"cpu_usage_usec": True}})
        root = damage_copy(self.base, stream="".join(json.dumps(r) + "\n" for r in rows))
        mc = self._check(root, "stream_metrics_valid")
        self.assertFalse(mc["passed"])

    def test_rows_consistent_mismatch_stream_state(self):
        root = damage_copy(self.base)
        report = {"errors": [], "cleanup": {"removed": True},
                  "measurement_quality": make_quality(),
                  "stream_state": {"rows_written": 100, "error": None},
                  "resource_samples": {"n_samples": N}}
        j = hr.judge({"judge_media": {"image_creates": 0, "video_creates": 0,
                                      "media_downloads": 0}}, root, report)
        rc = next(c for c in j["checks"] if c["check"] == "stream_rows_consistent")
        self.assertFalse(rc["passed"])

    def test_boundary_all_null(self):
        b = make_bounds(bstart={"scope": SCOPE, "scope_kind": KIND, "t_monotonic_ns": 0,
                                "cpu_usage_usec": None, "mem_current_bytes": None,
                                "io_read_bytes": None, "io_write_bytes": None,
                                "read_status": dict(RS)},
                        bend={"scope": SCOPE, "scope_kind": KIND, "t_monotonic_ns": (N - 1) * 10 ** 9,
                              "cpu_usage_usec": None, "mem_current_bytes": None,
                              "io_read_bytes": None, "io_write_bytes": None,
                              "read_status": dict(RS)})
        root = damage_copy(self.base, bounds=b)
        qr = self._check(root, "quality_recomputed")
        self.assertFalse(qr["passed"])

    def test_counter_regression_in_file(self):
        rows = make_rows(corrupt_at={"i": 6, "fields": {"cpu_usage_usec": 500}})
        root = damage_copy(self.base, stream="".join(json.dumps(r) + "\n" for r in rows))
        qr = self._check(root, "quality_recomputed")
        self.assertFalse(qr["passed"])


class TestBoundaryOnly(unittest.TestCase):
    def test_valid_short_task_boundary_only(self):
        b = make_bounds()
        q = assess_resource_quality(stream_rows=[], boundary_start=_mk(b["boundary_start"]),
                                    boundary_end=_mk(b["boundary_end"]),
                                    expected_scope=SCOPE, expected_scope_kind=KIND)
        self.assertEqual(q["cpu"]["status"], "boundary_only")
        self.assertTrue(q["cpu"]["passed"])
        self.assertIn("not a complete curve", q["cpu"]["reason"])

    def test_all_null_boundary_fails(self):
        b = make_bounds(bstart={"scope": SCOPE, "scope_kind": KIND, "t_monotonic_ns": 0,
                                "cpu_usage_usec": None, "mem_current_bytes": None,
                                "io_read_bytes": None, "io_write_bytes": None,
                                "read_status": dict(RS)},
                        bend={"scope": SCOPE, "scope_kind": KIND, "t_monotonic_ns": 10 ** 9,
                              "cpu_usage_usec": None, "mem_current_bytes": None,
                              "io_read_bytes": None, "io_write_bytes": None,
                              "read_status": dict(RS)})
        q = assess_resource_quality(stream_rows=[], boundary_start=_mk(b["boundary_start"]),
                                    boundary_end=_mk(b["boundary_end"]),
                                    expected_scope=SCOPE, expected_scope_kind=KIND)
        self.assertFalse(q["cpu"]["passed"])
        self.assertIn(q["cpu"]["status"], ("boundary_value_invalid", "boundary_value_missing"))

    def test_one_sided_missing_boundary_fails(self):
        b = make_bounds(bend={"scope": SCOPE, "scope_kind": KIND, "t_monotonic_ns": 10 ** 9,
                              "cpu_usage_usec": None, "mem_current_bytes": 1000,
                              "io_read_bytes": 100, "io_write_bytes": 50,
                              "read_status": dict(RS)})
        q = assess_resource_quality(stream_rows=[], boundary_start=_mk(b["boundary_start"]),
                                    boundary_end=_mk(b["boundary_end"]),
                                    expected_scope=SCOPE, expected_scope_kind=KIND)
        self.assertFalse(q["cpu"]["passed"])
        self.assertEqual(q["cpu"]["status"], "boundary_value_missing")

    def test_boundary_counter_regression_fails(self):
        b = make_bounds(bend={"scope": SCOPE, "scope_kind": KIND, "t_monotonic_ns": 10 ** 9,
                              "cpu_usage_usec": 10, "mem_current_bytes": 1000,
                              "io_read_bytes": 100, "io_write_bytes": 50,
                              "read_status": dict(RS)})
        q = assess_resource_quality(stream_rows=[], boundary_start=_mk(b["boundary_start"]),
                                    boundary_end=_mk(b["boundary_end"]),
                                    expected_scope=SCOPE, expected_scope_kind=KIND)
        self.assertFalse(q["cpu"]["passed"])
        self.assertEqual(q["cpu"]["status"], "boundary_counter_regression")


class TestAssessReadStatus(unittest.TestCase):
    def _rows(self, read_fail_at=None, status_missing_at=None):
        rows = []
        for i in range(4):
            rs = dict(RS)
            if read_fail_at is not None and i in read_fail_at:
                rs = {"cpuacct.usage": "unreadable", "memory.usage_in_bytes": "ok",
                      "io.stat": "ok_summed_devices"}
            if status_missing_at is not None and i in status_missing_at:
                rs.pop("cpuacct.usage")
            rows.append(CounterSnapshot(scope=SCOPE, scope_kind=KIND,
                                        t_monotonic_ns=i * 10 ** 9,
                                        cpu_usage_usec=1000 + i * 1000,
                                        mem_current_bytes=1000 + i,
                                        io_read_bytes=100 + i, io_write_bytes=50 + i,
                                        read_status=rs))
        return rows

    def test_read_failure_then_success_retained(self):
        rows = self._rows(read_fail_at={1})
        sp = ScopeSamples(scope=SCOPE, scope_kind=KIND, interval_target_s=0.5)
        sp.samples = rows; sp.boundary_start = rows[0]; sp.boundary_end = rows[-1]
        q = assess_resource_quality(sp, expected_scope=SCOPE, expected_scope_kind=KIND)
        self.assertEqual(q["cpu"]["status"], "read_failed")
        self.assertFalse(q["cpu"]["passed"])
        self.assertEqual(q["cpu"]["read_fail_samples"], [1])

    def test_status_missing_retained(self):
        rows = self._rows(status_missing_at={2})
        sp = ScopeSamples(scope=SCOPE, scope_kind=KIND, interval_target_s=0.5)
        sp.samples = rows; sp.boundary_start = rows[0]; sp.boundary_end = rows[-1]
        q = assess_resource_quality(sp, expected_scope=SCOPE, expected_scope_kind=KIND)
        self.assertEqual(q["cpu"]["status"], "status_missing")
        self.assertFalse(q["cpu"]["passed"])

    def test_success_all_complete(self):
        rows = self._rows()
        sp = ScopeSamples(scope=SCOPE, scope_kind=KIND, interval_target_s=0.5)
        sp.samples = rows; sp.boundary_start = rows[0]; sp.boundary_end = rows[-1]
        q = assess_resource_quality(sp, expected_scope=SCOPE, expected_scope_kind=KIND)
        self.assertEqual(q["cpu"]["status"], "complete")
        self.assertTrue(q["cpu"]["passed"])

    def test_scope_conflict_detected(self):
        rows = [CounterSnapshot(scope="other", scope_kind=KIND, t_monotonic_ns=i * 10 ** 9,
                                cpu_usage_usec=1000 + i * 1000, mem_current_bytes=1000,
                                io_read_bytes=100, io_write_bytes=50, read_status=dict(RS))
                for i in range(3)]
        sp = ScopeSamples(scope="s", scope_kind=KIND, interval_target_s=0.5)
        sp.samples = rows; sp.boundary_start = rows[0]; sp.boundary_end = rows[-1]
        q = assess_resource_quality(sp, expected_scope="s", expected_scope_kind=KIND)
        self.assertTrue(q["scope_identity"]["conflict"])
        self.assertIn("other", q["scope_identity"]["samples_scope"])

    def test_real_zero_valid(self):
        rows = [CounterSnapshot(scope=SCOPE, scope_kind=KIND, t_monotonic_ns=i * 10 ** 9,
                                cpu_usage_usec=1000, mem_current_bytes=0,
                                io_read_bytes=0, io_write_bytes=0, read_status=dict(RS))
                for i in range(3)]
        sp = ScopeSamples(scope=SCOPE, scope_kind=KIND, interval_target_s=0.5)
        sp.samples = rows; sp.boundary_start = rows[0]; sp.boundary_end = rows[-1]
        q = assess_resource_quality(sp, expected_scope=SCOPE, expected_scope_kind=KIND)
        self.assertEqual(q["memory"]["status"], "complete")
        self.assertEqual(q["memory"]["sampled"], 3)


class TestValidateStream(unittest.TestCase):
    def test_single_empty_object_invalid(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "s.jsonl"
            p.write_text("{}\n")
            v = validate_resource_stream(p)
            self.assertEqual(v["valid_count"], 0)
            self.assertGreaterEqual(len(v["invalid"]), 1)

    def test_not_object_invalid(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "s.jsonl"
            p.write_text("[1,2]\n")
            v = validate_resource_stream(p)
            self.assertEqual(v["valid_count"], 0)
            self.assertEqual(v["invalid"][0]["reason"], "not_object")

    def test_bool_negative_nan_invalid(self):
        bad = [{"schema": "resource-stream-v1", "scope": SCOPE, "scope_kind": KIND,
                "t_monotonic_ns": 1, "cpu_usage_usec": True},
               {"schema": "resource-stream-v1", "scope": SCOPE, "scope_kind": KIND,
                "t_monotonic_ns": 2, "cpu_usage_usec": -1},
               {"schema": "resource-stream-v1", "scope": SCOPE, "scope_kind": KIND,
                "t_monotonic_ns": 3, "mem_current_bytes": float("nan")}]
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "s.jsonl"
            p.write_text("".join(json.dumps(r) + "\n" for r in bad))
            v = validate_resource_stream(p)
            self.assertEqual(v["valid_count"], 0)
            reasons = ";".join(x["reason"] for x in v["invalid"])
            self.assertIn("bad_type", reasons)
            self.assertIn("negative", reasons)
            self.assertIn("non_finite", reasons)

    def test_good_rows_valid(self):
        rows = make_rows(n=5)
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "s.jsonl"
            p.write_text("".join(json.dumps(r) + "\n" for r in rows))
            v = validate_resource_stream(p)
            self.assertEqual(v["valid_count"], 5)
            self.assertEqual(v["status"], "ok")


if __name__ == "__main__":
    unittest.main(verbosity=2)
