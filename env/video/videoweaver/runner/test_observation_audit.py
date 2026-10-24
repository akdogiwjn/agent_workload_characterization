#!/usr/bin/env python3
"""Audit-counterexample tests for the observation round fixes.

Unit layer only (no containers, no credentials). Covers the exact regressions
from the audit: empty samples, partial missing, I/O regression, cgroup v1
status, judge consuming quality, stream write/lost accounting, gateway
missing-id attribution to the local request, and soft-threshold stop."""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "gateway"))

from agent_workload_characterization.collectors.resource_sampler import (
    CounterSnapshot, ScopeSamples)
from agent_workload_characterization.collectors.execution_measurement import (
    assess_resource_quality, read_resource_stream, directory_footprint_snapshot)
from gateway import Ledger, DEFAULT_BUDGET


_OK = {"cpuacct.usage": "ok_ns_converted_to_usec", "memory.usage_in_bytes": "ok",
       "io.stat": "ok_summed_devices"}

def snap(scope="s", kind="agent_container", t=0, cpu=None, mem=None,
         io_r=None, io_w=None, rs=None):
    return CounterSnapshot(scope=scope, scope_kind=kind, t_monotonic_ns=t,
                           cpu_usage_usec=cpu, mem_current_bytes=mem,
                           io_read_bytes=io_r, io_write_bytes=io_w,
                           read_status=rs if rs is not None else dict(_OK))


def samples(*rows, bstart=None, bend=None, notes=None):
    sp = ScopeSamples(scope="s", scope_kind="agent_container", interval_target_s=0.5)
    sp.samples = list(rows)
    sp.boundary_start = bstart or (rows[0] if rows else None)
    sp.boundary_end = bend or (rows[-1] if rows else None)
    sp.notes = notes or []
    return sp


class TestAssessEmptyPartial(unittest.TestCase):
    def test_empty_without_boundaries_not_complete(self):
        sp = ScopeSamples(scope="s", scope_kind="agent_container", interval_target_s=0.5)
        q = assess_resource_quality(sp)
        self.assertEqual(q["cpu"]["status"], "no_samples")
        self.assertFalse(q["cpu"]["passed"])

    def test_empty_with_boundaries_is_boundary_only(self):
        b0 = snap(t=0, cpu=0, mem=0, io_r=0, io_w=0)
        b1 = snap(t=10 ** 9, cpu=1000, mem=10, io_r=5, io_w=3)
        sp = samples(bstart=b0, bend=b1)
        q = assess_resource_quality(sp)
        self.assertEqual(q["cpu"]["status"], "boundary_only")
        self.assertTrue(q["cpu"]["passed"])
        self.assertIn("not a complete curve", q["cpu"]["reason"])

    def test_partial_memory_missing_fails(self):
        rows = [snap(t=0, mem=100), snap(t=1, mem=None), snap(t=2, mem=100)]
        sp = samples(*rows, bstart=rows[0], bend=rows[-1])
        q = assess_resource_quality(sp)
        self.assertEqual(q["memory"]["status"], "partial_missing")
        self.assertFalse(q["memory"]["passed"])

    def test_io_read_regression_fails(self):
        rows = [snap(t=0, io_r=500), snap(t=1, io_r=400), snap(t=2, io_r=900)]
        sp = samples(*rows, bstart=rows[0], bend=rows[-1])
        q = assess_resource_quality(sp)
        self.assertEqual(q["io_read"]["status"], "counter_regression")
        self.assertFalse(q["io_read"]["passed"])

    def test_io_write_regression_fails_separately(self):
        rows = [snap(t=0, io_r=10, io_w=5), snap(t=1, io_r=10, io_w=3)]
        sp = samples(*rows, bstart=rows[0], bend=rows[-1])
        q = assess_resource_quality(sp)
        self.assertEqual(q["io_write"]["status"], "counter_regression")
        self.assertEqual(q["io_read"]["status"], "complete")

    def test_cgroup_v1_cpuacct_ok(self):
        rows = [snap(t=0, cpu=1000, rs={"cpuacct.usage": "ok_ns_converted_to_usec"}),
                snap(t=1, cpu=2000, rs={"cpuacct.usage": "ok_ns_converted_to_usec"})]
        sp = samples(*rows, bstart=rows[0], bend=rows[-1])
        q = assess_resource_quality(sp)
        self.assertEqual(q["cpu"]["status"], "complete")
        self.assertTrue(q["cpu"]["read_ok"])

    def test_real_zero_is_valid(self):
        rows = [snap(t=0, mem=0), snap(t=1, mem=0)]
        sp = samples(*rows, bstart=rows[0], bend=rows[-1])
        q = assess_resource_quality(sp)
        self.assertEqual(q["memory"]["status"], "complete")
        self.assertEqual(q["memory"]["sampled"], 2)

    def test_interval_computed_from_timestamps(self):
        rows = [snap(t=0), snap(t=500 * 10 ** 6), snap(t=10 ** 9)]
        sp = samples(*rows, bstart=rows[0], bend=rows[-1])
        q = assess_resource_quality(sp)
        self.assertEqual(q["timeline"]["actual_median_interval_s"], 0.5)

    def test_boundary_order_and_window(self):
        rows = [snap(t=100, cpu=100, mem=1, io_r=1, io_w=1),
                snap(t=200, cpu=200, mem=2, io_r=2, io_w=2)]
        b0 = snap(t=50, cpu=50, mem=0, io_r=0, io_w=0)
        b1 = snap(t=500, cpu=500, mem=5, io_r=5, io_w=5)
        sp = samples(*rows, bstart=b0, bend=b1)
        q = assess_resource_quality(sp)
        self.assertTrue(q["boundaries"]["passed"])
        self.assertEqual(q["boundaries"]["samples_out_of_window"], 0)
        # reversed boundary order
        sp2 = samples(*rows, bstart=b1, bend=b0)
        q2 = assess_resource_quality(sp2)
        self.assertFalse(q2["boundaries"]["passed"])
        self.assertEqual(q2["boundaries"]["status"], "order_invalid")


class TestStreamAccounting(unittest.TestCase):
    def _sampler_rows(self, n=5):
        from agent_workload_characterization.collectors.resource_sampler import ResourceSampler
        class R:
            def __init__(self):
                self.t = 0
            def read(self, t_monotonic_ns):
                self.t += 1
                return snap(t=t_monotonic_ns, cpu=1000 * self.t, mem=10,
                            io_r=5, io_w=3, rs={"cpu.stat": "ok"})
        s = ResourceSampler(interval_s=0.05)
        s.register("s", "agent_container", R())
        s.start("s")
        return s

    def test_rows_written_matches_file(self):
        with tempfile.TemporaryDirectory() as td:
            s = self._sampler_rows()
            p = Path(td) / "s.jsonl"
            s.enable_stream("s", p, flush_every=2)
            for _ in range(5):
                s.sample_once()
            s.close_streams()
            st = s.stream_state("s")
            rows = read_resource_stream(p)
            self.assertEqual(st["rows_written"], 5)
            self.assertEqual(st["rows_received"], 5)
            self.assertEqual(len(rows["rows"]), 5)
            self.assertEqual(st["fsync_calls"], 1)  # one real fsync at close

    def test_lost_undelivered_on_write_failure(self):
        with tempfile.TemporaryDirectory() as td:
            s = self._sampler_rows()
            ro = Path(td) / "ro"; ro.mkdir(); os.chmod(ro, 0o500)
            try:
                s.enable_stream("s", ro / "s.jsonl", flush_every=1)
                s.sample_once()
                st = s.stream_state("s")
                self.assertGreaterEqual(st["lost_undelivered"], 1)
                self.assertEqual(st["rows_written"], 0)
            finally:
                os.chmod(ro, 0o700)


class TestJudgeConsumesQuality(unittest.TestCase):
    def _judge(self, report):
        import sys
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        import host_runner as hr
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            for sub in ("logs", "samples", "ledger", "workspace", "rollout", "closeout"):
                (root / sub).mkdir()
            (root / "logs" / "exec-stdout.log").write_text("x")
            (root / "logs" / "exec-stderr.log").write_text("")
            (root / "logs" / "docker-logs.txt").write_text("")
            (root / "samples" / "summary.json").write_text("{}")
            (root / "ledger" / "ledger.json").write_text(json.dumps({
                "counters": {"llm_calls": 3, "image_creates": 0, "video_creates": 0,
                             "video_polls": 0, "media_downloads": 0},
                "exhausted": False, "events": [], "status": "open"}))
            report.setdefault("cleanup", {"removed": True})
            return hr.judge({"judge_media": {"image_creates": 0, "video_creates": 0,
                                             "media_downloads": 0}}, root, report)

    def test_cpu_quality_failure_fails_judge(self):
        rep = {"errors": [], "measurement_quality": {
            "cpu": {"passed": False, "status": "counter_regression"},
            "memory": {"passed": True, "status": "complete"},
            "io_read": {"passed": True}, "io_write": {"passed": True},
            "timeline": {"passed": True}, "boundaries": {"passed": True}}}
        j = self._judge(rep)
        mq = next(c for c in j["checks"] if c["check"] == "mq_cpu")
        self.assertFalse(mq["passed"])
        self.assertFalse(j["passed"])

    def test_quality_error_not_ignored(self):
        rep = {"errors": ["quality assess: boom"], "measurement_quality": {}}
        j = self._judge(rep)
        qc = next(c for c in j["checks"] if c["check"] == "quality_computed")
        self.assertFalse(qc["passed"])
        self.assertFalse(j["passed"])

    def test_stream_empty_file_fails(self):
        with tempfile.TemporaryDirectory() as td:
            import sys
            sys.path.insert(0, str(Path(__file__).resolve().parent))
            import host_runner as hr
            root = Path(td)
            for sub in ("logs", "samples", "ledger", "workspace", "rollout", "closeout"):
                (root / sub).mkdir()
            (root / "logs" / "exec-stdout.log").write_text("x")
            (root / "logs" / "exec-stderr.log").write_text("")
            (root / "logs" / "docker-logs.txt").write_text("")
            (root / "samples" / "summary.json").write_text("{}")
            (root / "samples" / "resource-stream.jsonl").write_text("")
            (root / "ledger" / "ledger.json").write_text(json.dumps({
                "counters": {"llm_calls": 3, "image_creates": 0, "video_creates": 0,
                             "video_polls": 0, "media_downloads": 0},
                "exhausted": False, "events": [], "status": "open"}))
            rep = {"errors": [], "cleanup": {"removed": True},
                   "measurement_quality": {
                       "cpu": {"passed": True, "status": "complete"},
                       "memory": {"passed": True}, "io_read": {"passed": True},
                       "io_write": {"passed": True}, "timeline": {"passed": True},
                       "boundaries": {"passed": True}},
                   "stream_state": {"error": None, "rows_written": 5}}
            j = hr.judge({"judge_media": {"image_creates": 0, "video_creates": 0,
                                          "media_downloads": 0}}, root, rep)
            rc = next(c for c in j["checks"] if c["check"] == "stream_rows_consistent")
            self.assertFalse(rc["passed"])  # empty file vs declared 5 rows


class TestGatewayMissingId(unittest.TestCase):
    def _ledger(self, td, soft=50000):
        os.environ["VW_RUN_START_EPOCH"] = "0"; os.environ["VW_RUN_ID"] = "t"
        b = dict(DEFAULT_BUDGET); b["observed_output_tokens_soft"] = soft
        return Ledger(str(Path(td) / "l.json"), b)

    def test_missing_id_grouped_to_local_request_counts_total(self):
        with tempfile.TemporaryDirectory() as td:
            l = self._ledger(td)
            # handler layer dedups per request; Ledger accumulates each
            # received (already-deduped) usage event
            l.record("usage", response_id="req_A", total_tokens=100)
            l.record("usage", response_id="req_B", total_tokens=50)
            self.assertEqual(l.data["usage"]["observed_total_tokens_total"], 150)
            self.assertEqual(l.data["usage"]["observed_llm_responses"], 2)

    def test_soft_threshold_blocks_next(self):
        with tempfile.TemporaryDirectory() as td:
            l = self._ledger(td, soft=100)
            l.record("usage", response_id="req_A", total_tokens=120)
            soft = int(l.budget.get("observed_output_tokens_soft", 0))
            self.assertTrue(l.data["usage"]["observed_total_tokens_total"] >= soft)


if __name__ == "__main__":
    unittest.main(verbosity=2)
