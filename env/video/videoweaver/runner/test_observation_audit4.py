#!/usr/bin/env python3
"""Observation audit-4: content digest, counter conservation, zero-I/O status,
and continuous-sampling coverage reach the FINAL judge. Reuses the real
final.mp4 as read-only fixture (no per-test render)."""
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "gateway"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from agent_workload_characterization.collectors.execution_measurement import (
    assess_resource_quality, validate_resource_stream, sample_content_digest)
import host_runner as hr

N = 64
SCOPE = "videoweaver"
KIND = "agent_container"
RS = {"cpuacct.usage": "ok_ns_converted_to_usec",
      "memory.usage_in_bytes": "ok", "io.stat": "ok_summed_devices"}
ZERO_IO_RS = {"cpuacct.usage": "ok_ns_converted_to_usec",
              "memory.usage_in_bytes": "ok",
              "io": "ok_no_records_real_zero:blkio.throttle.io_service_bytes_recursive"}
UNREAD_IO_RS = {"cpuacct.usage": "ok_ns_converted_to_usec",
                "memory.usage_in_bytes": "ok", "io": "io_files_unavailable"}
FINAL_SRC = (Path(__file__).resolve().parents[1] / "evidence"
             / "audit-verify-133803")


def make_rows(n=N, scope=SCOPE, kind=KIND, rs=RS, corrupt_at=None,
              swap_at=None, t_shift_at=None):
    rows = []
    for i in range(n):
        r = {"schema": "resource-stream-v1", "scope": scope, "scope_kind": kind,
             "t_monotonic_ns": i * 10 ** 9, "cpu_usage_usec": 1000 + i * 1000,
             "mem_current_bytes": 1000 + i, "mem_peak_bytes": None,
             "io_read_bytes": 100 + i, "io_write_bytes": 50 + i,
             "read_status": dict(rs)}
        rows.append(r)
    if corrupt_at is not None:
        rows[corrupt_at["i"]].update(corrupt_at["fields"])
    if t_shift_at is not None:
        rows[t_shift_at]["t_monotonic_ns"] += int(10 ** 10)  # 10s jump (large gap)
    if swap_at is not None:
        rows[swap_at["i"]], rows[swap_at["j"]] = rows[swap_at["j"]], rows[swap_at["i"]]
    return rows


def make_bounds(scope=SCOPE, kind=KIND, cpu_end=64000, mem_peak=2000, rs=RS):
    return {
        "boundary_start": {"scope": scope, "scope_kind": kind, "t_monotonic_ns": 0,
                           "cpu_usage_usec": 1000, "mem_current_bytes": 1000,
                           "mem_peak_bytes": None, "io_read_bytes": 100,
                           "io_write_bytes": 50, "read_status": dict(rs)},
        "boundary_end": {"scope": scope, "scope_kind": kind,
                         "t_monotonic_ns": (N - 1) * 10 ** 9,
                         "cpu_usage_usec": cpu_end, "mem_current_bytes": 1000 + (N - 1),
                         "mem_peak_bytes": mem_peak, "io_read_bytes": 100 + (N - 1),
                         "io_write_bytes": 50 + (N - 1), "read_status": dict(rs)},
    }


def _mk(d):
    return hr.CounterSnapshot(scope=d["scope"], scope_kind=d["scope_kind"],
                              t_monotonic_ns=d["t_monotonic_ns"],
                              cpu_usage_usec=d.get("cpu_usage_usec"),
                              mem_current_bytes=d.get("mem_current_bytes"),
                              mem_peak_bytes=d.get("mem_peak_bytes"),
                              io_read_bytes=d.get("io_read_bytes"),
                              io_write_bytes=d.get("io_write_bytes"),
                              read_status=d.get("read_status") or {})


def make_report(rows, bounds, ss, *, interval=0.5, digest_rows=None,
                quality_rows=None, n_samples=N, wall=63.0,
                cpu_core=0.063, mem_peak=2000):
    digest_rows = digest_rows if digest_rows is not None else rows
    quality_rows = quality_rows if quality_rows is not None else rows
    q = assess_resource_quality(stream_rows=quality_rows,
                                boundary_start=_mk(bounds["boundary_start"]),
                                boundary_end=_mk(bounds["boundary_end"]),
                                expected_scope=SCOPE, expected_scope_kind=KIND,
                                interval_target_s=interval)
    mems = [r["mem_current_bytes"] for r in rows if r.get("mem_current_bytes") is not None]
    return {
        "errors": [],
        "cleanup": {"removed": True},
        "measurement_quality": q,
        "resource_samples": {"n_samples": n_samples, "cpu_core_seconds": cpu_core,
                             "memory_sampled_max_bytes": max(mems) if mems else None,
                             "memory_kernel_peak_bytes": mem_peak, "wall_s": wall},
        "stream_state": ss,
        "sample_metrics_summary": {"schema": "sample-metrics-summary-v1",
                                   "mem_sum": sum(mems) if mems else None,
                                   "mem_count": len(mems)},
        "sample_content_summary": sample_content_digest(digest_rows),
        "sample_interval_s": interval,
    }


def base_fixture(td: Path, *, stream=None, bounds=None):
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
    if stream is None:
        rows = make_rows()
        stream = "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows)
    (root / "samples" / "resource-stream.jsonl").write_text(stream)
    b = bounds if bounds is not None else make_bounds()
    (root / "samples" / "boundaries.json").write_text(json.dumps(b))
    (root / "samples" / "summary.json").write_text(json.dumps({"n_samples": N}))
    out = root / "closeout" / "merge-agent-output"
    out.mkdir(parents=True, exist_ok=True)
    finals = list(FINAL_SRC.rglob("final.mp4"))
    if finals:
        shutil.copy2(finals[0], out / "final.mp4")
    else:
        raise RuntimeError("no read-only final.mp4 under " + str(FINAL_SRC))
    return root


def build(td, *, stream=None, bounds=None, report=None):
    root = base_fixture(td, stream=stream, bounds=bounds)
    if report is None:
        rows = make_rows()
        report = make_report(rows, make_bounds(),
                             {"rows_received": N, "rows_written": N,
                              "rows_buffered": 0, "lost_undelivered": 0,
                              "error": None})
    return root, report


def run(root, rep):
    return hr.judge({"judge_media": {"image_creates": 0, "video_creates": 0,
                                     "media_downloads": 0}}, root, rep)


class TestFinalJudge4(unittest.TestCase):
    def _fresh(self):
        return tempfile.mkdtemp(prefix="vw-a4-")

    def _cleanup(self, td):
        shutil.rmtree(td, ignore_errors=True)

    def _find(self, j, name):
        return next(c for c in j["checks"] if c["check"] == name)

    # A. normal data -> PASS
    def test_a_normal_passes(self):
        td = self._fresh()
        try:
            root, rep = build(td)
            j = run(root, rep)
            self.assertTrue(j["passed"], [c["detail"] for c in j["checks"] if not c["passed"]])
        finally:
            self._cleanup(td)

    # B. internal CPU +1 -> content digest mismatch -> FAIL
    def test_b_cpu_plus1_digest_fails(self):
        td = self._fresh()
        try:
            rows = make_rows(corrupt_at={"i": 20, "fields": {"cpu_usage_usec": 21001}})
            stream = "".join(json.dumps(r) + "\n" for r in rows)
            rep = make_report(make_rows(), make_bounds(),  # report digest = normal rows
                              {"rows_received": N, "rows_written": N,
                               "rows_buffered": 0, "lost_undelivered": 0, "error": None})
            root, rep = build(td, stream=stream, report=rep)
            j = run(root, rep)
            self.assertFalse(j["passed"])
            c = self._find(j, "content_digest_consistent")
            self.assertFalse(c["passed"])
        finally:
            self._cleanup(td)

    # C. time change / read_status change / row swap -> digest mismatch
    def test_c_time_status_swap_digest_fails(self):
        for kind in ("time", "status", "swap"):
            td = self._fresh()
            try:
                if kind == "time":
                    rows = make_rows(corrupt_at={"i": 5, "fields": {"t_monotonic_ns": 6 * 10 ** 9}})
                elif kind == "status":
                    rows = make_rows(corrupt_at={"i": 5, "fields": {"read_status": {"io": "ok_no_records_real_zero:x"}}})
                else:
                    rows = make_rows(swap_at={"i": 5, "j": 6})
                stream = "".join(json.dumps(r) + "\n" for r in rows)
                rep = make_report(make_rows(), make_bounds(),
                                  {"rows_received": N, "rows_written": N,
                                   "rows_buffered": 0, "lost_undelivered": 0, "error": None})
                root, rep = build(td, stream=stream, report=rep)
                j = run(root, rep)
                self.assertFalse(j["passed"], kind)
                c = self._find(j, "content_digest_consistent")
                self.assertFalse(c["passed"], kind)
            finally:
                self._cleanup(td)

    # D. received != written+buffered+lost -> FAIL
    def test_d_counters_not_conserved_fails(self):
        td = self._fresh()
        try:
            rows = make_rows()
            stream = "".join(json.dumps(r) + "\n" for r in rows)
            rep = make_report(rows, make_bounds(),
                              {"rows_received": 100, "rows_written": 64,
                               "rows_buffered": 20, "lost_undelivered": 20, "error": None})
            root, rep = build(td, stream=stream, report=rep)
            j = run(root, rep)
            self.assertFalse(j["passed"])
            c = self._find(j, "stream_counters_conserved")
            self.assertFalse(c["passed"])
        finally:
            self._cleanup(td)

    # E. conserved but lost>0 -> measurement incomplete
    def test_e_lost_nonzero_fails(self):
        td = self._fresh()
        try:
            rows = make_rows()
            stream = "".join(json.dumps(r) + "\n" for r in rows)
            rep = make_report(rows, make_bounds(),
                              {"rows_received": 104, "rows_written": 64,
                               "rows_buffered": 20, "lost_undelivered": 20, "error": None})
            root, rep = build(td, stream=stream, report=rep)
            j = run(root, rep)
            self.assertFalse(j["passed"])
            c = self._find(j, "stream_no_loss")
            self.assertFalse(c["passed"])
        finally:
            self._cleanup(td)

    # F. buffered>0 at close -> incomplete
    def test_f_buffered_nonzero_fails(self):
        td = self._fresh()
        try:
            rows = make_rows()
            stream = "".join(json.dumps(r) + "\n" for r in rows)
            rep = make_report(rows, make_bounds(),
                              {"rows_received": 69, "rows_written": 64,
                               "rows_buffered": 5, "lost_undelivered": 0, "error": None})
            root, rep = build(td, stream=stream, report=rep)
            j = run(root, rep)
            self.assertFalse(j["passed"])
            c = self._find(j, "stream_flush_state")
            self.assertFalse(c["passed"])
        finally:
            self._cleanup(td)

    # G. missing / negative / bool counter -> FAIL
    def test_g_invalid_counters_fail(self):
        for name, ss in (("missing", {"rows_written": 64}),
                         ("negative", {"rows_received": -1, "rows_written": 64,
                                       "rows_buffered": 0, "lost_undelivered": 0}),
                         ("bool", {"rows_received": True, "rows_written": 64,
                                   "rows_buffered": 0, "lost_undelivered": 0})):
            td = self._fresh()
            try:
                rows = make_rows()
                stream = "".join(json.dumps(r) + "\n" for r in rows)
                rep = make_report(rows, make_bounds(), dict(ss))
                root, rep = build(td, stream=stream, report=rep)
                j = run(root, rep)
                self.assertFalse(j["passed"], name)
                c = self._find(j, "stream_counters_valid")
                self.assertFalse(c["passed"], name)
            finally:
                self._cleanup(td)

    # H. real-reader zero-I/O status + zero readings -> PASS
    def test_h_zero_io_passes(self):
        td = self._fresh()
        try:
            rows = make_rows(rs=ZERO_IO_RS)
            for r in rows:
                r["io_read_bytes"] = 0
                r["io_write_bytes"] = 0
            b = make_bounds(rs=ZERO_IO_RS)
            b["boundary_start"]["io_read_bytes"] = 0
            b["boundary_start"]["io_write_bytes"] = 0
            b["boundary_end"]["io_read_bytes"] = 0
            b["boundary_end"]["io_write_bytes"] = 0
            stream = "".join(json.dumps(r) + "\n" for r in rows)
            rep = make_report(rows, b,
                              {"rows_received": N, "rows_written": N,
                               "rows_buffered": 0, "lost_undelivered": 0, "error": None})
            root, rep = build(td, stream=stream, bounds=b, report=rep)
            j = run(root, rep)
            self.assertTrue(j["passed"], [c["detail"] for c in j["checks"] if not c["passed"]])
        finally:
            self._cleanup(td)

    # I. reader unreadable / unsupported -> kept, not fake zero -> FAIL
    def test_i_unreadable_io_fails(self):
        td = self._fresh()
        try:
            rows = make_rows(rs=UNREAD_IO_RS)
            b = make_bounds(rs=UNREAD_IO_RS)
            stream = "".join(json.dumps(r) + "\n" for r in rows)
            rep = make_report(rows, b,
                              {"rows_received": N, "rows_written": N,
                               "rows_buffered": 0, "lost_undelivered": 0, "error": None})
            root, rep = build(td, stream=stream, bounds=b, report=rep)
            j = run(root, rep)
            self.assertFalse(j["passed"])
            # io not treated as complete
            mq = self._find(j, "mq_io_read")
            self.assertFalse(mq["passed"])
        finally:
            self._cleanup(td)

    # J. effective short window, empty stream, valid boundaries -> boundary pass (coverage limited)
    def test_j_short_window_passes(self):
        td = self._fresh()
        try:
            b = make_bounds()
            b["boundary_end"]["t_monotonic_ns"] = int(0.4 * 10 ** 9)
            b["boundary_end"]["cpu_usage_usec"] = 1400
            rep = make_report([], b,
                              {"rows_received": 0, "rows_written": 0,
                               "rows_buffered": 0, "lost_undelivered": 0, "error": None},
                              digest_rows=[], quality_rows=[], n_samples=0,
                              wall=0.4, cpu_core=0.0004, mem_peak=2000)
            root, rep = build(td, stream="", bounds=b, report=rep)
            j = run(root, rep)
            self.assertTrue(j["passed"], [c["detail"] for c in j["checks"] if not c["passed"]])
            cov = self._find(j, "coverage_ok")
            self.assertTrue(cov["passed"])
        finally:
            self._cleanup(td)

    # K. 63s window, 0.5s target, empty stream -> coverage fails
    def test_k_long_window_empty_fails(self):
        td = self._fresh()
        try:
            b = make_bounds()
            rep = make_report([], b,
                              {"rows_received": 0, "rows_written": 0,
                               "rows_buffered": 0, "lost_undelivered": 0, "error": None},
                              digest_rows=[], quality_rows=[], n_samples=0,
                              wall=63.0, cpu_core=0.063, mem_peak=2000)
            root, rep = build(td, stream="", bounds=b, report=rep)
            j = run(root, rep)
            self.assertFalse(j["passed"])
            cov = self._find(j, "coverage_ok")
            self.assertFalse(cov["passed"])
        finally:
            self._cleanup(td)

    # L. middle large gap -> coverage gap (fails)
    def test_l_large_gap_fails(self):
        td = self._fresh()
        try:
            rows = make_rows(t_shift_at=30)  # 10s jump at row 30
            stream = "".join(json.dumps(r) + "\n" for r in rows)
            rep = make_report(rows, make_bounds(),
                              {"rows_received": N, "rows_written": N,
                               "rows_buffered": 0, "lost_undelivered": 0, "error": None})
            root, rep = build(td, stream=stream, report=rep)
            j = run(root, rep)
            self.assertFalse(j["passed"])
            cov = self._find(j, "coverage_ok")
            self.assertFalse(cov["passed"])
        finally:
            self._cleanup(td)


if __name__ == "__main__":
    unittest.main(verbosity=2)
