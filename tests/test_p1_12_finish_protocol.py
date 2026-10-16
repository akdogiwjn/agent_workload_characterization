"""Offline production-adapter finish-protocol regression.

The child runs the real fixed mini-SWE-agent loop and the production
AttachedDockerEnvironment.  Only the docker executable and model transport
are synthetic; no Docker daemon, network, source command, or benchmark runs.
"""
import json
import os
from pathlib import Path
import stat
import tempfile
import unittest
from unittest import mock

from agent_workload_characterization.collectors.semantic_recorder import (
    FakeClock, SemanticRecorder)
from agent_workload_characterization.runners.coding_pilot import (
    BudgetLimits, BudgetTracker)
from agent_workload_characterization.runners.container_runtime import (
    ContainerSpec, FakeContainerRuntime)
from agent_workload_characterization.runners.mini_agent_adapter import (
    AgentTask, MiniSweAgentHarness)

ROOT = Path(__file__).resolve().parents[1]
MINI_VENV = ROOT / ".venvs" / "mini-swe-agent-2.4.6-env01" / "bin" / "python"
SUBMIT_CMD = "echo COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT && cat patch.txt"
NONZERO_CMD = "submit-but-fail"
ORDINARY_CMD = "ordinary-marker-not-first"
CANDIDATE = "--- a/f.py\n+++ b/f.py\n@@ -1 +1 @@\n-old\n+new\n"


def tool_call(command):
    return {"id": "x", "object": "chat.completion", "created": 0,
            "model": "test-model", "choices": [{"index": 0,
            "message": {"role": "assistant", "content": "",
            "tool_calls": [{"id": "c1", "type": "function",
            "function": {"name": "bash",
            "arguments": json.dumps({"command": command})}}]},
            "finish_reason": "tool_calls"}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 20,
                       "total_tokens": 30}}


def make_docker(path):
    # The child invokes: docker exec -w <cwd> <id> bash -c <command>.
    path.write_text("""#!/usr/bin/python3
import sys
command = sys.argv[-1]
if command == %r:
    print(%r, end='')
elif command == %r:
    print(%r, end='')
    raise SystemExit(7)
elif command == %r:
    print('prefix\\nCOMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT\\nnot-a-submit\\n', end='')
else:
    print('ordinary output\\n', end='')
""" % (SUBMIT_CMD,
       "COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT\n" + CANDIDATE,
       NONZERO_CMD,
       "COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT\nshould-not-submit\n",
       ORDINARY_CMD))
    path.chmod(path.stat().st_mode | stat.S_IXUSR)


class AttachedFinishProtocolTests(unittest.TestCase):
    def setUp(self):
        if not MINI_VENV.is_file():
            self.skipTest("fixed mini-SWE-agent venv is unavailable")
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.bin = self.root / "bin"
        self.bin.mkdir()
        make_docker(self.bin / "docker")
        self.run_dir = self.root / "run"
        self.run_dir.mkdir()

    def tearDown(self):
        self.tmp.cleanup()

    def run_attached(self, responses, first_command):
        extras = {"_fake_transport": {"responses": responses}}
        harness = MiniSweAgentHarness(
            MINI_VENV, authorized=True,
            mini_config={"agent": {"system_template": "You are synthetic.",
                                   "instance_template": "{{task}}",
                                   "step_limit": 2,
                                   "wall_time_limit_seconds": 30,
                                   "cost_limit": 0},
                         "model": {"model_name": "openai/test-model",
                                   "model_kwargs": {"num_retries": 0}},
                         "environment": {"timeout": 5}},
            payload_extras=extras, poll_interval_s=0.02)
        clock = FakeClock()
        runtime = FakeContainerRuntime(clock)
        runtime.execute_script["git -c core.fileMode=false diff"] = {
            "returncode": 0, "output": CANDIDATE}
        task = AgentTask(instance_id="django__django-16485",
                         problem_statement="synthetic finish protocol",
                         image="synthetic-image")
        recorder = SemanticRecorder(self.run_dir, clock, run_id="finish",
                                    attempt_id="finish-a1",
                                    task_id=task.instance_id,
                                    source_type="synthetic")
        recorder.begin_run()
        budget = BudgetTracker(BudgetLimits(max_model_requests=2,
                                            max_steps=2,
                                            agent_wall_s=30,
                                            verifier_wall_s=5,
                                            total_wall_s=30), clock)
        budget.start()
        container = runtime.start(ContainerSpec(run_id="finish",
                                                scope="agent",
                                                image="synthetic-image"))
        old_path = os.environ.get("PATH", "")
        with mock.patch.dict(os.environ, {"PATH": str(self.bin) + os.pathsep + old_path}):
            result = harness.run(task, budget, recorder, runtime, container,
                                 run_dir=self.run_dir)
        return result, budget

    def test_attached_submit_stops_real_loop_and_preserves_submission(self):
        result, budget = self.run_attached([tool_call(SUBMIT_CMD)], SUBMIT_CMD)
        self.assertEqual(result.status, "ok")
        status_lines = [json.loads(line) for line in
                        (self.run_dir / "mini_status.jsonl").read_text().splitlines()
                        if line.strip()]
        self.assertTrue(status_lines)
        self.assertTrue(status_lines)
        self.assertTrue(all(line["n_calls"] == 1 for line in status_lines))
        starts = [json.loads(line) for line in (self.run_dir / 'mini_request_starts.jsonl').read_text().splitlines()]
        self.assertEqual(len(starts), 1)
        self.assertEqual(starts[0]['t_start_ns'], status_lines[0]['t_start_ns'])
        trajectory = json.loads((self.run_dir / "mini_trajectory.json").read_text())
        self.assertEqual(trajectory["info"]["exit_status"], "Submitted")
        self.assertEqual(trajectory["info"]["submission"], CANDIDATE)
        events = [json.loads(line) for line in
                  (self.run_dir / "mini_tool_events.jsonl").read_text().splitlines()]
        self.assertEqual(len([e for e in events if e["event"] == "open"]), 1)
        self.assertEqual(len([e for e in events if e["event"] == "error" and
                              e.get("exception_type") == "Submitted"]), 1)
        self.assertEqual(result.candidate_patch, CANDIDATE.strip())

    def test_nonzero_marker_is_not_submission(self):
        result, budget = self.run_attached(
            [tool_call(NONZERO_CMD), tool_call(ORDINARY_CMD)], NONZERO_CMD)
        trajectory = json.loads((self.run_dir / "mini_trajectory.json").read_text())
        self.assertNotEqual(trajectory["info"].get("exit_status"), "Submitted")
        self.assertGreaterEqual(budget.usage_dict()["requests"], 1)

    def test_started_transport_failure_retains_request_terminal(self):
        # Empty scripted transport fails locally; real network remains blocked.
        result, budget = self.run_attached([], ORDINARY_CMD)
        lines = [json.loads(line) for line in
                 (self.run_dir / 'mini_status.jsonl').read_text().splitlines()]
        self.assertEqual(len(lines), 1)
        self.assertEqual(lines[0]['n_calls'], 1)
        self.assertFalse(lines[0]['ok'])
        self.assertIsNotNone(lines[0]['error_type'])
        self.assertIsNone(lines[0]['usage'])
        self.assertGreaterEqual(lines[0]['t_end_ns'], lines[0]['t_start_ns'])
        self.assertEqual(budget.requests, 1)
        starts = [json.loads(line) for line in (self.run_dir / 'mini_request_starts.jsonl').read_text().splitlines()]
        self.assertEqual(len(starts), 1)
        self.assertEqual(starts[0]['n_calls'], 1)

    def test_marker_not_first_is_not_submission(self):
        result, budget = self.run_attached(
            [tool_call(ORDINARY_CMD), tool_call(ORDINARY_CMD)], ORDINARY_CMD)
        trajectory = json.loads((self.run_dir / "mini_trajectory.json").read_text())
        self.assertNotEqual(trajectory["info"].get("exit_status"), "Submitted")
        self.assertGreaterEqual(budget.usage_dict()["requests"], 1)


if __name__ == "__main__":
    unittest.main()
