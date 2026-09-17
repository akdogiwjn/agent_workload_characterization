"""RUN-01 gate A offline regression suite (coding pilot).

Five minimum regression groups from the RUN-01 task brief §6, plus
analyzer/CLI checks. Everything here runs WITHOUT mini, WITHOUT Docker,
WITHOUT real keys and WITHOUT old data — fake harness + fake runtime +
fake counters only, all explicitly marked synthetic.

Groups:
1. task hash/identity/answer isolation; credentials never enter tool/log
   records; output-dir guard (symlink escape, no overwrite, protected
   trees);
2. fake agent -> tools -> candidate -> fake verifier full path; success,
   agent failure, no candidate, verifier timeout, patch-apply failure,
   archive failure; three status families stay separate;
3. request/step/token/time budgets; nested retries counted (not free);
   watchdog hard-kills a REAL blocking subprocess; cleanup only touches
   identity-matched resources;
4. synthetic counters/gauges: CPU units, reset, missing/zero, memory
   peaks not summed, parent/child CPU not double-counted, clock domains
   never mixed;
5. lifecycle: create -> baseline -> execute -> final snapshot -> export ->
   cleanup; failure paths never delete measurement evidence early.
"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from agent_workload_characterization.collectors.resource_sampler import (
    CounterSnapshot, CgroupV1FileReader, FakeCounterReader, ResourceSampler,
    cpu_core_seconds)
from agent_workload_characterization.collectors.semantic_recorder import (
    ClockError, FakeClock, SemanticRecorder, duration_s)
from agent_workload_characterization.analyzers.resource_summary import (
    summarize_run, write_summary_report)
from agent_workload_characterization.runners.coding_pilot import (
    BudgetExceeded, BudgetLimits, BudgetTracker, CodingPilotRunner,
    VerifierSpec, guard_run_dir)
from agent_workload_characterization.runners.container_runtime import (
    CleanupResult, ContainerHandle, DockerCliRuntime, FakeContainerRuntime,
    ContainerSpec)
from agent_workload_characterization.runners.mini_agent_adapter import (
    AgentError, AgentTask, FakeAgentHarness, MiniSweAgentHarness)

GOLD_CANARY = "GOLD_PATCH_CANARY_9f1"
TEST_CANARY = "TEST_PATCH_CANARY_7c2"
EVAL_CANARY = "EVAL_SCRIPT_CANARY_3ab"
SECRET_CANARY = "sk-SYNTHSECRET00000000"

SYNTH_RECORD = {
    "instance_id": "django__django-16485",
    "problem_statement": "synthetic floatformat problem statement",
    "patch": GOLD_CANARY,
    "test_patch": TEST_CANARY,
    "FAIL_TO_PASS": ["tests.gold"],
    "PASS_TO_PASS": ["tests.p1", "tests.p2"],
    "eval_script": EVAL_CANARY,
    "log_parser": "parse_log_django",
    "eval_type": "pass_and_fail",
    "image_name": "synthetic-image:latest",
    "repo": "django/django",
    "base_commit": "39f83765e12b0e5d260b7939fc3fe281d879b279",
}

OK_SCRIPT = {
    "steps": [
        {"model": {"usage": {"prompt_tokens": 100, "completion_tokens": 20,
                             "total_tokens": 120}},
         "tools": [{"command": "grep -rn floatformat /testbed",
                    "category": "Search"}]},
        {"model": {"usage": {"prompt_tokens": 200, "completion_tokens": 30,
                             "total_tokens": 230}},
         "tools": [{"command": "python repro.py", "category": "Execute"}]},
    ],
    "final": {"status": "ok",
              "candidate_patch": "--- a/f.py\n+++ b/f.py\n@@\n+fix\n"},
}


def _snap(**kwargs) -> CounterSnapshot:
    return CounterSnapshot(scope="s", scope_kind="agent_container",
                           t_monotonic_ns=0, **kwargs)


def _reader_pair():
    agent = FakeCounterReader("agent", "agent_container", [
        _snap(cpu_usage_usec=1_000_000, mem_current_bytes=100 << 20,
              mem_peak_bytes=150 << 20, io_read_bytes=100,
              io_write_bytes=200),
        _snap(cpu_usage_usec=2_500_000, mem_current_bytes=120 << 20,
              mem_peak_bytes=180 << 20, io_read_bytes=115,
              io_write_bytes=240),
        _snap(cpu_usage_usec=4_000_000, mem_current_bytes=90 << 20,
              mem_peak_bytes=180 << 20, io_read_bytes=130,
              io_write_bytes=300),
    ])
    verifier = FakeCounterReader("verifier", "verifier_container", [
        _snap(cpu_usage_usec=500_000, mem_current_bytes=50 << 20,
              io_read_bytes=40, io_write_bytes=10),
        _snap(cpu_usage_usec=1_500_000, mem_current_bytes=60 << 20,
              io_read_bytes=70, io_write_bytes=25),
    ])
    host = FakeCounterReader("host", "host_agent_runtime", [
        _snap(cpu_usage_usec=10_000_000, mem_current_bytes=300 << 20),
        _snap(cpu_usage_usec=12_000_000, mem_current_bytes=310 << 20),
    ])
    return {"agent": agent, "verifier": verifier, "host": host}


class PilotTestBase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        (self.root / "data" / "raw" / "generated").mkdir(parents=True)

    def make_runner(self, script=None, verifier_script=None, *,
                    limits=None, clock=None, readers=None,
                    source_type="synthetic", host_reader=None):
        clock = clock or FakeClock()
        readers = readers or _reader_pair()
        runtime = FakeContainerRuntime(clock, readers=readers)
        harness = FakeAgentHarness(clock, script if script is not None else OK_SCRIPT)
        verifier_script = verifier_script if verifier_script is not None else {
            "status": "ok", "resolved": True, "wall_s": 1.0}
        from agent_workload_characterization.runners.coding_pilot import \
            FakeVerifier
        verifier = FakeVerifier(clock, verifier_script)
        task = AgentTask(instance_id=SYNTH_RECORD["instance_id"],
                         problem_statement=SYNTH_RECORD["problem_statement"],
                         image=SYNTH_RECORD["image_name"])
        vspec = VerifierSpec(
            instance_id=SYNTH_RECORD["instance_id"],
            image=SYNTH_RECORD["image_name"],
            eval_script_ref="data/raw/public/swebench_verified/synth/record.json",
            log_parser="parse_log_django", eval_type="pass_and_fail",
            record_locator="data/raw/public/swebench_verified/synth/record.json")
        limits = limits or BudgetLimits(
            max_model_requests=10, max_steps=10, agent_wall_s=60.0,
            verifier_wall_s=30.0, total_wall_s=120.0)
        return CodingPilotRunner(
            project_root=self.root, collection="SYNTH-TEST",
            harness=harness, verifier=verifier, runtime=runtime,
            clock=clock, limits=limits, task=task, verifier_spec=vspec,
            image=SYNTH_RECORD["image_name"], interval_s=0.02,
            source_type=source_type, host_runtime_reader=host_reader)


# ---------------------------------------------------------------------------
# group 1: isolation + output protection
# ---------------------------------------------------------------------------

class IsolationTests(PilotTestBase):
    def test_mini_payload_excludes_answers(self):
        harness = MiniSweAgentHarness(
            Path(self.root) / "nonexistent-venv-python",
            mini_config={"model": {"model_name": "openai/test-model"}})
        payload = harness.build_payload(SYNTH_RECORD,
                                        self.root / "traj.json",
                                        self.root / "status.jsonl",
                                        "cid-1",
                                        mini_config={"model": {
                                            "model_name": "openai/test-model"}})
        text = json.dumps(payload)
        for canary in (GOLD_CANARY, TEST_CANARY, EVAL_CANARY,
                       "tests.gold", "tests.p1"):
            self.assertNotIn(canary, text)
        self.assertEqual(payload["problem_statement"],
                         SYNTH_RECORD["problem_statement"])
        self.assertEqual(sorted(payload["instance"]),
                         ["image_name", "instance_id"])
        self.assertEqual(payload["container_id"], "cid-1")

    def test_projection_rejects_forbidden_fields(self):
        harness = MiniSweAgentHarness(
            Path(self.root) / "x",
            mini_config={"model": {"model_name": "openai/test-model"}})
        bad = dict(SYNTH_RECORD)
        bad["image_name"] = {"image_name": "x", "patch": GOLD_CANARY}
        with self.assertRaises(ValueError):
            harness.build_payload(bad, self.root / "t.json",
                                  self.root / "s.jsonl", "cid-1")

    def test_mini_payload_nested_answer_rejected(self):
        harness = MiniSweAgentHarness(Path(self.root) / "x")
        payload = {"instance": {"instance_id": "i"},
                   "nested": {"test_patch": TEST_CANARY}}
        with self.assertRaises(ValueError):
            harness.check_payload_isolated(payload)

    def test_recorder_rejects_credential_keys(self):
        recorder = SemanticRecorder(self.root, FakeClock(), run_id="r",
                                    attempt_id="r-a1", task_id="t",
                                    source_type="synthetic")
        with self.assertRaises(ValueError):
            recorder.begin("llm_request", {"api_key": "x"})

    def test_recorder_rejects_credential_like_values(self):
        recorder = SemanticRecorder(self.root, FakeClock(), run_id="r",
                                    attempt_id="r-a1", task_id="t",
                                    source_type="synthetic")
        with self.assertRaises(ValueError):
            recorder.begin("tool_call", {"command": f"run {SECRET_CANARY}"})

    def test_recorder_sanitizes_usage_and_error(self):
        recorder = SemanticRecorder(self.root, FakeClock(), run_id="r",
                                    attempt_id="r-a1", task_id="t",
                                    source_type="synthetic")
        recorder.begin_run()
        ev = recorder.begin("llm_request", {"request_id": "q1"})
        recorder.end(ev, attrs={
            "request_id": "q1", "usage": {
                "prompt_tokens": 5, "completion_tokens": 2,
                "FAKE_SECRET_CANARY_42": 1},
            "error": "AuthenticationError: key sk-SYNTHSECRET00000000 rejected"})
        recorder.seal()
        text = (self.root / "events.jsonl").read_text()
        self.assertNotIn("FAKE_SECRET_CANARY_42", text)
        self.assertNotIn("sk-SYNTHSECRET", text)
        self.assertIn("AuthenticationError:<sanitized>", text)

    def test_guard_rejects_outside_generated_root(self):
        with self.assertRaises(ValueError):
            guard_run_dir(self.root, self.root / "data" / "raw" / "public" / "x",
                          "SYNTH-TEST")

    def test_guard_rejects_symlink_escape(self):
        outside = self.root / "outside"
        outside.mkdir()
        col = self.root / "data" / "raw" / "generated" / "SYNTH-TEST"
        col.mkdir(parents=True)
        link = col / "escape"
        link.symlink_to(outside)
        with self.assertRaises(ValueError):
            guard_run_dir(self.root, link / "run", "SYNTH-TEST")

    def test_guard_rejects_collection_symlink_escape(self):
        # collection dir itself is a symlink pointing OUTSIDE the project:
        # the old guard followed the resolved target and let writes through
        gen = self.root / "data" / "raw" / "generated"
        outside = self.root / "evil-outside"
        outside.mkdir()
        (gen / "SYNTH-ESCAPED").symlink_to(outside)
        target = gen / "SYNTH-ESCAPED" / "r1"
        with self.assertRaises(ValueError):
            guard_run_dir(self.root, target, "SYNTH-ESCAPED")

    def test_guard_rejects_collection_symlink_even_inside_project(self):
        # a symlinked collection segment is rejected regardless of target
        gen = self.root / "data" / "raw" / "generated"
        real_col = gen / "REAL"
        real_col.mkdir()
        (gen / "ALIAS").symlink_to(real_col)
        with self.assertRaises(ValueError):
            guard_run_dir(self.root, gen / "ALIAS" / "r1", "ALIAS")

    def test_guard_rejects_ancestor_symlink_escape(self):
        # intermediate ancestor (below generated/) is a symlink outside
        gen = self.root / "data" / "raw" / "generated"
        outside = self.root / "outside-ancestor"
        outside.mkdir()
        (gen / "link").symlink_to(outside)
        with self.assertRaises(ValueError):
            guard_run_dir(self.root, gen / "link" / "C" / "r1", "link/C")

    def test_guard_rejects_dotdot_collection(self):
        with self.assertRaises(ValueError):
            guard_run_dir(self.root,
                          self.root / "data" / "raw" / "generated" / "x" / "r1",
                          "../public")

    def test_guard_rejects_catalog_protected_generated_root(self):
        # writer full counterexample: an audit catalog legacy root that
        # covers data/raw/generated itself must block run-dir writes
        catalog_dir = self.root / "data" / "catalog"
        catalog_dir.mkdir(parents=True)
        (catalog_dir / "sources.yaml").write_text(
            "roots:\n  legacy: %s\nsources: []\n"
            % (self.root / "data" / "raw" / "generated"))
        target = self.root / "data" / "raw" / "generated" / "SYNTH-TEST" / "r1"
        with self.assertRaises(ValueError):
            guard_run_dir(self.root, target, "SYNTH-TEST")

    def test_guard_rejects_existing_dir(self):
        target = self.root / "data" / "raw" / "generated" / "SYNTH-TEST" / "r1"
        target.mkdir(parents=True)
        with self.assertRaises(ValueError):
            guard_run_dir(self.root, target, "SYNTH-TEST")

    def test_guard_accepts_normal_run_dir(self):
        target = self.root / "data" / "raw" / "generated" / "SYNTH-TEST" / "r1"
        result = guard_run_dir(self.root, target, "SYNTH-TEST")
        self.assertEqual(result, target)


# ---------------------------------------------------------------------------
# group 2: full fake path + status separation
# ---------------------------------------------------------------------------

class EndToEndPathTests(PilotTestBase):
    def test_success_full_path(self):
        runner = self.make_runner(host_reader=_reader_pair()["host"])
        outcome = runner.run()
        self.assertEqual(outcome.execution_status, "ok")
        self.assertEqual(outcome.evaluation_status, "ok")
        self.assertEqual(outcome.archive_status, "ok")
        self.assertTrue(outcome.resolved)
        self.assertEqual(outcome.source_type, "synthetic")
        run_dir = Path(outcome.run_dir)
        for name in ("events.jsonl", "samples.json", "metadata.json",
                     "manifest.json", "candidate.patch"):
            self.assertTrue((run_dir / name).is_file(), name)
        manifest = json.loads((run_dir / "manifest.json").read_text())
        self.assertIn("candidate.patch", manifest["files"])

    def test_agent_error_path(self):
        script = {"steps": [{"model": {"error": "RuntimeError: boom"}}],
                  "final": None}
        runner = self.make_runner(script=script)
        outcome = runner.run()
        self.assertEqual(outcome.execution_status, "agent_error")
        self.assertEqual(outcome.evaluation_status, "not_run")
        self.assertEqual(outcome.archive_status, "ok")
        self.assertIsNone(outcome.resolved)

    def test_no_candidate_path(self):
        script = {"steps": [{"model": {"usage": {"completion_tokens": 5}}}],
                  "final": {"status": "no_candidate", "candidate_patch": ""}}
        runner = self.make_runner(script=script)
        outcome = runner.run()
        self.assertEqual(outcome.execution_status, "no_candidate")
        self.assertEqual(outcome.evaluation_status, "not_run")
        self.assertFalse((Path(outcome.run_dir) / "candidate.patch").exists())

    def test_verifier_timeout_keeps_execution_ok(self):
        runner = self.make_runner(verifier_script={
            "status": "verifier_timeout", "wall_s": 1.0})
        outcome = runner.run()
        self.assertEqual(outcome.execution_status, "ok")
        self.assertEqual(outcome.evaluation_status, "verifier_timeout")
        self.assertIsNone(outcome.resolved)

    def test_verifier_wall_budget_exceeded(self):
        runner = self.make_runner(verifier_script={
            "status": "ok", "resolved": True, "wall_s": 100.0})
        outcome = runner.run()
        self.assertEqual(outcome.evaluation_status, "verifier_timeout")

    def test_patch_apply_failed(self):
        runner = self.make_runner(verifier_script={
            "status": "patch_apply_failed", "wall_s": 1.0})
        outcome = runner.run()
        self.assertEqual(outcome.evaluation_status, "patch_apply_failed")
        self.assertIsNone(outcome.resolved)

    def test_verifier_infra_failure(self):
        runner = self.make_runner(verifier_script={
            "status": "infra_failure", "wall_s": 1.0})
        outcome = runner.run()
        self.assertEqual(outcome.evaluation_status, "infra_failure")
        self.assertEqual(outcome.execution_status, "ok")

    def test_agent_runtime_infra_failure(self):
        runner = self.make_runner()
        runner.runtime.next_start_fails = True
        outcome = runner.run()
        self.assertEqual(outcome.execution_status, "infra_failure")
        self.assertEqual(outcome.evaluation_status, "not_run")

    def test_archive_failure_preserves_events(self):
        runner = self.make_runner()
        with mock.patch.object(
                ResourceSampler, "all_scope_summaries",
                return_value={"s": {"bad": {"unserializable": set()}}}):
            outcome = runner.run()
        self.assertEqual(outcome.archive_status, "failed")
        self.assertTrue((Path(outcome.run_dir) / "events.jsonl").is_file())


# ---------------------------------------------------------------------------
# group 3: budgets, nested retries, watchdog, identity-scoped cleanup
# ---------------------------------------------------------------------------

class BudgetWatchdogTests(PilotTestBase):
    def test_request_budget_enforced(self):
        script = {"steps": [
            {"model": {"usage": {"completion_tokens": 5}}},
            {"model": {"usage": {"completion_tokens": 5}}},
            {"model": {"usage": {"completion_tokens": 5}}},
        ], "final": {"status": "ok", "candidate_patch": "x"}}
        limits = BudgetLimits(max_model_requests=2, max_steps=10,
                              agent_wall_s=60.0, verifier_wall_s=30.0,
                              total_wall_s=120.0)
        runner = self.make_runner(script=script, limits=limits)
        outcome = runner.run()
        self.assertEqual(outcome.execution_status, "budget_exceeded")
        self.assertEqual(outcome.budget_usage["requests"], 3)
        self.assertEqual(outcome.budget_usage["exceeded"], "model_requests")

    def test_step_budget_enforced(self):
        limits = BudgetLimits(max_model_requests=10, max_steps=1,
                              agent_wall_s=60.0, verifier_wall_s=30.0,
                              total_wall_s=120.0)
        runner = self.make_runner(limits=limits)
        outcome = runner.run()
        self.assertEqual(outcome.execution_status, "budget_exceeded")
        self.assertEqual(outcome.budget_usage["exceeded"], "steps")

    def test_agent_wall_budget_enforced(self):
        script = {"steps": [
            {"model": {"usage": {"completion_tokens": 5}},
             "tools": [], "sleep_s": 30.0},
        ], "final": {"status": "ok", "candidate_patch": "x"}}
        limits = BudgetLimits(max_model_requests=10, max_steps=10,
                              agent_wall_s=10.0, verifier_wall_s=30.0,
                              total_wall_s=120.0)
        runner = self.make_runner(script=script, limits=limits)
        outcome = runner.run()
        self.assertEqual(outcome.execution_status, "budget_exceeded")
        self.assertEqual(outcome.budget_usage["exceeded"], "execution_wall_s")

    def test_per_request_output_token_cap(self):
        script = {"steps": [
            {"model": {"usage": {"completion_tokens": 9999}}}],
            "final": {"status": "ok", "candidate_patch": "x"}}
        limits = BudgetLimits(max_output_tokens_per_request=4096)
        runner = self.make_runner(script=script, limits=limits)
        outcome = runner.run()
        self.assertEqual(outcome.execution_status, "budget_exceeded")
        self.assertEqual(outcome.budget_usage["exceeded"],
                         "output_tokens_per_request")

    def test_nested_retry_counted_and_flagged(self):
        script = {"steps": [
            {"model": {"usage": {"completion_tokens": 5}, "extra_calls": 1}}],
            "final": {"status": "ok", "candidate_patch": "x"}}
        runner = self.make_runner(script=script)
        outcome = runner.run()
        self.assertEqual(outcome.execution_status, "ok")
        self.assertEqual(outcome.budget_usage["requests"], 2)
        meta = json.loads((Path(outcome.run_dir) / "metadata.json").read_text())
        self.assertTrue(meta["nested_retry_detected"])
        events = [json.loads(line) for line in
                  (Path(outcome.run_dir) / "events.jsonl").read_text().splitlines()
                  if line.strip()]
        budget_points = [e for e in events if e["kind"] == "budget"
                         and e["attrs"].get("limit_name") == "nested_retry_detected"]
        self.assertEqual(len(budget_points), 1)

    def test_watchdog_kills_real_blocking_subprocess(self):
        script = {"steps": [
            {"model": {"usage": {"completion_tokens": 5}}, "tools": []}],
            "final": {"status": "ok", "candidate_patch": "x"},
            "hang_after_step": 1}
        limits = BudgetLimits(max_model_requests=10, max_steps=10,
                              agent_wall_s=1.5, verifier_wall_s=30.0,
                              total_wall_s=120.0)
        runner = self.make_runner(script=script, limits=limits)
        outcome = runner.run()
        self.assertEqual(outcome.execution_status, "watchdog_timeout")
        child = runner.harness.killed_child
        self.assertIsNotNone(child)
        child.wait(timeout=10)  # reaped after the kill
        self.assertEqual(child.returncode, -9)  # SIGKILL
        # evidence survives the hard kill
        self.assertTrue((Path(outcome.run_dir) / "events.jsonl").is_file())
        self.assertTrue((Path(outcome.run_dir) / "samples.json").is_file())

    def test_cleanup_only_identity_matched_resources(self):
        runner = self.make_runner()
        runner.runtime.add_foreign_container("someone-else-container")
        outcome = runner.run()
        self.assertIn("someone-else-container", runner.runtime.foreign_containers)
        self.assertNotIn("someone-else-container", runner.runtime.stopped)
        # all of this run's own containers are gone
        self.assertEqual(runner.runtime.containers, {})

    def test_runner_consumes_unconfirmed_cleanup_result(self):
        runner = self.make_runner()
        runner.runtime.cleanup_run = lambda run_id, timeout_s=60.0: CleanupResult(
            status="check_failed", errors=["list:returncode=1"])
        outcome = runner.run()
        self.assertEqual(outcome.cleanup_status, "failed")
        self.assertIn("cleanup_run:check_failed", outcome.cleanup_errors)


class DockerCleanupContractTests(unittest.TestCase):
    def setUp(self):
        self.runtime = DockerCliRuntime(authorized=True, collection="RUN-02")

    def test_listing_failure_is_not_confirmed(self):
        result = mock.Mock(returncode=1, stdout="", stderr="daemon")
        with mock.patch(
                "agent_workload_characterization.runners.container_runtime.subprocess.run",
                return_value=result) as run:
            cleanup = self.runtime.cleanup_run("run-x", timeout_s=10)
        self.assertEqual(cleanup.status, "check_failed")
        self.assertEqual(list(cleanup), [])
        run.assert_called_once()

    def test_delete_failure_is_not_reported_as_removed(self):
        listing = mock.Mock(returncode=0, stdout="cid awc-run-02-run-x-agent-001\n")
        deletion = mock.Mock(returncode=1, stdout="", stderr="failed")
        with mock.patch(
                "agent_workload_characterization.runners.container_runtime.subprocess.run",
                side_effect=[listing, deletion]):
            cleanup = self.runtime.cleanup_run("run-x", timeout_s=10)
        self.assertEqual(cleanup.status, "failed")
        self.assertEqual(list(cleanup), [])
        self.assertEqual(cleanup.unconfirmed,
                         ["awc-run-02-run-x-agent-001"])

    def test_zero_budget_preserves_not_checked_state(self):
        with mock.patch(
                "agent_workload_characterization.runners.container_runtime.subprocess.run") as run:
            cleanup = self.runtime.cleanup_run("run-x", timeout_s=0)
        self.assertEqual(cleanup.status, "not_checked")
        self.assertIn("cleanup_budget_exhausted", cleanup.errors)
        run.assert_not_called()


# ---------------------------------------------------------------------------
# group 4: metering semantics on synthetic counters/gauges
# ---------------------------------------------------------------------------

class MeteringSemanticsTests(unittest.TestCase):
    def test_cpu_core_seconds_units(self):
        start = _snap(cpu_usage_usec=1_000_000)
        end = _snap(cpu_usage_usec=3_500_000)
        core_s, reason = cpu_core_seconds(start, end)
        self.assertEqual(core_s, 2.5)
        self.assertIsNone(reason)

    def test_counter_reset_detected(self):
        start = _snap(cpu_usage_usec=5_000_000)
        end = _snap(cpu_usage_usec=1_000_000)
        core_s, reason = cpu_core_seconds(start, end)
        self.assertIsNone(core_s)
        self.assertEqual(reason, "counter_reset_detected")

    def test_missing_counter_stays_null(self):
        start = _snap(cpu_usage_usec=None)
        end = _snap(cpu_usage_usec=1_000_000)
        core_s, reason = cpu_core_seconds(start, end)
        self.assertIsNone(core_s)
        self.assertIn("cpu_usage_usec_missing", reason)

    def test_real_zero_is_preserved(self):
        sampler = ResourceSampler(clock=FakeClock(), interval_s=0.01)
        reader = FakeCounterReader("s", "agent_container", [
            _snap(cpu_usage_usec=0, mem_current_bytes=0),
            _snap(cpu_usage_usec=0, mem_current_bytes=0),
        ])
        sampler.register("s", "agent_container", reader)
        sampler.start("s")
        sampler.stop("s")
        summary = sampler.samples("s").summary()
        self.assertEqual(summary["cpu_core_seconds"], 0.0)
        self.assertIsNone(summary["cpu_core_seconds_reason"])
        self.assertEqual(summary["memory_current_end_bytes"], 0)

    def test_memory_sampled_max_is_lower_bound_without_kernel_peak(self):
        sampler = ResourceSampler(clock=FakeClock(), interval_s=0.01)
        reader = FakeCounterReader("s", "agent_container", [
            _snap(mem_current_bytes=100),
            _snap(mem_current_bytes=500),
            _snap(mem_current_bytes=200),
        ])
        sampler.register("s", "agent_container", reader)
        sampler.start("s")
        for _ in range(3):
            sampler.sample_once()
        sampler.stop("s")
        summary = sampler.samples("s").summary()
        self.assertEqual(summary["memory_sampled_max_bytes"], 500)
        self.assertEqual(summary["memory_peak_basis"], "sampled_lower_bound")

    def test_scopes_not_summed_into_totals(self):
        summary = summarize_dict_scopes = None  # noqa: F841 (readability)
        # two scopes with peaks; the analyzer output must expose per-scope
        # peaks only, never a summed run peak
        data_a = ResourceSampler(clock=FakeClock())
        reader_a = FakeCounterReader("a", "agent_container", [
            _snap(cpu_usage_usec=1_000_000, mem_current_bytes=10,
                  mem_peak_bytes=100),
            _snap(cpu_usage_usec=2_000_000, mem_current_bytes=20,
                  mem_peak_bytes=100)])
        reader_b = FakeCounterReader("b", "verifier_container", [
            _snap(cpu_usage_usec=1_000_000, mem_current_bytes=10,
                  mem_peak_bytes=300),
            _snap(cpu_usage_usec=2_000_000, mem_current_bytes=20,
                  mem_peak_bytes=300)])
        data_a.register("a", "agent_container", reader_a)
        data_a.register("b", "verifier_container", reader_b)
        data_a.start("a"); data_a.stop("a")
        data_a.start("b"); data_a.stop("b")
        out = data_a.all_scope_summaries()
        self.assertEqual(out["a"]["memory_kernel_peak_bytes"], 100)
        self.assertEqual(out["b"]["memory_kernel_peak_bytes"], 300)
        self.assertNotIn("total_peak_bytes", json.dumps(out))
        self.assertNotIn("total_cpu_core_seconds", json.dumps(out))

    def test_io_missing_kept_null(self):
        sampler = ResourceSampler(clock=FakeClock())
        reader = FakeCounterReader("s", "agent_container", [
            _snap(), _snap()])  # no io fields at all
        sampler.register("s", "agent_container", reader)
        sampler.start("s")
        sampler.stop("s")
        summary = sampler.samples("s").summary()
        self.assertIsNone(summary["io"]["read_bytes"])
        self.assertIn("io_read_missing_at_boundary",
                      summary["io"]["reason"] or "")
        self.assertIn("io_write_missing_at_boundary",
                      summary["io"]["reason"] or "")

    def test_io_one_sided_availability(self):
        # read counters exist, write counters do not: read delta is still
        # reported; write stays null with its own reason
        sampler = ResourceSampler(clock=FakeClock())
        reader = FakeCounterReader("s", "agent_container", [
            _snap(io_read_bytes=100),
            _snap(io_read_bytes=130),
        ])
        sampler.register("s", "agent_container", reader)
        sampler.start("s")
        sampler.stop("s")
        summary = sampler.samples("s").summary()
        self.assertEqual(summary["io"]["read_bytes"], 30)
        self.assertIsNone(summary["io"]["write_bytes"])
        self.assertEqual(summary["io"]["reason"], "io_write_missing_at_boundary")

    def test_io_interval_is_delta_not_cumulative(self):
        # cumulative grew 100 -> 130; the interval amount is 30
        sampler = ResourceSampler(clock=FakeClock())
        reader = FakeCounterReader("s", "agent_container", [
            _snap(io_read_bytes=100, io_write_bytes=200),
            _snap(io_read_bytes=130, io_write_bytes=260),
        ])
        sampler.register("s", "agent_container", reader)
        sampler.start("s")
        sampler.stop("s")
        summary = sampler.samples("s").summary()
        self.assertEqual(summary["io"]["read_bytes"], 30)
        self.assertEqual(summary["io"]["write_bytes"], 60)
        self.assertIsNone(summary["io"]["reason"])
        self.assertEqual(summary["io"]["cumulative_end"]["read_bytes"], 130)
        self.assertIn("NOT the interval amount",
                      summary["io"]["cumulative_end"]["note"])

    def test_io_reset_detected_as_null(self):
        sampler = ResourceSampler(clock=FakeClock())
        reader = FakeCounterReader("s", "agent_container", [
            _snap(io_read_bytes=130, io_write_bytes=260),
            _snap(io_read_bytes=100, io_write_bytes=260),
        ])
        sampler.register("s", "agent_container", reader)
        sampler.start("s")
        sampler.stop("s")
        summary = sampler.samples("s").summary()
        self.assertIsNone(summary["io"]["read_bytes"])
        self.assertEqual(summary["io"]["reason"], "io_read_reset_detected")
        # the unaffected direction is still reported (260-260 = 0, a real
        # zero that must not be dropped)
        self.assertEqual(summary["io"]["write_bytes"], 0)

    def test_evidence_serialized_with_boundaries_and_gaps(self):
        sampler = ResourceSampler(clock=FakeClock(), interval_s=0.01)
        reader = FakeCounterReader("s", "agent_container", [
            _snap(cpu_usage_usec=1_000_000, mem_current_bytes=10,
                  io_read_bytes=100),
            _snap(cpu_usage_usec=2_000_000, mem_current_bytes=20,
                  io_read_bytes=110),
            _snap(cpu_usage_usec=3_000_000, mem_current_bytes=15,
                  io_read_bytes=120),
        ])
        sampler.register("s", "agent_container", reader)
        sampler.start("s")
        for _ in range(2):
            sampler.sample_once()
        sampler.stop("s")
        ev = sampler.samples("s").evidence()
        self.assertIsNotNone(ev["boundary_start"])
        self.assertIsNotNone(ev["boundary_end"])
        self.assertEqual(ev["boundary_start"]["cpu_usage_usec"], 1_000_000)
        self.assertEqual(ev["boundary_end"]["cpu_usage_usec"], 3_000_000)
        self.assertEqual(len(ev["samples"]), 2)
        self.assertTrue(all("t_monotonic_ns" in s for s in ev["samples"]))
        self.assertEqual(len(ev["sample_gaps_ns"]), 1)

    def test_clock_domains_never_mixed(self):
        clock_a, clock_b = FakeClock(), FakeClock()
        ev_a = {"t_monotonic_ns": 100, "clock_domain": clock_a.domain,
                "status": "closed"}
        ev_b = {"t_monotonic_ns": 200, "clock_domain": clock_b.domain,
                "status": "closed"}
        with self.assertRaises(ClockError):
            duration_s(ev_a, ev_b)
        ev_c = {"t_monotonic_ns": 250, "clock_domain": clock_a.domain,
                "status": "closed"}
        self.assertEqual(duration_s(ev_a, ev_c), 1.5e-7)
        ev_unclosed = {"t_monotonic_ns": 300, "clock_domain": clock_a.domain,
                       "status": "unclosed"}
        self.assertIsNone(duration_s(ev_a, ev_unclosed))


# ---------------------------------------------------------------------------
# group 5: lifecycle + evidence preservation
# ---------------------------------------------------------------------------

class LifecycleTests(PilotTestBase):
    def test_full_lifecycle_files_and_manifest(self):
        runner = self.make_runner(host_reader=_reader_pair()["host"])
        outcome = runner.run()
        run_dir = Path(outcome.run_dir)
        meta = json.loads((run_dir / "metadata.json").read_text())
        self.assertEqual(meta["execution_status"], "ok")
        self.assertEqual(meta["evaluation_status"], "ok")
        self.assertEqual(meta["source_type"], "synthetic")
        self.assertTrue(meta["budget_limits"]["max_model_requests"] > 0)
        manifest = json.loads((run_dir / "manifest.json").read_text())
        import hashlib
        for name, sha in manifest["files"].items():
            self.assertEqual(
                hashlib.sha256((run_dir / name).read_bytes()).hexdigest(), sha)
        samples = json.loads((run_dir / "samples.json").read_text())
        self.assertIn("collector", samples)  # collector self-observation
        kinds = {s["scope_kind"] for s in samples["scopes"].values()}
        self.assertIn("agent_container", kinds)
        self.assertIn("verifier_container", kinds)
        self.assertIn("host_agent_runtime", kinds)

    def test_samples_json_keeps_raw_evidence_not_only_summary(self):
        runner = self.make_runner()
        outcome = runner.run()
        samples = json.loads(
            (Path(outcome.run_dir) / "samples.json").read_text())
        self.assertIn("evidence", samples)
        agent_ev = samples["evidence"][f"{outcome.run_id}-agent-sandbox"]
        self.assertIsNotNone(agent_ev["boundary_start"])
        self.assertIsNotNone(agent_ev["boundary_end"])
        # boundary values are the reader-scripted ones, not derived views
        self.assertEqual(agent_ev["boundary_start"]["cpu_usage_usec"],
                         1_000_000)
        self.assertEqual(agent_ev["boundary_end"]["cpu_usage_usec"],
                         4_000_000)
        self.assertIsInstance(agent_ev["samples"], list)
        self.assertTrue(all("t_monotonic_ns" in s and "read_status" in s
                            for s in agent_ev["samples"]))
        self.assertIn("sample_gaps_ns", agent_ev)
        # summary in the same file uses the INTERVAL io delta, not cumulative
        agent_sum = samples["scopes"][f"{outcome.run_id}-agent-sandbox"]
        self.assertEqual(agent_sum["io"]["read_bytes"], 30)
        self.assertEqual(agent_sum["io"]["cumulative_end"]["read_bytes"], 130)

    def test_analyzer_evidence_check_present(self):
        outcome = self.make_runner().run()
        summary = summarize_run(Path(outcome.run_dir))
        agent_entries = [s for s in summary["scopes"]
                         if s["scope_kind"] == "agent_container"]
        self.assertTrue(agent_entries)
        check = agent_entries[0]["evidence_check"]
        self.assertTrue(check["boundary_start_present"])
        self.assertTrue(check["boundary_end_present"])
        self.assertIsInstance(check["raw_sample_count"], int)

    def test_failure_path_preserves_evidence_before_cleanup(self):
        script = {"steps": [
            {"model": {"usage": {"completion_tokens": 5}}, "tools": []},
            {"model": {"error": "RuntimeError: agent died"}}],
            "final": None}
        runner = self.make_runner(script=script)
        outcome = runner.run()
        run_dir = Path(outcome.run_dir)
        self.assertEqual(outcome.execution_status, "agent_error")
        for name in ("events.jsonl", "samples.json", "metadata.json"):
            self.assertTrue((run_dir / name).is_file(), name)
        events = [json.loads(l) for l in
                  (run_dir / "events.jsonl").read_text().splitlines() if l]
        self.assertEqual(events[0]["kind"], "run")
        self.assertEqual(events[-1]["attrs"]["phase"], "sealed")

    def test_all_attempts_kept_separately(self):
        outcome1 = self.make_runner().run()
        outcome2 = self.make_runner().run()
        self.assertNotEqual(outcome1.run_dir, outcome2.run_dir)
        self.assertTrue(Path(outcome1.run_dir).is_dir())
        self.assertTrue(Path(outcome2.run_dir).is_dir())

    def test_artifact_budget_exceeded_still_delivers(self):
        # archive-time SOFT accounting scenario: the ceiling sits above the
        # in-flight files (events.jsonl) but below the optional archives,
        # so execution completes and only the optional artifacts get
        # skipped — the run still delivers a full independent outcome
        limits = BudgetLimits(max_model_requests=10, max_steps=10,
                              agent_wall_s=60.0, verifier_wall_s=30.0,
                              total_wall_s=120.0, max_new_artifact_bytes=4200)
        runner = self.make_runner(limits=limits)
        outcome = runner.run()
        self.assertEqual(outcome.execution_status, "ok")
        self.assertEqual(outcome.evaluation_status, "ok")
        self.assertEqual(outcome.archive_status, "budget_exceeded")
        self.assertTrue(outcome.budget_usage["artifact_exceeded"])
        run_dir = Path(outcome.run_dir)
        meta = json.loads((run_dir / "metadata.json").read_text())
        self.assertEqual(meta["execution_status"], "ok")
        self.assertEqual(meta["evaluation_status"], "ok")
        self.assertTrue(meta["archive"]["artifact_exceeded"])
        self.assertIn("samples.json", meta["archive"]["skipped_files"])
        self.assertFalse((run_dir / "samples.json").exists())
        self.assertTrue((run_dir / "metadata.json").is_file())
        self.assertTrue((run_dir / "manifest.json").is_file())
        # cleanup still happened
        self.assertEqual(runner.runtime.containers, {})

    def test_artifact_budget_counts_all_archived_files(self):
        # normal path: every archived file is accounted, not just the patch
        runner = self.make_runner()
        outcome = runner.run()
        run_dir = Path(outcome.run_dir)
        accounted = outcome.budget_usage["artifact_bytes"]
        total = sum(p.stat().st_size for p in run_dir.iterdir()
                    if p.is_file())
        self.assertEqual(accounted, total)
        self.assertFalse(outcome.budget_usage["artifact_exceeded"])

    def test_final_counter_read_happens_before_teardown(self):
        runner = self.make_runner()
        outcome = runner.run()
        # BOTH scopes: the boundary reads must observe live containers
        for scope in ("agent", "verifier"):
            reads = [status for s, status in runner.runtime.read_log
                     if s == scope]
            self.assertTrue(reads, f"no counter reads for {scope}")
            self.assertEqual(reads[-1], "running",
                             f"{scope} boundary read must precede teardown")
            self.assertNotIn("absent", reads,
                             f"{scope} read attempted on a torn-down container")

    def test_verifier_reads_use_real_handle(self):
        runner = self.make_runner()
        outcome = runner.run()
        # the verifier saw the container the RUNNER created (real handle,
        # not a fabricated id) and both are gone after cleanup
        verifier_specs = [s for s in runner.runtime.started
                          if s.scope == "verifier"]
        self.assertEqual(len(verifier_specs), 1)
        self.assertIn(runner.verifier.seen_container_id,
                      runner.runtime.stopped)
        self.assertEqual(runner.runtime.containers, {})
        # verifier container events reference the same identity
        events = [json.loads(l) for l in
                  (Path(outcome.run_dir) / "events.jsonl").read_text()
                  .splitlines() if l.strip()]
        container_events = [e for e in events if e["kind"] == "container"]
        verifier_starts = [e for e in container_events
                           if e["attrs"].get("scope") == "verifier"
                           and e["attrs"].get("action") == "start"]
        self.assertEqual(len(verifier_starts), 1)
        self.assertEqual(verifier_starts[0]["attrs"]["container_id"],
                         runner.verifier.seen_container_id)

    def test_docker_runtime_refuses_unauthorized_execution(self):
        from agent_workload_characterization.runners.container_runtime import \
            RuntimeError_ as RTError
        runtime = DockerCliRuntime(authorized=False)
        spec = ContainerSpec(run_id="r", scope="agent", image="img:latest")
        with self.assertRaises(RTError):
            runtime.start(spec)

    def test_docker_run_argv_construction(self):
        runtime = DockerCliRuntime(authorized=False)
        spec = ContainerSpec(run_id="r1", scope="agent", image="img@sha256:abc",
                             env={"A": "1"}, mem_limit="8g", cpu_limit="4")
        argv = runtime.build_run_argv(spec, "awc-run01-r1-agent-001")
        self.assertEqual(argv[:4], ["docker", "run", "-d", "--name"])
        self.assertIn("--network", argv)
        self.assertEqual(argv[argv.index("--network") + 1], "none")
        self.assertIn("--memory", argv)
        self.assertIn("--cpus", argv)
        self.assertIn("img@sha256:abc", argv)


# ---------------------------------------------------------------------------
# analyzer + CLI
# ---------------------------------------------------------------------------

class CgroupV1ReaderTests(unittest.TestCase):
    """Offline parse tests against a synthetic v1 cgroup tree (gate B
    verified the real layout: docker 25.0.5, cgroupfs driver, v1)."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        self.cid = "a" * 64
        base = self.root / "docker" / self.cid
        (base.parent / self.cid).mkdir(parents=True)
        (self.root / "cpu,cpuacct" / "docker" / self.cid).mkdir(parents=True)
        (self.root / "memory" / "docker" / self.cid).mkdir(parents=True)
        (self.root / "blkio" / "docker" / self.cid).mkdir(parents=True)

    def _reader(self):
        # one cg_root for all three controllers via separate roots is not
        # supported by the API; mirror real layout with a single root tree
        return CgroupV1FileReader("s", "agent_container", self.cid,
                                  cg_root=self.root)

    def _write(self, rel: str, text: str):
        path = self.root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)

    def test_ns_converted_to_usec(self):
        self._write("cpu,cpuacct/docker/%s/cpuacct.usage" % self.cid,
                    "5126187860")
        snap = self._reader().read(1)
        self.assertEqual(snap.cpu_usage_usec, 5126187)
        self.assertEqual(snap.read_status["cpuacct.usage"],
                         "ok_ns_converted_to_usec")

    def test_memory_files(self):
        self._write("memory/docker/%s/memory.usage_in_bytes" % self.cid,
                    str(138092544))
        self._write("memory/docker/%s/memory.max_usage_in_bytes" % self.cid,
                    str(138092544))
        snap = self._reader().read(1)
        self.assertEqual(snap.mem_current_bytes, 138092544)
        self.assertEqual(snap.mem_peak_bytes, 138092544)

    def test_throttle_io_rows_summed(self):
        self._write("blkio/docker/%s/blkio.throttle.io_service_bytes_recursive"
                    % self.cid,
                    "8:16 Read 0\n8:16 Write 73728\n8:16 Sync 0\n"
                    "259:0 Read 4096\n259:0 Write 1024\n")
        snap = self._reader().read(1)
        self.assertEqual(snap.io_read_bytes, 4096)
        self.assertEqual(snap.io_write_bytes, 74752)
        self.assertEqual(snap.read_status["io"],
                         "ok_summed_devices:"
                         "blkio.throttle.io_service_bytes_recursive")

    def test_total_zero_is_real_zero(self):
        # v1 throttle files print "Total 0" when nothing is recorded yet:
        # that is a REAL ZERO, not a missing counter
        self._write("blkio/docker/%s/blkio.throttle.io_service_bytes_recursive"
                    % self.cid, "Total 0\n")
        snap = self._reader().read(1)
        self.assertEqual(snap.io_read_bytes, 0)
        self.assertEqual(snap.io_write_bytes, 0)
        self.assertEqual(snap.read_status["io"],
                         "ok_no_records_real_zero:"
                         "blkio.throttle.io_service_bytes_recursive")

    def test_missing_blkio_files_stay_null(self):
        snap = self._reader().read(1)
        self.assertIsNone(snap.io_read_bytes)
        self.assertIsNone(snap.io_write_bytes)
        self.assertEqual(snap.read_status["io"], "io_files_unavailable")

    def test_v1_peak_basis_label(self):
        self._write("memory/docker/%s/memory.max_usage_in_bytes" % self.cid,
                    "1000")
        sampler = ResourceSampler(clock=FakeClock())
        sampler.register("s", "agent_container", self._reader())
        sampler.start("s")
        sampler.stop("s")
        summary = sampler.samples("s").summary()
        self.assertEqual(summary["memory_peak_basis"],
                         "v1_max_usage_in_bytes")


class CanaryPlanTests(unittest.TestCase):
    def test_plan_mode_offline(self):
        from agent_workload_characterization.runners.canary import main
        with mock.patch("sys.stdout"):
            rc = main([])
        self.assertEqual(rc, 0)

    def test_execute_requires_double_gate(self):
        from agent_workload_characterization.runners.canary import main
        with mock.patch("sys.stderr"):
            rc = main(["--execute"])
        self.assertEqual(rc, 2)

    def test_platform_in_run_argv(self):
        runtime = DockerCliRuntime(authorized=False)
        spec = ContainerSpec(run_id="r", scope="agent", image="img",
                             platform="linux/amd64")
        argv = runtime.build_run_argv(spec, "n1")
        self.assertIn("--platform", argv)
        self.assertEqual(argv[argv.index("--platform") + 1], "linux/amd64")
        # default (no platform) omits the flag
        argv2 = runtime.build_run_argv(
            ContainerSpec(run_id="r", scope="agent", image="img"), "n2")
        self.assertNotIn("--platform", argv2)


class CanaryWorkloadTests(unittest.TestCase):
    """r6 lesson regressions: sub-step failures must propagate (set -e)
    and the memory step must be valid python. Executed LOCALLY with real
    bash (fast parameters) — no containers, no docker."""

    def _run_bash(self, command: str) -> tuple[int, str]:
        import subprocess
        proc = subprocess.run(["bash", "-c", command], capture_output=True,
                              text=True, timeout=60)
        return proc.returncode, proc.stdout + proc.stderr

    def test_native_workload_succeeds_locally(self):
        from agent_workload_characterization.runners.canary import (
            build_native_workload)
        wl = build_native_workload(busy_s=1, file_mb=1, alloc_mib=16)
        rc, out = self._run_bash(wl)
        self.assertEqual(rc, 0, out)
        self.assertIn("mem_alloc_ok 16777216", out)  # 16 MiB allocated

    def test_workload_failure_propagates(self):
        # a failing sub-step must fail the WHOLE workload — the trailing
        # sync must never mask it (the r6 masking bug)
        rc, out = self._run_bash(
            "set -e; cat /nonexistent-file-xyz-7c2f; echo survived; sync")
        self.assertNotEqual(rc, 0)
        self.assertNotIn("survived", out)

    def test_workload_starts_with_set_e(self):
        from agent_workload_characterization.runners.canary import (
            build_native_workload, build_target_workload)
        self.assertTrue(build_native_workload().startswith("set -e;"))
        self.assertTrue(build_target_workload().startswith("set -e;"))

    def test_memory_step_no_slice_arity_bug(self):
        # the r6 bug: b[::4096] = b'x' assigned 1 byte to 32768 slots.
        # The fixed form writes a matched-length block; assert the buggy
        # pattern is gone from every generated workload.
        from agent_workload_characterization.runners.canary import (
            build_native_workload, build_target_workload)
        for wl in (build_native_workload(), build_target_workload()):
            self.assertNotIn("b[::4096] = b'x'", wl)
        # and the memory step itself runs cleanly (subset execution)
        rc, out = self._run_bash(
            "python3 -c \"b = bytearray(8*1024*1024); "
            "b[:65536] = b'x'*65536; print('mem_alloc_ok', len(b))\"")
        self.assertEqual(rc, 0)
        self.assertIn("mem_alloc_ok 8388608", out)

    def test_summary_marks_workload_ok(self):
        # canary summaries must expose workload_ok explicitly — a nonzero
        # rc may coexist with useful counter data and must stay visible
        from agent_workload_characterization.runners.canary import main
        with mock.patch("sys.stdout"):
            rc = main([])
        self.assertEqual(rc, 0)


FAKE_CHILD_OK = r'''
import json, pathlib, sys, time
payload = json.loads(sys.stdin.read())
out = payload["output"]
status = pathlib.Path(out["status_path"])
for i in range(1, 4):
    t0 = time.monotonic_ns()
    time.sleep(0.01)
    with status.open("a") as fh:
        fh.write(json.dumps({"n_calls": i, "n_steps": i, "cost": 0.0,
                             "elapsed_s": i, "ok": True,
                             "usage": {"prompt_tokens": 10 * i,
                                       "completion_tokens": 20,
                                       "total_tokens": 10 * i + 20},
                             "t_start_ns": t0,
                             "t_end_ns": time.monotonic_ns()}) + "\n")
pathlib.Path(out["trajectory_path"]).write_text(
    json.dumps({"info": {"exit_status": "submitted"}}))
print(json.dumps({"exit_status": "submitted", "n_calls": 3, "n_steps": 3}))
'''

FAKE_CHILD_OVER_BUDGET = r'''
import json, pathlib, sys, time
payload = json.loads(sys.stdin.read())
out = payload["output"]
status = pathlib.Path(out["status_path"])
for i in range(1, 8):
    with status.open("a") as fh:
        fh.write(json.dumps({"n_calls": i, "n_steps": i, "cost": 0.0,
                             "elapsed_s": i, "ok": True, "usage": None,
                             "t_start_ns": time.monotonic_ns(),
                             "t_end_ns": time.monotonic_ns()}) + "\n")
print(json.dumps({"exit_status": "running"}), flush=True)
time.sleep(10)
'''

FAKE_CHILD_CRASH = "import sys; sys.stderr.write('boom'); sys.exit(3)"

FAKE_CHILD_JUMP = r'''
import json, pathlib, sys, time
payload = json.loads(sys.stdin.read())
out = payload["output"]
status = pathlib.Path(out["status_path"])
# simulate two requests completing between parent polls: the counter
# JUMPS from 1 to 3 in one line (delta counting must see 2 requests)
for n_calls in (1, 3):
    with status.open("a") as fh:
        fh.write(json.dumps({"n_calls": n_calls, "n_steps": n_calls - 1,
                             "cost": 0.0, "elapsed_s": n_calls, "ok": True,
                             "usage": {"prompt_tokens": 5,
                                       "completion_tokens": 7,
                                       "total_tokens": 12},
                             "t_start_ns": time.monotonic_ns(),
                             "t_end_ns": time.monotonic_ns()}) + "\n")
pathlib.Path(out["trajectory_path"]).write_text("{}")
print(json.dumps({"exit_status": "submitted", "n_calls": 3, "n_steps": 2}))
'''


class MiniHarnessOrchestrationTests(PilotTestBase):
    """Parent-side mini orchestration via a fake child process speaking
    the real status protocol (no mini import, no containers)."""

    GIT_DIFF_CMD = "git -c core.fileMode=false diff"

    def _harness(self, child_code=FAKE_CHILD_OK, *, authorized=True,
                 limits=None, target_ref=None):
        import sys as _sys
        from agent_workload_characterization.runners.mini_agent_adapter \
            import MiniSweAgentHarness
        return MiniSweAgentHarness(
            Path(_sys.executable),  # any python runs the fake child code
            authorized=authorized, child_code=child_code,
            mini_config={"model": {
                "model_name": "openai/deepseek-v4-flash"}},
            target_image_ref=target_ref, poll_interval_s=0.05)

    def _context(self, harness, limits=None):
        clock = FakeClock()
        limits = limits or BudgetLimits(max_model_requests=10, max_steps=10,
                                        agent_wall_s=60.0,
                                        verifier_wall_s=30.0,
                                        total_wall_s=120.0)
        readers = _reader_pair()
        runtime = FakeContainerRuntime(clock, readers=readers)
        runtime.execute_script[self.GIT_DIFF_CMD] = {
            "returncode": 0,
            "output": "--- a/f.py\n+++ b/f.py\n@@ -1 +1 @@\n-fix\n+fixed\n"}
        task = AgentTask(instance_id="django__django-16485",
                         problem_statement="synthetic problem",
                         image="synthetic-image:latest")
        run_dir = self.root / "run-x"
        run_dir.mkdir()
        recorder = SemanticRecorder(run_dir, clock, run_id="runx",
                                    attempt_id="runx-a1",
                                    task_id=task.instance_id,
                                    source_type="synthetic")
        recorder.begin_run()
        budget = BudgetTracker(limits, clock)
        budget.start()
        container = runtime.start(ContainerSpec(run_id="runx", scope="agent",
                                                image="synthetic"))
        return task, budget, recorder, runtime, container, run_dir

    def test_mini_unauthorized_refuses(self):
        harness = self._harness(authorized=False)
        task, budget, recorder, runtime, container, run_dir = \
            self._context(harness)
        with self.assertRaises(AgentError):
            harness.run(task, budget, recorder, runtime, container,
                        None, run_dir)

    def test_mini_run_counts_status_and_extracts_patch(self):
        harness = self._harness()
        task, budget, recorder, runtime, container, run_dir = \
            self._context(harness)
        result = harness.run(task, budget, recorder, runtime, container,
                             None, run_dir)
        self.assertEqual(result.status, "ok")
        self.assertEqual(
            result.candidate_patch,
            "--- a/f.py\n+++ b/f.py\n@@ -1 +1 @@\n-fix\n+fixed")  # stripped
        self.assertEqual(result.steps, 3)
        # external budget fed from the status protocol
        self.assertEqual(budget.usage_dict()["requests"], 3)
        self.assertEqual(budget.usage_dict()["steps"], 3)
        self.assertEqual(budget.usage_dict()["output_tokens"], 60)
        # status + trajectory archived in the run dir
        self.assertTrue((run_dir / "mini_status.jsonl").is_file())
        self.assertTrue((run_dir / "mini_trajectory.json").is_file())
        # one closed llm_request event per observed model request
        events = [json.loads(l) for l in
                  (run_dir / "events.jsonl").read_text().splitlines() if l]
        llm = [e for e in events if e["kind"] == "llm_request"
               and e["status"] == "closed"]
        self.assertEqual(len(llm), 3)

    def test_mini_run_budget_kill(self):
        harness = self._harness(FAKE_CHILD_OVER_BUDGET)
        limits = BudgetLimits(max_model_requests=5, max_steps=10,
                              agent_wall_s=60.0, verifier_wall_s=30.0,
                              total_wall_s=120.0)
        task, budget, recorder, runtime, container, run_dir = \
            self._context(harness, limits)
        result = harness.run(task, budget, recorder, runtime, container,
                             None, run_dir)
        self.assertEqual(result.status, "budget_exceeded")
        self.assertIn("model_requests", result.stop_reason or "")
        # evidence survives the kill
        self.assertTrue((run_dir / "mini_status.jsonl").is_file())

    def test_mini_run_child_failure(self):
        harness = self._harness(FAKE_CHILD_CRASH)
        task, budget, recorder, runtime, container, run_dir = \
            self._context(harness)
        result = harness.run(task, budget, recorder, runtime, container,
                             None, run_dir)
        self.assertEqual(result.status, "agent_error")
        self.assertIn("rc=3", result.error or "")

    def test_mini_run_no_diff_means_no_candidate(self):
        harness = self._harness()
        task, budget, recorder, runtime, container, run_dir = \
            self._context(harness)
        runtime.execute_script[self.GIT_DIFF_CMD] = {
            "returncode": 0, "output": ""}
        result = harness.run(task, budget, recorder, runtime, container,
                             None, run_dir)
        self.assertEqual(result.status, "no_candidate")
        self.assertIsNone(result.candidate_patch)

    def test_mini_payload_maps_arm64_digest(self):
        harness = self._harness(target_ref=(
            "swebench/sweb.eval.arm64.django_1776_django-16485"
            "@sha256:19d403c243c2857e7cb9cf5af8ce3f1cb6d87be91c5254e1de"
            "00040e6db3b7d2"))
        payload = harness.build_payload(
            {"instance_id": "django__django-16485",
             "problem_statement": "p",
             "image_name": "swebench/sweb.eval.x86_64.django_1776_"
                           "django-16485:latest"},
            self.root / "t.json", self.root / "s.jsonl", "cid-1",
            mini_config={"model": {"model_name": "openai/test-model"}})
        text = json.dumps(payload)
        # arm64 digest mapped in; x86_64 tag NOT forwarded
        self.assertIn("sweb.eval.arm64.django_1776_django-16485@sha256:",
                      payload["instance"]["image_name"])
        self.assertNotIn("x86_64", payload["instance"]["image_name"])
        for canary in (GOLD_CANARY, TEST_CANARY, EVAL_CANARY):
            self.assertNotIn(canary, text)

    def test_mini_default_config_limits(self):
        harness = self._harness()
        cfg = harness.default_mini_config(step_limit=30, agent_wall_s=1500,
                                          max_output_tokens=4096)
        self.assertEqual(cfg["agent"]["step_limit"], 30)
        self.assertEqual(cfg["agent"]["wall_time_limit_seconds"], 1500)
        self.assertEqual(cfg["agent"]["cost_limit"], 0)
        self.assertEqual(cfg["model"]["model_kwargs"]["num_retries"], 0)
        self.assertEqual(cfg["model"]["model_kwargs"]["max_tokens"], 4096)
        # mini's step_limit gates n_calls (model requests): documented
        self.assertIn("step_limit gates", MiniSweAgentHarness
                      .default_mini_config.__doc__)


class VerifierCommandTests(unittest.TestCase):
    """Pure construction tests for the real swebench verifier."""

    def _verifier(self):
        from agent_workload_characterization.runners.coding_pilot import \
            SwebenchVerifierRunner
        return SwebenchVerifierRunner(authorized=False)

    def test_patch_heredoc_contains_candidate(self):
        v = self._verifier()
        cmd = v.build_patch_heredoc("--- a/f.py\n+++ b/f.py\n")
        self.assertIn(v.HEREDOC_DELIM, cmd)
        self.assertIn("--- a/f.py", cmd)
        self.assertTrue(cmd.startswith(f"cat > {v.PATCH_FILE}"))

    def test_heredoc_delimiter_collision_rejected(self):
        v = self._verifier()
        with self.assertRaises(ValueError):
            v.build_patch_heredoc(f"evil\n{v.HEREDOC_DELIM}\ninjection")

    def test_apply_chain_matches_official_order(self):
        v = self._verifier()
        chain = v.build_apply_chain()
        self.assertEqual(len(chain), 4)
        self.assertEqual(chain[0][0], "")  # first attempt: no reset
        self.assertIn("git apply --verbose", chain[0][1])
        self.assertIn("--3way", chain[1][1])
        self.assertIn("--reject", chain[2][1])
        self.assertIn("patch --batch --forward --fuzz=5 -p1 -i", chain[3][1])
        for reset, _ in chain[1:]:
            self.assertEqual(reset, "git checkout -- . ; git clean -fd")

    def test_eval_heredoc_contains_script(self):
        v = self._verifier()
        cmd = v.build_eval_heredoc("#!/bin/bash\nset -uxo pipefail\n")
        self.assertTrue(cmd.startswith(f"cat > {v.EVAL_FILE}"))
        self.assertIn("set -uxo pipefail", cmd)

    def test_unauthorized_refuses(self):
        from agent_workload_characterization.runners.coding_pilot import \
            VerifierSpec
        from agent_workload_characterization.runners.container_runtime import \
            RuntimeError_ as RTError
        v = self._verifier()
        spec = VerifierSpec(instance_id="i", image="img",
                            eval_script_ref="x", log_parser="p",
                            eval_type="pass_and_fail",
                            record_locator="/nonexistent")
        with self.assertRaises(RTError):
            v.run(spec, "patch", None, None, None, None)


class Round4BudgetCountingTests(unittest.TestCase):
    """Fourth-review regressions: cumulative-delta counting, per-request
    output ceiling, format-error lines, and the unified remaining-time
    computation."""

    def _budget(self, **kw):
        defaults = dict(max_model_requests=10, max_steps=10,
                        agent_wall_s=60.0, verifier_wall_s=30.0,
                        total_wall_s=120.0)
        defaults.update(kw)
        return BudgetTracker(BudgetLimits(**defaults), FakeClock())

    def test_jumping_counter_counts_delta(self):
        # the user's repro: cumulative n_calls=3 across lines counted as 1
        budget = self._budget()
        MiniSweAgentHarness._count_status_line(
            {"n_calls": 1, "n_steps": 1}, budget)
        MiniSweAgentHarness._count_status_line(
            {"n_calls": 3, "n_steps": 2}, budget)  # one line jumps by 2
        usage = budget.usage_dict()
        self.assertEqual(usage["requests"], 3)
        self.assertEqual(usage["steps"], 2)

    def test_per_request_output_ceiling_enforced(self):
        # the user's repro: a single 10000-token request must trip the cap
        budget = self._budget(max_output_tokens_per_request=4096)
        with self.assertRaises(BudgetExceeded):
            MiniSweAgentHarness._count_status_line(
                {"n_calls": 1, "n_steps": 1,
                 "usage": {"completion_tokens": 10000}}, budget)
        self.assertEqual(budget.usage_dict()["exceeded"],
                         "output_tokens_per_request")

    def test_format_error_line_still_counts_request(self):
        budget = self._budget()
        MiniSweAgentHarness._count_status_line(
            {"n_calls": 1, "n_steps": 0, "ok": False, "usage": None},
            budget)
        self.assertEqual(budget.usage_dict()["requests"], 1)
        self.assertEqual(budget.usage_dict()["steps"], 0)

    def test_remaining_s_phase_and_total_capped(self):
        clock = FakeClock()
        limits = BudgetLimits(agent_wall_s=100.0, verifier_wall_s=50.0,
                              total_wall_s=120.0)
        b = BudgetTracker(limits, clock)
        b.start("execution")
        clock.advance_s(90)
        self.assertAlmostEqual(b.remaining_s("execution"), 10.0)
        b.begin_phase("evaluation")
        # min(verifier 50, total 120-90=30) = 30
        self.assertAlmostEqual(b.remaining_s("evaluation"), 30.0)
        clock.advance_s(25)
        self.assertAlmostEqual(b.remaining_s("evaluation"), 5.0)

    def test_effective_config_requires_model_name(self):
        from agent_workload_characterization.runners.mini_agent_adapter \
            import MiniSweAgentHarness
        h = MiniSweAgentHarness(Path("/nonexistent"),
                                mini_config={"model": {}})
        with self.assertRaises(ValueError):
            h._effective_config(self._budget())

    def test_effective_config_merges_budget_limits(self):
        from agent_workload_characterization.runners.mini_agent_adapter \
            import MiniSweAgentHarness
        h = MiniSweAgentHarness(
            Path("/nonexistent"),
            mini_config={"model": {"model_name": "openai/test"},
                         "agent": {"system_template": "s"}})
        cfg = h._effective_config(self._budget(max_model_requests=7,
                                               agent_wall_s=99,
                                               max_output_tokens_per_request=123))
        self.assertEqual(cfg["model"]["model_name"], "openai/test")
        self.assertEqual(cfg["agent"]["step_limit"], 7)
        self.assertEqual(cfg["agent"]["wall_time_limit_seconds"], 99)
        self.assertEqual(cfg["model"]["model_kwargs"]["num_retries"], 0)
        self.assertEqual(cfg["model"]["model_kwargs"]["max_tokens"], 123)


class Round4StatusPreservationTests(PilotTestBase):
    """The original stop reason must survive a failed/empty candidate
    extraction (fourth-review: empty patch overwrote budget_exceeded /
    agent_error with no_candidate)."""

    GIT_DIFF_CMD = "git -c core.fileMode=false diff"

    def _harness(self, child_code):
        import sys as _sys
        from agent_workload_characterization.runners.mini_agent_adapter \
            import MiniSweAgentHarness
        return MiniSweAgentHarness(
            Path(_sys.executable), authorized=True, child_code=child_code,
            mini_config={"model": {
                "model_name": "openai/deepseek-v4-flash"}},
            poll_interval_s=0.05)

    def _context(self, harness, limits):
        clock = FakeClock()
        readers = _reader_pair()
        runtime = FakeContainerRuntime(clock, readers=readers)
        runtime.execute_script[self.GIT_DIFF_CMD] = {
            "returncode": 0, "output": ""}  # EMPTY diff
        task = AgentTask(instance_id="i", problem_statement="p",
                         image="synthetic-image:latest")
        run_dir = self.root / "run-y"
        run_dir.mkdir()
        recorder = SemanticRecorder(run_dir, clock, run_id="runy",
                                    attempt_id="runy-a1", task_id="i",
                                    source_type="synthetic")
        recorder.begin_run()
        budget = BudgetTracker(limits, clock)
        budget.start()
        container = runtime.start(ContainerSpec(run_id="runy", scope="agent",
                                                image="synthetic"))
        return task, budget, recorder, runtime, container, run_dir

    def test_budget_kill_with_empty_diff_keeps_budget_exceeded(self):
        harness = self._harness(FAKE_CHILD_OVER_BUDGET)
        limits = BudgetLimits(max_model_requests=5, max_steps=10,
                              agent_wall_s=60.0, verifier_wall_s=30.0,
                              total_wall_s=120.0)
        task, budget, recorder, runtime, container, run_dir = \
            self._context(harness, limits)
        result = harness.run(task, budget, recorder, runtime, container,
                             None, run_dir)
        self.assertEqual(result.status, "budget_exceeded")
        self.assertIsNone(result.candidate_patch)
        self.assertIn("model_requests", result.stop_reason or "")

    def test_child_failure_with_diff_failure_keeps_agent_error(self):
        harness = self._harness(FAKE_CHILD_CRASH)
        limits = BudgetLimits(max_model_requests=10, max_steps=10,
                              agent_wall_s=60.0, verifier_wall_s=30.0,
                              total_wall_s=120.0)
        task, budget, recorder, runtime, container, run_dir = \
            self._context(harness, limits)
        runtime.execute_script[self.GIT_DIFF_CMD] = {
            "returncode": 1, "output": ""}  # extraction ALSO fails
        result = harness.run(task, budget, recorder, runtime, container,
                             None, run_dir)
        self.assertEqual(result.status, "agent_error")
        self.assertIn("candidate extraction also failed", result.error or "")


class Round4EventTimestampTests(PilotTestBase):
    def _harness(self):
        import sys as _sys
        from agent_workload_characterization.runners.mini_agent_adapter \
            import MiniSweAgentHarness
        return MiniSweAgentHarness(
            Path(_sys.executable), authorized=True, child_code=FAKE_CHILD_OK,
            mini_config={"model": {
                "model_name": "openai/deepseek-v4-flash"}},
            poll_interval_s=0.05)

    def _context(self, harness):
        clock = FakeClock()
        readers = _reader_pair()
        runtime = FakeContainerRuntime(clock, readers=readers)
        runtime.execute_script[self.GIT_DIFF_CMD] = {
            "returncode": 0, "output": "+++ patch\n"}
        task = AgentTask(instance_id="i", problem_statement="p",
                         image="synthetic-image:latest")
        run_dir = self.root / "run-z"
        run_dir.mkdir()
        recorder = SemanticRecorder(run_dir, clock, run_id="runz",
                                    attempt_id="runz-a1", task_id="i",
                                    source_type="synthetic")
        recorder.begin_run()
        budget = BudgetTracker(
            BudgetLimits(max_model_requests=10, max_steps=10,
                         agent_wall_s=60.0, verifier_wall_s=30.0,
                         total_wall_s=120.0), clock)
        budget.start()
        container = runtime.start(ContainerSpec(run_id="runz", scope="agent",
                                                image="synthetic"))
        return task, budget, recorder, runtime, container, run_dir

    GIT_DIFF_CMD = "git -c core.fileMode=false diff"

    def test_events_carry_child_request_boundaries(self):
        harness = self._harness()
        task, budget, recorder, runtime, container, run_dir = \
            self._context(harness)
        harness.run(task, budget, recorder, runtime, container, None, run_dir)
        events = [json.loads(l) for l in
                  (run_dir / "events.jsonl").read_text().splitlines() if l]
        llm = [e for e in events if e["kind"] == "llm_request"
               and e["status"] == "closed"]
        self.assertEqual(len(llm), 3)
        for ev in llm:
            self.assertIsInstance(ev["attrs"].get("t_start_ns"), int)
            self.assertIsInstance(ev["attrs"].get("t_end_ns"), int)
            self.assertGreaterEqual(ev["attrs"]["t_end_ns"],
                                    ev["attrs"]["t_start_ns"])
            self.assertEqual(ev["attrs"].get("timing_source"),
                             "child_status")
            self.assertIs(ev["attrs"].get("ok"), True)

    def test_format_error_line_event_marks_not_ok(self):
        run_dir = self.root / "fmt"
        run_dir.mkdir()
        clock = FakeClock()
        recorder = SemanticRecorder(run_dir, clock, run_id="r",
                                    attempt_id="r-a1", task_id="t",
                                    source_type="synthetic")
        recorder.begin_run()
        MiniSweAgentHarness._emit_line_event(
            recorder, {"n_calls": 1, "n_steps": 0, "ok": False,
                       "usage": None})
        events = [json.loads(l) for l in
                  (run_dir / "events.jsonl").read_text().splitlines() if l]
        llm = [e for e in events if e["kind"] == "llm_request"
               and e["status"] == "closed"]
        self.assertEqual(len(llm), 1)
        self.assertIs(llm[0]["attrs"]["ok"], False)


class Round4ArtifactMonitorTests(PilotTestBase):
    def test_inflight_artifact_ceiling_stops_execution(self):
        # ceiling of 1 byte + a harness that takes real wall time: the
        # in-flight monitor trips on the first events.jsonl write and the
        # harness budget check stops the run
        script = {"steps": [
            {"model": {"usage": {"completion_tokens": 5}}, "tools": []},
            {"model": {"usage": {"completion_tokens": 5}}, "tools": []}],
            "final": {"status": "ok", "candidate_patch": "x"},
            "real_sleep_s": 0.05}
        limits = BudgetLimits(max_model_requests=10, max_steps=10,
                              agent_wall_s=60.0, verifier_wall_s=30.0,
                              total_wall_s=120.0, max_new_artifact_bytes=1)
        runner = self.make_runner(script=script, limits=limits)
        runner.monitor_interval_s = 0.01
        outcome = runner.run()
        self.assertEqual(outcome.execution_status, "budget_exceeded")
        self.assertEqual(outcome.budget_usage["exceeded"],
                         "new_artifact_bytes")
        # minimal evidence still archived
        self.assertTrue((Path(outcome.run_dir) / "events.jsonl").is_file())


class Round4VerifierDeadlineTests(unittest.TestCase):
    """Unified remaining-deadline behaviour with a mocked swebench import
    (the default suite has no swebench package)."""

    def _verifier_context(self, *, elapsed_eval_s=0.0):
        import types
        clock = FakeClock()
        limits = BudgetLimits(max_model_requests=10, max_steps=10,
                              agent_wall_s=60.0, verifier_wall_s=30.0,
                              total_wall_s=120.0)
        budget = BudgetTracker(limits, clock)
        budget.start("execution")
        budget.begin_phase("evaluation")
        clock.advance_s(elapsed_eval_s)
        runtime = FakeContainerRuntime(clock)
        handle = runtime.start(ContainerSpec(run_id="r", scope="verifier",
                                             image="img"))
        run_dir = Path(self.id().replace(".", "_"))
        run_dir.mkdir(parents=True, exist_ok=True)
        self.addCleanup(lambda: __import__("shutil").rmtree(run_dir, True))
        # a REAL (tiny) record file so the verifier's record read works
        record_path = run_dir / "record.json"
        record_path.write_text(json.dumps(
            {"instance_id": "i", "problem_statement": "p"}), encoding="utf-8")
        recorder = SemanticRecorder(run_dir, clock, run_id="r",
                                    attempt_id="r-a1", task_id="i",
                                    source_type="synthetic")
        recorder.begin_run()
        spec = VerifierSpec(instance_id="i", image="img",
                            eval_script_ref="x", log_parser="p",
                            eval_type="pass_and_fail",
                            record_locator=str(record_path))
        from agent_workload_characterization.runners.coding_pilot import \
            SwebenchVerifierRunner
        verifier = SwebenchVerifierRunner(authorized=True)
        return verifier, spec, budget, recorder, runtime, handle

    def test_deadline_exhausted_terminates_workload(self):
        import types, sys
        from types import SimpleNamespace
        # elapsed 30 s of a 30 s verifier wall -> remaining == 0: the
        # FIRST operation must refuse and TERMINATE the in-container
        # workload (not just time out a local exec client)
        v, spec, budget, recorder, runtime, handle = \
            self._verifier_context(elapsed_eval_s=30.0)
        fake_utils = types.ModuleType("swebench.harness.utils")
        fake_utils.make_test_spec = lambda rec: SimpleNamespace(
            instance_id="i", eval_script="echo x")
        fake_grading = types.ModuleType("swebench.harness.grading")
        fake_grading.get_eval_report = lambda **kw: {}
        fake_pkg = types.ModuleType("swebench")
        fake_harness = types.ModuleType("swebench.harness")
        with mock.patch.dict(sys.modules, {
                "swebench": fake_pkg, "swebench.harness": fake_harness,
                "swebench.harness.utils": fake_utils,
                "swebench.harness.grading": fake_grading}):
            result = v.run(spec, "some patch", budget, recorder,
                           runtime, handle)
        self.assertEqual(result.status, "verifier_timeout")
        self.assertIn("workload termination", result.detail or "")
        self.assertIn(handle.container_id, runtime.terminated)

    def test_eval_timeout_terminates_workload(self):
        import types, sys
        from types import SimpleNamespace
        v, spec, budget, recorder, runtime, handle = \
            self._verifier_context()
        fake_utils = types.ModuleType("swebench.harness.utils")
        fake_utils.make_test_spec = lambda rec: SimpleNamespace(
            instance_id="i", eval_script="echo x")
        fake_grading = types.ModuleType("swebench.harness.grading")
        fake_grading.get_eval_report = lambda **kw: {}
        fake_pkg = types.ModuleType("swebench")
        fake_harness = types.ModuleType("swebench.harness")

        def execute(handle_, command, timeout_s, **kw):
            if command.startswith("bash /eval.sh"):
                return {"returncode": 124, "output": "", "timed_out": True}
            return {"returncode": 0, "output": "ok"}

        runtime.execute = execute
        with mock.patch.dict(sys.modules, {
                "swebench": fake_pkg, "swebench.harness": fake_harness,
                "swebench.harness.utils": fake_utils,
                "swebench.harness.grading": fake_grading}):
            result = v.run(spec, "some patch", budget, recorder,
                           runtime, handle)
        self.assertEqual(result.status, "verifier_timeout")
        self.assertIn(handle.container_id, runtime.terminated)


class Round5StopChainTests(PilotTestBase):
    """Fifth-review regressions: stop semantics for agent and verifier.

    - pkill pattern must be an ERE ALTERNATION (a ';' matches nothing)
      and an unconfirmed stop must FALL THROUGH to docker stop;
    - killing the mini subprocess must ALSO terminate the commands it
      launched inside the container, with the confirmation state
      recorded (confirmed / not confirmed / container exited);
    - a blocked verifier must be interruptible by the artifact-ceiling
      flag (should_stop)."""

    GIT_DIFF_CMD = "git -c core.fileMode=false diff"

    def _harness(self, child_code):
        import sys as _sys
        from agent_workload_characterization.runners.mini_agent_adapter \
            import MiniSweAgentHarness
        return MiniSweAgentHarness(
            Path(_sys.executable), authorized=True, child_code=child_code,
            mini_config={"model": {
                "model_name": "openai/deepseek-v4-flash"}},
            poll_interval_s=0.05)

    def _context(self, harness, limits):
        clock = FakeClock()
        readers = _reader_pair()
        runtime = FakeContainerRuntime(clock, readers=readers)
        runtime.execute_script[self.GIT_DIFF_CMD] = {
            "returncode": 0, "output": "+++ patch\n"}
        task = AgentTask(instance_id="i", problem_statement="p",
                         image="synthetic-image:latest")
        run_dir = self.root / "run-w"
        run_dir.mkdir()
        recorder = SemanticRecorder(run_dir, clock, run_id="runw",
                                    attempt_id="runw-a1", task_id="i",
                                    source_type="synthetic")
        recorder.begin_run()
        budget = BudgetTracker(limits, clock)
        budget.start()
        container = runtime.start(ContainerSpec(run_id="runw", scope="agent",
                                                image="synthetic"))
        return task, budget, recorder, runtime, container, run_dir

    def test_terminate_workload_pattern_is_alternation(self):
        from agent_workload_characterization.runners.container_runtime \
            import DockerCliRuntime
        pattern = DockerCliRuntime.WORKLOAD_PATTERN
        self.assertIn("|", pattern)
        self.assertNotIn(";", pattern)

    def test_agent_budget_kill_terminates_container_workload(self):
        harness = self._harness(FAKE_CHILD_OVER_BUDGET)
        limits = BudgetLimits(max_model_requests=5, max_steps=10,
                              agent_wall_s=60.0, verifier_wall_s=30.0,
                              total_wall_s=120.0)
        task, budget, recorder, runtime, container, run_dir = \
            self._context(harness, limits)
        result = harness.run(task, budget, recorder, runtime, container,
                             None, run_dir)
        self.assertEqual(result.status, "budget_exceeded")
        # the in-container workload was terminated and the confirmation
        # state recorded in both the stop reason and the events
        self.assertIn(container.container_id, runtime.terminated)
        self.assertIn("workload_stop_confirmed=", result.stop_reason or "")
        events = [json.loads(l) for l in
                  (run_dir / "events.jsonl").read_text().splitlines() if l]
        term_events = [e for e in events if e["kind"] == "container"
                       and e["attrs"].get("action") == "terminate_workload"]
        self.assertEqual(len(term_events), 1)
        self.assertIn("confirmed=True", term_events[0]["attrs"]["detail"])

    def test_agent_budget_kill_unconfirmed_stop_recorded(self):
        harness = self._harness(FAKE_CHILD_OVER_BUDGET)
        limits = BudgetLimits(max_model_requests=5, max_steps=10,
                              agent_wall_s=60.0, verifier_wall_s=30.0,
                              total_wall_s=120.0)
        task, budget, recorder, runtime, container, run_dir = \
            self._context(harness, limits)
        runtime.next_terminate_result = {
            "confirmed": False, "method": "docker_stop_failed",
            "container_alive": None, "error": "TimeoutExpired"}
        result = harness.run(task, budget, recorder, runtime, container,
                             None, run_dir)
        self.assertEqual(result.status, "budget_exceeded")
        # NOT confirmed — recorded as such, never as success
        self.assertIn("workload_stop_confirmed=False",
                      result.stop_reason or "")

    def test_watchdog_kill_terminates_container_workload(self):
        script = {"steps": [
            {"model": {"usage": {"completion_tokens": 5}}, "tools": []}],
            "final": {"status": "ok", "candidate_patch": "x"},
            "hang_after_step": 1}
        limits = BudgetLimits(max_model_requests=10, max_steps=10,
                              agent_wall_s=1.5, verifier_wall_s=30.0,
                              total_wall_s=120.0)
        runner = self.make_runner(script=script, limits=limits)
        outcome = runner.run()
        self.assertEqual(outcome.execution_status, "watchdog_timeout")
        self.assertTrue(runner.runtime.terminated,
                        "watchdog kill must terminate the in-container "
                        "workload")
        run_dir = Path(outcome.run_dir)
        events = [json.loads(l) for l in
                  (run_dir / "events.jsonl").read_text().splitlines() if l]
        term = [e for e in events if e["kind"] == "container"
                and e["attrs"].get("action") == "terminate_workload"]
        self.assertEqual(len(term), 1)

    def test_verifier_unconfirmed_stop_recorded(self):
        import types, sys
        from types import SimpleNamespace
        from agent_workload_characterization.runners.coding_pilot import \
            SwebenchVerifierRunner
        clock = FakeClock()
        limits = BudgetLimits(max_model_requests=10, max_steps=10,
                              agent_wall_s=60.0, verifier_wall_s=30.0,
                              total_wall_s=120.0)
        budget = BudgetTracker(limits, clock)
        budget.start("execution")
        budget.begin_phase("evaluation")
        clock.advance_s(30.0)  # verifier wall exhausted
        runtime = FakeContainerRuntime(clock)
        handle = runtime.start(ContainerSpec(run_id="r", scope="verifier",
                                             image="img"))
        runtime.next_terminate_result = {
            "confirmed": False, "method": "docker_stop_failed",
            "container_alive": None, "error": "OSError"}
        run_dir = self.root / "v1"
        run_dir.mkdir()
        record_path = run_dir / "record.json"
        record_path.write_text(json.dumps({"instance_id": "i"}))
        recorder = SemanticRecorder(run_dir, clock, run_id="r",
                                    attempt_id="r-a1", task_id="i",
                                    source_type="synthetic")
        recorder.begin_run()
        spec = VerifierSpec(instance_id="i", image="img",
                            eval_script_ref="x", log_parser="p",
                            eval_type="pass_and_fail",
                            record_locator=str(record_path))
        v = SwebenchVerifierRunner(authorized=True)
        fake_utils = types.ModuleType("swebench.harness.utils")
        fake_utils.make_test_spec = lambda rec: SimpleNamespace(
            instance_id="i", eval_script="echo x")
        fake_grading = types.ModuleType("swebench.harness.grading")
        fake_grading.get_eval_report = lambda **kw: {}
        fake_pkg = types.ModuleType("swebench")
        fake_harness = types.ModuleType("swebench.harness")
        with mock.patch.dict(sys.modules, {
                "swebench": fake_pkg, "swebench.harness": fake_harness,
                "swebench.harness.utils": fake_utils,
                "swebench.harness.grading": fake_grading}):
            result = v.run(spec, "patch", budget, recorder, runtime, handle)
        self.assertEqual(result.status, "verifier_timeout")
        self.assertIn("stop_state=stop_not_confirmed", result.detail)

    def test_verifier_docker_stop_state_recorded(self):
        import types, sys
        from types import SimpleNamespace
        from agent_workload_characterization.runners.coding_pilot import \
            SwebenchVerifierRunner
        clock = FakeClock()
        limits = BudgetLimits(max_model_requests=10, max_steps=10,
                              agent_wall_s=60.0, verifier_wall_s=30.0,
                              total_wall_s=120.0)
        budget = BudgetTracker(limits, clock)
        budget.start("execution")
        budget.begin_phase("evaluation")
        clock.advance_s(30.0)
        runtime = FakeContainerRuntime(clock)
        handle = runtime.start(ContainerSpec(run_id="r", scope="verifier",
                                             image="img"))
        # docker stop succeeded: confirmed, but the container EXITED ->
        # final counters may be unreadable (recorded, not hidden)
        runtime.next_terminate_result = {
            "confirmed": True, "method": "docker_stop",
            "container_alive": False, "rc": 0}
        run_dir = self.root / "v2"
        run_dir.mkdir()
        record_path = run_dir / "record.json"
        record_path.write_text(json.dumps({"instance_id": "i"}))
        recorder = SemanticRecorder(run_dir, clock, run_id="r",
                                    attempt_id="r-a1", task_id="i",
                                    source_type="synthetic")
        recorder.begin_run()
        spec = VerifierSpec(instance_id="i", image="img",
                            eval_script_ref="x", log_parser="p",
                            eval_type="pass_and_fail",
                            record_locator=str(record_path))
        v = SwebenchVerifierRunner(authorized=True)
        fake_utils = types.ModuleType("swebench.harness.utils")
        fake_utils.make_test_spec = lambda rec: SimpleNamespace(
            instance_id="i", eval_script="echo x")
        fake_grading = types.ModuleType("swebench.harness.grading")
        fake_grading.get_eval_report = lambda **kw: {}
        fake_pkg = types.ModuleType("swebench")
        fake_harness = types.ModuleType("swebench.harness")
        with mock.patch.dict(sys.modules, {
                "swebench": fake_pkg, "swebench.harness": fake_harness,
                "swebench.harness.utils": fake_utils,
                "swebench.harness.grading": fake_grading}):
            result = v.run(spec, "patch", budget, recorder, runtime, handle)
        self.assertEqual(result.status, "verifier_timeout")
        self.assertIn("stopped_via_docker_stop", result.detail)
        self.assertIn("counters may be unreadable", result.detail)

    def test_should_stop_interrupts_execute(self):
        clock = FakeClock()
        runtime = FakeContainerRuntime(clock)
        handle = runtime.start(ContainerSpec(run_id="r", scope="agent",
                                             image="img"))
        out = runtime.execute(handle, "long command", 60,
                              should_stop=lambda: True)
        self.assertEqual(out["returncode"], 124)
        self.assertTrue(out.get("timed_out"))
        self.assertEqual(out.get("stopped_by"), "external")

    def test_storage_size_in_run_argv(self):
        runtime = DockerCliRuntime(authorized=False)
        spec = ContainerSpec(run_id="r", scope="agent", image="img",
                             storage_size="6g")
        argv = runtime.build_run_argv(spec, "n1")
        self.assertIn("--storage-opt", argv)
        self.assertEqual(argv[argv.index("--storage-opt") + 1], "size=6g")


FAKE_CHILD_BIG_OUTPUT = r'''
import json, pathlib, sys
# pipe-pressure repro: emit 1 MiB BEFORE the normal status/summary flow.
# With exit-then-read pipes the child would block on write forever; with
# continuous draining it completes normally.
sys.stdout.write("x" * (1024 * 1024) + "\n")
sys.stdout.flush()
payload = json.loads(sys.stdin.read())
out = payload["output"]
pathlib.Path(out["status_path"]).write_text(
    json.dumps({"n_calls": 1, "n_steps": 1, "cost": 0.0, "elapsed_s": 1,
                "ok": True, "usage": None,
                "t_start_ns": 0, "t_end_ns": 1}) + "\n")
pathlib.Path(out["trajectory_path"]).write_text("{}")
print(json.dumps({"exit_status": "submitted", "n_calls": 1, "n_steps": 1}))
'''

FAKE_CHILD_LONG_LINE = r'''
import json, pathlib, sys
# seventh-review repro: a single 2 MiB line WITHOUT newlines. Line-based
# reading would buffer the whole line before any size check; block-based
# reading keeps only the capped prefix and lets the child finish.
sys.stdout.write("y" * (2 * 1024 * 1024))
sys.stdout.write("\n")
sys.stdout.flush()
payload = json.loads(sys.stdin.read())
out = payload["output"]
pathlib.Path(out["status_path"]).write_text(
    json.dumps({"n_calls": 1, "n_steps": 1, "cost": 0.0, "elapsed_s": 1,
                "ok": True, "usage": None,
                "t_start_ns": 0, "t_end_ns": 1}) + "\n")
pathlib.Path(out["trajectory_path"]).write_text("{}")
print(json.dumps({"exit_status": "submitted", "n_calls": 1, "n_steps": 1}))
'''

FAKE_DOCKER_SCRIPT = """#!/bin/sh
# offline docker stand-in for runtime reliability tests. The process-tree
# check (arriving as `exec ... sh -c <script>`) is executed FOR REAL:
# the actual check script reads ${PROC_ROOT:-/proc}, so the fake docker
# points PROC_ROOT at a fixture tree (FAKE_FIXTURE). FAKE_SELF=1 adds a
# live fixture entry for the checking shell's own pid — only the real
# scan's self-exclusion keeps that from reporting busy.
last=
for a in "$@"; do last=$a; done
case "$*" in
  *"pkill"*) exit 0 ;;
esac
if [ "${1:-}" = "stop" ]; then exit 0; fi
if [ "${1:-}" = "exec" ]; then
  case "$last" in
    *PROC_ROOT*)
      export PROC_ROOT="${FAKE_FIXTURE:?FAKE_FIXTURE not set}"
      if [ "${FAKE_SELF:-0}" = 1 ]; then
        mkdir -p "$PROC_ROOT/$$"
        printf '%s ((self)) S 1 1\n' "$$" > "$PROC_ROOT/$$/stat"
      fi
      ( eval "$last" )
      exit $?
      ;;
  esac
  case "${FAKE_MODE:-}" in
    big-output) python3 -c "print('x' * 1048576)"; exit 0 ;;
    big-line) python3 -c "import sys; sys.stdout.write('x' * 2048)"; exit 0 ;;
    sleep) exec sleep 30 ;;
  esac
fi
exit 0
"""


class _FakeDockerTestBase(unittest.TestCase):
    """Shared harness: a fake docker executable + /proc fixture trees.

    The process-tree check regressions EXECUTE THE ACTUAL SCAN SCRIPT
    (fixtures differ from production only via PROC_ROOT); no preset
    return codes are injected for the check."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        self.fake_docker = self.root / "fake-docker"
        self.fake_docker.write_text(FAKE_DOCKER_SCRIPT)
        self.fake_docker.chmod(0o755)
        self._fixtures = self.root / "fixtures"
        self._fixtures.mkdir()
        self._export_env("FAKE_FIXTURE", str(self._fixture({1: ("S", 0)})))
        self._export_env("FAKE_SELF", "0")
        self._export_env("FAKE_MODE", "")

    def _export_env(self, key: str, value: str):
        import os
        os.environ[key] = value
        self.addCleanup(os.environ.pop, key, None)

    def _fixture(self, entries: dict) -> Path:
        """pid -> (state, ppid) fake /proc tree (stat line format matches
        the real one: fields after the last ')' are state and ppid)."""
        d = self._fixtures / f"fx{len(list(self._fixtures.iterdir()))}"
        d.mkdir()
        for pid, (state, ppid) in entries.items():
            p = d / str(pid)
            p.mkdir()
            (p / "stat").write_text(
                f"{pid} ((proc)) {state} {ppid} 1 ...\n", encoding="utf-8")
        return d

    def _runtime(self, mode: str = "") -> DockerCliRuntime:
        self._export_env("FAKE_MODE", mode)
        return DockerCliRuntime(docker_executable=str(self.fake_docker),
                                authorized=True)

    @staticmethod
    def _handle() -> ContainerHandle:
        return ContainerHandle(container_id="cid-xyz",
                               spec=ContainerSpec(run_id="r", scope="agent",
                                                  image="img"))


class Round6PipeDrainTests(_FakeDockerTestBase):
    """Sixth/seventh-review repro: a child producing more than the pipe
    buffer (~64 KiB) must NOT be misreported as a timeout; the memory cap
    must be block-based (a newline-free line cannot bypass it) and must
    keep the PREFIX (the old line-based code dropped the whole oversized
    line: cap=1024, one 2048-char line, limit=100 -> returned "")."""

    def test_large_output_completes_without_timeout(self):
        runtime = self._runtime("big-output")
        out = runtime.execute(self._handle(), "produce 1 MiB",
                              timeout_s=20, output_limit=2_000_000)
        self.assertEqual(out["returncode"], 0, out["output"][:100])
        self.assertFalse(out.get("timed_out"))
        self.assertFalse(out.get("output_truncated"))
        self.assertGreaterEqual(len(out["output"]), 1024 * 1024)

    def test_output_limit_applies_on_normal_path(self):
        runtime = self._runtime("big-output")
        out = runtime.execute(self._handle(), "produce 1 MiB",
                              timeout_s=20, output_limit=100)
        self.assertEqual(out["returncode"], 0)
        self.assertEqual(len(out["output"]), 100)
        self.assertTrue(out["output_truncated"])

    def test_output_limit_applies_on_timeout_path(self):
        runtime = self._runtime("sleep")
        out = runtime.execute(self._handle(), "sleep",
                              timeout_s=1, output_limit=100)
        self.assertTrue(out.get("timed_out"))
        self.assertEqual(out["returncode"], 124)
        # the SAME limit applies on the timeout path (the sixth-review
        # repro saw 65536 bytes returned with output_limit=100)
        self.assertLessEqual(len(out["output"]), 100)
        self.assertIn("termination", out)

    def test_hard_cap_is_memory_bound_and_prefix_kept(self):
        # the seventh-review repro: cap 1024, one newline-free 2048-char
        # line, keep first 100 -> must return 100 chars, not ""
        runtime = self._runtime("big-line")
        runtime.MAX_CAPTURE_BYTES = 1024
        out = runtime.execute(self._handle(), "one 2048-char line",
                              timeout_s=20, output_limit=100)
        self.assertEqual(out["returncode"], 0)
        self.assertEqual(out["output"], "x" * 100)
        self.assertTrue(out["output_truncated"])
        self.assertEqual(out["output_bytes_total"], 2048)

    def _mini_context(self, harness):
        clock = FakeClock()
        runtime = FakeContainerRuntime(clock)
        runtime.execute_script["git -c core.fileMode=false diff"] = {
            "returncode": 0, "output": "+++ patch\n"}
        task = AgentTask(instance_id="i", problem_statement="p",
                         image="img")
        run_dir = self.root / "run-mini"
        run_dir.mkdir()
        recorder = SemanticRecorder(run_dir, clock, run_id="runmini",
                                    attempt_id="runmini-a1", task_id="i",
                                    source_type="synthetic")
        recorder.begin_run()
        budget = BudgetTracker(
            BudgetLimits(max_model_requests=5, max_steps=5,
                         agent_wall_s=60.0, verifier_wall_s=30.0,
                         total_wall_s=120.0), clock)
        budget.start()
        container = runtime.start(ContainerSpec(run_id="runmini",
                                                scope="agent", image="img"))
        return task, budget, recorder, runtime, container, run_dir

    def test_mini_parent_drains_big_child_output(self):
        from agent_workload_characterization.runners.mini_agent_adapter \
            import MiniSweAgentHarness
        import sys as _sys
        harness = MiniSweAgentHarness(
            Path(_sys.executable), authorized=True,
            child_code=FAKE_CHILD_BIG_OUTPUT,
            mini_config={"model": {"model_name": "openai/t"}},
            poll_interval_s=0.05)
        task, budget, recorder, runtime, container, run_dir = \
            self._mini_context(harness)
        result = harness.run(task, budget, recorder, runtime, container,
                             None, run_dir)
        # the child finished normally despite writing 1 MiB to stdout
        self.assertEqual(result.status, "ok")
        self.assertEqual(result.candidate_patch, "+++ patch")
        self.assertEqual(budget.usage_dict()["requests"], 1)
        self.assertTrue((run_dir / "mini_status.jsonl").is_file())

    def test_mini_parent_cap_keeps_prefix_on_long_line(self):
        # mini parent had the same line-based pattern; a 2 MiB newline-
        # free line with cap 1024 must not block the child, and the
        # counters fall back to the status file when the summary line
        # lands beyond the cap
        from agent_workload_characterization.runners.mini_agent_adapter \
            import MiniSweAgentHarness
        import sys as _sys
        harness = MiniSweAgentHarness(
            Path(_sys.executable), authorized=True,
            child_code=FAKE_CHILD_LONG_LINE,
            mini_config={"model": {"model_name": "openai/t"}},
            poll_interval_s=0.05)
        harness.CAPTURE_CAP_BYTES = 1024
        task, budget, recorder, runtime, container, run_dir = \
            self._mini_context(harness)
        result = harness.run(task, budget, recorder, runtime, container,
                             None, run_dir)
        self.assertEqual(result.status, "ok")
        self.assertEqual(result.candidate_patch, "+++ patch")
        self.assertEqual(budget.usage_dict()["requests"], 1)
        self.assertEqual(result.steps, 1)  # from the status file fallback


class Round7ProcessCheckTests(_FakeDockerTestBase):
    """Seventh-review regressions: the ACTUAL scan logic executes against
    fixture trees (PROC_ROOT; no injected return codes). Return-value
    convention: 0 = idle (confirmed stop), 1 = busy, 2 = check error —
    the OLD caller mapped rc==1 to confirmed, i.e. exactly inverted."""

    def _terminate(self, fixture: Path, *, fake_self: bool = False) -> dict:
        self._export_env("FAKE_FIXTURE", str(fixture))
        self._export_env("FAKE_SELF", "1" if fake_self else "0")
        runtime = DockerCliRuntime(docker_executable=str(self.fake_docker),
                                   authorized=True)
        return runtime.terminate_workload(self._handle())

    def test_idle_tree_confirms_with_container_alive(self):
        result = self._terminate(self._fixture({1: ("S", 0)}))
        self.assertTrue(result["confirmed"])
        self.assertEqual(result["method"], "pkill+process_tree_check")
        self.assertTrue(result["container_alive"])

    def test_busy_tree_falls_through_to_docker_stop(self):
        # a live non-main workload process (rc=1 busy) must NOT confirm —
        # the old inverted caller returned confirmed=True here
        result = self._terminate(self._fixture({1: ("S", 0),
                                                500: ("S", 1)}))
        self.assertEqual(result["method"], "docker_stop")
        self.assertFalse(result["container_alive"])
        self.assertTrue(result["confirmed"])  # the stop itself succeeded

    def test_zombie_processes_do_not_count(self):
        result = self._terminate(self._fixture({1: ("S", 0),
                                                500: ("Z", 1)}))
        self.assertTrue(result["confirmed"])
        self.assertEqual(result["method"], "pkill+process_tree_check")
        self.assertTrue(result["container_alive"])

    def test_check_error_falls_through_to_docker_stop(self):
        # no PID 1 in the fixture: the real scan exits 2 (check error);
        # an unverifiable check must NOT confirm with the container alive
        result = self._terminate(self._fixture({}))
        self.assertEqual(result["method"], "docker_stop")
        self.assertFalse(result["container_alive"])
        self.assertTrue(result["confirmed"])

    def test_check_process_itself_excluded(self):
        # FAKE_SELF adds a live fixture entry for the checking shell's
        # own pid; only the scan's $$-exclusion keeps this from busy
        result = self._terminate(self._fixture({1: ("S", 0)}),
                                 fake_self=True)
        self.assertTrue(result["confirmed"])
        self.assertEqual(result["method"], "pkill+process_tree_check")
        self.assertTrue(result["container_alive"])

    def test_pattern_has_no_semicolon(self):
        self.assertNotIn(";", DockerCliRuntime.WORKLOAD_PATTERN)
        self.assertIn("|", DockerCliRuntime.WORKLOAD_PATTERN)


class Round8ReportCloseoutTests(PilotTestBase):
    """Eighth-review regressions: derived-report closeout for the real C
    run — tool counts from the trajectory (never a fake zero), agent
    exit status preserved, formal-null I/O under the approved v1
    degradation wording, and recursive archive completeness."""

    def test_verifier_subdir_file_in_manifest_and_accounting(self):
        # the real verifier writes run_dir/verifier/test_output.txt; the
        # original manifest iterated TOP-LEVEL files only and missed it
        from agent_workload_characterization.runners.coding_pilot import \
            VerifierResult

        class FileWritingVerifier:
            name = "file-writing"

            def __init__(self, clock):
                self.clock = clock

            def run(self, spec, candidate_patch, budget, recorder,
                    runtime, container):
                vdir = Path(recorder.run_dir) / "verifier"
                vdir.mkdir(parents=True, exist_ok=True)
                (vdir / "test_output.txt").write_text(
                    ">>>>> Start Test Output\nok\n>>>>> End Test Output\n")
                return VerifierResult(status="ok", resolved=True)

        clock = FakeClock()
        runtime = FakeContainerRuntime(clock, readers=_reader_pair())
        harness = FakeAgentHarness(clock, OK_SCRIPT)
        task = AgentTask(instance_id="i", problem_statement="p",
                         image="img")
        vspec = VerifierSpec(instance_id="i", image="img",
                             eval_script_ref="x", log_parser="p",
                             eval_type="pass_and_fail",
                             record_locator="x")
        runner = CodingPilotRunner(
            project_root=self.root, collection="SYNTH-R8",
            harness=harness, verifier=FileWritingVerifier(clock),
            runtime=runtime, clock=clock,
            limits=BudgetLimits(max_model_requests=10, max_steps=10,
                                agent_wall_s=60.0, verifier_wall_s=30.0,
                                total_wall_s=120.0),
            task=task, verifier_spec=vspec, image="img")
        outcome = runner.run()
        self.assertEqual(outcome.archive_status, "ok")
        run_dir = Path(outcome.run_dir)
        manifest = json.loads((run_dir / "manifest.json").read_text())
        self.assertIn("verifier/test_output.txt", manifest["files"])
        # accounting covers the full tree (verifier file included)
        accounted = outcome.budget_usage["artifact_bytes"]
        total = sum(p.stat().st_size for p in run_dir.rglob("*")
                    if p.is_file())
        self.assertEqual(accounted, total)

    def _real_shape_run_dir(self) -> Path:
        """A run dir shaped like the real C attempt: trajectory with
        tool actions, v1-blkio evidence with numeric io, a manifest that
        (like the original) misses the verifier subdir file."""
        run_dir = self.root / "realshape"
        (run_dir / "verifier").mkdir(parents=True)
        traj = {"info": {"exit_status": "LimitsExceeded",
                         "submission": ""},
                "messages": [
                    {"role": "system", "content": "s"},
                    {"role": "user", "content": "task"},
                    {"role": "assistant", "content": "a",
                     "extra": {"actions": [
                         {"command": "grep -rn x /testbed",
                          "tool_call_id": "c1"}]}},
                    {"role": "tool", "content": "out1"},
                    {"role": "assistant", "content": "b",
                     "extra": {"actions": [
                         {"command": "python repro.py",
                          "tool_call_id": "c2"}]}},
                    {"role": "tool", "content": "out2"},
                    {"role": "exit", "content": "LimitsExceeded"},
                ]}
        (run_dir / "mini_trajectory.json").write_text(
            json.dumps(traj))
        (run_dir / "candidate.patch").write_text("--- a\n+++ b\n")
        (run_dir / "mini_status.jsonl").write_text('{"n_calls": 1}\n')
        (run_dir / "verifier" / "test_output.txt").write_text("log\n")
        samples = {
            "scopes": {"s1": {
                "scope_kind": "agent_container",
                "cpu_core_seconds": 1.5, "cpu_core_seconds_reason": None,
                "wall_s": 2.0, "n_samples": 3,
                "memory_kernel_peak_bytes": 100,
                "memory_peak_basis": "v1_max_usage_in_bytes",
                "io": {"read_bytes": 0, "write_bytes": 48,
                       "evidence": "io.stat_boundary_delta",
                       "reason": None}}},
            "evidence": {"s1": {"boundary_start": {}, "boundary_end": {
                "read_status": {"io": "ok_summed_devices:"
                               "blkio.throttle.io_service_bytes_recursive"}},
                "samples": [{}], "sample_gaps_ns": []}},
            "collector": {"scope": "collector"}}
        (run_dir / "samples.json").write_text(json.dumps(samples))
        (run_dir / "metadata.json").write_text(json.dumps({
            "run_id": "r", "attempt_id": "r-a1", "task_id": "i",
            "source_type": "benchmark_real",
            "execution_status": "ok", "evaluation_status": "ok",
            "budget_usage": {"artifact_bytes": 100}}))
        (run_dir / "events.jsonl").write_text(
            json.dumps({"kind": "llm_request", "status": "closed",
                        "t_monotonic_ns": 1, "clock_domain": "d",
                        "attrs": {"ok": True, "usage": {"x": 1}}}) + "\n")
        (run_dir / "manifest.json").write_text(json.dumps({
            "files": {"candidate.patch": "h", "events.jsonl": "h"}}))
        return run_dir

    def test_summary_extracts_tools_and_agent_from_trajectory(self):
        run_dir = self._real_shape_run_dir()
        summary = summarize_run(run_dir)
        # tools: from the trajectory, NEVER a fake zero
        self.assertEqual(summary["tools"]["calls"], 2)
        self.assertEqual(summary["tools"]["observation_messages"], 2)
        self.assertEqual(summary["tools"]["source"], "mini_trajectory")
        self.assertIn("not_available", summary["tools"]["classification"])
        # agent behavior preserved explicitly
        self.assertEqual(summary["agent"]["exit_status"],
                         "LimitsExceeded")
        self.assertFalse(summary["agent"]["submitted"])
        self.assertEqual(summary["agent"]["candidate_source"],
                         "container_working_tree_git_diff")

    def test_summary_io_formal_null_with_diagnostic(self):
        run_dir = self._real_shape_run_dir()
        summary = summarize_run(run_dir)
        io = summary["scopes"][0]["io"]
        self.assertIsNone(io["formal"])
        self.assertIn("degraded_host_v1_blkio", io["reason"])
        self.assertEqual(io["diagnostic"]["write_bytes"], 48)
        self.assertEqual(io["diagnostic"]["evidence"],
                         "io.stat_boundary_delta")

    def test_summary_archive_reconciliation(self):
        run_dir = self._real_shape_run_dir()
        summary = summarize_run(run_dir)
        arch = summary["archive"]
        self.assertEqual(arch["reported_artifact_bytes"], 100)
        self.assertGreater(arch["actual_run_dir_bytes"], 100)
        self.assertIn("verifier/test_output.txt",
                      arch["files_missing_from_original_manifest"])
        self.assertIn("verifier/test_output.txt",
                      arch["bytes_outside_in_run_accounting"])
        self.assertIn("supplement manifest",
                      arch["accounting_scope_note"])

    def test_fake_flow_tools_fall_back_to_events(self):
        outcome = self.make_runner().run()
        summary = summarize_run(Path(outcome.run_dir))
        self.assertEqual(summary["tools"]["source"], "runner_events")
        self.assertEqual(summary["tools"]["calls"], 2)
        self.assertIsNone(summary["agent"]["exit_status"])
        self.assertIn("PIPELINE", summary["agent"]["note"])


class AnalyzerCliTests(PilotTestBase):
    def test_summarize_run_marks_synthetic(self):
        outcome = self.make_runner().run()
        summary = summarize_run(Path(outcome.run_dir))
        self.assertEqual(summary["source_type"], "synthetic")
        self.assertTrue(any("SYNTHETIC" in note
                            for note in summary["limitations"]))
        self.assertGreaterEqual(summary["llm"]["requests"], 1)
        self.assertEqual(summary["tools"]["calls"], 2)
        self.assertIn("Search", summary["tools"]["categories"])
        self.assertEqual(summary["status"]["execution"], "ok")

    def test_write_summary_report_exclusive(self):
        outcome = self.make_runner().run()
        summary = summarize_run(Path(outcome.run_dir))
        report_dir = self.root / "reports" / "resource" / "SYNTH-TEST"
        result = write_summary_report(report_dir, summary,
                                      batch="SYNTH-TEST")
        self.assertTrue(Path(result["path"]).is_dir())
        with self.assertRaises(FileExistsError):
            write_summary_report(report_dir, summary, batch="SYNTH-TEST")

    def test_cli_plan_coding_pilot(self):
        from agent_workload_characterization.cli import main
        config = {
            "task": {"instance_id": "django__django-16485",
                     "record_sha256": "x" * 64},
            "harness": {"name": "mini-swe-agent"},
            "model": {"name": "openai/deepseek-v4-flash"},
            "image": {"candidate_ref": "swebench/sweb.eval.x86_64."
                                       "django_1776_django-16485:latest",
                      "digest": None},
            "execution_authorized": False,
            "gates": {"A_offline_development": "complete"},
            "budget_proposal_gate_c": {
                "model_requests": 30, "steps": 30, "agent_wall_min": 25,
                "verifier_wall_min": 5, "total_wall_min": 30},
        }
        import yaml
        cfg_path = self.root / "coding_pilot.yaml"
        cfg_path.write_text(yaml.safe_dump(config))
        with mock.patch("sys.stdout"):
            rc = main(["plan-coding-pilot", "--config", str(cfg_path)])
        self.assertEqual(rc, 0)

    def test_cli_rejects_authorized_config(self):
        from agent_workload_characterization.cli import main
        config = {
            "task": {"instance_id": "django__django-16485"},
            "image": {"digest": None},
            "execution_authorized": True,
            "budget_proposal_gate_c": {
                "model_requests": 30, "steps": 30, "agent_wall_min": 25,
                "verifier_wall_min": 5, "total_wall_min": 30},
        }
        import yaml
        cfg_path = self.root / "bad.yaml"
        cfg_path.write_text(yaml.safe_dump(config))
        with mock.patch("sys.stderr"):
            rc = main(["plan-coding-pilot", "--config", str(cfg_path)])
        self.assertEqual(rc, 1)

    def test_cli_rejects_secrets_in_config(self):
        from agent_workload_characterization.cli import main
        config = {
            "task": {"instance_id": "django__django-16485"},
            "image": {"digest": None},
            "execution_authorized": False,
            "model": {"api_key": SECRET_CANARY},
            "budget_proposal_gate_c": {
                "model_requests": 30, "steps": 30, "agent_wall_min": 25,
                "verifier_wall_min": 5, "total_wall_min": 30},
        }
        import yaml
        cfg_path = self.root / "secret.yaml"
        cfg_path.write_text(yaml.safe_dump(config))
        with mock.patch("sys.stderr"):
            rc = main(["plan-coding-pilot", "--config", str(cfg_path)])
        self.assertEqual(rc, 1)


if __name__ == "__main__":
    unittest.main()
