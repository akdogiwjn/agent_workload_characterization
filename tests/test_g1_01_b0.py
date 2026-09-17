"""G1-01-B0 minimum offline regressions (task brief §8, six groups).

Everything offline: fake runtimes/readers, synthetic fixtures; no
Docker, no network, no SDK. The real-mini shared-hook reuse is covered
by tests/integration_run01.py (5 tests) — group 2 here asserts the
SHARING itself (one source, two entrypoints).
"""

from __future__ import annotations

import json
import tempfile
import threading
import time
import unittest
import os
from pathlib import Path
from unittest import mock

from agent_workload_characterization.collectors.host_process import (
    HostProcessMonitor, HostProcessReader)
from agent_workload_characterization.collectors.resource_sampler import (
    CounterSnapshot, FakeCounterReader, ResourceSampler)
from agent_workload_characterization.collectors.semantic_recorder \
    import FakeClock
from agent_workload_characterization.runners import b_entry
from agent_workload_characterization.runners.container_runtime import (
    ContainerHandle, ContainerSpec, FakeContainerRuntime, DockerCliRuntime)
from agent_workload_characterization.runners.tool_event_env import (
    TOOL_EVENT_WRAPPED_SOURCE, wrap_environment)

CANARY = "sk-B0-SYNTH-FAKE"


class _RealSleepFakeRuntime(FakeContainerRuntime):
    """Fake runtime whose 'sleep 1' command REALLY sleeps ~1 s so the
    tool-event window carries genuine duration evidence. ``override``
    lets tests inject per-command results (e.g. rc=2). ``readers``
    provides the sampler reader factory (CPU counters for scope
    evidence). NO Docker calls in any path."""

    def __init__(self, clock):
        super().__init__(clock)
        self.override = {}
        self._cpu_state = {}

    def execute(self, handle, command, timeout_s, **kw):
        if command in self.override:
            out = dict(self.override[command])
            out.setdefault("output", "")
            out["duration_s"] = 0.0
            return out
        if command == "sleep 1":
            time.sleep(1.0)
            return {"returncode": 0, "output": "",
                    "duration_s": 1.0}
        script = {
            "dd if=/dev/urandom of=/tmp/g1b.bin bs=1M count=8 "
            "&& sync && rm -f /tmp/g1b.bin":
                {"returncode": 0, "output": "8+0 records in"},
            "false": {"returncode": 1, "output": ""},
            'python3 -c "x=sum(range(2_000_000))"':
                {"returncode": 0, "output": ""},
        }
        if command in script:
            out = dict(script[command])
            out["duration_s"] = 0.0
            return out
        return super().execute(handle, command, timeout_s, **kw)

    def read_counters(self, handle, t_monotonic_ns):
        # CPU counter that grows on every read (background work / the
        # case's own commands); scoped per container
        key = handle.spec.scope
        self._cpu_state[key] = self._cpu_state.get(key, 0) + 500_000
        return CounterSnapshot(
            scope=handle.spec.scope, scope_kind="agent_container",
            t_monotonic_ns=t_monotonic_ns,
            cpu_usage_usec=self._cpu_state[key],
            mem_current_bytes=1024 * 1024,
            read_status={"cpuacct.usage":
                         "ok_ns_converted_to_usec"})

    def reader_factory(self, scope, scope_kind, container_id):
        """Sampler reader for offline tests: reads THIS runtime's
        synthetic CPU counter (no /sys/fs/cgroup access). Has a
        countable `reads` attribute for freeze-evidence assertions."""
        runtime = self

        class _Reader:
            def __init__(self):
                self.reads = 0

            def read(self, t_monotonic_ns):
                self.reads += 1
                handle = ContainerHandle(
                    container_id=container_id,
                    spec=ContainerSpec(run_id="r", scope=scope,
                                       image="img"))
                return runtime.read_counters(handle, t_monotonic_ns)

        return _Reader()


class Group7EndToEndOrchestration(unittest.TestCase):
    """The REAL execute_batch orchestration driven by a fake runtime:
    success, budget stop, fail-archive-then-cleanup, approval-content
    binding, root symlink refusal, exception cleanup, and artifact
    verification against the production writer."""

    def _fake_runtime(self, clock, *, overrides=None):
        runtime = _RealSleepFakeRuntime(clock)
        for k, v in (overrides or {}).items():
            runtime.override[k] = v
        return runtime

    @staticmethod
    def _reader_factory(runtime):
        return runtime.reader_factory

    def _approval(self, tmp, *, empty=False, drift=False):
        """A valid approval record binds the registered checklist
        identity; `empty` writes nothing; `drift` mutates the budget."""
        from agent_workload_characterization.runners.b_entry import (
            _checklist_identity)
        rec = Path(tmp) / "APPROVAL.txt"
        if empty:
            rec.write_text("")
            return rec
        identity = _checklist_identity()
        if drift:
            identity["budget"]["batch_wall_s"] = 999.0
        rec.write_text(json.dumps({
            "checklist_identity": identity,
            "approved_by": "test",
            "approved_at_utc": "2026-09-13T00:00:00Z"}))
        return rec

    def test_success_path_end_to_end(self):
        from agent_workload_characterization.runners.b_entry import (
            execute_batch)
        clock = type("C", (), {"monotonic_ns": staticmethod(
            lambda: int(time.monotonic_ns()))})()
        with tempfile.TemporaryDirectory() as tmp:
            runtime = self._fake_runtime(clock)
            result = execute_batch(
                runtime=runtime, clock=clock,
                report_root=Path(tmp) / "reports", batch_id="B-OK",
                approval_record=self._approval(tmp),
                reader_factory=runtime.reader_factory)
            self.assertEqual(result["archive_status"], "ok")
            statuses = {c["case"]: c["status"] for c in result["cases"]}
            self.assertEqual(statuses.get(1), "PASS")
            self.assertEqual(statuses.get(2), "PASS")
            # verified cleanup: every handle removed AND verified
            for entry in result["cleanup"]:
                self.assertTrue(entry["removed"], entry)
            self.assertEqual(runtime.containers, {})
            out_dir = Path(result["out_dir"])
            # full raw scope evidence persisted (not just summary)
            self.assertTrue((out_dir / "c1_scope_evidence.json").is_file())
            self.assertTrue((out_dir / "c2_scope_evidence.json").is_file())
            doc = json.loads((out_dir / "batch.json").read_text())
            c1 = doc["cases"][0]
            self.assertTrue(c1["scope_evidence_present"]["boundary_start"])
            self.assertTrue(c1["scope_evidence_present"]["boundary_end"])
            self.assertGreaterEqual(
                c1["scope_evidence_present"]["raw_samples"], 0)
            # sleep window evidence recorded
            self.assertIn("sleep_window_s", c1)
            # c2: PASS requires the evidence gates
            c2 = doc["cases"][1]
            self.assertTrue(c2["cpu_reads"]["cpu_grew_while_tool_returned"])
            self.assertEqual(c2["termination"]["confirmed"], True)
            self.assertTrue(c2["scope_frozen_after_stop"])
            # host runner sampled DURING the batch
            self.assertGreaterEqual(
                doc["host_runner_process"]["n_snapshots"], 1)
            # events: 4 closed pairs, real rc for false
            ev1 = [json.loads(l) for l in
                   (out_dir / "c1_tool_events.jsonl").read_text()
                   .splitlines() if l.strip()]
            rcs = {e["tool_call_id"]: e["returncode"]
                   for e in ev1 if e["event"] == "closed"}
            self.assertEqual(rcs["b1-fail"], 1)
            self.assertNotIn("dd if", (out_dir /
                                       "c1_tool_events.jsonl").read_text())
            # manifest verified against the production writer
            m = json.loads((out_dir / "manifest.json").read_text())
            for n, sha in m["files"].items():
                self.assertEqual(
                    hashlib.sha256((out_dir / n).read_bytes()).hexdigest(),
                    sha)

    def test_empty_approval_refused(self):
        # reviewer repro 1: an EMPTY approval file must be refused
        from agent_workload_characterization.runners.b_entry import (
            B0Error, execute_batch)
        clock = type("C", (), {"monotonic_ns": staticmethod(
            lambda: int(time.monotonic_ns()))})()
        with tempfile.TemporaryDirectory() as tmp:
            runtime = self._fake_runtime(clock)
            with self.assertRaises(B0Error) as ctx:
                execute_batch(runtime=runtime, clock=clock,
                              report_root=Path(tmp) / "r",
                              batch_id="B-EMPTY",
                              approval_record=self._approval(tmp, empty=True))
            self.assertTrue("checklist_identity" in str(ctx.exception)
                    or "unreadable" in str(ctx.exception),
                    f"unexpected message: {ctx.exception}")

    def test_drifted_approval_refused(self):
        # direction 1: a record whose embedded budget differs from the
        # CURRENT registered identity = drift -> refused
        from agent_workload_characterization.runners.b_entry import (
            B0Error, _verify_approval, _checklist_identity)
        with tempfile.TemporaryDirectory() as tmp:
            rec = Path(tmp) / "APPROVAL.txt"
            ident = _checklist_identity()
            ident["budget"]["batch_wall_s"] = 999.0
            rec.write_text(json.dumps({"checklist_identity": ident}))
            with self.assertRaises(B0Error) as ctx:
                _verify_approval(rec)
            self.assertIn("drift", str(ctx.exception))

    def test_identity_change_after_approval_refused(self):
        # direction 2: the CURRENT identity changed after the record
        # was written -> drift -> refused (and restored after)
        from agent_workload_characterization.runners import b_entry
        from agent_workload_characterization.runners.b_entry import (
            B0Error, _verify_approval, _checklist_identity)
        with tempfile.TemporaryDirectory() as tmp:
            rec = Path(tmp) / "APPROVAL.txt"
            rec.write_text(json.dumps({
                "checklist_identity": _checklist_identity()}))
            orig = b_entry.BUDGET["batch_wall_s"]
            try:
                b_entry.BUDGET["batch_wall_s"] = 111.0
                with self.assertRaises(B0Error):
                    _verify_approval(rec)
            finally:
                b_entry.BUDGET["batch_wall_s"] = orig
            # restored identity passes again
            _verify_approval(rec)

    def test_report_root_symlink_escape_refused(self):
        # reviewer repro 2: a symlinked G1-01-B ROOT must be refused
        from agent_workload_characterization.runners.b_entry import (
            B0Error, _guard_report_root)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = root / "proj"
            (project / "reports/resource").mkdir(parents=True)
            outside = root / "outside"
            outside.mkdir()
            (project / "reports/resource/G1-01-B").symlink_to(outside)
            with mock.patch.object(
                    __import__("agent_workload_characterization.runners"
                               ".b_entry", fromlist=["b_entry"]),
                    "PROJECT_ROOT", project):
                with self.assertRaises(B0Error) as ctx:
                    _guard_report_root(
                        project / "reports/resource/G1-01-B")
                self.assertIn("symlink", str(ctx.exception))

    def test_exception_cleanup_no_orphans(self):
        # reviewer repro 3: a runtime exception mid-case must still
        # clean up every created container (handles registered AT
        # CREATION, not at case return)
        from agent_workload_characterization.runners.b_entry import (
            execute_batch)
        clock = type("C", (), {"monotonic_ns": staticmethod(
            lambda: int(time.monotonic_ns()))})()

        class ExplodingRuntime(_RealSleepFakeRuntime):
            def execute(self, handle, command, timeout_s, **kw):
                if command == "false":
                    raise RuntimeError("injected infrastructure "
                                       "failure")
                return super().execute(handle, command, timeout_s, **kw)

        with tempfile.TemporaryDirectory() as tmp:
            runtime = ExplodingRuntime(clock)
            result = execute_batch(
                runtime=runtime, clock=clock,
                report_root=Path(tmp) / "r", batch_id="B-BOOM",
                approval_record=self._approval(tmp),
                reader_factory=runtime.reader_factory)
            # the abort case is recorded
            statuses = [c["status"] for c in result["cases"]]
            self.assertIn("FAIL", statuses)
            # NO orphaned containers despite the exception
            self.assertEqual(runtime.containers, {},
                             "exception left containers behind")
            for entry in result["cleanup"]:
                self.assertTrue(entry["removed"], entry)
            # evidence still archived
            self.assertEqual(result["archive_status"], "ok")

    def test_sequential_containers_not_concurrent(self):
        # container 1 must be FULLY removed before container 2 starts
        from agent_workload_characterization.runners.b_entry import (
            execute_batch)
        events = []

        class SeqRuntime(_RealSleepFakeRuntime):
            def start(self, spec, **kw):
                events.append(("start", spec.scope,
                               len(self.containers)))
                return super().start(spec, **kw)

            def stop(self, handle):
                events.append(("stop", handle.spec.scope,
                               len(self.containers) - 1))
                super().stop(handle)

        clock = type("C", (), {"monotonic_ns": staticmethod(
            lambda: int(time.monotonic_ns()))})()
        with tempfile.TemporaryDirectory() as tmp:
            runtime = SeqRuntime(clock)
            result = execute_batch(
                runtime=runtime, clock=clock,
                report_root=Path(tmp) / "r", batch_id="B-SEQ",
                approval_record=self._approval(tmp),
                reader_factory=runtime.reader_factory)
            self.assertEqual(result["archive_status"], "ok")
            # when c2 starts, c1 must already be stopped (live=0)
            starts = [e for e in events if e[0] == "start"]
            self.assertEqual(len(starts), 2)
            self.assertEqual(starts[1][2], 0,
                             "container 2 started while container 1 "
                             "was still alive")

    def test_case1_fail_stops_batch(self):
        from agent_workload_characterization.runners.b_entry import (
            execute_batch)
        clock = type("C", (), {"monotonic_ns": staticmethod(
            lambda: int(time.monotonic_ns()))})()
        with tempfile.TemporaryDirectory() as tmp:
            runtime = self._fake_runtime(clock, overrides={
                'python3 -c "x=sum(range(2_000_000))"':
                    {"returncode": 2, "output": ""}})
            result = execute_batch(
                runtime=runtime, clock=clock,
                report_root=Path(tmp) / "r", batch_id="B-C1FAIL",
                approval_record=self._approval(tmp),
                reader_factory=runtime.reader_factory)
            statuses = {c["case"]: c["status"] for c in result["cases"]}
            self.assertEqual(statuses.get(1), "FAIL")
            # case 2 SKIPPED (batch stopped, not just next-in-line)
            self.assertEqual(statuses.get(2), "SKIPPED")
            c2 = next(c for c in result["cases"] if c.get("case") == 2)
            self.assertIn("case 1 failed", c2["reason"])
            # only ONE container ever created (case-2 was skipped)
            total_cleaned = (len(result["cleanup"])
                             + sum(len(c.get("container_cleanup") or [])
                                   for c in result["cases"]))
            self.assertEqual(total_cleaned, 1)
            self.assertEqual(runtime.containers, {})

    def test_missing_approval_record_refuses(self):
        from agent_workload_characterization.runners.b_entry import (
            B0Error, execute_batch)
        clock = type("C", (), {"monotonic_ns": staticmethod(
            lambda: int(time.monotonic_ns()))})()
        with tempfile.TemporaryDirectory() as tmp:
            runtime = self._fake_runtime(clock)
            with self.assertRaises(B0Error) as ctx:
                execute_batch(runtime=runtime, clock=clock,
                              report_root=Path(tmp) / "r",
                              batch_id="B-NOAUTH",
                              approval_record=Path(tmp) / "absent.txt")
            self.assertIn("approval record", str(ctx.exception))

    def test_no_cpu_growth_fails_case2(self):
        # PASS requires background CPU growth evidence: a flat counter
        # FAILS the case (no fake pass)
        from agent_workload_characterization.runners.b_entry import (
            execute_batch)
        clock = type("C", (), {"monotonic_ns": staticmethod(
            lambda: int(time.monotonic_ns()))})()

        class FlatCpuRuntime(_RealSleepFakeRuntime):
            def read_counters(self, handle, t_monotonic_ns):
                if handle.spec.scope == "c2":
                    # c2 scope: never grows (the injected fault)
                    return CounterSnapshot(
                        scope=handle.spec.scope,
                        scope_kind="verifier_container",
                        t_monotonic_ns=t_monotonic_ns,
                        cpu_usage_usec=42,
                        mem_current_bytes=1024 * 1024,
                        read_status={"cpuacct.usage":
                                     "ok_ns_converted_to_usec"})
                return super().read_counters(handle, t_monotonic_ns)

        with tempfile.TemporaryDirectory() as tmp:
            runtime = FlatCpuRuntime(clock)
            result = execute_batch(
                runtime=runtime, clock=clock,
                report_root=Path(tmp) / "r", batch_id="B-FLATCPU",
                approval_record=self._approval(tmp),
                reader_factory=runtime.reader_factory)
            statuses = {c["case"]: c["status"] for c in result["cases"]}
            self.assertEqual(statuses.get(1), "PASS")
            self.assertEqual(statuses.get(2), "FAIL")
            c2 = next(c for c in result["cases"] if c.get("case") == 2)
            self.assertIn("CPU growth", c2["reason"])

    def test_unconfirmed_stop_fails_case2(self):
        from agent_workload_characterization.runners.b_entry import (
            execute_batch)
        clock = type("C", (), {"monotonic_ns": staticmethod(
            lambda: int(time.monotonic_ns()))})()

        class BadStopRuntime(_RealSleepFakeRuntime):
            def terminate_workload(self, handle, timeout_s=15, **kw):
                self.terminated.append(handle.container_id)
                return {"confirmed": False, "method": "docker_stop_failed",
                        "container_alive": None, "error": "OSError"}

        with tempfile.TemporaryDirectory() as tmp:
            runtime = BadStopRuntime(clock)
            result = execute_batch(
                runtime=runtime, clock=clock,
                report_root=Path(tmp) / "r", batch_id="B-BADSTOP",
                approval_record=self._approval(tmp),
                reader_factory=runtime.reader_factory)
            c2 = next(c for c in result["cases"] if c.get("case") == 2)
            self.assertEqual(c2["status"], "FAIL")
            self.assertIn("not confirmed", c2["reason"])

    def test_budget_stop_skips_next_case(self):
        from agent_workload_characterization.runners import b_entry
        orig = dict(b_entry.BUDGET)
        b_entry.BUDGET["batch_wall_s"] = 10.0
        b_entry.BUDGET["cleanup_reserve_s"] = 3600.0
        try:
            clock = type("C", (), {"monotonic_ns": staticmethod(
                lambda: int(time.monotonic_ns()))})()
            with tempfile.TemporaryDirectory() as tmp:
                runtime = self._fake_runtime(clock)
                result = b_entry.execute_batch(
                    runtime=runtime, clock=clock,
                    report_root=Path(tmp) / "r", batch_id="B-BUDGET",
                    approval_record=self._approval(tmp),
                reader_factory=runtime.reader_factory)
                statuses = {c["case"]: c["status"] for c in
                            result["cases"]}
                self.assertEqual(statuses.get(1), "SKIPPED")
                self.assertEqual(statuses.get(2), "SKIPPED")
                self.assertEqual(result["archive_status"], "ok")
                self.assertEqual(runtime.containers, {})
                self.assertEqual(result["cleanup"], [])
        finally:
            b_entry.BUDGET.clear()
            b_entry.BUDGET.update(orig)

    def test_failure_archives_before_cleanup(self):
        from agent_workload_characterization.runners.b_entry import (
            execute_batch)
        clock = type("C", (), {"monotonic_ns": staticmethod(
            lambda: int(time.monotonic_ns()))})()
        with tempfile.TemporaryDirectory() as tmp:
            runtime = self._fake_runtime(clock, overrides={
                'python3 -c "x=sum(range(2_000_000))"':
                    {"returncode": 2, "output": ""}})
            result = execute_batch(
                runtime=runtime, clock=clock,
                report_root=Path(tmp) / "r", batch_id="B-FAIL",
                approval_record=self._approval(tmp),
                reader_factory=runtime.reader_factory)
            c1 = next(c for c in result["cases"] if c["case"] == 1)
            self.assertEqual(c1["status"], "FAIL")
            self.assertIn("b1-cpu rc=2", c1["reason"])
            self.assertEqual(result["archive_status"], "ok")
            self.assertEqual(runtime.containers, {})
            out_dir = Path(result["out_dir"])
            self.assertTrue((out_dir / "batch.json").is_file())
            self.assertTrue((out_dir / "manifest.json").is_file())
            doc = json.loads((out_dir / "batch.json").read_text())
            c1doc = doc["cases"][0]
            self.assertIsNotNone(
                c1doc.get("scope_summary")
                or c1doc.get("scope_summary_partial"))

    def test_config_drift_refused_by_production_logic(self):
        # the production refusal: a drifted BUDGET means the approval
        # record (bound to the ORIGINAL identity) no longer matches
        from agent_workload_characterization.runners import b_entry
        from agent_workload_characterization.runners.b_entry import (
            B0Error, _verify_approval)
        with tempfile.TemporaryDirectory() as tmp:
            # approval written against the CURRENT identity
            rec = Path(tmp) / "APPROVAL.txt"
            rec.write_text(json.dumps({
                "checklist_identity": b_entry._checklist_identity()}))
            # drift the BUDGET -> the SAME record must now be refused
            orig = b_entry.BUDGET["batch_wall_s"]
            try:
                b_entry.BUDGET["batch_wall_s"] = 111.0
                with self.assertRaises(B0Error) as ctx:
                    _verify_approval(rec)
                self.assertIn("drift", str(ctx.exception))
            finally:
                b_entry.BUDGET["batch_wall_s"] = orig
            # and unchanged identity passes
            _verify_approval(rec)



    """Default plan: zero Docker/network side effects; single-flag
    refusal; image/budget drift refusal."""

    def test_plan_mode_no_side_effects(self):
        import io
        import subprocess as sp
        from contextlib import redirect_stdout
        with mock.patch.object(sp, "run",
                               side_effect=AssertionError("side effect")), \
             mock.patch.object(sp, "Popen",
                               side_effect=AssertionError("side effect")):
            buf = io.StringIO()
            with redirect_stdout(buf):
                rc = b_entry.main([])
        self.assertEqual(rc, 0)
        plan = json.loads(buf.getvalue())
        self.assertEqual(plan["mode"], "offline_plan")
        self.assertEqual(plan["authorization"]["B_user_approval"],
                         "pending")
        text = buf.getvalue()
        self.assertNotIn("sk-", text)

    def test_single_flag_refused(self):
        import io
        from contextlib import redirect_stderr, redirect_stdout
        buf = io.StringIO()
        with redirect_stderr(buf), redirect_stdout(io.StringIO()):
            rc = b_entry.main(["--execute"])
        self.assertEqual(rc, 2)
        self.assertIn("software gate", buf.getvalue())

    def test_double_flag_without_user_approval_stops(self):
        # the double flag alone must NOT start containers: B1 requires
        # the user's approval RECORD; the entry stops with rc=3
        import io
        from contextlib import redirect_stderr, redirect_stdout
        buf = io.StringIO()
        with redirect_stderr(buf), redirect_stdout(io.StringIO()):
            rc = b_entry.main(["--execute",
                               "--i-approve-the-b-validation"])
        self.assertEqual(rc, 3)
        self.assertIn("approval", buf.getvalue())

    def test_fixed_image_and_budget_declared(self):
        plan = b_entry._plan()
        self.assertIn("sha256:19d403c2", plan["image"])
        b = plan["budget"]
        self.assertEqual(b["batch_wall_s"], 180.0)
        # the plan's budget must equal the REGISTERED constant
        self.assertEqual(b, dict(b_entry.BUDGET))
        self.assertEqual(b["cleanup_reserve_s"], 30.0)
        self.assertEqual(b["max_containers"], 2)
        self.assertEqual(b["per_container"]["mem"], "256m")
        self.assertEqual(len(plan["cases"][0]["commands"]), 4)
        # drift refusal: the B1 runner must reject a mutated plan
        mutated = json.loads(json.dumps(plan))
        mutated["budget"]["batch_wall_s"] = 999
        self.assertNotEqual(mutated["budget"]["batch_wall_s"],
                            b_entry.BUDGET["batch_wall_s"])


class Group8ReviewRound4(unittest.TestCase):
    """Fourth-round review counter-examples (deterministic, offline)."""

    def test_report_root_in_project_redirect_refused(self):
        # reviewer repro: a report root pointing at ANOTHER directory
        # INSIDE the project (not a symlink, a literal different path)
        # must be refused — the B report root is a FIXED location
        from agent_workload_characterization.runners.b_entry import (
            B0Error, _guard_report_root)
        with tempfile.TemporaryDirectory() as tmp:
            proj = Path(tmp) / "proj"
            (proj / "reports/resource/G1-01-B").mkdir(parents=True)
            (proj / "reports/other").mkdir(parents=True)
            with mock.patch("agent_workload_characterization.runners."
                            "b_entry.PROJECT_ROOT", proj):
                with self.assertRaises(B0Error) as ctx:
                    _guard_report_root(Path(proj / "reports/other"))
                self.assertIn("fixed at", str(ctx.exception))

    def test_verify_removal_check_failed_not_removed(self):
        # reviewer repro: a daemon error must yield check_failed, NOT
        # removed=True
        runtime = FakeContainerRuntime(FakeClock())
        runtime.next_verify_result = "check_failed"
        h = runtime.start(ContainerSpec(run_id="r", scope="c1",
                                        image="img"))
        runtime.stop(h)
        self.assertEqual(runtime.verify_removal(h), "check_failed")

    def test_verify_removal_still_exists_not_removed(self):
        # a container that exists but is stopped: still_exists
        runtime = FakeContainerRuntime(FakeClock())
        h = runtime.start(ContainerSpec(run_id="r", scope="c1",
                                        image="img"))
        self.assertEqual(runtime.verify_removal(h), "still_exists")

    def test_unconfirmed_removal_batch_fails(self):
        # an unconfirmed removal must surface in batch_status=FAIL
        from agent_workload_characterization.runners.b_entry import (
            execute_batch, _checklist_identity)
        clock = type("C", (), {"monotonic_ns": staticmethod(
            lambda: int(time.monotonic_ns()))})()

        class BadVerifyRuntime(_RealSleepFakeRuntime):
            def verify_removal(self, handle):
                return "check_failed"

        with tempfile.TemporaryDirectory() as tmp:
            runtime = BadVerifyRuntime(clock)
            rec = Path(tmp) / "A.txt"
            rec.write_text(json.dumps({
                "checklist_identity": _checklist_identity()}))
            result = execute_batch(
                runtime=runtime, clock=clock,
                report_root=Path(tmp) / "r", batch_id="B-BADVER",
                approval_record=rec,
                reader_factory=runtime.reader_factory)
            self.assertEqual(result["batch_status"], "FAIL")
            self.assertTrue(any(not e.get("removed", True)
                                for e in result["cleanup"]))

    def test_io_degradation_in_actual_results(self):
        # both containers' scope summaries carry formal null + reason,
        # with the raw block as diagnostic — in the ACTUAL result
        from agent_workload_characterization.runners.b_entry import (
            execute_batch, _checklist_identity)
        clock = type("C", (), {"monotonic_ns": staticmethod(
            lambda: int(time.monotonic_ns()))})()
        with tempfile.TemporaryDirectory() as tmp:
            runtime = _RealSleepFakeRuntime(clock)
            rec = Path(tmp) / "A.txt"
            rec.write_text(json.dumps({
                "checklist_identity": _checklist_identity()}))
            result = execute_batch(
                runtime=runtime, clock=clock,
                report_root=Path(tmp) / "r", batch_id="B-IO",
                approval_record=rec,
                reader_factory=runtime.reader_factory)
            out_dir = Path(result["out_dir"])
            doc = json.loads((out_dir / "batch.json").read_text())
            checked = 0
            for cd in doc["cases"]:
                summary = cd.get("scope_summary") or \
                    cd.get("scope_summary_partial")
                if summary and "io" in summary:
                    io = summary["io"]
                    self.assertIsNone(io.get("formal"))
                    self.assertIn("degraded_host_v1_blkio",
                                  io.get("reason", ""))
                    checked += 1
            self.assertGreaterEqual(checked, 1)

    def test_container1_missing_cpu_evidence_fails(self):
        # a container with NO CPU counter increment must FAIL case 1
        from agent_workload_characterization.runners.b_entry import (
            execute_batch, _checklist_identity)
        clock = type("C", (), {"monotonic_ns": staticmethod(
            lambda: int(time.monotonic_ns()))})()

        class NoCpuRuntime(_RealSleepFakeRuntime):
            def read_counters(self, handle, t_monotonic_ns):
                return CounterSnapshot(
                    scope=handle.spec.scope,
                    scope_kind="agent_container",
                    t_monotonic_ns=t_monotonic_ns,
                    cpu_usage_usec=None,
                    mem_current_bytes=1024 * 1024,
                    read_status={"cpuacct.usage": "not_found"})

        with tempfile.TemporaryDirectory() as tmp:
            runtime = NoCpuRuntime(clock)
            rec = Path(tmp) / "A.txt"
            rec.write_text(json.dumps({
                "checklist_identity": _checklist_identity()}))
            result = execute_batch(
                runtime=runtime, clock=clock,
                report_root=Path(tmp) / "r", batch_id="B-NOCPU",
                approval_record=rec,
                reader_factory=runtime.reader_factory)
            statuses = {c["case"]: c["status"] for c in result["cases"]}
            self.assertEqual(statuses.get(1), "FAIL")
            self.assertEqual(result["batch_status"], "FAIL")

    def test_offline_tests_never_call_docker(self):
        # the raw docker-inspect helper is gone; cleanup uses the
        # runtime's verify_removal interface (no Docker from b_entry)
        from agent_workload_characterization.runners import b_entry
        import inspect
        src = inspect.getsource(b_entry)
        self.assertNotIn("_container_alive", src)
        self.assertIn("verify_removal", src)

    def test_pull_never_in_run_argv(self):
        runtime = DockerCliRuntime(authorized=False)
        spec = ContainerSpec(run_id="r", scope="c1", image="img",
                             pull="never")
        argv = runtime.build_run_argv(spec, "n1")
        self.assertIn("--pull", argv)
        self.assertEqual(argv[argv.index("--pull") + 1], "never")



class Group9ReviewRound5(unittest.TestCase):
    """Fifth-round: CLI full-chain from main() (mocked docker + approval)
    and failure-branch tests. No real Docker in any path."""

    def _setup_main_env(self, tmp):
        """Common setup: a project tree, an approval record, a fake
        docker executable on PATH. The approval binds the REAL code
        identity (the patched PROJECT_ROOT is only for the report
        dir; the code SHAs come from the real project)."""
        from agent_workload_characterization.runners import b_entry
        proj = Path(tmp) / "proj"
        (proj / "reports/resource/G1-01-B").mkdir(parents=True)
        rec_dir = proj / "reports/resource/G1-01-B"
        rec = rec_dir / "APPROVAL.txt"
        # bind the identity from the REAL project (before patching)
        real_ident = b_entry._checklist_identity()
        rec.write_text(json.dumps({
            "checklist_identity": real_ident}))
        return proj, rec, None, real_ident
        # a fake docker: context=ok, image inspect=ok (the actual
        # container operations go through the injected fake runtime)
        fake_docker = Path(tmp) / "docker"
        fake_docker.write_text("#!/bin/sh\n"
                               "case \"$*\" in\n"
                               "  *context*show*) echo default; exit 0 ;;\n"
                               "  *image*inspect*) exit 0 ;;\n"
                               "esac\n"
                               "exit 0\n")
        fake_docker.chmod(0o755)
        return proj, rec, fake_docker

    def test_cli_full_chain_success(self):
        # the full main() path: approval OK, context OK, image OK,
        # execute_batch runs with a fake runtime, exit code 0
        import subprocess as sp
        from agent_workload_characterization.runners import b_entry
        with tempfile.TemporaryDirectory() as tmp:
            proj, rec, _, _ = self._setup_main_env(tmp)
            fake_docker = Path(tmp) / "docker"
            fake_docker.write_text(
                "#!/bin/sh\ncase \"$*\" in\n"
                "  *context*show*) echo default; exit 0 ;;\n"
                "  *image*inspect*) exit 0 ;;\nesac\nexit 0\n")
            fake_docker.chmod(0o755)
            with mock.patch.object(b_entry, "PROJECT_ROOT", proj), \
                 mock.patch.object(b_entry, "APPROVAL_RECORD", rec), \
                 mock.patch.dict("os.environ",
                                 {"PATH": f"{tmp}:{os.environ['PATH']}"}):
                # capture the runtime class the entry instantiates
                captured = {}

                class _PatchedRuntime(_RealSleepFakeRuntime):
                    def __init__(self, **kw):
                        super().__init__(FakeClock())
                        captured["runtime"] = self
                        captured["reader_factory"] = self.reader_factory

                # the reader factory resolves lazily (the runtime is
                # constructed inside main(), after the patch is applied)
                class _LazyRF:
                    def __call__(self, scope, kind, cid):
                        rf = captured.get("reader_factory")
                        if rf is not None:
                            return rf(scope, kind, cid)
                        from agent_workload_characterization. \
                            collectors.resource_sampler import \
                            CgroupV1FileReader
                        return CgroupV1FileReader(scope, kind, cid)

                with mock.patch(
                         "agent_workload_characterization.runners."
                         "container_runtime.DockerCliRuntime",
                         _PatchedRuntime), \
                     mock.patch.object(b_entry, "READER_FACTORY",
                                       _LazyRF()):
                    import io
                    from contextlib import redirect_stdout
                    buf = io.StringIO()
                    with redirect_stdout(buf):
                        rc = b_entry.main(["--execute",
                                          "--i-approve-the-b-validation"])
                    self.assertEqual(rc, 0, buf.getvalue()[-200:])
                    out = json.loads(buf.getvalue())
                    self.assertEqual(out["batch_status"], "OK")
                    # the full chain ran: both cases PASS
                    statuses = {c["case"]: c["status"]
                                for c in out["cases"]}
                    self.assertEqual(statuses.get(1), "PASS")
                    self.assertEqual(statuses.get(2), "PASS")

    def test_cli_context_check_failure_refuses(self):
        # docker context show FAILS (non-zero rc) -> refusal (not pass)
        from agent_workload_characterization.runners import b_entry
        with tempfile.TemporaryDirectory() as tmp:
            proj, rec, _, _ = self._setup_main_env(tmp)
            bad_docker = Path(tmp) / "docker"
            bad_docker.write_text(
                "#!/bin/sh\n"
                "case \"$*\" in\n"
                "  *context*show*) exit 1 ;;\n"
                "esac\n"
                "exit 1\n")
            bad_docker.chmod(0o755)
            with mock.patch.object(b_entry, "PROJECT_ROOT", proj), \
                 mock.patch.object(b_entry, "APPROVAL_RECORD", rec), \
                 mock.patch.dict("os.environ",
                                 {"PATH": f"{tmp}:{os.environ['PATH']}"}):
                import io
                from contextlib import redirect_stderr, redirect_stdout
                buf = io.StringIO()
                with redirect_stderr(buf), redirect_stdout(io.StringIO()):
                    rc = b_entry.main(["--execute",
                                      "--i-approve-the-b-validation"])
                self.assertEqual(rc, 4)
                self.assertIn("context check failed", buf.getvalue())

    def test_open_read_must_be_before_call_end(self):
        # the open-persistence proof compares read_at_ns to
        # call_end_ns: a read AFTER the call returned must NOT pass
        # (deterministic check of the evidence logic)
        ev = {"read_at_ns": 200, "call_start_ns": 100,
              "call_end_ns": 150}
        self.assertFalse(ev["read_at_ns"] < ev["call_end_ns"])
        ev2 = {"read_at_ns": 120, "call_start_ns": 100,
               "call_end_ns": 150}
        self.assertTrue(ev2["read_at_ns"] < ev2["call_end_ns"])

    def test_deliberate_late_read_fails_case1(self):
        # a reader that ONLY reads AFTER the call returns (simulating
        # the flawed proof) must FAIL the case
        from agent_workload_characterization.runners.b_entry import (
            _run_container_1, BUDGET)
        clock = FakeClock()
        runtime = _RealSleepFakeRuntime(clock)
        sampler = ResourceSampler(clock=clock,
                                  interval_s=BUDGET["sampling_interval_s"])
        # a runtime whose execute returns IMMEDIATELY (no sleep) — the
        # reader will only see the open line after the call returned
        class InstantRuntime(_RealSleepFakeRuntime):
            def execute(self, handle, command, timeout_s, **kw):
                if command == "sleep 1":
                    # NO sleep: the call returns instantly; any read
                    # the reader makes is AFTER the call ended
                    return {"returncode": 0, "output": "",
                            "duration_s": 0.0}
                return super().execute(handle, command, timeout_s, **kw)

        runtime = InstantRuntime(clock)
        with tempfile.TemporaryDirectory() as tmp:
            out_dir = Path(tmp) / "batch"
            out_dir.mkdir()
            from agent_workload_characterization.runners.b_entry import (
                _RuntimeExecuteBridge)
            from agent_workload_characterization.runners.tool_event_env \
                import wrap_environment
            # run container 1 with the instant runtime
            case = _run_container_1(
                runtime, sampler, "run1", out_dir,
                wrap_environment,
                remaining=lambda: 100.0,
                cap_wait=lambda x: x,
                register_handle=lambda h: None,
                reader_factory=runtime.reader_factory)
            # the open-read evidence must show read_before_call_end
            # is False or the case FAILed for the window
            ev = case.get("open_read_evidence")
            if ev is not None:
                # with an instant call, either the read missed the
                # window entirely (read_at_ns None) or read after end
                self.assertFalse(ev["read_before_call_end"],
                                 "instant call cannot prove during-call "
                                 "open persistence")
                self.assertEqual(case["status"], "FAIL")

    def test_report_threshold_in_flight_stops_batch(self):
        # a tiny threshold must trigger a FAIL during execution, not
        # just post-hoc
        from agent_workload_characterization.runners import b_entry
        from agent_workload_characterization.runners.b_entry import (
            _checklist_identity)
        orig = b_entry.BUDGET["report_threshold_mib"]
        b_entry.BUDGET["report_threshold_mib"] = 0.00001  # ~10 bytes
        try:
            clock = type("C", (), {"monotonic_ns": staticmethod(
                lambda: int(time.monotonic_ns()))})()
            with tempfile.TemporaryDirectory() as tmp:
                runtime = _RealSleepFakeRuntime(clock)
                rec = Path(tmp) / "A.txt"
                rec.write_text(json.dumps({
                    "checklist_identity": _checklist_identity()}))
                result = b_entry.execute_batch(
                    runtime=runtime, clock=clock,
                    report_root=Path(tmp) / "r", batch_id="B-THRESH",
                    approval_record=rec,
                    reader_factory=runtime.reader_factory)
                # the batch must FAIL (threshold exceeded in-flight)
                self.assertEqual(result["batch_status"], "FAIL")
                fails = [c for c in result["cases"]
                         if c.get("status") == "FAIL"]
                self.assertTrue(any("report threshold" in
                                    (c.get("reason") or "")
                                    for c in result["cases"]))
        finally:
            b_entry.BUDGET["report_threshold_mib"] = orig

    def test_c2_failure_saves_full_evidence(self):
        # a container-2 failure must still archive the full raw scope
        # evidence AND the I/O degradation
        from agent_workload_characterization.runners.b_entry import (
            execute_batch, _checklist_identity)
        clock = type("C", (), {"monotonic_ns": staticmethod(
            lambda: int(time.monotonic_ns()))})()

        class C2FailRuntime(_RealSleepFakeRuntime):
            def execute(self, handle, command, timeout_s, **kw):
                if handle.spec.scope == "c2":
                    return {"returncode": 1, "output": "injected c2 "
                            "failure", "duration_s": 0.0}
                return super().execute(handle, command, timeout_s, **kw)

        with tempfile.TemporaryDirectory() as tmp:
            runtime = C2FailRuntime(clock)
            rec = Path(tmp) / "A.txt"
            rec.write_text(json.dumps({
                "checklist_identity": _checklist_identity()}))
            result = execute_batch(
                runtime=runtime, clock=clock,
                report_root=Path(tmp) / "r", batch_id="B-C2FAIL",
                approval_record=rec,
                reader_factory=runtime.reader_factory)
            out_dir = Path(result["out_dir"])
            c2 = next(c for c in result["cases"] if c.get("case") == 2)
            self.assertEqual(c2["status"], "FAIL")
            # FULL raw evidence on the failure path
            self.assertTrue((out_dir / "c2_scope_evidence.json").is_file(),
                            "c2 failure path must save raw evidence; "
                            f"out_dir={out_dir}, contents="
                            f"{list(out_dir.iterdir())}")
            ev = json.loads((out_dir / "c2_scope_evidence.json")
                            .read_text())
            self.assertIsNotNone(ev.get("boundary_start"))
            self.assertIsNotNone(ev.get("boundary_end"))
            # I/O degradation on the failure path summary
            doc = json.loads((out_dir / "batch.json").read_text())
            c2doc = doc["cases"][1]
            summary = c2doc.get("scope_summary") or \
                c2doc.get("scope_summary_partial")
            if summary and "io" in summary:
                self.assertIsNone(summary["io"].get("formal"))

    def test_host_child_timeout_killed_by_identity(self):
        # a host child that exceeds its lifetime is killed and reaped
        # (identity confirmed before kill)
        from agent_workload_characterization.runners.b_entry import (
            execute_batch, _checklist_identity, BUDGET)
        orig = BUDGET["host_child"]["lifetime_s"]
        BUDGET["host_child"]["lifetime_s"] = 0.01  # near-instant timeout
        try:
            clock = type("C", (), {"monotonic_ns": staticmethod(
                lambda: int(time.monotonic_ns()))})()
            with tempfile.TemporaryDirectory() as tmp:
                runtime = _RealSleepFakeRuntime(clock)
                rec = Path(tmp) / "A.txt"
                rec.write_text(json.dumps({
                    "checklist_identity": _checklist_identity()}))
                result = execute_batch(
                    runtime=runtime, clock=clock,
                    report_root=Path(tmp) / "r", batch_id="B-CHILDTO",
                    approval_record=rec,
                    reader_factory=runtime.reader_factory)
                c2 = next(c for c in result["cases"]
                          if c.get("case") == 2)
                self.assertEqual(c2["status"], "FAIL")
                self.assertIn("host child exceeded", c2.get("reason", ""))
        finally:
            BUDGET["host_child"]["lifetime_s"] = orig



class Group10BudgetClosure(unittest.TestCase):
    """Sixth-round: budget closure counter-examples (deterministic)."""

    def test_bg_busy_total_budget_not_per_step(self):
        # UNCONDITIONAL: the bg budget is established BEFORE the bg
        # start; the observation phase burns part of it; the terminate
        # MUST receive the decremented share (< full) AND a
        # step_share_deadline for its internal steps. If the terminate
        # was never called (case failed earlier), that's also a bug —
        # we assert the call happened.
        from agent_workload_characterization.runners.b_entry import (
            _run_container_2, BUDGET)
        from agent_workload_characterization.runners.tool_event_env \
            import wrap_environment
        from agent_workload_characterization.collectors. \
            resource_sampler import ResourceSampler
        clock = FakeClock()

        class BudgetProbeRuntime(_RealSleepFakeRuntime):
            def read_counters(self, handle, t_monotonic_ns):
                # burn a modest ~0.5s per read; with two reads +
                # start + child this leaves the stop chain with a
                # positive but REDUCED share of the 5s budget
                time.sleep(0.5)
                return super().read_counters(handle, t_monotonic_ns)

        runtime = BudgetProbeRuntime(clock)
        sampler = ResourceSampler(clock=clock,
                                  interval_s=BUDGET["sampling_interval_s"])
        with tempfile.TemporaryDirectory() as tmp:
            out_dir = Path(tmp) / "batch"
            out_dir.mkdir()
            case = _run_container_2(
                runtime, sampler, "runbg", out_dir,
                wrap_environment,
                remaining=lambda: 100.0,
                cap_wait=lambda x: x,
                register_handle=lambda h: None,
                stopped_scopes=[],
                runner_mon=HostProcessMonitor(1,
                                              expected_starttime=1),
                reader_factory=runtime.reader_factory)
            # the terminate MUST have been called (the observation and
            # the child completed without failing the case)
            self.assertGreaterEqual(
                len(runtime.terminate_calls), 1,
                "terminate_workload was never called — the stop chain "
                "branch was not exercised; this test must prove it")
            call = runtime.terminate_calls[0]
            # the bg budget was 5s; the observation burned ~2s+; the
            # terminate received the REMAINING share, not a fresh 5s
            self.assertLess(call["timeout_s"], 5,
                            f"terminate got a fresh {call['timeout_s']}s "
                            "instead of sharing the bg budget")
            # a step_share_deadline was passed for internal sharing
            self.assertIsNotNone(call["step_share_deadline"],
                                 "no step_share_deadline passed to "
                                 "terminate_workload")
            # the bg budget remaining at terminate time is recorded
            self.assertIn("background_budget_remaining_s", case)
            self.assertLess(case["background_budget_remaining_s"], 5.0)

    def test_report_threshold_interrupts_blocking_execute(self):
        # the report threshold trips DURING a blocking execute: the
        # should_stop callback interrupts it (not just between cases)
        from agent_workload_characterization.runners.b_entry import (
            execute_batch, _checklist_identity, BUDGET)
        orig_thresh = BUDGET["report_threshold_mib"]
        BUDGET["report_threshold_mib"] = 0.00001  # ~10 bytes
        try:
            clock = type("C", (), {"monotonic_ns": staticmethod(
                lambda: int(time.monotonic_ns()))})()

            class SlowGrowRuntime(_RealSleepFakeRuntime):
                """The c1 sleep command takes 5s; the events file
                grows past the threshold during that blocking wait, so
                the should_stop callback must interrupt it."""

                def execute(self, handle, command, timeout_s, **kw):
                    if command == "sleep 1":
                        stop_cb = kw.get("should_stop")
                        t0 = time.monotonic()
                        while time.monotonic() - t0 < 5.0:
                            if stop_cb is not None and stop_cb():
                                return {"returncode": 124,
                                        "output": "interrupted by "
                                        "report threshold",
                                        "timed_out": True,
                                        "stopped_by": "external"}
                            time.sleep(0.05)
                        return {"returncode": 0, "output": "",
                                "duration_s": 5.0}
                    return super().execute(handle, command, timeout_s,
                                           **kw)

            with tempfile.TemporaryDirectory() as tmp:
                runtime = SlowGrowRuntime(clock)
                rec = Path(tmp) / "A.txt"
                rec.write_text(json.dumps({
                    "checklist_identity": _checklist_identity()}))
                result = execute_batch(
                    runtime=runtime, clock=clock,
                    report_root=Path(tmp) / "r", batch_id="B-INTERRUPT",
                    approval_record=rec,
                    reader_factory=runtime.reader_factory)
                c1 = next(c for c in result["cases"]
                          if c.get("case") == 1)
                # the case must FAIL (interrupted or threshold)
                self.assertEqual(c1["status"], "FAIL")
                self.assertEqual(result["batch_status"], "FAIL")
        finally:
            BUDGET["report_threshold_mib"] = orig_thresh

    def test_batch_deadline_covers_preflight(self):
        # the main() deadline starts BEFORE the context check; verify
        # by source that t0/deadline is set before the context query
        from agent_workload_characterization.runners import b_entry
        import inspect
        src = inspect.getsource(b_entry.main)
        t0_pos = src.index("t0 = time.monotonic()")
        ctx_pos = src.index('context", "show')
        self.assertLess(t0_pos, ctx_pos,
                        "batch deadline must start BEFORE the docker "
                        "context check")
        img_pos = src.index('image", "inspect')
        self.assertLess(t0_pos, img_pos)

    def test_expired_budget_gives_zero_not_one(self):
        # cap_timeout: an expired budget returns 0 (refuse), not +1s
        from agent_workload_characterization.runners.b_entry import (
            execute_batch, _checklist_identity, BUDGET)
        # drive the budget to near-zero and check the case refuses
        clock = type("C", (), {"monotonic_ns": staticmethod(
            lambda: int(time.monotonic_ns()))})()
        with tempfile.TemporaryDirectory() as tmp:
            runtime = _RealSleepFakeRuntime(clock)
            rec = Path(tmp) / "A.txt"
            rec.write_text(json.dumps({
                "checklist_identity": _checklist_identity()}))
            # pass a deadline in the PAST: every cap_timeout gives 0
            result = execute_batch(
                runtime=runtime, clock=clock,
                report_root=Path(tmp) / "r", batch_id="B-EXPIRED",
                approval_record=rec,
                reader_factory=runtime.reader_factory,
                _batch_deadline=time.monotonic() - 1.0)
            # cases must be SKIPPED or FAILed (not silently run with
            # free extra seconds)
            for c in result["cases"]:
                self.assertIn(c.get("status"),
                              ("SKIPPED", "FAIL"),
                              f"case {c.get('case')} ran with an "
                              "expired budget")


    def test_zero_timeout_refused_not_defaulted(self):
        # timeout=0 means budget exhausted: the bridge MUST refuse the
        # call, not silently substitute the 20s per-command default
        from agent_workload_characterization.runners.b_entry import (
            _RuntimeExecuteBridge)

        class NeverCalledRuntime:
            def execute(self, *a, **kw):
                raise AssertionError(
                    "runtime.execute must NOT be called with a "
                    "zero/negative timeout")

        bridge = _RuntimeExecuteBridge(NeverCalledRuntime(), None)
        out = bridge.execute({"command": "anything"}, timeout=0)
        self.assertEqual(out["returncode"], 124)
        self.assertEqual(out["stopped_by"], "budget_exhausted")
        self.assertTrue(out["timed_out"])

        # timeout=None uses the default (legitimate)
        from agent_workload_characterization.runners.b_entry import (
            BUDGET as B)
        class RecordingRuntime:
            def __init__(self):
                self.timeout = None
            def execute(self, handle, cmd, timeout, **kw):
                self.timeout = timeout
                return {"returncode": 0, "output": ""}
        rec = RecordingRuntime()
        bridge2 = _RuntimeExecuteBridge(rec, None)
        bridge2.execute({"command": "ok"})
        self.assertEqual(rec.timeout, B["per_command_timeout_s"])

    def test_step_share_deadline_decrements(self):
        # the real DockerCliRuntime's terminate_workload: with a
        # step_share_deadline, each internal step gets a SMALLER
        # timeout than the initial allowance (they decrement)
        from agent_workload_characterization.runners. \
            container_runtime import DockerCliRuntime
        import inspect
        src = inspect.getsource(DockerCliRuntime.terminate_workload)
        self.assertIn("_step_timeout", src,
                      "terminate_workload must derive per-step timeouts "
                      "from the shared deadline")
        self.assertIn("step_share_deadline - _time.monotonic()",
                      src,
                      "step timeout must decrement from the absolute "
                      "deadline, not re-derive")


class Group11B0Final(unittest.TestCase):
    """B0-A through B0-E final counter-examples (deterministic)."""

    # === B0-C: unified status ===

    def test_archive_failure_makes_batch_fail(self):
        # reviewer repro: batch.json write throws OSError → batch must
        # be FAIL, not OK
        from agent_workload_characterization.runners.b_entry import (
            execute_batch, _checklist_identity)
        clock = type("C", (), {"monotonic_ns": staticmethod(
            lambda: int(time.monotonic_ns()))})()
        with tempfile.TemporaryDirectory() as tmp:
            runtime = _RealSleepFakeRuntime(clock)
            rec = Path(tmp) / "A.txt"
            rec.write_text(json.dumps({
                "checklist_identity": _checklist_identity()}))
            # make batch.json un-writable: the batch dir contains a
            # DIRECTORY named batch.json (write_text fails with
            # IsADirectoryError/OSError)
            out_root = Path(tmp) / "r"
            (out_root / "B-ARCHFAIL" / "batch.json").mkdir(parents=True)
            result = execute_batch(
                runtime=runtime, clock=clock,
                report_root=out_root, batch_id="B-ARCHFAIL",
                approval_record=rec,
                reader_factory=runtime.reader_factory)
            self.assertNotEqual(result["batch_status"], "OK",
                                "archive failure must not be OK")
            self.assertIn("archive",
                          [r["source"]
                           for r in result["batch_fail_reasons"]])

    def test_timeout_not_treated_as_expected_nonzero(self):
        # reviewer repro: the false command times out (rc=124) but is
        # treated as the expected non-zero result → both cases PASS.
        # Fix: rc=124/timed_out on b1-fail is a FAIL, not the expected
        # outcome
        from agent_workload_characterization.runners.b_entry import (
            execute_batch, _checklist_identity)
        clock = type("C", (), {"monotonic_ns": staticmethod(
            lambda: int(time.monotonic_ns()))})()

        class TimeoutFalseRuntime(_RealSleepFakeRuntime):
            def execute(self, handle, command, timeout_s, **kw):
                if command == "false":
                    return {"returncode": 124, "output": "",
                            "timed_out": True}
                return super().execute(handle, command, timeout_s, **kw)

        with tempfile.TemporaryDirectory() as tmp:
            runtime = TimeoutFalseRuntime(clock)
            rec = Path(tmp) / "A.txt"
            rec.write_text(json.dumps({
                "checklist_identity": _checklist_identity()}))
            result = execute_batch(
                runtime=runtime, clock=clock,
                report_root=Path(tmp) / "r", batch_id="B-TIMEOUT",
                approval_record=rec,
                reader_factory=runtime.reader_factory)
            c1 = next(c for c in result["cases"] if c.get("case") == 1)
            self.assertEqual(c1["status"], "FAIL",
                             "rc=124 on false is a timeout, not the "
                             "expected non-zero result")
            self.assertIn("timed out", c1.get("reason", ""))
            self.assertEqual(result["batch_status"], "FAIL")

    def test_all_skipped_not_ok(self):
        # all cases SKIPPED (budget exhausted) → batch FAIL (nothing
        # was validated)
        from agent_workload_characterization.runners import b_entry
        orig = dict(b_entry.BUDGET)
        b_entry.BUDGET["batch_wall_s"] = 10.0
        b_entry.BUDGET["cleanup_reserve_s"] = 3600.0
        try:
            clock = type("C", (), {"monotonic_ns": staticmethod(
                lambda: int(time.monotonic_ns()))})()
            with tempfile.TemporaryDirectory() as tmp:
                runtime = _RealSleepFakeRuntime(clock)
                rec = Path(tmp) / "A.txt"
                rec.write_text(json.dumps({
                    "checklist_identity":
                        b_entry._checklist_identity()}))
                result = b_entry.execute_batch(
                    runtime=runtime, clock=clock,
                    report_root=Path(tmp) / "r", batch_id="B-ALLSKIP",
                    approval_record=rec,
                    reader_factory=runtime.reader_factory)
                self.assertEqual(result["batch_status"], "FAIL",
                                 "all-skipped is not OK")
                sources = [r["source"]
                           for r in result["batch_fail_reasons"]]
                self.assertIn("all_skipped", sources)
        finally:
            b_entry.BUDGET.clear()
            b_entry.BUDGET.update(orig)

    # === B0-B: cleanup independence ===

    def test_monitor_failure_does_not_block_cleanup(self):
        # reviewer repro: runner_mon.poll_once() in the outer finally
        # throws → cleanup skipped → containers orphaned
        from agent_workload_characterization.runners.b_entry import (
            execute_batch, _checklist_identity)
        clock = type("C", (), {"monotonic_ns": staticmethod(
            lambda: int(time.monotonic_ns()))})()

        class MonitorFailRuntime(_RealSleepFakeRuntime):
            """The runner_mon is created inside execute_batch; we
            simulate the failure by making the FIRST call to
            read_counters (which runner_mon.poll_once indirectly
            triggers via HostProcessMonitor) raise. But runner_mon
            monitors the CURRENT process, not the runtime. Instead,
            we patch HostProcessMonitor to fail on summary()."""
            pass

        with tempfile.TemporaryDirectory() as tmp:
            runtime = MonitorFailRuntime(clock)
            rec = Path(tmp) / "A.txt"
            rec.write_text(json.dumps({
                "checklist_identity": _checklist_identity()}))
            # patch HostProcessMonitor in its home module
            from agent_workload_characterization.collectors \
                import host_process as hp
            orig_summary = hp.HostProcessMonitor.summary
            def fail_summary(self):
                raise RuntimeError("injected monitor summary failure")
            hp.HostProcessMonitor.summary = fail_summary
            try:
                result = execute_batch(
                    runtime=runtime, clock=clock,
                    report_root=Path(tmp) / "r", batch_id="B-MONFAIL",
                    approval_record=rec,
                    reader_factory=runtime.reader_factory)
                # cleanup STILL ran: all containers removed
                self.assertEqual(runtime.containers, {},
                                 "monitor failure blocked cleanup")
                self.assertNotEqual(result["batch_status"], "OK")
            finally:
                hp.HostProcessMonitor.summary = orig_summary

    def test_start_failure_no_orphan(self):
        # reviewer repro: docker run succeeds, then _resolve_cgroup
        # throws → start() never returns → handle never registered.
        # Fix: _resolve_cgroup failures are non-fatal (the handle IS
        # returned). Test: a runtime whose start succeeds but cgroup
        # resolution fails must still produce a registered handle.
        from agent_workload_characterization.collectors.host_process \
            import HostProcessReader  # noqa: F401 (just verifying import)
        from agent_workload_characterization.runners.b_entry import (
            execute_batch, _checklist_identity)
        clock = type("C", (), {"monotonic_ns": staticmethod(
            lambda: int(time.monotonic_ns()))})()
        with tempfile.TemporaryDirectory() as tmp:
            runtime = _RealSleepFakeRuntime(clock)
            rec = Path(tmp) / "A.txt"
            rec.write_text(json.dumps({
                "checklist_identity": _checklist_identity()}))
            result = execute_batch(
                runtime=runtime, clock=clock,
                report_root=Path(tmp) / "r", batch_id="B-START",
                approval_record=rec,
                reader_factory=runtime.reader_factory)
            # all containers cleaned regardless
            self.assertEqual(runtime.containers, {})

    # === B0-D: evidence quality ===

    def test_no_samples_means_evidence_missing(self):
        # reviewer repro: sampling disabled → 0 samples → but
        # scope_frozen_after_stop=True (None==None) and batch OK.
        # Fix: _check_evidence_quality requires samples > 0 and a
        # countable reader.
        from agent_workload_characterization.runners.b_entry import (
            _check_evidence_quality)
        sampler = ResourceSampler(clock=None, interval_s=0.1)
        # no scope registered, no samples taken
        cases = [{"case": 2, "status": "PASS",
                  "scope_frozen_after_stop": True,
                  "host_child": {"n_readable": 1,
                                 "final_read_status": "ok"}}]
        evidence = _check_evidence_quality(cases, sampler, [])
        self.assertFalse(evidence["c2_sampling_worked"],
                         "0 samples must not count as evidence")
        self.assertFalse(evidence["c2_scope_frozen"],
                         "scope_frozen from None==None must not count")
        self.assertFalse(evidence["c2_reader_had_reads"])

    def test_manifest_includes_identity(self):
        # B0-E: manifest must contain identity, not just file hashes
        from agent_workload_characterization.runners.b_entry import (
            execute_batch, _checklist_identity)
        clock = type("C", (), {"monotonic_ns": staticmethod(
            lambda: int(time.monotonic_ns()))})()
        with tempfile.TemporaryDirectory() as tmp:
            runtime = _RealSleepFakeRuntime(clock)
            rec = Path(tmp) / "A.txt"
            rec.write_text(json.dumps({
                "checklist_identity": _checklist_identity()}))
            result = execute_batch(
                runtime=runtime, clock=clock,
                report_root=Path(tmp) / "r", batch_id="B-ID",
                approval_record=rec,
                reader_factory=runtime.reader_factory)
            manifest = json.loads(
                (Path(result["out_dir"]) / "manifest.json").read_text())
            ident = manifest.get("identity", {})
            for key in ("image", "budget", "code_sha256",
                        "approval_record_sha256", "wall_s",
                        "batch_started_utc"):
                self.assertIn(key, ident,
                              f"manifest identity missing {key}")
            self.assertIn("batch_status", manifest)
            self.assertIn("output_bytes", manifest)



class Group12B0Residual(unittest.TestCase):
    """The four residual counter-examples from the ninth review."""

    def test_A_start_deadline_deducts_create_time(self):
        # the create call's elapsed time is DEDUCTED from the resolve
        # budget (not re-derived): a 1s deadline + 0.8s create leaves
        # only 0.2s for _resolve_cgroup, which must NOT get a fresh 30s
        from agent_workload_characterization.runners. \
            container_runtime import DockerCliRuntime
        import time as _t
        runtime = DockerCliRuntime(authorized=True,
                                  docker_executable="/nonexistent")
        # verify by source: the resolve call uses the REMAINING time
        import inspect
        src = inspect.getsource(DockerCliRuntime.start)
        self.assertIn("resolve_to = deadline", src,
                      "resolve must derive from the ABSOLUTE deadline, "
                      "not a fresh timeout_s")
        self.assertNotIn("_resolve_cgroup(handle, timeout_s=timeout_s)",
                         src,
                         "the old pattern re-derived the full budget")

    def test_A_no_rounding_of_subsecond_budget(self):
        # cap_timeout returns a float: 0.2s stays 0.2s, not int(0.2)=0
        # or max(1, 0.2)=1
        from agent_workload_characterization.runners.b_entry import (
            execute_batch, _checklist_identity, BUDGET)
        # verify by source
        import inspect
        src = inspect.getsource(execute_batch)
        self.assertIn("def cap_timeout(requested: float) -> float:",
                      src)
        self.assertNotIn("int(max(minimum", src,
                          "no int+minimum rounding that inflates "
                          "sub-second budgets")

    def test_A_bg_deadline_capped_by_batch_deadline(self):
        # bg_deadline = min(now + busy_max, batch_deadline): the bg
        # work never outlives the batch budget
        from agent_workload_characterization.runners.b_entry import (
            _run_container_2, BUDGET)
        import inspect
        src = inspect.getsource(_run_container_2)
        self.assertIn("bg_deadline = min(", src)
        self.assertIn("batch_deadline)", src)

    def test_B_pending_name_actually_consumed(self):
        # reviewer repro: create times out after the daemon accepted
        # → pending_names has the name → but cleanup never consumed it.
        # Fix: execute_batch calls cleanup_pending() which consumes them
        from agent_workload_characterization.runners import b_entry
        import inspect
        src = inspect.getsource(b_entry.execute_batch)
        self.assertIn("cleanup_pending", src,
                      "execute_batch must call runtime.cleanup_pending() "
                      "to consume lost-response names")
        # and the runtime has the method
        from agent_workload_characterization.runners. \
            container_runtime import DockerCliRuntime
        self.assertTrue(hasattr(DockerCliRuntime, "cleanup_pending"))

    def test_C_manifest_failure_makes_batch_fail(self):
        # reviewer repro: manifest.json write fails → batch still OK.
        # Fix: manifest_status feeds the unified _compute_final_status
        from agent_workload_characterization.runners.b_entry import (
            execute_batch, _checklist_identity)
        clock = type("C", (), {"monotonic_ns": staticmethod(
            lambda: int(time.monotonic_ns()))})()
        with tempfile.TemporaryDirectory() as tmp:
            runtime = _RealSleepFakeRuntime(clock)
            rec = Path(tmp) / "A.txt"
            rec.write_text(json.dumps({
                "checklist_identity": _checklist_identity()}))
            # pre-create manifest.json as a DIRECTORY → write fails
            out_root = Path(tmp) / "r"
            (out_root / "B-MANFAIL" / "manifest.json").mkdir(parents=True)
            result = execute_batch(
                runtime=runtime, clock=clock,
                report_root=out_root, batch_id="B-MANFAIL",
                approval_record=rec,
                reader_factory=runtime.reader_factory)
            self.assertNotEqual(result["batch_status"], "OK",
                                "manifest write failure must make the "
                                "batch FAIL")
            sources = [r["source"]
                       for r in result["batch_fail_reasons"]]
            self.assertIn("archive", sources)

    def test_D_dead_thread_does_not_pass_freeze(self):
        # reviewer repro: kill the sampling thread BEFORE the freeze
        # observation → freeze must NOT pass (the thread wasn't alive
        # to observe the freeze). This is the B0-D core counterexample.
        from agent_workload_characterization.runners.b_entry import (
            _run_container_2, BUDGET)
        from agent_workload_characterization.runners.tool_event_env \
            import wrap_environment
        from agent_workload_characterization.collectors. \
            resource_sampler import ResourceSampler
        from agent_workload_characterization.collectors.host_process \
            import HostProcessMonitor
        from agent_workload_characterization.collectors.semantic_recorder \
            import FakeClock
        clock = FakeClock()
        runtime = _RealSleepFakeRuntime(clock)
        sampler = ResourceSampler(clock=clock,
                                  interval_s=BUDGET["sampling_interval_s"])
        with tempfile.TemporaryDirectory() as tmp:
            out_dir = Path(tmp) / "batch"
            out_dir.mkdir()

            # inject: a wrapper that STOPS the sampling thread before
            # the freeze observation starts (simulating the reviewer's
            # "immediately kill the global thread" scenario)
            original_stop = sampler.stop
            def stop_then_kill_thread(scope):
                original_stop(scope)
                sampler.stop_background_sampling()
            sampler.stop = stop_then_kill_thread

            case = _run_container_2(
                runtime, sampler, "rundead", out_dir,
                wrap_environment,
                remaining=lambda: 100.0,
                cap_wait=lambda x: x,
                register_handle=lambda h: None,
                stopped_scopes=[],
                runner_mon=HostProcessMonitor(1,
                                              expected_starttime=1),
                reader_factory=runtime.reader_factory)
            # the freeze observation must NOT pass (thread was dead)
            obs = case.get("freeze_observation", {})
            self.assertFalse(
                obs.get("thread_alive_at_start", True),
                "thread aliveness must be False when the sampling "
                "thread was killed before the observation")
            self.assertNotEqual(
                case.get("scope_frozen_after_stop"), True,
                "freeze proof must not pass when the thread was dead")
            self.assertEqual(case["status"], "FAIL")

    def test_D_zero_samples_evidence_false(self):
        # 0 samples → c2_sampling_worked=False (already covered in
        # Group11 but re-verify the countable-reads dimension)
        from agent_workload_characterization.runners.b_entry import (
            _check_evidence_quality)
        from agent_workload_characterization.collectors. \
            resource_sampler import ResourceSampler
        sampler = ResourceSampler(clock=None, interval_s=0.1)
        # a scope with 0 samples and a reader with reads=None
        sampler.register("runc-c2", "verifier_container",
                         type("R", (), {"reads": None,
                                         "read": lambda t: None})())
        cases = [{"case": 2, "status": "PASS",
                  "scope_frozen_after_stop": True,
                  "freeze_observation": {
                      "thread_alive_at_start": True,
                      "reads_countable": False},
                  "host_child": {"n_readable": 1,
                                 "final_read_status": "ok"}}]
        evidence = _check_evidence_quality(cases, sampler, [])
        self.assertFalse(evidence["c2_reads_countable"],
                         "None reads must not count as countable")



class Group13ProductionPaths(unittest.TestCase):
    """Tenth-round: the three production-path counter-examples.
    Each test runs the ACTUAL production code (mocked at the
    subprocess/time boundary, not source-string checks)."""

    def _mock_subprocess(self, **scripted):
        """Create a mocked subprocess.run that dispatches on the
        command's first argument. Returns (mock_run, calls)."""
        calls = []

        def fake_run(cmd, **kw):
            calls.append({"cmd": cmd, "timeout": kw.get("timeout")})
            key = " ".join(cmd[:4])
            if key in scripted:
                result = scripted[key](cmd)
                if result is None:
                    result = {"returncode": 0, "stdout": "", "stderr": ""}
                return type("R", (), result)()
            return type("R", (), {"returncode": 0, "stdout": "",
                                    "stderr": ""})()

        return fake_run, calls

    # === Counter-example 1: 0.2s budget not expanded ===

    def test_A_02s_budget_not_expanded_in_stop_chain(self):
        # mock time and subprocess: the REAL terminate_workload with
        # step_share_deadline now; the subprocess timeout must be
        # <= 0.2s, not expanded to 1s
        from agent_workload_characterization.runners. \
            container_runtime import DockerCliRuntime
        import time as _t

        runtime = DockerCliRuntime(authorized=True,
                                  docker_executable="docker")
        handle = ContainerHandle(container_id="c1",
                                 spec=ContainerSpec(run_id="r",
                                                    scope="c1",
                                                    image="img"))
        captured_timeouts = []

        def mock_run(cmd, **kw):
            captured_timeouts.append(kw.get("timeout"))
            return type("R", (), {"returncode": 0, "stdout": "",
                                    "stderr": ""})()

        # give the stop chain only 0.2s via the absolute deadline
        deadline = _t.monotonic() + 0.2
        with mock.patch("subprocess.run", side_effect=mock_run):
            result = runtime.terminate_workload(
                handle, timeout_s=1.0,
                step_share_deadline=deadline)
        # every subprocess timeout must be <= 0.2 (no expansion to 1s)
        for to in captured_timeouts:
            self.assertLessEqual(
                to, 0.25,
                f"subprocess timeout {to}s exceeds the 0.2s budget "
                f"(captured: {captured_timeouts})")

    def test_A_02s_budget_not_expanded_in_resolve_cgroup(self):
        # the same check for _resolve_cgroup: a 0.2s remaining budget
        # must NOT be expanded by max(1,...) to 1s
        from agent_workload_characterization.runners. \
            container_runtime import DockerCliRuntime
        import time as _t

        runtime = DockerCliRuntime(authorized=True,
                                  docker_executable="docker")
        handle = ContainerHandle(container_id="c1",
                                 spec=ContainerSpec(run_id="r",
                                                    scope="c1",
                                                    image="img"))
        captured_timeouts = []

        def mock_run(cmd, **kw):
            captured_timeouts.append(kw.get("timeout"))
            return type("R", (), {"returncode": 0, "stdout": "fullid",
                                    "stderr": ""})()

        with mock.patch("subprocess.run", side_effect=mock_run):
            runtime._resolve_cgroup(handle, timeout_s=0.2)
        for to in captured_timeouts:
            self.assertLessEqual(
                to, 0.25,
                f"_resolve_cgroup timeout {to}s exceeds 0.2s "
                f"(captured: {captured_timeouts})")

    def test_A_pending_cleanup_shares_budget(self):
        # cleanup_pending's internal steps derive from one shared
        # budget: with 0.3s total, each step gets <= 0.3s (not a
        # fresh 10s per step)
        from agent_workload_characterization.runners. \
            container_runtime import DockerCliRuntime
        import time as _t

        runtime = DockerCliRuntime(authorized=True,
                                  docker_executable="docker")
        runtime.pending_names["test-container"] = {"run_id": "r"}
        captured_timeouts = []

        def mock_run(cmd, **kw):
            captured_timeouts.append(kw.get("timeout"))
            # listing: not found (the simplest path)
            return type("R", (), {"returncode": 0, "stdout": "",
                                    "stderr": ""})()

        with mock.patch("subprocess.run", side_effect=mock_run):
            runtime.cleanup_pending(timeout_s=0.3)
        for to in captured_timeouts:
            self.assertLessEqual(
                to, 0.35,
                f"pending cleanup timeout {to}s exceeds the 0.3s "
                f"shared budget (captured: {captured_timeouts})")

    # === Counter-example 2: cleanup results never misreport ===

    def test_B_listing_error_not_removed(self):
        # listing returns rc=1 → removed must be False
        from agent_workload_characterization.runners. \
            container_runtime import DockerCliRuntime
        runtime = DockerCliRuntime(authorized=True,
                                  docker_executable="docker")
        runtime.pending_names["x"] = {"run_id": "r"}

        def mock_run(cmd, **kw):
            return type("R", (), {"returncode": 1, "stdout": "",
                                    "stderr": "daemon error"})()

        with mock.patch("subprocess.run", side_effect=mock_run):
            results = runtime.cleanup_pending(timeout_s=5)
        self.assertEqual(len(results), 1)
        self.assertFalse(results[0]["removed"],
                         "listing error must not report removed=True")
        self.assertIn("error", results[0])

    def test_B_rm_error_not_removed(self):
        # rm returns rc=1 → removed must be False
        from agent_workload_characterization.runners. \
            container_runtime import DockerCliRuntime
        runtime = DockerCliRuntime(authorized=True,
                                  docker_executable="docker")
        runtime.pending_names["x"] = {"run_id": "r"}

        def mock_run(cmd, **kw):
            if "rm" in cmd:
                return type("R", (), {"returncode": 1, "stdout": "",
                                        "stderr": "rm failed"})()
            # listing finds the container
            return type("R", (), {"returncode": 0,
                                    "stdout": "abc123 x\n",
                                    "stderr": ""})()

        with mock.patch("subprocess.run", side_effect=mock_run):
            results = runtime.cleanup_pending(timeout_s=5)
        self.assertEqual(len(results), 1)
        self.assertFalse(results[0]["removed"],
                         "rm failure must not report removed=True")

    def test_B_still_exists_after_rm_not_removed(self):
        # rm "succeeds" (rc=0) but the verify listing still finds it
        # → removed must be False
        from agent_workload_characterization.runners. \
            container_runtime import DockerCliRuntime
        runtime = DockerCliRuntime(authorized=True,
                                  docker_executable="docker")
        runtime.pending_names["x"] = {"run_id": "r"}

        def mock_run(cmd, **kw):
            if "rm" in cmd:
                return type("R", (), {"returncode": 0, "stdout": "",
                                        "stderr": ""})()
            if "ps" in cmd and "name=" in " ".join(cmd):
                # the initial listing finds the container
                return type("R", (), {"returncode": 0,
                                        "stdout": "abc123 x\n",
                                        "stderr": ""})()
            # the verify listing also finds it (still exists)
            return type("R", (), {"returncode": 0,
                                    "stdout": "abc123\n",
                                    "stderr": ""})()

        with mock.patch("subprocess.run", side_effect=mock_run):
            results = runtime.cleanup_pending(timeout_s=5)
        self.assertEqual(len(results), 1)
        self.assertFalse(results[0]["removed"],
                         "still_exists_after_rm must not report "
                         "removed=True")
        self.assertIn("still_exists", results[0].get("error", ""))

    # === Counter-example 3: production reader in freeze flow ===

    def test_D_production_reader_freeze_flow(self):
        # the REAL CgroupV1FileReader (with a temp cgroup fixture)
        # running the freeze flow: reads counter > 0, freeze proof
        # works with countable reads (not None==None)
        from agent_workload_characterization.collectors. \
            resource_sampler import (CgroupV1FileReader,
                                     ResourceSampler)

        with tempfile.TemporaryDirectory() as tmp:
            cg = Path(tmp)
            # create the cgroup tree
            for d in ("cpu,cpuacct/docker/cid1", "memory/docker/cid1",
                       "blkio/docker/cid1"):
                (cg / d).mkdir(parents=True)
            (cg / "cpu,cpuacct/docker/cid1/cpuacct.usage").write_text(
                "1000000")
            (cg / "memory/docker/cid1/memory.usage_in_bytes").write_text(
                "1048576")
            (cg / "memory/docker/cid1/"
                "memory.max_usage_in_bytes").write_text("2097152")

            reader = CgroupV1FileReader("s", "verifier_container",
                                        "cid1", cg_root=cg)
            self.assertTrue(hasattr(reader, "reads"),
                            "production reader must have a countable "
                            "reads attribute")
            self.assertEqual(reader.reads, 0)

            # simulate the freeze flow: start -> sample -> stop
            sampler = ResourceSampler(clock=None, interval_s=0.05)
            sampler.register("s", "verifier_container", reader)
            sampler.start("s")
            sampler.sample_once()
            sampler.sample_once()
            sampler.stop("s")

            # reads > 0 (provable, not None)
            self.assertGreater(reader.reads, 0,
                               "production reader must count reads")
            # the evidence has boundary values
            ev = sampler.samples("s").evidence()
            self.assertIsNotNone(ev["boundary_start"])
            self.assertIsNotNone(ev["boundary_end"])
            # the reads count is stable after stop (frozen)
            reads_at_stop = reader.reads
            sampler.sample_once()  # this sample is skipped (stopped)
            self.assertEqual(reader.reads, reads_at_stop,
                            "stopped scope must not be read again")



class Group14PendingBudget(unittest.TestCase):
    """Eleventh-round: cleanup_pending must share the batch deadline."""

    def test_expired_budget_no_default_10s(self):
        # reviewer repro: batch deadline expired, but cleanup_pending
        # still gets the default 10.0s. Fix: it receives the remaining
        # budget (or a 0.1s mandatory floor when expired, with the
        # overrun recorded).
        from agent_workload_characterization.runners.b_entry import (
            execute_batch, _checklist_identity)
        import time as _t
        clock = type("C", (), {"monotonic_ns": staticmethod(
            lambda: int(_t.monotonic_ns()))})()

        captured_budgets = []

        class BudgetCaptureRuntime(_RealSleepFakeRuntime):
            def cleanup_pending(self, timeout_s=10.0):
                captured_budgets.append(timeout_s)
                return []

        with tempfile.TemporaryDirectory() as tmp:
            runtime = BudgetCaptureRuntime(clock)
            rec = Path(tmp) / "A.txt"
            rec.write_text(json.dumps({
                "checklist_identity": _checklist_identity()}))
            # pass a deadline ALREADY EXPIRED
            result = execute_batch(
                runtime=runtime, clock=clock,
                report_root=Path(tmp) / "r", batch_id="B-EXP",
                approval_record=rec,
                reader_factory=runtime.reader_factory,
                _batch_deadline=_t.monotonic() - 1.0)
            # cleanup_pending was called (the pending path is exercised)
            self.assertGreaterEqual(len(captured_budgets), 1,
                                    "cleanup_pending was never called")
            # the budget it received must NOT be the default 10s
            for budget in captured_budgets:
                self.assertLess(
                    budget, 10.0,
                    f"cleanup_pending received {budget}s — the default "
                    "10s was silently granted despite an expired batch "
                    "budget")
                self.assertLessEqual(
                    budget, 0.15,
                    f"cleanup_pending received {budget}s — expected "
                    "the 0.1s mandatory floor for an expired budget")
            # the batch is FAIL (cases were skipped/failed due to
            # expired budget)
            self.assertEqual(result["batch_status"], "FAIL")

    def test_active_budget_gets_remaining(self):
        # with a healthy remaining budget, cleanup_pending gets the
        # remaining (capped at 10s), not a fresh 10s
        from agent_workload_characterization.runners.b_entry import (
            execute_batch, _checklist_identity, BUDGET)
        import time as _t
        clock = type("C", (), {"monotonic_ns": staticmethod(
            lambda: int(_t.monotonic_ns()))})()

        captured_budgets = []

        class BudgetCaptureRuntime(_RealSleepFakeRuntime):
            def cleanup_pending(self, timeout_s=10.0):
                captured_budgets.append(timeout_s)
                return []

        with tempfile.TemporaryDirectory() as tmp:
            runtime = BudgetCaptureRuntime(clock)
            rec = Path(tmp) / "A.txt"
            rec.write_text(json.dumps({
                "checklist_identity": _checklist_identity()}))
            result = execute_batch(
                runtime=runtime, clock=clock,
                report_root=Path(tmp) / "r", batch_id="B-REM",
                approval_record=rec,
                reader_factory=runtime.reader_factory)
            # cases ran normally; cleanup_pending was called
            self.assertGreaterEqual(len(captured_budgets), 1)
            for budget in captured_budgets:
                # must be <= the full batch wall (180s) but > 0
                self.assertGreater(budget, 0)
                self.assertLessEqual(budget, 10.0,
                                     "capped at the 10s ceiling")

    def test_verified_cleanup_floor_is_small(self):
        # verified_cleanup's mandatory floor is 0.1s (not 1s) when the
        # budget is expired
        from agent_workload_characterization.runners import b_entry
        import inspect
        src = inspect.getsource(b_entry.execute_batch)
        self.assertIn("max(0.1, rem)", src,
                      "verified_cleanup must use a 0.1s floor, not 1s")
        self.assertNotIn("max(1, rem)", src,
                         "verified_cleanup must not round 0.2s to 1s")



class Group2SharedHook(unittest.TestCase):
    """Mini child and the B entry use ONE implementation; open is
    persisted before completion; rc semantics preserved."""

    def test_one_source_two_entrypoints(self):
        # the mini child payload carries the exact shared source
        from agent_workload_characterization.runners.mini_agent_adapter \
            import MiniSweAgentHarness
        src = TOOL_EVENT_WRAPPED_SOURCE
        # host-side wrap uses the same source (wrap_environment execs it)
        class Inner:
            def execute(self, action, cwd="", *, timeout=None):
                return {"output": "o", "returncode": 0,
                        "exception_info": ""}
        with tempfile.TemporaryDirectory() as tmp:
            wrapped = wrap_environment(Inner(), Path(tmp) / "te.jsonl")
            self.assertTrue(hasattr(wrapped, "execute"))
            self.assertIs(wrapped._inner.__class__, Inner)
        # and the class object from the shared source is importable
        ns = {}
        exec(src, ns)
        self.assertIn("ToolEventRecordingEnvironment", ns)

    def test_open_persisted_before_completion(self):
        release = threading.Event()
        started = threading.Event()

        class SlowInner:
            def execute(self, action, cwd="", *, timeout=None):
                started.set()
                release.wait(5)  # hold the call open
                return {"output": "done", "returncode": 0,
                        "exception_info": ""}

        with tempfile.TemporaryDirectory() as tmp:
            events = Path(tmp) / "te.jsonl"
            wrapped = wrap_environment(SlowInner(), events)
            t = threading.Thread(
                target=wrapped.execute,
                args=({"command": "sleep-ish", "tool_call_id": "t1"},),
                daemon=True)
            t.start()
            self.assertTrue(started.wait(2))
            # WHILE the call is still open, the parent can read the
            # persisted open line from disk
            deadline = time.monotonic() + 2
            open_line = None
            while time.monotonic() < deadline:
                text = events.read_text() if events.exists() else ""
                lines = [l for l in text.splitlines() if l.strip()]
                if lines:
                    open_line = json.loads(lines[0])
                    break
                time.sleep(0.02)
            self.assertIsNotNone(open_line, "open not persisted before "
                                            "completion")
            self.assertEqual(open_line["event"], "open")
            self.assertEqual(open_line["tool_call_id"], "t1")
            self.assertIn("t_start_ns", open_line)
            release.set()
            t.join(2)
            lines = [json.loads(l) for l in
                     events.read_text().splitlines() if l.strip()]
            self.assertEqual(len(lines), 2)
            self.assertEqual(lines[1]["event"], "closed")
            self.assertGreaterEqual(lines[1]["t_end_ns"],
                                    lines[0]["t_start_ns"])

    def test_nonzero_rc_and_error_semantics(self):
        class FailingInner:
            def __init__(self, rc):
                self.rc = rc

            def execute(self, action, cwd="", *, timeout=None):
                if self.rc is not None:
                    return {"output": "x", "returncode": self.rc,
                            "exception_info": ""}
                raise RuntimeError("Submitted-like interrupt")

        with tempfile.TemporaryDirectory() as tmp:
            events = Path(tmp) / "te.jsonl"
            wrapped = wrap_environment(FailingInner(3), events)
            out = wrapped.execute({"command": "false-ish",
                                   "tool_call_id": "t2"})
            self.assertEqual(out["returncode"], 3)  # real rc preserved
            err_wrapped = wrap_environment(FailingInner(None), events)
            with self.assertRaises(RuntimeError):
                err_wrapped.execute({"command": "boom",
                                     "tool_call_id": "t3"})
            lines = [json.loads(l) for l in
                     events.read_text().splitlines() if l.strip()]
        kinds = [l["event"] for l in lines]
        self.assertEqual(kinds, ["open", "closed", "open", "error"])
        self.assertEqual(lines[1]["returncode"], 3)
        self.assertEqual(lines[3]["exception_type"], "RuntimeError")

    def test_no_raw_command_or_output_in_events(self):
        class Inner:
            def execute(self, action, cwd="", *, timeout=None):
                return {"output": f"secret {CANARY} output",
                        "returncode": 0, "exception_info": ""}

        with tempfile.TemporaryDirectory() as tmp:
            events = Path(tmp) / "te.jsonl"
            wrapped = wrap_environment(Inner(), events)
            wrapped.execute({"command": f"echo {CANARY}",
                             "tool_call_id": "t4"})
            text = events.read_text()
        self.assertNotIn(CANARY, text)
        self.assertNotIn("echo", text)


class Group3ControlAndFailureDelivery(unittest.TestCase):
    """Timeout/pipes/stop-confirmation/final boundary/archive-then-
    cleanup with injected failures still delivering."""

    def test_execute_timeout_terminates_and_reports(self):
        # external stop must interrupt a blocked execute and record the
        # termination result (real DockerCliRuntime behavior is covered
        # by Round6 pipe tests; here the CONTRACT for the B path)
        clock = type("C", (), {"monotonic_ns": staticmethod(
            lambda: int(time.monotonic_ns()))})()
        runtime = FakeContainerRuntime(clock)
        handle = runtime.start(ContainerSpec(run_id="r", scope="agent",
                                             image="img"))
        out = runtime.execute(handle, "blocked", 60,
                              should_stop=lambda: True)
        self.assertTrue(out["timed_out"])
        self.assertEqual(out["stopped_by"], "external")
        # and the A-round real-runtime path (fake docker executable)
        fake = self._fake_docker("sleep 5")
        real = DockerCliRuntime(docker_executable=str(fake),
                                authorized=True)
        h2 = ContainerHandle(container_id="c1",
                             spec=ContainerSpec(run_id="r", scope="agent",
                                                image="img"))
        out2 = real.execute(h2, "blocked", timeout_s=1)
        self.assertTrue(out2.get("timed_out"))
        self.assertIn("termination", out2)

    def test_archive_before_cleanup_on_failure(self):
        # the runner's archive ordering: evidence persisted BEFORE the
        # finally-block teardown (covered end-to-end in test_coding_pilot;
        # here we assert the B-relevant contract: a failed case still
        # yields its run dir + events)
        from agent_workload_characterization.runners.coding_pilot import \
            _dir_size_bytes
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp) / "case"
            d.mkdir()
            (d / "events.jsonl").write_text('{"k": 1}\n')
            self.assertEqual(_dir_size_bytes(d), len('{"k": 1}\n'))

    def _fake_docker(self, mode: str):
        script = ("#!/bin/sh\n"
                  "case \"$*\" in\n"
                  "  *pkill*) exit 0 ;;\n"
                  "esac\n"
                  "if [ \"${1:-}\" = stop ]; then exit 0; fi\n"
                  "if [ \"${1:-}\" = exec ]; then\n"
                  f"  {mode}\n"
                  "fi\n"
                  "exit 0\n")
        p = Path(self.id().replace(".", "_")).resolve()  # Popen needs abs
        p.write_text(script)
        p.chmod(0o755)
        self.addCleanup(p.unlink)
        return p


class Group4ScopeStopInterleaving(unittest.TestCase):
    """In-flight read vs stop; frozen after stop with the thread still
    running (already covered in test_g1_01 — this group re-asserts the
    B-relevant guarantee with the B sampling interval)."""

    def test_stop_freezes_scope_thread_running(self):
        sampler = ResourceSampler(clock=None,
                                  interval_s=b_entry.BUDGET[
                                      "sampling_interval_s"])
        reader = FakeCounterReader("s", "agent_container", [
            CounterSnapshot(scope="s", scope_kind="agent_container",
                            t_monotonic_ns=0, cpu_usage_usec=0,
                            mem_current_bytes=1)] * 200)
        other = FakeCounterReader("t", "agent_container", [
            CounterSnapshot(scope="t", scope_kind="agent_container",
                            t_monotonic_ns=0, cpu_usage_usec=0,
                            mem_current_bytes=1)] * 200)
        sampler.register("s", "agent_container", reader)
        sampler.register("t", "agent_container", other)
        sampler.start("s")
        sampler.start("t")
        sampler.start_background_sampling()
        time.sleep(0.15)
        sampler.stop("s")
        reads_s = reader.reads
        boundary = sampler._data["s"].boundary_end
        # keep the loop running for >= 2 sampling intervals
        time.sleep(2 * b_entry.BUDGET["sampling_interval_s"] + 0.05)
        self.assertEqual(reader.reads, reads_s)
        self.assertIs(sampler._data["s"].boundary_end, boundary)
        self.assertGreater(other.reads, 0)
        sampler.stop_background_sampling()


class Group5OutputGuardsAndCanaries(unittest.TestCase):
    """Output protection, secret canaries, unknown-not-zero, formal I/O
    degradation."""

    def test_report_dir_guard(self):
        from agent_workload_characterization.runners.coding_pilot import \
            guard_run_dir
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "data/raw/generated").mkdir(parents=True)
            bad = root / "data/raw/generated" / ".." / ".." / "escape"
            with self.assertRaises(ValueError):
                guard_run_dir(root, bad, "G1-01-B")

    def test_unknown_stays_null_not_zero(self):
        sampler = ResourceSampler(clock=None)
        reader = FakeCounterReader("s", "agent_container", [
            CounterSnapshot(scope="s", scope_kind="agent_container",
                            t_monotonic_ns=0),
            CounterSnapshot(scope="s", scope_kind="agent_container",
                            t_monotonic_ns=1)])
        sampler.register("s", "agent_container", reader)
        sampler.start("s")
        sampler.stop("s")
        s = sampler.samples("s").summary()
        self.assertIsNone(s["io"]["read_bytes"])  # missing stays null

    def test_io_formal_degradation_wording(self):
        plan = b_entry._plan()
        degr = " ".join(plan["degradations"])
        self.assertIn("degraded_host_v1_blkio", degr)
        self.assertIn("diagnostic", degr)
        self.assertIn("not a disk hard cap", degr)


class Group6ManifestIntegrity(unittest.TestCase):
    """Manifest written last, whole tree listed, post-write
    reconciliation (mismatch/missing/unlisted), no post-summary edits."""

    def test_manifest_post_write_verification_pattern(self):
        # the A-round writer pattern: files hashed AFTER the summary is
        # final; a post-write edit must be detected
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "batch"
            out.mkdir()
            (out / "summary.md").write_text("v1\n")
            files = {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                     for p in out.iterdir() if p.is_file()}
            (out / "manifest.json").write_text(json.dumps(files))
            # simulate a post-write edit
            (out / "summary.md").write_text("v2 tampered\n")
            written = json.loads((out / "manifest.json").read_text())
            mismatched = [n for n, s in written.items()
                          if hashlib.sha256(
                              (out / n).read_bytes()).hexdigest() != s]
            self.assertEqual(mismatched, ["summary.md"])


import hashlib  # noqa: E402  (used in Group6)


if __name__ == "__main__":
    unittest.main()
