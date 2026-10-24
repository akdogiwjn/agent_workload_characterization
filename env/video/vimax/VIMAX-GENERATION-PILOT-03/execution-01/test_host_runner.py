from __future__ import annotations

import ast
import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path
from subprocess import CompletedProcess
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import host_runner as hr


class Samples:
    def __init__(self):
        self.boundary_start = type("Point", (), {"cpu_usage_usec": 1, "mem_current_bytes": 10})()
        self.samples = []


class FakeSampler:
    def __init__(self, fail=False, events=None, export_fail=False):
        self.scope = Samples()
        self.fail = fail
        self.export_fail = export_fail
        self.events = events if events is not None else []
        self.stopped = False

    def register(self, *_): self.events.append("sampler_register")
    def start(self, *_): self.events.append("sampler_baseline")
    def start_background_sampling(self):
        self.events.append("sampler_start")
        if self.fail: raise RuntimeError("synthetic sampler failure")
        self.scope.samples = [type("Point", (), {"cpu_usage_usec": 2, "mem_current_bytes": 11})()]
    def samples(self, _): return self.scope
    def stop_background_sampling(self): self.events.append("sampler_stop")
    def stop(self, *_): self.events.append("sampler_boundary"); self.stopped = True
    def all_scope_evidence(self):
        if self.export_fail: raise OSError("synthetic resource export failure")
        return {"fake": {"samples": [{"cpu_usage_usec": 2, "mem_current_bytes": 11}]}}
    def all_scope_summaries(self): return {"fake": {"sample_count": len(self.scope.samples)}}


class FakeOps:
    def __init__(self, out, *, start_fail=False, owner_fail=False, sampler_fail=False,
                 no_ready=False, agent_fail=False, state_write_fail=False):
        self.out = out
        self.work = out / "workspace"
        self.events = []
        self.start_fail = start_fail
        self.owner_fail = owner_fail
        self.no_ready = no_ready
        self.agent_fail = agent_fail
        self.state_write_fail = state_write_fail
        self.export_fail = False
        self.state_write_failed = False
        self.running = False
        self.removed = False
        self.cid = "fake-container-id"
        self.sampler = FakeSampler(sampler_fail, self.events)
        self.request_sends = 0

    def run(self, argv, timeout=30):
        verb = argv[3] if len(argv) > 3 else ""
        self.events.append("docker_" + verb)
        if verb == "run":
            if self.start_fail: return CompletedProcess(argv, 1, "", "synthetic start failure")
            self.running = True
            if not self.no_ready:
                (self.work / "attempt" / "STARTUP-READY.json").write_text('{"state":"ready"}\n')
            return CompletedProcess(argv, 0, self.cid + "\n", "")
        if verb == "inspect":
            fmt = argv[5] if len(argv) > 5 else ""
            if self.removed: return CompletedProcess(argv, 1, "", "not found")
            if "Config.Labels" in fmt:
                return CompletedProcess(argv, 0, ("wrong" if self.owner_fail else self.run_id) + "\n", "")
            if "State.Running" in fmt:
                return CompletedProcess(argv, 0, ("false" if self.agent_fail else "true") + "\n", "")
            return CompletedProcess(argv, 0, "", "")
        if verb == "wait": return CompletedProcess(argv, 0, ("1" if self.agent_fail else "0") + "\n", "")
        if verb == "rm": self.removed = True; self.running = False; return CompletedProcess(argv, 0, self.cid + "\n", "")
        return CompletedProcess(argv, 0, "", "")

    def credentials(self):
        self.events.append("credentials_runtime")
        return {"DASHSCOPE_API_KEY": "synthetic-key", "BAILIAN_WORKSPACE_ID": "synthetic-workspace"}, "synthetic-workspace.cn-beijing.maas.aliyuncs.com"

    def sampler_factory(self): return self.sampler
    def cgroup_reader_factory(self, *_): return object()
    def net_snapshot(self, _):
        self.events.append("net_sample")
        return {"read_status": "ok", "t_monotonic_ns": 1, "interfaces": {"lo": {"rx_bytes": 0, "tx_bytes": 0}}}
    def monotonic(self):
        import time
        return time.monotonic()
    def sleep(self, seconds):
        import time
        time.sleep(seconds)
    def write(self, path, payload):
        if self.state_write_fail and path.name == "run-record.json" and isinstance(payload, dict) and payload.get("container", {}).get("id") and not self.state_write_failed:
            self.state_write_failed = True
            raise PermissionError("synthetic record write failure")
        hr.write(path, payload)
        if path.name == "STARTUP-RELEASE.json":
            self.events.append("release")
            (self.work / "attempt" / "STARTUP-ACK.json").write_text('{"state":"released"}\n')
            if not self.agent_fail:
                (self.work / "attempt" / "COMPLETE").write_text('{"render_tool_ok":true}\n')


def fixture(out: Path, ops: FakeOps):
    out.mkdir(parents=True)
    (out / "workspace/attempt").mkdir(parents=True)
    entry_sha = "a" * 64
    pre = {"image": {"id": hr.IMAGE_ID, "platform": "linux/arm64"}, "generation_entry_sha256": entry_sha,
           "model_config": {"llm_model": "qwen3.7-plus"}, "budget": {"llm_calls": 80}}
    hr.write(out / "preflight.json", pre)
    identity = {"task": "VIMAX-GENERATION-PILOT-03", "run_id": "pilot03-test-run", "image": pre["image"], "generation_entry_sha256": entry_sha}
    hr.write(out / "identity-01.json", identity)
    approval = {"identity_sha256": hr.sha(out / "identity-01.json")}
    hr.write(out / "APPROVAL-01.json", approval)
    ops.run_id = identity["run_id"]


class HostRunnerLifecycleTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self): self.tmp.cleanup()

    def run_attempt(self, **kwargs):
        out = self.root / "run-01"
        ops = FakeOps(out, **kwargs)
        fixture(out, ops)
        rc = hr.start_attempt(out, out / "APPROVAL-01.json", ops=ops)
        record = json.loads((out / "run-record.json").read_text())
        return rc, record, ops, out

    def test_normal_container_lifecycle_releases_only_after_sampler(self):
        rc, record, ops, _ = self.run_attempt()
        self.assertEqual(rc, 0)
        self.assertTrue(record["startup_gate"]["ready"])
        self.assertTrue(record["startup_gate"]["sampling_ready"])
        self.assertTrue(record["startup_gate"]["released"])
        self.assertTrue(record["startup_gate"]["acknowledged"])
        self.assertLess(ops.events.index("sampler_start"), ops.events.index("release"))
        self.assertTrue(record["container_removed_verified"])
        self.assertEqual(ops.request_sends, 0)

    def test_container_start_failure_does_not_attempt_sampling_or_send(self):
        rc, record, ops, _ = self.run_attempt(start_fail=True)
        self.assertEqual(rc, 1)
        self.assertEqual(record["termination"], "runner_exception")
        self.assertNotIn("sampler_start", ops.events)
        self.assertEqual(ops.request_sends, 0)

    def test_ownership_failure_removes_container_before_release(self):
        rc, record, ops, _ = self.run_attempt(owner_fail=True)
        self.assertEqual(rc, 1)
        self.assertIn("ownership verification failed", record["primary_error"]["message"])
        self.assertFalse(record["startup_gate"]["released"])
        self.assertTrue(record["container_removed_verified"])

    def test_run_record_write_failure_blocks_release_and_cleans_container(self):
        rc, record, ops, _ = self.run_attempt(state_write_fail=True)
        self.assertEqual(rc, 1)
        self.assertFalse(record["startup_gate"]["released"])
        self.assertTrue(record["container_removed_verified"])
        self.assertEqual(ops.request_sends, 0)

    def test_sampler_failure_blocks_agent_and_removes_container(self):
        rc, record, ops, _ = self.run_attempt(sampler_fail=True)
        self.assertEqual(rc, 1)
        self.assertFalse(record["startup_gate"]["released"])
        self.assertTrue(record["container_removed_verified"])
        self.assertEqual(ops.request_sends, 0)

    def test_agent_exit_without_complete_still_stops_sampler_and_cleans(self):
        rc, record, ops, _ = self.run_attempt(agent_fail=True)
        self.assertEqual(rc, 1)
        self.assertEqual(record["termination"], "container_exited_without_complete")
        self.assertIn("sampler_stop", ops.events)
        self.assertTrue(record["container_removed_verified"])

    def test_report_failure_does_not_skip_sampler_or_container_cleanup(self):
        out = self.root / "run-01"; ops = FakeOps(out); fixture(out, ops)
        with patch.object(hr, "summarize", side_effect=OSError("synthetic report failure")):
            rc = hr.start_attempt(out, out / "APPROVAL-01.json", ops=ops)
        record = json.loads((out / "run-record.json").read_text())
        self.assertEqual(rc, 1)
        self.assertEqual(record["report_generation"]["status"], "failed")
        self.assertIn("run_report:OSError", record["cleanup_errors"])
        self.assertTrue(record["container_removed_verified"])
        self.assertIn("sampler_stop", ops.events)

    def test_resource_export_failure_does_not_skip_container_cleanup(self):
        out = self.root / "run-01"; ops = FakeOps(out); fixture(out, ops)
        ops.sampler.export_fail = True
        rc = hr.start_attempt(out, out / "APPROVAL-01.json", ops=ops)
        record = json.loads((out / "run-record.json").read_text())
        self.assertEqual(rc, 1)
        self.assertTrue(record["container_removed_verified"])
        self.assertIn("resource_export:OSError", record["cleanup_errors"])
        self.assertIn("sampler_stop", ops.events)

    def test_missing_handshake_times_out_without_release_or_sends(self):
        out = self.root / "run-01"; ops = FakeOps(out, no_ready=True); fixture(out, ops)
        with patch.object(hr, "STARTUP_HANDSHAKE_TIMEOUT_S", .12):
            rc = hr.start_attempt(out, out / "APPROVAL-01.json", ops=ops)
        record = json.loads((out / "run-record.json").read_text())
        self.assertEqual(rc, 1)
        self.assertFalse(record["startup_gate"]["released"])
        self.assertTrue(record["container_removed_verified"])
        self.assertEqual(ops.request_sends, 0)

    def test_original_dict_slice_antipattern_is_detected(self):
        historical = 'record["route_workspace_host_value":"redacted"]'
        parsed = ast.parse(historical, mode="exec")
        def bad_record_slice(tree):
            return any(isinstance(n, ast.Subscript) and isinstance(n.value, ast.Name)
                       and n.value.id == "record" and isinstance(n.slice, ast.Slice)
                       for n in ast.walk(tree))
        has_slice = bad_record_slice(parsed)
        current = ast.parse((HERE / "host_runner.py").read_text())
        current_has_slice = bad_record_slice(current)
        self.assertTrue(has_slice)
        self.assertFalse(current_has_slice)


if __name__ == "__main__":
    unittest.main(verbosity=2)
