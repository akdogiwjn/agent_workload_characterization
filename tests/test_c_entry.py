"""RUN-01 gate C entry: offline assembly and refusal-path regressions.

Everything here runs OFFLINE against SYNTHETIC fixtures: a fake record,
a fake catalog and a fake venv tree are built in a temp directory and
patched over the module constants — the default suite never depends on
the local real record, catalog or venvs. No containers, no model
requests, no network. The real-mini path is NOT exercised here (it
lives in tests/integration_run01.py against fake transport/env).
"""

from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import yaml

from agent_workload_characterization.collectors.semantic_recorder import (
    FakeClock, SemanticRecorder)
from agent_workload_characterization.runners import c_entry
from agent_workload_characterization.runners.coding_pilot import (
    BudgetLimits, CodingPilotRunner, VerifierSpec)
from agent_workload_characterization.runners.container_runtime import (
    ContainerSpec, FakeContainerRuntime)
from agent_workload_characterization.runners.mini_agent_adapter import (
    AgentTask, FakeAgentHarness)

FAKE_KEY_CANARY = "sk-SYNTH-C-ENTRY-FAKE"

SYNTH_RECORD = {
    "instance_id": "synth__repo-00001",
    "problem_statement": "synthetic problem statement for the entry",
    "log_parser": "parse_log_synth",
    "eval_type": "pass_and_fail",
    "base_commit": "0" * 40,
    "patch": "SECRET-GOLD-CANARY",
    "test_patch": "SECRET-TEST-CANARY",
}

SYNTH_BUDGET = {
    "model_requests": 30, "steps": 30, "output_tokens_per_request": 4096,
    "agent_wall_min": 25, "verifier_wall_min": 5, "total_wall_min": 30,
    "new_artifacts_gib": 5,
    "agent_container_cpu": 4, "agent_container_memory_gib": 8,
    "verifier_container_cpu": 4, "verifier_container_memory_gib": 8,
}

SYNTH_MINI_CONFIG = {
    "agent": {"system_template": "sys {{task}}",
              "instance_template": "{{task}}", "step_limit": 99},
    "model": {"model_name": "anthropic/default",
              "model_kwargs": {"temperature": 0}},
    "environment": {"timeout": 42, "interpreter": ["bash", "-c"]},
}


class _SynthEntryEnv:
    """Builds a temp fixture tree and patches every identity constant."""

    def __init__(self, *, budget_overrides: dict | None = None,
                 execution_authorized: bool = False):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        budget = dict(SYNTH_BUDGET)
        budget.update(budget_overrides or {})

        # fake record
        self.record_path = self.root / "record.json"
        raw = json.dumps(SYNTH_RECORD).encode()
        self.record_path.write_bytes(raw)
        import hashlib
        self.record_sha = hashlib.sha256(raw).hexdigest()

        # fake catalog (registered identity = its actual hash)
        self.catalog_path = self.root / "catalog.yaml"
        catalog = {"execution_authorized": execution_authorized,
                   "budget_proposal_gate_c": budget,
                   "gates": {"C_real_single_task": "synthetic"}}
        self.catalog_path.write_text(yaml.safe_dump(catalog))
        self.catalog_sha = hashlib.sha256(
            self.catalog_path.read_bytes()).hexdigest()

        # fake venv tree with a bundled mini config
        self.mini_venv = self.root / "mini-venv"
        (self.mini_venv / "bin").mkdir(parents=True)
        python = self.mini_venv / "bin/python"
        python.write_text("#!/bin/sh\n")
        python.chmod(0o755)
        bundled = (self.mini_venv / "lib/python3.11/site-packages"
                   / "minisweagent/config/benchmarks/swebench.yaml")
        bundled.parent.mkdir(parents=True)
        bundled.write_text(yaml.safe_dump(SYNTH_MINI_CONFIG))
        self.eval_venv = self.root / "eval-venv"
        (self.eval_venv / "bin").mkdir(parents=True)
        (self.eval_venv / "bin/python").write_text("#!/bin/sh\n")

    def patch(self):
        """Context manager patching ALL identity constants onto the
        synthetic tree."""
        return mock.patch.multiple(
            c_entry,
            RECORD_PATH=self.record_path,
            RECORD_SHA256=self.record_sha,
            CATALOG_PATH=self.catalog_path,
            CATALOG_SHA256=self.catalog_sha,
            MINI_VENV_PY=self.mini_venv / "bin/python",
            EVAL_VENV_PY=self.eval_venv / "bin/python",
            TARGET_IMAGE="synth/img@sha256:" + "a" * 64)

    def cleanup(self):
        self._tmp.cleanup()


class CEntrySynthTests(unittest.TestCase):
    def setUp(self):
        self.env = _SynthEntryEnv()
        self.addCleanup(self.env.cleanup)

    # -- plan ---------------------------------------------------------------

    def test_plan_mode_secret_free_and_complete(self):
        import io
        from contextlib import redirect_stdout
        with self.env.patch():
            buf = io.StringIO()
            with redirect_stdout(buf):
                rc = c_entry.main([])
        self.assertEqual(rc, 0)
        plan = json.loads(buf.getvalue())
        self.assertEqual(plan["mode"], "offline_plan")
        self.assertTrue(all(plan["identity_checks"].values()))
        a = plan["assembly"]
        self.assertEqual(a["task"]["instance_id"], "synth__repo-00001")
        self.assertEqual(a["model"], "openai/deepseek-v4-flash")
        self.assertEqual(a["budget"]["max_model_requests"], 30)
        self.assertEqual(a["budget"]["agent_wall_s"], 1500.0)
        self.assertEqual(a["container_limits"]["agent_container_cpu"], "4")
        self.assertEqual(plan["authorization_state"]["c_executed"], False)
        text = buf.getvalue()
        self.assertIn("PILOT_API_BASE", text)
        for secret in ("sk-", "Bearer ", SECRET_GOLD, SECRET_TEST):
            self.assertNotIn(secret, text)
        # the synthetic record's ANSWER canaries must never reach the
        # assembled task either
        self.assertNotIn(SECRET_GOLD, json.dumps(a))

    def test_execute_requires_double_gate(self):
        import io
        from contextlib import redirect_stderr, redirect_stdout
        with self.env.patch():
            buf = io.StringIO()
            with redirect_stderr(buf), redirect_stdout(io.StringIO()):
                rc = c_entry.main(["--execute"])
        self.assertEqual(rc, 2)
        self.assertIn("i-approve-the-c-run", buf.getvalue())

    # -- refusals -----------------------------------------------------------

    def test_execute_missing_credentials_fails_before_assembly(self):
        env = {k: v for k, v in os.environ.items()
               if k not in (c_entry.USER_API_BASE_ENV,
                            c_entry.USER_API_KEY_ENV)}
        with self.env.patch():
            with mock.patch.dict(os.environ, env, clear=True):
                with self.assertRaises(c_entry.CEntryError) as ctx:
                    c_entry.execute_c()
        self.assertIn("PILOT_API_BASE", str(ctx.exception))

    def test_config_cannot_authorize(self):
        bad = _SynthEntryEnv(execution_authorized=True)
        self.addCleanup(bad.cleanup)
        with bad.patch():
            with self.assertRaises(c_entry.CEntryError) as ctx:
                c_entry._load_catalog()
        self.assertIn("cannot grant execution", str(ctx.exception))

    def test_record_hash_drift_refuses(self):
        with self.env.patch():
            with mock.patch.object(c_entry, "RECORD_SHA256", "0" * 64):
                with self.assertRaises(c_entry.CEntryError):
                    c_entry.load_fixed_record()

    # -- budget validation (independent second line of defense: even a
    #    catalog whose hash was re-registered must fail sanity checks;
    #    the 30 -> 300 edit itself is caught by the hash pin below) ----

    def test_invalid_budget_value_refuses_even_with_matching_hash(self):
        # a NON-POSITIVE request count with a freshly-registered hash:
        # the hash pin cannot catch this (the hash matches the new file),
        # the value validation must
        tampered = _SynthEntryEnv(budget_overrides={"model_requests": 0})
        self.addCleanup(tampered.cleanup)
        with tampered.patch():
            with self.assertRaises(c_entry.CEntryError) as ctx:
                c_entry.build_c_runner(authorized=False)
        self.assertIn("model_requests", str(ctx.exception))

    def test_nan_wall_refuses(self):
        # direct function-level check: the value passes YAML (string
        # 'nan' -> float nan) but must fail the finite/positive gate
        catalog = {"budget_proposal_gate_c": dict(
            SYNTH_BUDGET, agent_wall_min=float("nan"))}
        with self.assertRaises(c_entry.CEntryError) as ctx:
            c_entry.budget_limits_from_catalog(catalog)
        self.assertIn("agent_wall_min", str(ctx.exception))

    def test_non_positive_and_non_int_budget_refuse(self):
        for overrides in ({"model_requests": 0},
                          {"total_wall_min": -1},
                          {"steps": "30"},
                          {"new_artifacts_gib": float("inf")}):
            catalog = {"budget_proposal_gate_c": dict(SYNTH_BUDGET,
                                                      **overrides)}
            with self.assertRaises(c_entry.CEntryError):
                c_entry.budget_limits_from_catalog(catalog)

    def test_container_limit_validation(self):
        catalog = {"budget_proposal_gate_c": dict(
            SYNTH_BUDGET, agent_container_cpu="four")}
        with self.assertRaises(c_entry.CEntryError):
            c_entry.container_limits_from_catalog(catalog)

    # -- catalog identity binding -------------------------------------------

    def test_catalog_hash_drift_refuses_assembly(self):
        # same registered hash, EDITED catalog content -> refusal in BOTH
        # modes (the reviewer repro: change 30 -> 300, assembly accepted)
        with self.env.patch():
            catalog = yaml.safe_load(self.env.catalog_path.read_text())
            catalog["budget_proposal_gate_c"]["model_requests"] = 300
            self.env.catalog_path.write_text(yaml.safe_dump(catalog))
            with self.assertRaises(c_entry.CEntryError) as ctx:
                c_entry.build_c_runner(authorized=False)
        self.assertIn("catalog sha256 mismatch", str(ctx.exception))
        # and the plan mode is refused too, not just execution
        with self.env.patch():
            import io
            from contextlib import redirect_stderr, redirect_stdout
            # catalog still tampered on disk; the pinned hash is stale
            catalog = yaml.safe_load(self.env.catalog_path.read_text())
            catalog["budget_proposal_gate_c"]["model_requests"] = 300
            self.env.catalog_path.write_text(yaml.safe_dump(catalog))
            buf = io.StringIO()
            with redirect_stderr(buf), redirect_stdout(io.StringIO()):
                with self.assertRaises(c_entry.CEntryError):
                    c_entry.build_plan()

    # -- assembly -----------------------------------------------------------

    def test_build_c_runner_offline_assembly(self):
        with self.env.patch():
            runner, identity = c_entry.build_c_runner(authorized=False)
        self.assertEqual(runner.collection, "RUN-01-C")
        self.assertIn("sha256:" + "a" * 16, runner.image)
        self.assertEqual(runner.source_type, "benchmark_real")
        # bundled templates actually loaded from the FAKE venv tree
        self.assertEqual(
            runner.harness.mini_config["agent"]["system_template"],
            "sys {{task}}")
        self.assertEqual(runner.harness.mini_config["environment"]["timeout"],
                         42)
        # model name overridden to the fixed pilot model; cost tracking
        self.assertEqual(runner.harness.mini_config["model"]["model_name"],
                         "openai/deepseek-v4-flash")
        self.assertEqual(runner.harness.mini_config["model"]
                         ["cost_tracking"], "ignore_errors")
        self.assertFalse(runner.harness.authorized)
        self.assertFalse(runner.verifier.authorized)
        self.assertFalse(runner.runtime.authorized)
        self.assertIsNone(runner.credentials)
        self.assertEqual(runner.limits.max_model_requests, 30)
        self.assertEqual(runner.agent_container_cpu, "4")
        self.assertEqual(runner.verifier_container_mem, "8g")
        # answer canaries never reach the agent task input
        self.assertNotIn(SECRET_GOLD, runner.task.problem_statement)
        text = json.dumps(identity)
        self.assertNotIn(SECRET_GOLD, text)


SECRET_GOLD = SYNTH_RECORD["patch"]
SECRET_TEST = SYNTH_RECORD["test_patch"]


class CredentialsWiringTests(unittest.TestCase):
    """The runner must forward in-memory credentials to the harness;
    the credential value must not land in ANY archived file. The scan
    runs BEFORE the temp dir is cleaned up and asserts that files were
    actually inspected (a scan over a deleted directory is a no-op)."""

    def test_runner_forwards_credentials_and_nothing_leaks(self):
        captured = {}

        class CapturingHarness(FakeAgentHarness):
            def run(self, task, budget, recorder, runtime, container,
                    watchdog=None, run_dir=None, credentials=None):
                captured["credentials"] = credentials
                return super().run(task, budget, recorder, runtime,
                                   container, watchdog, run_dir)

        script = {"steps": [
            {"model": {"usage": {"completion_tokens": 5}},
             "tools": []}],
            "final": {"status": "ok", "candidate_patch": "x"}}
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "data/raw/generated").mkdir(parents=True)
            clock = FakeClock()
            runtime = FakeContainerRuntime(clock)
            harness = CapturingHarness(clock, script)
            verifier = FakeVerifierStub(clock)
            task = AgentTask(instance_id="i", problem_statement="p",
                             image="img")
            vspec = VerifierSpec(instance_id="i", image="img",
                                 eval_script_ref="x", log_parser="p",
                                 eval_type="pass_and_fail",
                                 record_locator="x")
            runner = CodingPilotRunner(
                project_root=root, collection="SYNTH-CRED",
                harness=harness, verifier=verifier, runtime=runtime,
                clock=clock,
                limits=BudgetLimits(max_model_requests=5, max_steps=5,
                                    agent_wall_s=60.0, verifier_wall_s=30.0,
                                    total_wall_s=120.0),
                task=task, verifier_spec=vspec, image="img",
                credentials={"OPENAI_API_KEY": FAKE_KEY_CANARY})
            outcome = runner.run()
            self.assertEqual(outcome.execution_status, "ok")
            # credentials reached the harness in memory
            self.assertEqual(captured["credentials"],
                             {"OPENAI_API_KEY": FAKE_KEY_CANARY})
            # scan INSIDE the temp dir, before cleanup, and prove files
            # were actually inspected
            scanned = []
            leaked = []
            for p in Path(outcome.run_dir).rglob("*"):
                if p.is_file():
                    scanned.append(p.name)
                    if FAKE_KEY_CANARY in p.read_text(
                            encoding="utf-8", errors="replace"):
                        leaked.append(str(p))
            self.assertGreater(len(scanned), 0,
                               "scan inspected no files (vacuous check)")
            self.assertIn("events.jsonl", scanned)
            self.assertIn("metadata.json", scanned)
            self.assertEqual(leaked, [])


class FakeVerifierStub:
    name = "stub"

    def __init__(self, clock=None):
        self.clock = clock

    def run(self, spec, candidate_patch, budget, recorder, runtime,
            container):
        from agent_workload_characterization.runners.coding_pilot import \
            VerifierResult
        return VerifierResult(status="ok", resolved=True)


if __name__ == "__main__":
    unittest.main()
