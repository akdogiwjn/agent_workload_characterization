#!/usr/bin/env python3
"""Audit-5: REAL-ResourceSampler integration for the sample content digest.

The production closeout calls sample_content_digest(samples.samples) where
samples are CounterSnapshot objects (not dicts). This suite drives a REAL
sampler + synthetic reader + enable_stream, takes the actual in-memory
CounterSnapshot list, and proves the in-memory digest equals the digest
recomputed from the on-disk JSONL. No hand-written dict substitutes the
production path."""
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "gateway"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from agent_workload_characterization.collectors.resource_sampler import (
    CounterSnapshot, ResourceSampler, ScopeReader)
from agent_workload_characterization.collectors.execution_measurement import (
    sample_content_digest, validate_resource_stream, assess_resource_quality)
import host_runner as hr

SCOPE = "vw"
KIND = "agent_container"
RS = {"cpuacct.usage": "ok_ns_converted_to_usec",
      "memory.usage_in_bytes": "ok", "io.stat": "ok_summed_devices"}
FINAL_SRC = (Path(__file__).resolve().parents[1] / "evidence"
             / "audit-verify-133803")
N = 5


class SeqReader(ScopeReader):
    """Synthetic reader producing deterministic monotonic counters."""

    def __init__(self, scope, kind):
        self.scope = scope
        self.kind = kind
        self.i = 0

    def read(self, t_monotonic_ns):
        self.i += 1
        return CounterSnapshot(
            scope=self.scope, scope_kind=self.kind,
            t_monotonic_ns=t_monotonic_ns,
            cpu_usage_usec=1000 * self.i,
            mem_current_bytes=2048 * self.i,
            mem_peak_bytes=4096 * self.i,
            io_read_bytes=512 * self.i, io_write_bytes=256 * self.i,
            read_status=dict(RS))


def _read_jsonl(path):
    rows = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def _run_real_sampler(td, n=N, flush_every=2):
    s = ResourceSampler(interval_s=0.05)
    s.register(SCOPE, KIND, SeqReader(SCOPE, KIND))
    s.start(SCOPE)
    p = Path(td) / "resource-stream.jsonl"
    s.enable_stream(SCOPE, p, flush_every=flush_every)
    for _ in range(n):
        s.sample_once()
    s.stop(SCOPE)
    s.close_streams()
    return s, p


class TestRealSamplerDigest(unittest.TestCase):
    def test_real_counterSnapshot_memory_digest_equals_file_digest(self):
        with tempfile.TemporaryDirectory() as td:
            s, p = _run_real_sampler(td)
            mem = s.samples(SCOPE).samples
            # REAL production type, not dicts
            self.assertTrue(all(isinstance(x, CounterSnapshot) for x in mem))
            self.assertEqual(len(mem), N)
            # production closeout call (same as host_runner.py line ~827)
            mem_d = sample_content_digest(mem)  # must not raise
            file_rows = _read_jsonl(p)
            file_d = sample_content_digest(file_rows)
            self.assertEqual(mem_d["digest"], file_d["digest"])
            self.assertEqual(mem_d["n_samples"], file_d["n_samples"], N)
            # stream_state counters
            st = s.stream_state(SCOPE)
            self.assertEqual(st["rows_written"], N)
            self.assertEqual(st["rows_received"], N)
            self.assertEqual(st["rows_buffered"], 0)
            self.assertEqual(st["lost_undelivered"], 0)
            self.assertIsNone(st["error"])
            # boundaries saved in memory evidence
            bs = s.samples(SCOPE).boundary_start
            be = s.samples(SCOPE).boundary_end
            self.assertIsNotNone(bs)
            self.assertIsNotNone(be)
            self.assertGreater(be.t_monotonic_ns, bs.t_monotonic_ns)

    def test_file_cpu_change_breaks_digest(self):
        with tempfile.TemporaryDirectory() as td:
            s, p = _run_real_sampler(td)
            mem_d = sample_content_digest(s.samples(SCOPE).samples)
            rows = _read_jsonl(p)
            rows[2]["cpu_usage_usec"] += 1
            self.assertNotEqual(mem_d["digest"],
                                 sample_content_digest(rows)["digest"])

    def test_time_status_change_and_swap_break_digest(self):
        with tempfile.TemporaryDirectory() as td:
            s, p = _run_real_sampler(td)
            mem_d = sample_content_digest(s.samples(SCOPE).samples)
            rows = _read_jsonl(p)
            r1 = [dict(r) for r in rows]
            r1[1]["t_monotonic_ns"] += 10 ** 9
            self.assertNotEqual(mem_d["digest"], sample_content_digest(r1)["digest"])
            r2 = [dict(r) for r in rows]
            r2[1]["read_status"] = dict(RS)
            r2[1]["read_status"]["io.stat"] = "not_found"
            self.assertNotEqual(mem_d["digest"], sample_content_digest(r2)["digest"])
            r3 = [dict(r) for r in rows]
            r3[0], r3[1] = r3[1], r3[0]
            self.assertNotEqual(mem_d["digest"], sample_content_digest(r3)["digest"])

    def test_read_status_key_order_irrelevant(self):
        with tempfile.TemporaryDirectory() as td:
            s, p = _run_real_sampler(td)
            rows = _read_jsonl(p)
            base = sample_content_digest(rows)["digest"]
            reordered = []
            for r in rows:
                r2 = dict(r)
                ks = list(r2["read_status"].keys())[::-1]
                r2["read_status"] = {k: r2["read_status"][k] for k in ks}
                reordered.append(r2)
            self.assertEqual(base, sample_content_digest(reordered)["digest"])

    def test_null_vs_missing_field_not_equivalent(self):
        a = {"schema": "resource-stream-v1", "scope": SCOPE, "scope_kind": KIND,
             "t_monotonic_ns": 1, "cpu_usage_usec": 1, "mem_current_bytes": None,
             "mem_peak_bytes": None, "io_read_bytes": 0, "io_write_bytes": 0,
             "read_status": dict(RS)}
        b = dict(a)
        del b["mem_current_bytes"]
        self.assertNotEqual(sample_content_digest([a])["digest"],
                            sample_content_digest([b])["digest"])

    def test_invalid_values_rejected_not_placeholder(self):
        base = {"schema": "resource-stream-v1", "scope": SCOPE, "scope_kind": KIND,
                "t_monotonic_ns": 1, "cpu_usage_usec": 1, "mem_current_bytes": 1,
                "mem_peak_bytes": None, "io_read_bytes": 0, "io_write_bytes": 0,
                "read_status": dict(RS)}
        for bad in (True, float("nan"), float("inf"), -1):
            r = dict(base)
            r["cpu_usage_usec"] = bad
            with self.assertRaises(ValueError):
                sample_content_digest([r])

    def test_missing_schema_rejected_by_validator_not_patched(self):
        with tempfile.TemporaryDirectory() as td:
            s, p = _run_real_sampler(td)
            rows = _read_jsonl(p)
            del rows[1]["schema"]
            bad = Path(td) / "bad.jsonl"
            bad.write_text("".join(json.dumps(r) + "\n" for r in rows))
            v = validate_resource_stream(bad)
            self.assertEqual(v["valid_count"], N - 1)
            self.assertIn("schema_mismatch",
                          ";".join(x["reason"] for x in v["invalid"]))
            # digest of the surviving rows still well-defined
            self.assertEqual(sample_content_digest(v["valid_rows"])["n_samples"], N - 1)

    def test_empty_short_task_digest_consistent_and_boundary_limited(self):
        with tempfile.TemporaryDirectory() as td:
            s = ResourceSampler(interval_s=0.5)
            s.register(SCOPE, KIND, SeqReader(SCOPE, KIND))
            s.start(SCOPE)
            p = Path(td) / "s.jsonl"
            s.enable_stream(SCOPE, p)
            # no sample_once at all: boundary-only short task
            s.stop(SCOPE)
            s.close_streams()
            mem = s.samples(SCOPE).samples
            self.assertEqual(len(mem), 0)
            self.assertEqual(sample_content_digest(mem)["n_samples"], 0)
            # sink opens lazily; an empty stream may leave no file — 0 rows both ways
            if p.exists():
                self.assertEqual(sample_content_digest(_read_jsonl(p))["n_samples"], 0)
            else:
                self.assertEqual(sample_content_digest([])["n_samples"], 0)
            q = assess_resource_quality(
                stream_rows=[], boundary_start=s.samples(SCOPE).boundary_start,
                boundary_end=s.samples(SCOPE).boundary_end,
                expected_scope=SCOPE, expected_scope_kind=KIND,
                interval_target_s=0.5)
            cov = q["coverage"]
            self.assertEqual(cov["status"], "boundary_only_limited")


class TestJudgeDigestContract(unittest.TestCase):
    def _fixture(self, td, *, report):
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
        return root

    def _full_report(self, rows, bounds, interval=0.5):
        q = assess_resource_quality(
            stream_rows=rows, boundary_start=hr.CounterSnapshot(**bounds[0]),
            boundary_end=hr.CounterSnapshot(**bounds[1]),
            expected_scope=SCOPE, expected_scope_kind=KIND,
            interval_target_s=interval)
        ss = {"rows_received": len(rows), "rows_written": len(rows),
              "rows_buffered": 0, "lost_undelivered": 0, "error": None}
        return {"errors": [], "cleanup": {"removed": True},
                "measurement_quality": q,
                "resource_samples": {"n_samples": len(rows)},
                "stream_state": ss, "sample_interval_s": interval}

    def _bounds(self):
        b0 = {"scope": SCOPE, "scope_kind": KIND, "t_monotonic_ns": 0,
              "cpu_usage_usec": 1000, "mem_current_bytes": 1000,
              "mem_peak_bytes": None, "io_read_bytes": 100,
              "io_write_bytes": 50, "read_status": dict(RS)}
        b1 = {"scope": SCOPE, "scope_kind": KIND, "t_monotonic_ns": 2 * 10 ** 9,
              "cpu_usage_usec": 3000, "mem_current_bytes": 1002,
              "mem_peak_bytes": 2000, "io_read_bytes": 102,
              "io_write_bytes": 52, "read_status": dict(RS)}
        return [b0, b1]

    def _rows(self):
        rows = []
        for i in range(3):
            rows.append({"schema": "resource-stream-v1", "scope": SCOPE,
                         "scope_kind": KIND, "t_monotonic_ns": i * 10 ** 9,
                         "cpu_usage_usec": 1000 + i * 1000,
                         "mem_current_bytes": 1000 + i, "mem_peak_bytes": None,
                         "io_read_bytes": 100 + i, "io_write_bytes": 50 + i,
                         "read_status": dict(RS)})
        return rows

    def _final(self, root):
        out = root / "closeout" / "merge-agent-output"
        out.mkdir(parents=True, exist_ok=True)
        finals = list(FINAL_SRC.rglob("final.mp4"))
        shutil.copy2(finals[0], out / "final.mp4")

    def test_new_contract_missing_digest_fails_judge(self):
        td = tempfile.mkdtemp(prefix="vw-a5-")
        try:
            rows = self._rows()
            rep = self._full_report(rows, self._bounds())
            # NOTE: sample_content_summary intentionally absent
            root = self._fixture(td, report=rep)
            (root / "samples" / "resource-stream.jsonl").write_text(
                "".join(json.dumps(r) + "\n" for r in rows))
            (root / "samples" / "boundaries.json").write_text(
                json.dumps({"boundary_start": self._bounds()[0],
                            "boundary_end": self._bounds()[1]}))
            self._final(root)
            j = hr.judge({"judge_media": {"image_creates": 0, "video_creates": 0,
                                          "media_downloads": 0}}, root, rep)
            self.assertFalse(j["passed"])
            c = next(c for c in j["checks"] if c["check"] == "content_digest_consistent")
            self.assertFalse(c["passed"])
            self.assertIn("missing", c["detail"])
        finally:
            shutil.rmtree(td, ignore_errors=True)

    def test_legacy_without_digest_and_interval_stays_unknown_pass(self):
        td = tempfile.mkdtemp(prefix="vw-a5-")
        try:
            rows = self._rows()
            rep = self._full_report(rows, self._bounds())
            # legacy: no sample_interval_s, no content summary
            rep.pop("sample_interval_s")
            root = self._fixture(td, report=rep)
            (root / "samples" / "resource-stream.jsonl").write_text(
                "".join(json.dumps(r) + "\n" for r in rows))
            (root / "samples" / "boundaries.json").write_text(
                json.dumps({"boundary_start": self._bounds()[0],
                            "boundary_end": self._bounds()[1]}))
            self._final(root)
            j = hr.judge({"judge_media": {"image_creates": 0, "video_creates": 0,
                                          "media_downloads": 0}}, root, rep)
            c = next(c for c in j["checks"] if c["check"] == "content_digest_consistent")
            self.assertTrue(c["passed"])
            self.assertIn("legacy", c["detail"].lower())
        finally:
            shutil.rmtree(td, ignore_errors=True)

    def test_new_contract_with_matching_digest_passes(self):
        td = tempfile.mkdtemp(prefix="vw-a5-")
        try:
            rows = self._rows()
            rep = self._full_report(rows, self._bounds())
            rep["sample_content_summary"] = sample_content_digest(rows)
            root = self._fixture(td, report=rep)
            (root / "samples" / "resource-stream.jsonl").write_text(
                "".join(json.dumps(r) + "\n" for r in rows))
            (root / "samples" / "boundaries.json").write_text(
                json.dumps({"boundary_start": self._bounds()[0],
                            "boundary_end": self._bounds()[1]}))
            self._final(root)
            j = hr.judge({"judge_media": {"image_creates": 0, "video_creates": 0,
                                          "media_downloads": 0}}, root, rep)
            c = next(c for c in j["checks"] if c["check"] == "content_digest_consistent")
            self.assertTrue(c["passed"])
        finally:
            shutil.rmtree(td, ignore_errors=True)


if __name__ == "__main__":
    unittest.main(verbosity=2)
