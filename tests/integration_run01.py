"""RUN-01 C-chain offline integration: REAL installed mini through the
harness subprocess.

Run with the ENV-01 mini venv interpreter:

    PYTHONPATH=src .venvs/mini-swe-agent-2.4.6-env01/bin/python \
        -m unittest tests.integration_run01 -v

What is REAL here: the mini venv child process runs the genuine
DefaultAgent loop + LitellmModel + our StatusTrackingAgent hook, with a
fake httpx transport (network blocked at the transport layer inside the
child) and a fake scripted environment executor (no docker, no model API,
no containers). What remains fake: model responses and tool outputs —
this validates ORCHESTRATION against the real mini code, not model
quality.
"""

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

MINI_VENV = ROOT / ".venvs" / "mini-swe-agent-2.4.6-env01" / "bin" / "python"

from agent_workload_characterization.collectors.semantic_recorder import (  # noqa: E402
    FakeClock, SemanticRecorder)
from agent_workload_characterization.runners.coding_pilot import (  # noqa: E402
    BudgetLimits, BudgetTracker)
from agent_workload_characterization.runners.container_runtime import (  # noqa: E402
    ContainerSpec, FakeContainerRuntime)
from agent_workload_characterization.runners.mini_agent_adapter import (  # noqa: E402
    AgentTask, MiniSweAgentHarness)

GREP_CMD = "grep -rn floatformat /testbed/django/template/defaultfilters.py"
SUBMIT_CMD = "echo COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT && cat patch.txt"
GIT_DIFF_CMD = "git -c core.fileMode=false diff"
CANDIDATE = "--- a/f.py\n+++ b/f.py\n@@ -1 +1 @@\n-fix\n+fixed\n"

FAKE_ENV = {
    GREP_CMD: {"returncode": 0, "output": "184:def floatformat(text, arg=-1):"},
    SUBMIT_CMD: {"returncode": 0,
                 "output": "COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT\n" + CANDIDATE},
}


def _tool_call(command: str) -> dict:
    return {
        "id": "x", "object": "chat.completion", "created": 0,
        "model": "test-model",
        "choices": [{"index": 0, "message": {
            "role": "assistant", "content": "",
            "tool_calls": [{"id": "c1", "type": "function",
                            "function": {"name": "bash",
                                         "arguments": json.dumps(
                                             {"command": command})}}]},
            "finish_reason": "tool_calls"}],
        "usage": {"prompt_tokens": 10, "completion_tokens": 20,
                  "total_tokens": 30}}


MINI_CFG = {
    "agent": {
        "system_template": "You are a test agent.",
        "instance_template": "{{task}}",
        "step_limit": 30,
        "cost_limit": 0,
        "wall_time_limit_seconds": 120,
    },
    "model": {"model_name": "openai/test-model",
              "model_kwargs": {"num_retries": 0}},
    "environment": {"timeout": 30},
}


class MiniThroughputTestBase(unittest.TestCase):
    def setUp(self):
        if not MINI_VENV.is_file():
            self.skipTest(f"mini venv not found: {MINI_VENV}")
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        self.run_dir = self.root / "run-it"
        self.run_dir.mkdir()

    def _harness(self, responses, *, env_script=None, limits=None,
                 poll=0.05):
        extras = {
            "env_mode": "fake",
            "_fake_env": env_script if env_script is not None else FAKE_ENV,
            "_fake_transport": {"responses": responses},
        }
        return MiniSweAgentHarness(
            MINI_VENV, authorized=True, mini_config=MINI_CFG,
            payload_extras=extras, poll_interval_s=poll)

    def _context(self, harness, limits=None, *, git_diff_output=CANDIDATE,
                 budget_clock=None):
        clock = FakeClock()
        runtime = FakeContainerRuntime(clock)
        runtime.execute_script[GIT_DIFF_CMD] = {
            "returncode": 0, "output": git_diff_output}
        task = AgentTask(instance_id="django__django-16485",
                         problem_statement="synthetic floatformat problem",
                         image="synthetic-image:latest")
        recorder = SemanticRecorder(self.run_dir, clock, run_id="runit",
                                    attempt_id="runit-a1",
                                    task_id="django__django-16485",
                                    source_type="synthetic")
        recorder.begin_run()
        budget = BudgetTracker(
            limits or BudgetLimits(max_model_requests=10, max_steps=10,
                                   agent_wall_s=60.0, verifier_wall_s=30.0,
                                   total_wall_s=120.0,
                                   max_output_tokens_per_request=4096),
            budget_clock or clock)
        budget.start()
        container = runtime.start(ContainerSpec(run_id="runit",
                                                scope="agent",
                                                image="synthetic"))
        return task, budget, recorder, runtime, container


class RealMiniChainTests(MiniThroughputTestBase):
    def test_full_chain_submit_and_patch_extraction(self):
        harness = self._harness([_tool_call(GREP_CMD),
                                 _tool_call(SUBMIT_CMD)])
        task, budget, recorder, runtime, container = self._context(harness)
        result = harness.run(task, budget, recorder, runtime, container,
                             None, self.run_dir)
        self.assertEqual(result.status, "ok")
        # candidate extracted from the (fake) working tree
        self.assertEqual(result.candidate_patch, CANDIDATE.strip())
        # two model requests: grep step + submit step
        status = [json.loads(l) for l in
                  (self.run_dir / "mini_status.jsonl").read_text()
                  .splitlines() if l.strip()]
        self.assertEqual(len(status), 2)
        self.assertEqual(status[0]["n_calls"], 1)
        self.assertEqual(status[1]["n_calls"], 2)
        self.assertTrue(all(line.get("ok") for line in status))
        self.assertTrue(all(isinstance(line.get("t_start_ns"), int)
                            and isinstance(line.get("t_end_ns"), int)
                            for line in status))
        # budget fed via cumulative-delta counting
        self.assertEqual(budget.usage_dict()["requests"], 2)
        self.assertEqual(budget.usage_dict()["output_tokens"], 40)
        # real mini trajectory archived; no credential material in it
        traj = json.loads((self.run_dir / "mini_trajectory.json").read_text())
        self.assertEqual(traj["info"]["exit_status"], "Submitted")
        self.assertIn("submission", traj["info"])
        # events carry the child's own request boundaries
        events = [json.loads(l) for l in
                  (self.run_dir / "events.jsonl").read_text().splitlines()
                  if l.strip()]
        llm = [e for e in events if e["kind"] == "llm_request"
               and e["status"] == "closed"]
        self.assertEqual(len(llm), 2)
        for ev in llm:
            self.assertEqual(ev["attrs"].get("timing_source"),
                             "child_status")
            self.assertIsInstance(ev["attrs"].get("t_start_ns"), int)

    def test_format_error_requests_counted_and_flagged(self):
        # plain-text replies force mini's FormatError; 3 in a row end the
        # run with RepeatedFormatError — every billed query must appear in
        # the status file with ok=false and count toward the budget
        plain = {"id": "x", "object": "chat.completion", "created": 0,
                 "model": "test-model",
                 "choices": [{"index": 0, "finish_reason": "stop",
                              "message": {"role": "assistant",
                                          "content": "no tool call"}}],
                 "usage": {"prompt_tokens": 5, "completion_tokens": 3,
                           "total_tokens": 8}}
        harness = self._harness([plain])
        task, budget, recorder, runtime, container = self._context(
            harness, git_diff_output="")
        result = harness.run(task, budget, recorder, runtime, container,
                             None, self.run_dir)
        status = [json.loads(l) for l in
                  (self.run_dir / "mini_status.jsonl").read_text()
                  .splitlines() if l.strip()]
        self.assertGreaterEqual(len(status), 3)
        self.assertTrue(all(line.get("ok") is False for line in status))
        self.assertEqual(budget.usage_dict()["requests"], len(status))
        traj = json.loads((self.run_dir / "mini_trajectory.json").read_text())
        self.assertEqual(traj["info"]["exit_status"], "RepeatedFormatError")
        # clean exit, no working-tree changes -> no_candidate
        self.assertEqual(result.status, "no_candidate")
        self.assertIsNone(result.candidate_patch)

    def test_tool_event_hook_records_real_boundaries(self):
        # G1-01-A2: the tool-event hook must bracket EVERY env.execute
        # with an open line persisted BEFORE the call and a closed line
        # after — real installed mini, fake transport + fake executor,
        # network blocked in child. One failing command (rc!=0) and one
        # normal command both covered.
        bad_cmd = "python repro.py"
        good_cmd = GREP_CMD
        env_script = {bad_cmd: {"returncode": 1, "output": "boom"},
                      GREP_CMD: {"returncode": 0, "output": "found"},
                      SUBMIT_CMD: FAKE_ENV[SUBMIT_CMD]}
        harness = self._harness([_tool_call(bad_cmd),
                                 _tool_call(good_cmd),
                                 _tool_call(SUBMIT_CMD)],
                                 env_script=env_script)
        task, budget, recorder, runtime, container = self._context(harness)
        result = harness.run(task, budget, recorder, runtime, container,
                             None, self.run_dir)
        self.assertEqual(result.status, "ok")
        events_path = self.run_dir / "mini_tool_events.jsonl"
        self.assertTrue(events_path.is_file())
        events = [json.loads(l) for l in
                  events_path.read_text().splitlines() if l.strip()]
        opens = [e for e in events if e["event"] == "open"]
        closes = [e for e in events if e["event"] == "closed"]
        errors = [e for e in events if e["event"] == "error"]
        self.assertEqual(len(opens), 3)
        # the third call raises Submitted (task completion interrupt):
        # the hook must keep it as an ERROR event with the open left
        # explicitly non-closed — never a fake closed record
        self.assertEqual(len(closes), 2)
        self.assertEqual(len(errors), 1)
        self.assertEqual(errors[0]["exception_type"], "Submitted")
        self.assertIsNotNone(errors[0]["t_end_ns"])
        # open lines are persisted before execution: for every closed
        # event its matching open (same event_id) was written earlier
        for c in closes:
            match = [o for o in opens if o["event_id"] == c["event_id"]]
            self.assertEqual(len(match), 1)
            self.assertLessEqual(match[0]["t_start_ns"], c["t_start_ns"])
        # real execution boundaries: t_start <= t_end on every close
        for c in closes:
            self.assertLessEqual(c["t_start_ns"], c["t_end_ns"])
        # identity: tool_call_id preserved; safe projection only
        ids = {c["tool_call_id"] for c in closes}
        self.assertTrue(all(ids))
        for e in events:
            self.assertNotIn("command", e)  # only sha256/length views
            self.assertNotIn("output", e)   # no raw output in any event
        for o in opens:
            self.assertIn("sha256", o["command_view"])
        # failing tool recorded with its returncode (no fake success)
        rc_map = {c["seq"]: c["returncode"] for c in closes}
        self.assertEqual(rc_map[1], 1)
        self.assertEqual(rc_map[2], 0)
        # the failed command text never appears in the event file
        self.assertNotIn("repro.py", events_path.read_text())
        # host observation file (A3) is a STRUCTURED document: identity
        # (pid+starttime), units (clk_tck/page_size), coverage interval,
        # per-snapshot records and the full summary — all persisted, the
        # in-memory-only gap closed
        host_path = self.run_dir / "host_process.jsonl"
        self.assertTrue(host_path.is_file())
        host = json.loads(host_path.read_text())
        self.assertIn("identity", host)
        self.assertIn("pid", host["identity"])
        self.assertIn("starttime_ticks", host["identity"])
        self.assertIn("units", host)
        self.assertIn("clk_tck", host["units"])
        self.assertIn("page_size", host["units"])
        self.assertIn("coverage", host)
        self.assertGreaterEqual(host["coverage"]["n_snapshots"], 1)
        self.assertIsNotNone(host["coverage"]["first_t_monotonic_ns"])
        self.assertIsNotNone(host["coverage"]["last_t_monotonic_ns"])
        self.assertIn("records", host)
        self.assertIn("summary", host)
        self.assertGreaterEqual(len(host["records"]), 1)
        self.assertIn(host["records"][-1]["stat"],
                      ("process_exited", "ok"))
        self.assertEqual(host["summary"]["scope"], "host_mini_child")
        # the harness archive status is recorded (no silent failure)
        self.assertIn(harness.host_archive_status, ("ok", None))

    def test_format_error_branch_writes_no_tool_events(self):
        # format-error requests never reach env.execute: the hook must
        # stay silent (no tool events), and the 3-in-a-row plain replies
        # end with RepeatedFormatError
        plain = {"id": "x", "object": "chat.completion", "created": 0,
                 "model": "test-model",
                 "choices": [{"index": 0, "finish_reason": "stop",
                              "message": {"role": "assistant",
                                          "content": "no tool call"}}],
                 "usage": {"prompt_tokens": 5, "completion_tokens": 3,
                           "total_tokens": 8}}
        harness = self._harness([plain])
        task, budget, recorder, runtime, container = self._context(
            harness, git_diff_output="")
        result = harness.run(task, budget, recorder, runtime, container,
                             None, self.run_dir)
        self.assertEqual(result.status, "no_candidate")
        events_path = self.run_dir / "mini_tool_events.jsonl"
        if events_path.exists():
            content = events_path.read_text().strip()
            self.assertEqual(content, "",
                             "no tool events may be written for "
                             "format-error requests")

    def test_budget_kill_preserves_evidence(self):
        # the INTERNAL mini limits equal the external ones by design
        # (first/second line of defense), so this exercises the EXTERNAL
        # wall kill: slow tool executions + a 4 s agent wall -> the parent
        # kills the child mid-run and keeps the evidence. The assertions
        # are UNCONDITIONAL: at least one model request AND one tool
        # execution must have happened before the kill (otherwise the
        # test would only prove that the wall expired during the ~3 s SDK
        # import phase).
        from agent_workload_characterization.collectors.semantic_recorder \
            import SystemClock
        slow_env = {GREP_CMD: {"returncode": 0,
                               "output": "184:def floatformat(...):",
                               "sleep_s": 0.15}}
        harness = self._harness([_tool_call(GREP_CMD)], env_script=slow_env,
                                poll=0.02)
        limits = BudgetLimits(max_model_requests=30, max_steps=30,
                              agent_wall_s=4.0, verifier_wall_s=30.0,
                              total_wall_s=120.0)
        task, budget, recorder, runtime, container = self._context(
            harness, limits=limits, budget_clock=SystemClock())
        result = harness.run(task, budget, recorder, runtime, container,
                             None, self.run_dir)
        self.assertEqual(result.status, "budget_exceeded")
        self.assertIn("wall_s", result.stop_reason or "")
        # UNCONDITIONAL: >= 1 model request recorded before the kill
        status = [json.loads(l) for l in
                  (self.run_dir / "mini_status.jsonl").read_text()
                  .splitlines() if l.strip()]
        self.assertGreaterEqual(len(status), 1,
                                "no model request recorded before the kill")
        # UNCONDITIONAL: the tool stage was actually entered
        env_log = [json.loads(l) for l in
                   (self.run_dir / "mini_env_log.jsonl").read_text()
                   .splitlines() if l.strip()]
        self.assertGreaterEqual(len(env_log), 1,
                                "no tool command executed before the kill")
        self.assertEqual(env_log[0]["command"], GREP_CMD)
        # the kill terminated the in-container workload too (agent-side
        # stop chain) and recorded the confirmation state
        self.assertIn(container.container_id, runtime.terminated)
        self.assertIn("workload_stop_confirmed=",
                      result.stop_reason or "")
        # evidence preserved after the kill
        self.assertTrue((self.run_dir / "events.jsonl").is_file())


if __name__ == "__main__":
    unittest.main()
