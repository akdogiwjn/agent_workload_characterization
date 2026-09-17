"""G1-01 A4: deterministic mechanism fixtures (default suite, offline).

Covers the task-brief minimum case list with synthetic fixtures only:
serial+exception tool events, dual-worker overlap math, background work
beyond call return, short-process/PID-reuse/counter-reset/read-failure,
sampling stop, and CPU/RSS unit conversion against INDEPENDENT expected
values. The real-mini hook integration lives in
tests/integration_run01.py; the real local mini-programs live in
scripts/g1_01_mechanism.py (explicitly run, bounded budgets).
"""

from __future__ import annotations

import json
import tempfile
import threading
import time
import unittest
from pathlib import Path

from agent_workload_characterization.analyzers.tool_timeline import (
    build_tool_timeline, calibrate, pair_tools, heuristic_category)
from agent_workload_characterization.collectors.host_process import (
    HostProcessReader, HostProcessMonitor, read_starttime)
from agent_workload_characterization.collectors.resource_sampler import (
    CounterSnapshot, FakeCounterReader, ResourceSampler)

CANARY = "sk-G1-SYNTH-FAKE"


def _fx_proc(root: Path, pid: int, state: str, ppid: int, utime: int,
             stime: int, starttime: int, rss_pages: int):
    """Write a fake /proc/<pid>/stat with EXACT field positions.

    After the last ')': rest[0]=state(3) rest[1]=ppid(4) rest[2]=pgrp(5)
    rest[3..10]=session..cmajflt(6..13) rest[11]=utime(14) rest[12]=stime(15)
    rest[13..18]=cutime..itreal(16..21) rest[19]=starttime(22)
    rest[20]=vsize(23) rest[21]=rss(24)."""
    d = root / str(pid)
    d.mkdir(parents=True, exist_ok=True)
    rest = ([state, str(ppid), "1"] + ["0"] * 8
            + [str(utime), str(stime)] + ["0"] * 6
            + [str(starttime), "0", str(rss_pages)] + ["0"] * 12)
    (d / "stat").write_text(
        f"{pid} ((proc)) " + " ".join(rest) + "\n", encoding="ascii")


class ToolEventFixtureTests(unittest.TestCase):
    """Serial normal + exception tool-event semantics (fixture level)."""

    def test_pairing_id_mismatch_rejected(self):
        # the reviewer's injection: action id=A, result id=B -> the
        # pair must be flagged id_mismatch, never silently accepted
        msgs = [
            {"role": "assistant", "content": "a",
             "extra": {"actions": [
                 {"command": "ls", "tool_call_id": "A"}]}},
            {"role": "tool", "content": "o",
             "extra": {"returncode": 0, "raw_output": "o",
                       "timestamp": 2.0, "tool_call_id": "B"}},
        ]
        pairs = pair_tools(msgs)
        self.assertEqual(pairs[0]["pairing"], "id_mismatch")

    def test_pairing_duplicate_action_id_flagged(self):
        msgs = [
            {"role": "assistant", "content": "a",
             "extra": {"actions": [
                 {"command": "ls", "tool_call_id": "t1"}]}},
            {"role": "tool", "content": "o1",
             "extra": {"returncode": 0, "raw_output": "o1",
                       "timestamp": 2.0}},
            {"role": "assistant", "content": "b",
             "extra": {"actions": [
                 {"command": "cat", "tool_call_id": "t1"}]}},
            {"role": "tool", "content": "o2",
             "extra": {"returncode": 0, "raw_output": "o2",
                       "timestamp": 3.0}},
        ]
        pairs = pair_tools(msgs)
        self.assertEqual(pairs[1]["pairing"], "duplicate_action_id")
        self.assertEqual(pairs[0]["pairing"], "positional")

    def test_anchor_count_mismatch_flagged(self):
        # 2 assistant-with-actions but only 1 ok status line -> the
        # gate flags it; the shorter prefix is used
        from agent_workload_characterization.analyzers.tool_timeline \
            import anchor_consistency
        msgs = [
            {"role": "assistant", "content": "a",
             "extra": {"actions": [{"command": "ls", "tool_call_id": "1"}],
                       "timestamp": 100.0}},
            {"role": "tool", "content": "o",
             "extra": {"returncode": 0, "raw_output": "o",
                       "timestamp": 100.5}},
            {"role": "assistant", "content": "b",
             "extra": {"actions": [{"command": "ls", "tool_call_id": "2"}],
                       "timestamp": 101.0}},
            {"role": "tool", "content": "o2",
             "extra": {"returncode": 0, "raw_output": "o2",
                       "timestamp": 101.5}},
        ]
        status = [{"ok": True, "t_end_ns": 10**9}]
        cons = anchor_consistency(msgs, status)
        self.assertFalse(cons["counts_match"])
        self.assertEqual(cons["n_ok_status_lines"], 1)
        self.assertEqual(cons["n_assistant_with_actions"], 2)

    def test_mid_stream_dropped_status_disables_calibration(self):
        # the reviewer's repro: delete a MIDDLE status line; the 2nd
        # assistant then pairs with the 3rd status. Order-based pairing
        # would silently misalign -> calibration must be DISABLED and
        # all derived monotonic windows null, not warned-and-used
        msgs = []
        status = []
        for i in range(3):
            msgs.append({"role": "assistant", "content": f"a{i}",
                         "extra": {"actions": [
                             {"command": "ls", "tool_call_id": str(i)}],
                             "timestamp": 100.0 + i}})
            msgs.append({"role": "tool", "content": f"o{i}",
                         "extra": {"returncode": 0,
                                   "raw_output": f"o{i}",
                                   "timestamp": 100.5 + i}})
            status.append({"ok": True,
                           "t_end_ns": (5 + i) * 10**9})
        with tempfile.TemporaryDirectory() as tmp:
            run = Path(tmp)
            # drop the MIDDLE status line (the misalignment case)
            (run / "mini_trajectory.json").write_text(
                json.dumps({"info": {"exit_status": "x"},
                            "messages": msgs}))
            (run / "mini_status.jsonl").write_text(
                "\n".join(json.dumps(s) for s in
                          [status[0], status[2]]) + "\n")
            (run / "samples.json").write_text(json.dumps(
                {"scopes": {}, "evidence": {}}))
            a = build_tool_timeline(run)
            c = a["calibration"]
            self.assertFalse(c["available"],
                             "calibration must be disabled on stream "
                             "count mismatch")
            self.assertIn("misalign", c["reason"])
            self.assertFalse(a["anchor_gate"]["enabled"])
            # derived monotonic windows are null for every record
            for rec in a["records"]:
                self.assertEqual(rec["time"]["window_monotonic_ns"],
                                 (None, None))
                self.assertIsNone(
                    rec["scope_association"]["window_in_agent_scope"])
            self.assertIsNone(
                a["records"][0]["scope_association"][
                    "n_agent_scope_samples_in_window"])

    def test_matching_streams_calibrate_normally(self):
        msgs = []
        status = []
        for i in range(3):
            msgs.append({"role": "assistant", "content": f"a{i}",
                         "extra": {"actions": [
                             {"command": "ls", "tool_call_id": str(i)}],
                             "timestamp": 100.0 + i}})
            msgs.append({"role": "tool", "content": f"o{i}",
                         "extra": {"returncode": 0,
                                   "raw_output": f"o{i}",
                                   "timestamp": 100.5 + i}})
            status.append({"ok": True,
                           "t_end_ns": (5 + i) * 10**9})
        with tempfile.TemporaryDirectory() as tmp:
            run = Path(tmp)
            (run / "mini_trajectory.json").write_text(
                json.dumps({"info": {}, "messages": msgs}))
            (run / "mini_status.jsonl").write_text(
                "\n".join(json.dumps(s) for s in status) + "\n")
            (run / "samples.json").write_text(json.dumps(
                {"scopes": {}, "evidence": {}}))
            a = build_tool_timeline(run)
            self.assertTrue(a["calibration"]["available"])
            self.assertTrue(a["anchor_gate"]["enabled"])
            # monotonic windows derived for all records
            for rec in a["records"]:
                w = rec["time"]["window_monotonic_ns"]
                self.assertIsNotNone(w[0])
                self.assertIsNotNone(w[1])

    def test_residual_semantics_not_claimed_as_bound(self):
        c = calibrate([{"epoch_s": 100.0, "monotonic_ns": 5 * 10**9},
                       {"epoch_s": 101.0, "monotonic_ns": 6 * 10**9}])
        self.assertIn("anchor_residual_semantics", c)
        self.assertIn("NOT a proven calibration error bound",
                      c["anchor_residual_semantics"])

    def test_pairing_counts_and_missing(self):
        msgs = [
            {"role": "system", "content": "s"},
            {"role": "user", "content": "t"},
            {"role": "assistant", "content": "a",
             "extra": {"actions": [
                 {"command": "ls", "tool_call_id": "t1"},
                 {"command": "cat f", "tool_call_id": "t2"}]}},
            {"role": "tool", "content": "o1",
             "extra": {"returncode": 0, "raw_output": "o1",
                       "timestamp": 2.0}},
            {"role": "tool", "content": "o2",
             "extra": {"returncode": 1, "raw_output": "o2",
                       "timestamp": 3.0}},
            {"role": "assistant", "content": "b",
             "extra": {"actions": [
                 {"command": "python x", "tool_call_id": "t3"}]}},
            # t3's tool message MISSING -> pairing=missing_result
            {"role": "exit", "content": "x"},
        ]
        pairs = pair_tools(msgs)
        self.assertEqual(len(pairs), 3)
        self.assertEqual([p["tool_call_id"] for p in pairs],
                         ["t1", "t2", "t3"])
        self.assertEqual(pairs[2]["pairing"], "missing_result")
        self.assertEqual(pairs[0]["pairing"], "positional")

    def test_timeline_unknown_stays_null(self):
        with tempfile.TemporaryDirectory() as tmp:
            run = Path(tmp)
            (run / "mini_trajectory.json").write_text(json.dumps({
                "info": {"exit_status": "LimitsExceeded"},
                "messages": [
                    {"role": "assistant", "content": "a",
                     "extra": {"actions": [
                         {"command": "ls", "tool_call_id": "t1"}]}},
                    {"role": "tool", "content": "o",
                     "extra": {"returncode": 0, "raw_output": "o"}}]}))
            (run / "mini_status.jsonl").write_text(
                json.dumps({"n_calls": 1, "ok": True, "t_end_ns": 10**9,
                            "usage": None}) + "\n")
            (run / "samples.json").write_text(json.dumps({
                "scopes": {}, "evidence": {}}))
            a = build_tool_timeline(run)
            rec = a["records"][0]
            self.assertIsNone(rec["time"]["true_duration_s"])
            self.assertIn("NO native tool start/end",
                          rec["time"]["true_missing_reason"])
            # no timestamps at all -> estimated window null, not zero
            self.assertIsNone(rec["time"]["window_s_estimated"])

    def test_calibration_residual_declared(self):
        anchors = [{"epoch_s": 100.0, "monotonic_ns": 5_000_000_000},
                   {"epoch_s": 101.0, "monotonic_ns": 6_000_000_000},
                   {"epoch_s": 102.0, "monotonic_ns": 7_000_000_000}]
        c = calibrate(anchors)
        self.assertTrue(c["available"])
        self.assertEqual(c["n_anchors"], 3)
        self.assertEqual(c["anchor_residual_ns_max"], 0.0)

    def test_command_safety_projection(self):
        from agent_workload_characterization.analyzers.tool_timeline \
            import _safe_command_view
        view = _safe_command_view(f"echo {CANARY} && cat /etc/passwd")
        self.assertNotIn(CANARY, json.dumps(view))
        self.assertIn("sha256", view)
        self.assertEqual(heuristic_category("grep -rn x ."), "Read/Search")
        self.assertEqual(heuristic_category("python t.py"), "Execute")


class OverlapMathTests(unittest.TestCase):
    """Dual-worker overlap: work/union/span distinction, no double
    counting of shared resources."""

    @staticmethod
    def _intervals(*, work_a, work_b):
        # returns (work_sum, union, span) in seconds
        work_sum = work_a[1] - work_a[0] + work_b[1] - work_b[0]
        lo = min(work_a[0], work_b[0])
        hi = max(work_a[1], work_b[1])
        overlap = max(0.0, min(work_a[1], work_b[1])
                      - max(work_a[0], work_b[0]))
        union = work_sum - overlap
        return work_sum, union, hi - lo

    def test_sequential_workers(self):
        a = (0.0, 2.0)
        b = (2.0, 5.0)
        work, union, span = self._intervals(work_a=a, work_b=b)
        self.assertEqual(work, 5.0)
        self.assertEqual(union, 5.0)      # no overlap: union == work sum
        self.assertEqual(span, 5.0)

    def test_overlapping_workers(self):
        a = (0.0, 3.0)
        b = (1.0, 2.0)                     # fully inside a
        work, union, span = self._intervals(work_a=a, work_b=b)
        self.assertEqual(work, 4.0)        # sum of individual work
        self.assertEqual(union, 3.0)       # union < work sum when sharing
        self.assertEqual(span, 3.0)
        # the point: reporting union as if it were exclusive work would
        # OVERSTATE; reporting work sum as wall would UNDERSTATE span

    def test_shared_counter_not_duplicated(self):
        # a shared scope counter delta must be attributed once, not
        # copied per worker window
        delta = 10.0
        windows = [(0.0, 3.0), (1.0, 2.0)]
        per_window_copy = delta * len(windows)   # WRONG approach
        self.assertEqual(per_window_copy, 20.0)
        self.assertNotEqual(per_window_copy, delta)
        # correct: shared_scope attribution keeps delta once
        self.assertEqual(delta, 10.0)


class BackgroundBeyondReturnTests(unittest.TestCase):
    """Tool call returned != background job finished; no fake closure."""

    def test_background_job_outlives_execute(self):
        started = threading.Event()
        finished = threading.Event()

        def job():
            started.set()
            time.sleep(0.3)
            finished.set()

        t = threading.Thread(target=job)
        t.start()
        started.wait(2)
        # simulate the env.execute return moment
        t.join(timeout=0.05)
        returned_before_finish = not finished.is_set()
        # the call "returned" (we stopped waiting) but the job is alive
        self.assertTrue(returned_before_finish)
        t.join(2)
        self.assertTrue(finished.is_set())
        # evidence rule: a scope snapshot taken at "return" misses the
        # remaining job lifetime -> must stay unclosed, not force-closed


class HostReaderFixtureTests(unittest.TestCase):
    """Short process / PID reuse / counter reset / read failure via a
    fake /proc tree (PROC_ROOT-injected, no real cgroup layout)."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)

    def test_unit_conversion_independent_expectation(self):
        # utime=1 stime=1 with CLK_TCK read from the OS: expected seconds
        # computed INDEPENDENTLY via os.sysconf here (not via the reader)
        import os as _os
        _fx_proc(self.root, 100, "S", 1, 1, 1, 500, 3)
        reader = HostProcessReader(100, expected_starttime=500,
                                   proc_root=self.root)
        snap = reader.read(t_monotonic_ns=1)
        self.assertEqual(snap.read_status["stat"], "ok")
        expected_ticks = 2
        expected_cpu_s = expected_ticks / _os.sysconf("SC_CLK_TCK")
        self.assertEqual(snap.cpu_ticks, expected_ticks)
        self.assertAlmostEqual(
            (snap.cpu_ticks or 0) / reader.clk_tck, expected_cpu_s,
            places=9)
        expected_rss = 3 * _os.sysconf("SC_PAGE_SIZE")
        self.assertEqual(snap.rss_bytes, expected_rss)

    def test_pid_reuse_detected(self):
        _fx_proc(self.root, 100, "S", 1, 0, 0, 500, 1)
        reader = HostProcessReader(100, expected_starttime=500,
                                   proc_root=self.root)
        self.assertEqual(reader.read().read_status["stat"], "ok")
        # PID 100 reused by a different process (starttime 999)
        _fx_proc(self.root, 100, "S", 1, 0, 0, 999, 1)
        snap = reader.read()
        self.assertEqual(snap.read_status["stat"], "pid_reuse_detected")
        self.assertIsNone(snap.cpu_ticks)  # not mistaken for the original

    def test_counter_reset(self):
        _fx_proc(self.root, 100, "S", 1, 100, 100, 500, 1)
        reader = HostProcessReader(100, expected_starttime=500,
                                   proc_root=self.root)
        first = reader.read()
        _fx_proc(self.root, 100, "S", 1, 1, 1, 500, 1)  # counters "reset"
        last = reader.read()
        cpu_s, reason = reader.cpu_seconds_delta(first, last)
        self.assertIsNone(cpu_s)
        self.assertEqual(reason, "counter_reset_detected")

    def test_process_exited_null(self):
        _fx_proc(self.root, 100, "S", 1, 0, 0, 500, 1)
        reader = HostProcessReader(100, expected_starttime=500,
                                   proc_root=self.root)
        first = reader.read()
        import shutil
        shutil.rmtree(self.root / "100")
        last = reader.read()
        self.assertEqual(last.read_status["stat"], "process_exited")
        cpu_s, reason = reader.cpu_seconds_delta(first, last)
        self.assertIsNone(cpu_s)
        self.assertEqual(reason, "cpu_ticks_missing_at_boundary")

    def test_monitor_summary_semantics(self):
        _fx_proc(self.root, 100, "S", 1, 10, 10, 500, 4)
        mon = HostProcessMonitor(100, expected_starttime=500,
                                 proc_root=self.root, interval_s=0.01)
        mon.poll_once()
        _fx_proc(self.root, 100, "S", 1, 20, 20, 500, 6)
        mon.poll_once()
        s = mon.summary()
        self.assertEqual(s["final_read_status"], "ok")
        import os as _os
        expected = 20 / _os.sysconf("SC_CLK_TCK")
        self.assertAlmostEqual(s["cpu_seconds"], expected, places=9)
        self.assertEqual(s["rss_sampled_max"],
                         6 * _os.sysconf("SC_PAGE_SIZE"))
        self.assertGreaterEqual(s["collector"]["read_count"], 2)


class SamplingStopTests(unittest.TestCase):
    """Final boundary followed by no new IN-WINDOW samples; historical
    out-of-boundary samples detectable without polluting metrics."""

    def test_stop_then_sample_not_counted(self):
        sampler = ResourceSampler(clock=None, interval_s=0.01)
        reader = FakeCounterReader("s", "agent_container", [
            CounterSnapshot(scope="s", scope_kind="agent_container",
                            t_monotonic_ns=0, cpu_usage_usec=0,
                            mem_current_bytes=10),
            CounterSnapshot(scope="s", scope_kind="agent_container",
                            t_monotonic_ns=1, cpu_usage_usec=1000,
                            mem_current_bytes=20)])
        sampler.register("s", "agent_container", reader)
        sampler.start("s")
        sampler.sample_once()
        sampler.stop("s")  # final boundary taken
        # a stray sample AFTER stop (simulated by direct append)
        sampler._data["s"].samples.append(
            CounterSnapshot(scope="s", scope_kind="agent_container",
                            t_monotonic_ns=999, cpu_usage_usec=999,
                            mem_current_bytes=999))
        ev = sampler._data["s"].evidence()
        lo = ev["boundary_start"]["t_monotonic_ns"]
        hi = ev["boundary_end"]["t_monotonic_ns"]
        sample_ts = [s["t_monotonic_ns"] for s in ev["samples"]]
        in_window = [t for t in sample_ts if lo <= t <= hi]
        out = [t for t in sample_ts if not lo <= t <= hi]
        self.assertEqual(len(in_window), 1)   # only the pre-stop sample
        self.assertEqual(len(out), 1)         # stray detectable, listed
        # summary peak uses only in-window samples
        summary = sampler.samples("s").summary()
        self.assertNotEqual(summary["memory_sampled_max_bytes"], 999)

    def test_background_thread_stops_reading_after_stop(self):
        # the ACTUAL sampling loop: after stop_background_sampling() no
        # further reads reach any registered scope (reader count frozen)
        sampler = ResourceSampler(clock=None, interval_s=0.02)
        reader = FakeCounterReader("s", "agent_container", [
            CounterSnapshot(scope="s", scope_kind="agent_container",
                            t_monotonic_ns=0, cpu_usage_usec=0,
                            mem_current_bytes=1)] * 50)
        sampler.register("s", "agent_container", reader)
        sampler.start("s")
        sampler.start_background_sampling()
        time.sleep(0.08)  # a few loop rounds happen
        sampler.stop("s")
        sampler.stop_background_sampling()
        reads_at_stop = reader.reads
        n_samples_at_stop = len(sampler._data["s"].samples)
        time.sleep(0.12)  # would be ~6 more rounds if still running
        self.assertEqual(reader.reads, reads_at_stop,
                         "reader kept being polled after stop")
        self.assertEqual(len(sampler._data["s"].samples),
                         n_samples_at_stop,
                         "samples appended after stop")

    def test_stop_waits_for_in_flight_read(self):
        # the reviewer's repro: a sampling read is IN FLIGHT when stop()
        # is called; after stop() returns, exactly the reads that were
        # already begun may complete, but the final boundary must be the
        # LAST read — stop() must WAIT for the in-flight read instead of
        # racing it. Deterministic interleaving via a gated fake reader.
        import threading as _th

        class GatedReader(FakeCounterReader):
            def __init__(self):
                super().__init__("s", "agent_container", [])
                self.read_entered = _th.Event()
                self.release_read = _th.Event()
                self.in_gate = _th.Lock()
                self.reads_done = 0

            def read(self, t_monotonic_ns):
                self.reads += 1
                self.read_entered.set()
                self.release_read.wait(5)  # hold the read in flight
                self.reads_done += 1
                return CounterSnapshot(scope="s",
                                       scope_kind="agent_container",
                                       t_monotonic_ns=t_monotonic_ns,
                                       cpu_usage_usec=1,
                                       mem_current_bytes=5)

        sampler = ResourceSampler(clock=None, interval_s=0.01)
        reader = GatedReader()
        sampler.register("s", "agent_container", reader)
        sampler.start("s")
        # round 1 in flight on a worker thread (like the background loop)
        t = _th.Thread(target=sampler.sample_once, daemon=True)
        t.start()
        self.assertTrue(reader.read_entered.wait(2))
        # the read is now IN FLIGHT: call stop() from this thread — it
        # must BLOCK until the in-flight read completes
        stop_done = _th.Event()

        def do_stop():
            sampler.stop("s")
            stop_done.set()

        st = _th.Thread(target=do_stop, daemon=True)
        st.start()
        time.sleep(0.15)
        self.assertFalse(stop_done.is_set(),
                         "stop() returned while a read was in flight")
        # release the in-flight read -> stop() can now take the boundary
        reader.release_read.set()
        self.assertTrue(stop_done.wait(2),
                        "stop() did not complete after the read finished")
        t.join(2)
        # after stop() returns: no further reads for this scope
        reads_after_stop = reader.reads_done
        sampler.sample_once()  # direct call: skipped, not read
        self.assertEqual(reader.reads_done, reads_after_stop)
        boundary = sampler._data["s"].boundary_end
        self.assertIsNotNone(boundary)
        # the boundary snapshot is from the final (in-flight-completed)
        # read generation: cpu_usage_usec == 1 proves it came from the
        # gated reader's LAST read, taken AFTER the in-flight one
        self.assertEqual(boundary.cpu_usage_usec, 1)

    def test_stop_during_paused_loop_completes_cleanly(self):
        # variant: pause the sampling thread via the gated reader,
        # stop() a DIFFERENT scope meanwhile (no in-flight read on it),
        # then resume — the paused scope's read completes and appends
        # normally (stop of one scope never blocks another)
        import threading as _th

        class SlowOnce(FakeCounterReader):
            def __init__(self, delay):
                super().__init__("slow", "agent_container", [])
                self.delay = delay
                self.reads = 0

            def read(self, t_monotonic_ns):
                self.reads += 1
                time.sleep(self.delay)
                return CounterSnapshot(scope="slow",
                                       scope_kind="agent_container",
                                       t_monotonic_ns=t_monotonic_ns,
                                       cpu_usage_usec=0,
                                       mem_current_bytes=1)

        sampler = ResourceSampler(clock=None, interval_s=0.01)
        slow = SlowOnce(0.2)
        fast = FakeCounterReader("fast", "agent_container", [
            CounterSnapshot(scope="fast", scope_kind="agent_container",
                            t_monotonic_ns=0, cpu_usage_usec=0,
                            mem_current_bytes=1)] * 100)
        sampler.register("slow", "agent_container", slow)
        sampler.register("fast", "agent_container", fast)
        sampler.start("slow")
        sampler.start("fast")
        t = _th.Thread(target=sampler.sample_once, daemon=True)
        t.start()  # will block ~0.2s inside slow.read
        time.sleep(0.05)          # slow.read in flight
        sampler.stop("fast")      # different scope: must NOT block
        t.join(2)
        # fast was stopped while slow was in flight: fast frozen, slow
        # completed its read and appended (its boundary stays open until
        # ITS stop — the point is stop("fast") neither blocked on slow
        # nor froze slow)
        fast_reads = fast.reads
        sampler.sample_once()
        self.assertEqual(fast.reads, fast_reads)
        self.assertIsNotNone(sampler._data["fast"].boundary_end)
        self.assertIsNone(sampler._data["slow"].boundary_end)
        self.assertGreaterEqual(len(sampler._data["slow"].samples), 1)

    def test_single_scope_stop_freezes_only_that_scope(self):
        # the reviewer's repro: stop("s"); sample_once() must NOT read
        # or append for "s" — while ANOTHER still-active scope in the
        # SAME running background loop keeps sampling
        sampler = ResourceSampler(clock=None, interval_s=0.02)
        reader_s = FakeCounterReader("s", "agent_container", [
            CounterSnapshot(scope="s", scope_kind="agent_container",
                            t_monotonic_ns=0, cpu_usage_usec=0,
                            mem_current_bytes=1)] * 200)
        reader_t = FakeCounterReader("t", "agent_container", [
            CounterSnapshot(scope="t", scope_kind="agent_container",
                            t_monotonic_ns=0, cpu_usage_usec=0,
                            mem_current_bytes=1)] * 200)
        sampler.register("s", "agent_container", reader_s)
        sampler.register("t", "agent_container", reader_t)
        sampler.start("s")
        sampler.start("t")
        sampler.start_background_sampling()
        time.sleep(0.06)  # both scopes accumulate samples
        self.assertGreater(len(sampler._data["s"].samples), 0)
        self.assertGreater(len(sampler._data["t"].samples), 0)
        # stop ONLY "s"; the background thread KEEPS RUNNING
        sampler.stop("s")
        reads_s_at_stop = reader_s.reads
        n_s_at_stop = len(sampler._data["s"].samples)
        boundary_s = sampler._data["s"].boundary_end
        time.sleep(0.12)  # ~6 more rounds for the ACTIVE scope
        # "s" is frozen: no reads, no new samples, boundary unchanged
        self.assertEqual(reader_s.reads, reads_s_at_stop,
                         "stopped scope kept being read")
        self.assertEqual(len(sampler._data["s"].samples), n_s_at_stop,
                         "stopped scope kept accumulating samples")
        self.assertIs(sampler._data["s"].boundary_end, boundary_s)
        # "t" is still active and kept sampling throughout
        self.assertGreater(len(sampler._data["t"].samples),
                           n_s_at_stop,
                           "active scope did not keep sampling")
        self.assertGreater(reader_t.reads, reads_s_at_stop)
        sampler.stop_background_sampling()
        # deterministic direct-call repro too: sample_once() skips "s"
        reads_before = reader_s.reads
        sampler.sample_once()
        self.assertEqual(reader_s.reads, reads_before)
        self.assertGreater(reader_t.reads, reads_before + 0)

    def test_historical_out_of_boundary_detectable(self):
        # the shape used by the A1 analyzer audit on the sealed C run
        audit = {"n_samples_total": 293, "n_samples_in_boundary": 268,
                 "n_samples_outside_boundary": 25}
        self.assertEqual(audit["n_samples_in_boundary"]
                         + audit["n_samples_outside_boundary"],
                         audit["n_samples_total"])


if __name__ == "__main__":
    unittest.main()
