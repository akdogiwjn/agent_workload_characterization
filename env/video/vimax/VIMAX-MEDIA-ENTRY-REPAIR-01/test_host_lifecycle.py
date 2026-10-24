#!/usr/bin/env python3
"""Host-side lifecycle regression for the REPAIR-01 runner (no docker).

FakeOps drives start_attempt through its FULL code path — the same path
production uses — which is exactly what the PILOT-02 dict-slice incident
taught us: compile checks cannot catch `record["k":"v"]` (legal syntax,
runtime TypeError). Any such line in the runner is executed here.

Cases:
  1. normal path: gate -> seed markers -> COMPLETE -> cleanup; record is
     JSON-valid at every checkpoint; no dict-slice/TypeError escapes.
  5. netns sampling failure -> runner exception; NO model-events.jsonl in
     the workspace (send count zero).
  9. persistence failure injected -> cleanup errors recorded, run-record
     still attempted, original termination preserved.
  10. tiny work window -> work_deadline termination with partial evidence.
"""
from __future__ import annotations

import json
import subprocess
import sys
import threading
import time
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import host_runner  # noqa: E402


class FakeProc:
    def __init__(self, rc=0, out=""):
        self.returncode = rc
        self.stdout = out
        self.stderr = ""

    def wait(self, timeout=None):
        return self.returncode

    def terminate(self):
        pass


class FakeOps(host_runner.RuntimeOps):
    """Deterministic docker-command simulation for the full lifecycle."""

    def __init__(self, *, fail_netns=False, fail_write=False,
                 fail_write_after=0, cid="fake" * 16):
        self.fail_netns = fail_netns
        self.fail_write = fail_write
        self.fail_write_after = fail_write_after
        self._writes = 0
        self.cid = cid
        self.commands: list[list] = []
        self.stopped = threading.Event()
        self._label = ""
        self._removed = False

    def run(self, argv, timeout=30):
        self.commands.append(list(argv))
        joined = " ".join(argv)
        if "image" in argv and "inspect" in argv:
            return FakeProc(0, host_runner.DEFAULT_CONFIG["image_id"]
                            + " linux arm64")
        if argv[:2] == host_runner.DOCKER[:2] and "run" in argv:
            for a in argv:
                if a.startswith("org.agent-workload.task="):
                    self._label = a.split("=", 1)[1]
            return FakeProc(0, self.cid)
        if "inspect" in argv and "{{.State.Running}}" in joined:
            return FakeProc(0, "true")
        if "Config.Labels" in joined:
            return FakeProc(0, self._label) if self._label else FakeProc(1, "")
        if "wait" in argv:
            return FakeProc(0, "0")
        if "logs" in argv:
            return FakeProc(0, "2026-01-01T00:00:00Z fake container log line\n")
        if "rm" in argv:
            self._removed = True
            return FakeProc(0, self.cid)
        if "stop" in argv or "kill" in argv:
            self.stopped.set()
            return FakeProc(0, "")
        if "inspect" in argv:
            # after rm the container is gone -> inspect fails (removed ok)
            return FakeProc(1, "no such object") if self._removed \
                else FakeProc(0, "true")
        return FakeProc(0, "")

    def popen(self, argv, *args, **kwargs):
        self.commands.append(list(argv))
        return FakeProc(0, "")

    def credentials(self):
        return ({"DASHSCOPE_API_KEY": "fake", "BAILIAN_WORKSPACE_ID": "ws"},
                "ws.cn-beijing.maas.aliyuncs.com")

    def net_snapshot(self, cid):
        if self.fail_netns:
            return {"read_status": "error", "error": "injected"}
        return {"t_monotonic_ns": 1, "read_status": "ok",
                "interfaces": {"eth0": {"rx_bytes": 1, "tx_bytes": 1}}}

    def write(self, path, obj):
        self._writes += 1
        if self.fail_write or self._writes > self.fail_write_after > 0:
            raise OSError("injected write failure")
        return host_runner.write(path, obj)

    # sampler: minimal fake exposing the used surface
    class _Samples:
        class _Snap:
            cpu_usage_usec = 1
            mem_current_bytes = 1

        boundary_start = _Snap()
        samples = [_Snap()]

    class _Sampler:
        def __init__(self):
            self.stopped = False

        def register(self, *a):
            pass

        def start(self, *a):
            pass

        def start_background_sampling(self):
            pass

        def stop_background_sampling(self):
            pass

        def stop(self, *a):
            self.stopped = True

        def samples(self, scope):
            return FakeOps._Samples()

        def all_scope_evidence(self):
            return {}

        def all_scope_summaries(self):
            return {}

    def sampler_factory(self):
        return FakeOps._Sampler()


def _setup_run(tmp: Path, cfg=None) -> tuple[Path, dict]:
    import shutil
    if tmp.exists():
        shutil.rmtree(tmp)
    cfg = json.loads(json.dumps(host_runner.DEFAULT_CONFIG))
    if cfg:
        pass
    # plan dir must exist for the mount source check
    (tmp).mkdir(parents=True)
    return tmp, cfg


class _DelayedMarkerDriver:
    """Real-time marker writer; COMPLETE arrives after `complete_delay`."""

    def __init__(self, out: Path, complete_delay: float = 0.3):
        attempt = out / "workspace/attempt"
        attempt.mkdir(parents=True, exist_ok=True)
        self.stop = threading.Event()
        self.t = threading.Thread(target=self._loop,
                                  args=(attempt, complete_delay), daemon=True)
        self.t.start()

    def _loop(self, attempt, delay):
        time.sleep(0.15)
        (attempt / "STARTUP-READY.json").write_text("{}")
        time.sleep(0.1)
        (attempt / "STARTUP-RELEASE.json").write_text("{}")
        time.sleep(0.1)
        (attempt / "STARTUP-ACK.json").write_text("{}")
        self.stop.wait(delay)
        (attempt / "COMPLETE").write_text(json.dumps(
            {"render_tool_ok": True, "main_agent_returncode": 0}))

    def join(self):
        self.stop.set()
        self.t.join(timeout=5)


class LifecycleTest(unittest.TestCase):
    def _run(self, ops, cfg_overrides=None, tmpname="run-x"):
        out = HERE / "runs" / tmpname
        import shutil
        if out.exists():
            shutil.rmtree(out, ignore_errors=True)
        out.mkdir(parents=True)
        cfg = json.loads(json.dumps(host_runner.DEFAULT_CONFIG))
        cfg["plan_dir"] = str(HERE)  # any existing dir works for FakeOps
        cfg.update(cfg_overrides or {})
        # the workspace attempt dir must pre-exist (host_runner creates it)
        rc, record = host_runner.start_attempt(out, cfg, ops=ops)
        return out, rc, record

    def _fake_entry_markers(self, out: Path):
        """Simulate the entry writing gate markers as the clock advances."""
        attempt = out / "workspace/attempt"

        class MarkerDriver:
            def __init__(self):
                self.t = threading.Thread(target=self._loop, daemon=True)
                self.stop = threading.Event()
                self.t.start()

            def _loop(self):
                time.sleep(0.2)
                (attempt / "STARTUP-READY.json").write_text("{}")
                time.sleep(0.1)
                (attempt / "STARTUP-RELEASE.json").write_text("{}")
                time.sleep(0.1)
                (attempt / "STARTUP-ACK.json").write_text("{}")
                time.sleep(0.3)
                (attempt / "COMPLETE").write_text(json.dumps({
                    "render_tool_ok": True, "main_agent_returncode": 0}))
                return

            def join(self):
                self.stop.set()
                self.t.join(timeout=5)
        return MarkerDriver()

    def test_normal_path_produces_valid_record(self):
        """Full lifecycle through the production code path (dict-slice and
        any runtime TypeError in the runner body would explode here)."""
        ops = FakeOps()
        out = HERE / "runs" / "lc-normal"
        import shutil
        if out.exists():
            shutil.rmtree(out, ignore_errors=True)
        out.mkdir(parents=True)
        cfg = json.loads(json.dumps(host_runner.DEFAULT_CONFIG))
        cfg["plan_dir"] = str(HERE)
        ops2 = ops
        driver = self._fake_entry_markers(out)
        try:
            rc, record = host_runner.start_attempt(out, cfg, ops=ops2)
        finally:
            driver.join()
        # validate every persisted record is JSON and well-formed
        raw = (out / "run-record.json").read_text()
        data = json.loads(raw)  # raises on any corruption
        self.assertIn(data["termination"],
                      ("native_agent_done", "container_exited_without_complete"))
        self.assertEqual(data["container"]["ownership_verified"], True)
        self.assertTrue(data["container_removed_verified"])
        self.assertEqual(data["cleanup_errors"], [])
        # the dict-slice class of bug (unhashable slice) would have raised
        # TypeError inside start_attempt and landed in runner_exception
        self.assertNotEqual(data["termination"], "runner_exception",
                            data.get("primary_error"))

    def test_netns_failure_zero_sends(self):
        ops = FakeOps(fail_netns=True)
        out, rc, record = self._run(ops, tmpname="lc-netns-fail")
        self.assertEqual(record["termination"], "runner_exception")
        self.assertIn("netns", json.dumps(record.get("primary_error", {})))
        # no model-events.jsonl was ever written (send count zero)
        self.assertFalse((out / "workspace/attempt/model-events.jsonl").exists())

    def test_persistence_failure_still_cleans_up(self):
        # first write succeeds (attempt started); every later persist fails
        ops = FakeOps(fail_write_after=1)
        out, rc, record = self._run(ops, tmpname="lc-write-fail")
        self.assertEqual(record["termination"], "runner_exception")
        self.assertTrue(any(e.startswith("run_record_write")
                            for e in record["cleanup_errors"]),
                        record["cleanup_errors"])
        # cleanup commands still issued (docker stop/rm recorded)
        joined = " ".join(" ".join(c) for c in ops.commands)
        self.assertIn("rm", joined)

    def test_work_deadline_partial_evidence(self):
        ops = FakeOps()
        out = HERE / "runs" / "lc-deadline"
        import shutil
        if out.exists():
            shutil.rmtree(out, ignore_errors=True)
        out.mkdir(parents=True)
        cfg = json.loads(json.dumps(host_runner.DEFAULT_CONFIG))
        cfg["plan_dir"] = str(HERE)
        cfg.update({"work_seconds": 1.0, "handshake_timeout_s": 5.0,
                    "closeout_seconds": 10.0})
        driver = _DelayedMarkerDriver(out, complete_delay=10.0)
        try:
            rc, record = host_runner.start_attempt(out, cfg, ops=ops)
        finally:
            driver.join()
        self.assertEqual(record["termination"], "work_deadline")
        self.assertIn("agent_work", record["phase_boundaries"])
        joined = " ".join(" ".join(c) for c in ops.commands)
        self.assertIn("kill", joined)  # deadline kills the container


if __name__ == "__main__":
    unittest.main(verbosity=2)
