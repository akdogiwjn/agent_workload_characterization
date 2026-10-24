#!/usr/bin/env python3
"""Observation audit-3 counterexamples: prove the FINAL judge result flips
with each single-target corruption. Reuses the real final.mp4 from
audit-verify-133803 as read-only fixture input (no per-test FFmpeg render)."""
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
FINAL_SRC = (Path(__file__).resolve().parents[1] / "evidence"
             / "audit-verify-133803")


def make_rows(n=N, scope=SCOPE, kind=KIND, corrupt_at=None, drop_field=None):
    rows = []
    for i in range(n):
        r = {"schema": "resource-stream-v1", "scope": scope, "scope_kind": kind,
             "t_monotonic_ns": i * 10 ** 9, "cpu_usage_usec": 1000 + i * 1000,
             "mem_current_bytes": 1000 + i, "mem_peak_bytes": None,
             "io_read_bytes": 100 + i, "io_write_bytes": 50 + i,
             "read_status": dict(RS)}
        if corrupt_at is not None and i == corrupt_at["i"]:
            r.update(corrupt_at["fields"])
        if drop_field and i == 5:
            r.pop(drop_field, None)
        rows.append(r)
    return rows


def make_bounds(scope=SCOPE, kind=KIND, cpu_end=64000, mem_peak=2000):
    return {
        "boundary_start": {"scope": scope, "scope_kind": kind, "t_monotonic_ns": 0,
                           "cpu_usage_usec": 1000, "mem_current_bytes": 1000,
                           "mem_peak_bytes": None, "io_read_bytes": 100,
                           "io_write_bytes": 50, "read_status": dict(RS)},
        "boundary_end": {"scope": scope, "scope_kind": kind,
                         "t_monotonic_ns": (N - 1) * 10 ** 9,
                         "cpu_usage_usec": cpu_end, "mem_current_bytes": 1000 + (N - 1),
                         "mem_peak_bytes": mem_peak, "io_read_bytes": 100 + (N - 1),
                         "io_write_bytes": 50 + (N - 1), "read_status": dict(RS)},
    }


def make_report(rows=None, bounds=None, quality_rows=None, ssm=True,
                stream_state_rows=N, n_samples=N, mem_sum=None):
    rows = rows if rows is not None else make_rows()
    bounds = bounds if bounds is not None else make_bounds()
    quality_rows = quality_rows if quality_rows is not None else rows
    q = assess_resource_quality(stream_rows=quality_rows, boundary_start=_mk(bounds["boundary_start"]),
                                boundary_end=_mk(bounds["boundary_end"]),
                                expected_scope=SCOPE, expected_scope_kind=KIND)
    mems = [r["mem_current_bytes"] for r in rows if r.get("mem_current_bytes") is not None]
    report = {
        "errors": [],
        "cleanup": {"removed": True},
        "measurement_quality": q,
        "resource_samples": {
            "n_samples": n_samples,
            "cpu_core_seconds": (bounds["boundary_end"]["cpu_usage_usec"]
                                 - bounds["boundary_start"]["cpu_usage_usec"]) / 1e6,
            "memory_sampled_max_bytes": max(mems) if mems else None,
            "memory_kernel_peak_bytes": bounds["boundary_end"].get("mem_peak_bytes"),
            "wall_s": (bounds["boundary_end"]["t_monotonic_ns"]
                       - bounds["boundary_start"]["t_monotonic_ns"]) / 1e9,
        },
        "stream_state": {"rows_written": stream_state_rows, "rows_received": stream_state_rows,
                         "rows_buffered": 0, "lost_undelivered": 0, "error": None},
    }
    if ssm:
        report["sample_metrics_summary"] = {
            "schema": "sample-metrics-summary-v1",
            "mem_sum": mem_sum if mem_sum is not None else (sum(mems) if mems else None),
            "mem_count": len(mems),
        }
    return report


def _mk(d):
    return hr.CounterSnapshot(scope=d["scope"], scope_kind=d["scope_kind"],
                              t_monotonic_ns=d["t_monotonic_ns"],
                              cpu_usage_usec=d.get("cpu_usage_usec"),
                              mem_current_bytes=d.get("mem_current_bytes"),
                              mem_peak_bytes=d.get("mem_peak_bytes"),
                              io_read_bytes=d.get("io_read_bytes"),
                              io_write_bytes=d.get("io_write_bytes"),
                              read_status=d.get("read_status") or {})


def base_fixture(td: Path, *, stream=None, bounds=None, report_override=None,
                 stream_state_rows=N):
    """Complete merge-validated fixture; only the target is corrupted by callers."""
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
        raise RuntimeError("no read-only final.mp4 fixture found under "
                           + str(FINAL_SRC))
    return root


def build(td, *, stream=None, bounds=None, report_override=None, ssm=True,
          mem_sum=None, stream_state_rows=N):
    root = base_fixture(td, stream=stream, bounds=bounds)
    rep = make_report(stream_state_rows=stream_state_rows, ssm=ssm, mem_sum=mem_sum)
    if report_override:
        rep.update(report_override)
    return root, rep


def run(root, rep):
    return hr.judge({"judge_media": {"image_creates": 0, "video_creates": 0,
                                     "media_downloads": 0}}, root, rep)


def check_fail(j, name):
    c = next(c for c in j["checks"] if c["check"] == name)
    return not c["passed"], c["detail"]


class TestFinalJudge(unittest.TestCase):
    def _fresh(self):
        return tempfile.mkdtemp(prefix="vw-a3-")

    def _cleanup(self, td):
        shutil.rmtree(td, ignore_errors=True)

    # A. normal data -> final PASS
    def test_a_normal_passes(self):
        td = self._fresh()
        try:
            root, rep = build(td)
            j = run(root, rep)
            self.assertTrue(j["passed"], [c["detail"] for c in j["checks"] if not c["passed"]])
        finally:
            self._cleanup(td)

    # B. one memory 1 TiB -> final FAIL
    def test_b_mem_1tib_fails(self):
        td = self._fresh()
        try:
            rows = make_rows(corrupt_at={"i": 20, "fields": {"mem_current_bytes": 1024 ** 4}})
            root, rep = build(td, stream="".join(json.dumps(r) + "\n" for r in rows))
            j = run(root, rep)
            self.assertFalse(j["passed"])
            ok, det = check_fail(j, "numeric_consistent")
            self.assertTrue(ok)
            self.assertIn("mem_sampled_max", det)
        finally:
            self._cleanup(td)

    # C. one internal sample changed without peak/count change -> FAIL via saved summary
    def test_c_internal_change_fails(self):
        td = self._fresh()
        try:
            rows = make_rows(corrupt_at={"i": 10, "fields": {"mem_current_bytes": 1010 + 1}})
            # mem[10]=1010 -> 1011; max unchanged (1063), count unchanged
            root, rep = build(td, stream="".join(json.dumps(r) + "\n" for r in rows))
            j = run(root, rep)
            self.assertFalse(j["passed"])
            ok, det = check_fail(j, "numeric_consistent")
            self.assertTrue(ok)
            self.assertIn("mem_sum", det)
        finally:
            self._cleanup(td)

    # D. both boundary scopes = "other" -> final FAIL
    def test_d_boundary_scope_other_fails(self):
        td = self._fresh()
        try:
            b = make_bounds(scope="other")
            root, rep = build(td, bounds=b)
            j = run(root, rep)
            self.assertFalse(j["passed"])
            ok, det = check_fail(j, "scope_identity_ok")
            self.assertTrue(ok)
        finally:
            self._cleanup(td)

    # E. missing scope in one sample -> final FAIL
    def test_e_missing_scope_fails(self):
        td = self._fresh()
        try:
            rows = make_rows(drop_field="scope")
            root, rep = build(td, stream="".join(json.dumps(r) + "\n" for r in rows))
            j = run(root, rep)
            self.assertFalse(j["passed"])
            ok, det = check_fail(j, "stream_metrics_valid")
            self.assertTrue(ok)
            self.assertIn("scope_missing", det)
        finally:
            self._cleanup(td)

    # F. valid short task: empty periodic stream + valid boundaries + declared 0 -> boundary pass
    def test_f_boundary_only_passes(self):
        td = self._fresh()
        try:
            # effective short window (< target interval 0.5s): boundary_only_limited
            b = make_bounds()
            b["boundary_end"]["t_monotonic_ns"] = int(0.4 * 10 ** 9)
            b["boundary_end"]["cpu_usage_usec"] = 1400
            root, rep = build(td, stream="", bounds=b, ssm=False,
                              stream_state_rows=0)
            rep["resource_samples"] = {"n_samples": 0, "cpu_core_seconds": 0.0004,
                                       "memory_sampled_max_bytes": None,
                                       "memory_kernel_peak_bytes": 2000, "wall_s": 0.4}
            rep["sample_interval_s"] = 0.5
            rep["sample_content_summary"] = sample_content_digest([])
            rep["measurement_quality"] = assess_resource_quality(
                stream_rows=[], boundary_start=_mk(b["boundary_start"]),
                boundary_end=_mk(b["boundary_end"]),
                expected_scope=SCOPE, expected_scope_kind=KIND,
                interval_target_s=0.5)
            j = run(root, rep)
            self.assertTrue(j["passed"], [c["detail"] for c in j["checks"] if not c["passed"]])
            # continuous sampling explicitly limited
            cov = rep["measurement_quality"]["coverage"]
            self.assertEqual(cov["status"], "boundary_only_limited")
            q = rep["measurement_quality"]
            self.assertEqual(q["cpu"]["status"], "boundary_only")
            self.assertIn("not a complete curve", q["cpu"]["reason"])
        finally:
            self._cleanup(td)

    # G. same empty stream but invalid boundaries -> final FAIL
    def test_g_boundary_only_invalid_boundaries_fail(self):
        td = self._fresh()
        try:
            nullb = make_bounds()
            nullb["boundary_start"]["cpu_usage_usec"] = None
            nullb["boundary_end"]["cpu_usage_usec"] = None
            root, rep = build(td, stream="", bounds=nullb, ssm=False,
                              stream_state_rows=0)
            rep["resource_samples"] = {"n_samples": 0, "cpu_core_seconds": None,
                                       "memory_sampled_max_bytes": None,
                                       "memory_kernel_peak_bytes": 2000, "wall_s": 63.0}
            # report quality from VALID boundaries (normal run) to force mismatch
            vb = make_bounds()
            rep["measurement_quality"] = assess_resource_quality(
                stream_rows=[], boundary_start=_mk(vb["boundary_start"]),
                boundary_end=_mk(vb["boundary_end"]),
                expected_scope=SCOPE, expected_scope_kind=KIND)
            j = run(root, rep)
            self.assertFalse(j["passed"])
            ok, det = check_fail(j, "quality_recomputed")
            self.assertTrue(ok)
        finally:
            self._cleanup(td)

    # H. required metric key missing -> structural + final FAIL
    def test_h_required_key_missing_fails(self):
        td = self._fresh()
        try:
            rows = make_rows(drop_field="io_read_bytes")
            root, rep = build(td, stream="".join(json.dumps(r) + "\n" for r in rows))
            j = run(root, rep)
            self.assertFalse(j["passed"])
            ok, det = check_fail(j, "stream_metrics_valid")
            self.assertTrue(ok)
            self.assertIn("io_read_bytes_missing", det)
        finally:
            self._cleanup(td)

    # I. metric key present but null -> structurally valid, metric missing (not complete)
    def test_i_null_metric_is_missing_not_complete(self):
        td = self._fresh()
        try:
            rows = make_rows(corrupt_at={"i": 3, "fields": {"io_read_bytes": None}})
            stream = "".join(json.dumps(r) + "\n" for r in rows)
            v = validate_resource_stream(Path(td) / "x.jsonl") if False else None
            root, rep = build(td, stream=stream)
            j = run(root, rep)
            # structural validation passes (null is legal), but io_read partial-missing
            sv = next(c for c in j["checks"] if c["check"] == "stream_validated")
            self.assertTrue(sv["passed"])
            # metric missing reflects in quality -> final FAIL (not complete)
            self.assertFalse(j["passed"])
        finally:
            self._cleanup(td)


if __name__ == "__main__":
    unittest.main(verbosity=2)
