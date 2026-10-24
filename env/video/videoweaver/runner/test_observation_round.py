#!/usr/bin/env python3
"""Targeted offline tests for the observation/collection round.

No real API, no credentials, no containers for these unit tests (gateway usage
logic is exercised through the Ledger + parser units; a separate offline
container check covers the production mounting)."""
import json
import os
import sys
import tempfile
import threading
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "gateway"))

from agent_workload_characterization.collectors.resource_sampler import (
    ResourceSampler, CounterSnapshot, ScopeReader, ScopeSamples)
from agent_workload_characterization.collectors.execution_measurement import (
    assess_resource_quality, read_resource_stream, directory_footprint_snapshot)
import gateway as G
from gateway import Ledger, DEFAULT_BUDGET, SseParser


class FakeReader(ScopeReader):
    def __init__(self, scope, kind):
        self.scope = scope; self.kind = kind; self.t = 0

    def read(self, t_monotonic_ns):
        self.t += 1
        return CounterSnapshot(scope=self.scope, scope_kind=self.kind,
                               t_monotonic_ns=t_monotonic_ns,
                               cpu_usage_usec=1000 * self.t,
                               mem_current_bytes=2048,
                               io_read_bytes=512, io_write_bytes=256,
                               read_status={"cpu.stat": "ok", "memory.current": "ok"})


class TestStreamSink(unittest.TestCase):
    def _sampler(self):
        s = ResourceSampler(interval_s=0.05)
        s.register("s", "agent_container", FakeReader("s", "agent_container"))
        s.start("s")
        return s

    def test_append_writes_jsonl(self):
        with tempfile.TemporaryDirectory() as td:
            s = self._sampler()
            p = Path(td) / "resource-stream.jsonl"
            s.enable_stream("s", p, flush_every=2)
            for _ in range(5):
                s.sample_once()
            s.close_streams()
            rows = read_resource_stream(p)
            self.assertEqual(rows["status"], "ok")
            self.assertEqual(len(rows["rows"]), 5)
            self.assertEqual(rows["rows"][0]["schema"], "resource-stream-v1")
            self.assertIn("t_monotonic_ns", rows["rows"][0])
            st = s.stream_state("s")
            self.assertEqual(st["rows_written"], 5)

    def test_write_failure_exposed(self):
        with tempfile.TemporaryDirectory() as td:
            s = self._sampler()
            ro = Path(td) / "ro"
            ro.mkdir(); os.chmod(ro, 0o500)
            try:
                s.enable_stream("s", ro / "stream.jsonl", flush_every=1)
                s.sample_once()
                st = s.stream_state("s")
                self.assertIsNotNone(st["error"])
            finally:
                os.chmod(ro, 0o700)

    def test_truncated_last_line(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "stream.jsonl"
            p.write_text('{"a":1}\n{"b":2}\n{"c":3')  # final line cut (no trailing newline)
            rows = read_resource_stream(p)
            self.assertTrue(rows["truncated_tail"])
            self.assertEqual(len(rows["rows"]), 2)


class TestQualityAssess(unittest.TestCase):
    def _samples(self, regression=False, order_broken=False):
        sp = ScopeSamples(scope="s", scope_kind="agent_container", interval_target_s=0.5)
        snaps = []
        ts = [1000, 1001, 1002, 1003] if not order_broken else [1003, 1002, 1001, 1000]
        cpus = [1000, 2000, 3000, 4000] if not regression else [4000, 3000, 2000, 1000]
        for i in range(4):
            snap = CounterSnapshot(scope="s", scope_kind="agent_container",
                                   t_monotonic_ns=ts[i], cpu_usage_usec=cpus[i],
                                   mem_current_bytes=2048, io_read_bytes=512, io_write_bytes=256,
                                   read_status={"cpu.stat": "ok", "memory.current": "ok",
                                              "io.stat": "ok_summed_devices"})
            snaps.append(snap)
        sp.boundary_start = snaps[0]; sp.boundary_end = snaps[-1]
        sp.samples = snaps
        return sp

    def test_quality_ok(self):
        sp = self._samples()
        q = assess_resource_quality(sp)
        self.assertEqual(q["cpu"]["status"], "complete")
        self.assertTrue(q["timeline"]["passed"])
        self.assertTrue(q["boundaries"]["passed"])

    def test_quality_counter_regression(self):
        sp = self._samples(regression=True)
        q = assess_resource_quality(sp)
        self.assertEqual(q["cpu"]["status"], "counter_regression")

    def test_quality_order_violation(self):
        sp = self._samples(order_broken=True)
        q = assess_resource_quality(sp)
        self.assertEqual(q["timeline"]["status"], "order_violation")


class TestDirectorySnapshot(unittest.TestCase):
    def test_missing_and_symlink_and_overlap(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            real = root / "real"; real.mkdir(); (real / "a.bin").write_bytes(b"x" * 100)
            link = root / "link"; link.symlink_to(real)
            specs = [
                {"role": "missing", "path": str(root / "nope")},
                {"role": "symlink", "path": str(link)},
                {"role": "real", "path": str(real)},
                {"role": "overlap", "path": str(real / "a.bin")},
            ]
            snap = directory_footprint_snapshot(specs, timeout_s=1.0)
            by = {e["role"]: e for e in snap["entries"]}
            self.assertEqual(by["missing"]["status"], "path_missing")
            self.assertEqual(by["symlink"]["status"], "symlink_not_followed")
            self.assertEqual(by["real"]["bytes"], 100)
            self.assertEqual(by["overlap"]["status"], "overlapping_path_excluded")


class TestGatewayUsage(unittest.TestCase):
    def _ledger(self, td, soft=50000):
        os.environ["VW_RUN_START_EPOCH"] = "0"; os.environ["VW_RUN_ID"] = "t"
        b = dict(DEFAULT_BUDGET); b["observed_output_tokens_soft"] = soft
        return Ledger(str(Path(td) / "l.json"), b)

    def test_non_sse_total_counts_soft_not_output_only(self):
        with tempfile.TemporaryDirectory() as td:
            l = self._ledger(td)
            l.record("usage", response_id=None, total_tokens=100,
                     output_tokens=20, cached_input_tokens=80)
            self.assertEqual(l.data["usage"]["observed_total_tokens_total"], 100)
            self.assertEqual(l.data["usage"]["observed_output_tokens_total"], 20)

    def test_unattributed_not_accumulated(self):
        with tempfile.TemporaryDirectory() as td:
            l = self._ledger(td)
            l.record("usage_unattributed", total_tokens=999, output_tokens=9)
            self.assertEqual(l.data["usage"]["observed_total_tokens_total"], 0)

    def test_usage_without_id_not_merged(self):
        with tempfile.TemporaryDirectory() as td:
            l = self._ledger(td)
            l.record("usage", response_id="r1", total_tokens=50)
            l.record("usage", response_id=None, total_tokens=30)  # distinct, not merged into r1
            self.assertEqual(l.data["usage"]["observed_total_tokens_total"], 80)
            self.assertEqual(l.data["usage"]["observed_llm_responses"], 2)

    def test_soft_threshold_crossed_next_forward(self):
        with tempfile.TemporaryDirectory() as td:
            l = self._ledger(td, soft=100)
            l.record("usage", response_id="r1", total_tokens=120)
            soft = int(l.budget.get("observed_output_tokens_soft", 0))
            self.assertTrue(l.data["usage"]["observed_total_tokens_total"] >= soft)


class TestSseParserExtra(unittest.TestCase):
    def test_completed_with_nested_usage(self):
        p = SseParser()
        for l in ['data: {"type":"response.completed","response":{"id":"r9","status":"completed","usage":{"input_tokens":5,"output_tokens":3,"total_tokens":8}}}', ""]:
            p.feed_line(l)
        ev = p.flush()
        self.assertEqual(len(ev), 1)
        self.assertEqual(json.loads(ev[0]["data"])["response"]["status"], "completed")

    def test_incomplete_status(self):
        p = SseParser()
        for l in ['data: {"type":"response.incomplete","response":{"id":"r1","status":"incomplete"}}', ""]:
            p.feed_line(l)
        ev = p.flush()
        self.assertEqual(ev[0]["data"].count("incomplete") > 0, True)


if __name__ == "__main__":
    unittest.main(verbosity=2)
