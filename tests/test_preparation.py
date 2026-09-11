"""PREP-01 offline preparation tests: synthetic fixtures only.

No legacy data dependency, no Docker daemon, no mini/litellm import, no
network. Real task-record checks run via explicit paths and are marked.
"""

import copy
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

import yaml

from agent_workload_characterization.runners.preparation import (
    PreparationError, agent_view, check_model_config, environment_view,
    evaluator_view, image_plan, limits_plan, load_task_record,
    local_task_input_route, prepare, record_call, reject_startup_command,
    retry_policy, ImagePlan)
import test_skeleton as skeleton


# ---------------- synthetic fixtures ----------------

CANARY_PATCH = "GOLDPATCH_CANARY_9f1a"
CANARY_TEST = "TESTPATCH_CANARY_7b2c"
CANARY_HINT = "HINT_CANARY_3d4e"
CANARY_F2P = ["F2P_CANARY_test_a", "F2P_CANARY_test_b"]


def synth_record(instance_id="synth__task-0001"):
    return {
        "instance_id": instance_id,
        "problem_statement": "Fix the floatformat crash.",
        "repo": "synth/repo", "base_commit": "a" * 40, "version": "1.0",
        "environment_setup_commit": "b" * 40,
        "image": "swebench/sweb.eval.x86_64.synth_task-0001:latest",
        "patch": CANARY_PATCH, "test_patch": CANARY_TEST,
        "hints_text": CANARY_HINT, "FAIL_TO_PASS": CANARY_F2P,
        "PASS_TO_PASS": ["P2P_CANARY_c"],
        "eval_script": "eval_CANARY.sh", "eval_type": "pass_and_fail",
        "log_parser": "parse_log_django",
        "new_future_field": "SHOULD_NOT_PROPAGATE",  # default-exclusion test
    }


def synth_record_file(base: Path, record=None):
    p = base / "record.json"
    p.write_text(json.dumps(record or synth_record()))
    return p, hashlib.sha256(p.read_bytes()).hexdigest()


def synth_config(**over):
    cfg = {
        "provider_protocol_class": "openai_compatible",
        "model": {"model_name": "fake/deepseek-v4-flash",
                  "model_kwargs": {"drop_params": True},
                  "cost_tracking": "ignore_errors",
                  "litellm_routing": "unverified"},
        "agent": {"step_limit": 250, "cost_limit": 3.0},
        "environment": {"timeout": 60, "api_base_env": "PILOT_API_BASE",
                        "auth_env": "PILOT_API_KEY",
                        "forward_env": ["PILOT_API_BASE", "PILOT_API_KEY"]},
        "run": {"env_startup_command": None},
    }
    cfg.update(over)
    return cfg


# ---------------- A1: task input ----------------

class TaskInputTests(unittest.TestCase):
    def test_whitelist_projection(self):
        v = agent_view(synth_record())
        self.assertEqual(sorted(v), ["instance_id", "problem_statement"])

    def test_new_field_does_not_propagate(self):
        v = agent_view(synth_record())
        self.assertNotIn("new_future_field", v)

    def test_wrong_hash_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            p, sha = synth_record_file(Path(tmp))
            with self.assertRaises(PreparationError):
                load_task_record(p, expected_instance_id="synth__task-0001",
                                 expected_sha256="0" * 64)

    def test_wrong_instance_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            p, _ = synth_record_file(Path(tmp))
            with self.assertRaises(PreparationError):
                load_task_record(p, expected_instance_id="OTHER__task")

    def test_missing_statement_rejected(self):
        r = synth_record(); del r["problem_statement"]
        with tempfile.TemporaryDirectory() as tmp:
            p, _ = synth_record_file(Path(tmp), r)
            with self.assertRaises(PreparationError):
                load_task_record(p, expected_instance_id="synth__task-0001")

    def test_environment_view_scoped(self):
        v = environment_view(synth_record())
        self.assertIn("base_commit", v)
        self.assertNotIn("patch", v)
        self.assertNotIn("problem_statement", v)


# ---------------- answer isolation ----------------

class AnswerIsolationTests(unittest.TestCase):
    def test_canaries_absent_from_agent_view(self):
        blob = json.dumps(agent_view(synth_record()))
        for canary in (CANARY_PATCH, CANARY_TEST, CANARY_HINT, "F2P_CANARY"):
            self.assertNotIn(canary, blob)

    def test_canaries_absent_from_evaluator_view(self):
        blob = json.dumps(evaluator_view(synth_record()))
        for canary in (CANARY_PATCH, CANARY_TEST, CANARY_HINT):
            self.assertNotIn(canary, blob)
        # F2P names appear only as count, not content
        self.assertNotIn("F2P_CANARY_test_a", blob)

    def test_startup_command_rejected(self):
        with self.assertRaises(PreparationError):
            reject_startup_command({"run": {"env_startup_command": "echo {{ patch }}"}})

    def test_prepare_rejects_startup_command(self):
        with tempfile.TemporaryDirectory() as tmp:
            p, sha = synth_record_file(Path(tmp))
            cfg = synth_config()
            cfg["run"]["env_startup_command"] = "x"
            with self.assertRaises(PreparationError):
                prepare(p, cfg, expected_instance_id="synth__task-0001", expected_sha256=sha)


# ---------------- credential protection ----------------

class CredentialTests(unittest.TestCase):
    def test_secret_key_rejected_anywhere(self):
        for key in ("api_key", "apiKey", "Authorization", "x-api-key", "token", "password"):
            with self.subTest(key=key):
                cfg = synth_config()
                cfg["model"]["model_kwargs"][key] = "sk-SYNTH-SECRET"
                with self.assertRaises(PreparationError):
                    check_model_config(cfg)

    def test_nested_secret_rejected(self):
        cfg = synth_config()
        cfg["extra"] = {"deep": {"nested_api_key": "secret"}}
        with self.assertRaises(PreparationError):
            check_model_config(cfg)

    def test_valid_config_has_no_secret_paths(self):
        plan = check_model_config(synth_config())
        blob = json.dumps(plan.__dict__)
        for marker in ("sk-", "secret", "api_key=", "Bearer "):
            self.assertNotIn(marker, blob)

    def test_model_kwargs_restricted(self):
        cfg = synth_config()
        cfg["model"]["model_kwargs"]["api_base"] = "https://gateway.example"
        with self.assertRaises(PreparationError):
            check_model_config(cfg)


# ---------------- model preparation ----------------

class ModelPrepTests(unittest.TestCase):
    def test_synthetic_mapping_checkable(self):
        plan = check_model_config(synth_config())
        self.assertEqual(plan.model_name, "fake/deepseek-v4-flash")
        self.assertEqual(plan.auth_env, "PILOT_API_KEY")
        self.assertEqual(plan.litellm_routing, "unverified")

    def test_unknown_routing_preserved_not_faked(self):
        plan = check_model_config(synth_config())
        self.assertEqual(plan.litellm_routing, "unverified")  # fake success ≠ real compat

    def test_forward_env_must_be_unique_names(self):
        cfg = synth_config()
        cfg["environment"]["forward_env"] = ["A", "A"]
        with self.assertRaises(PreparationError):
            check_model_config(cfg)


# ---------------- cost & request records ----------------

class CostRecordTests(unittest.TestCase):
    def test_usage_present_price_unknown(self):
        r = record_call({"input_tokens": 10, "output_tokens": 5}, cost_fn=None)
        self.assertEqual(r.cost_status, "unknown")
        self.assertIsNone(r.cost)
        self.assertEqual(r.usage["input_tokens"], 10)

    def test_price_error_keeps_usage(self):
        def boom():
            raise RuntimeError("no price")
        r = record_call({"input_tokens": 1}, cost_fn=boom)
        self.assertEqual(r.cost_status, "error")
        self.assertIsNone(r.cost)
        self.assertIsNotNone(r.usage)  # response/usage NOT discarded

    def test_zero_cost_is_source_value_not_free(self):
        r = record_call({"input_tokens": 1}, cost_fn=lambda: 0.0)
        self.assertEqual(r.cost, 0.0)
        self.assertEqual(r.cost_status, "computed")  # source value; caller must not relabel as free

    def test_failed_call_kept_without_retry(self):
        r = record_call(None, cost_fn=None, error="AuthenticationError")
        self.assertFalse(r.ok)
        self.assertIsNone(r.usage)


# ---------------- image adaptation ----------------

class ImageTests(unittest.TestCase):
    def test_field_adaptation(self):
        r = synth_record()
        plan = image_plan(r)
        self.assertEqual(plan.mini_source, "derived_from_instance_id")  # no image_name/docker_image cols
        # derived name substitutes __ -> _1776_, so tag differs from evaluator
        # image when instance_id contains "__": match=False, adaptation logged.
        self.assertFalse(plan.match)
        self.assertIn("_1776_", plan.mini_image)

    def test_field_adaptation_match_when_no_dunder(self):
        r = synth_record(instance_id="synth_task-0002")
        r["image"] = "swebench/sweb.eval.x86_64.synth_task-0002:latest"
        plan = image_plan(r)
        self.assertTrue(plan.match)

    def test_conflict_rejected(self):
        r = synth_record()
        r["image_name"] = "img:a"; r["docker_image"] = "img:b"
        with self.assertRaises(PreparationError):
            image_plan(r)

    def test_missing_digest_stays_unready(self):
        plan = image_plan(synth_record())
        self.assertIsNone(plan.digest)
        self.assertEqual(plan.status, "unverified")

    def test_missing_evaluator_image_rejected(self):
        r = synth_record(); del r["image"]
        with self.assertRaises(PreparationError):
            image_plan(r)


# ---------------- limits / retry ----------------

class LimitsRetryTests(unittest.TestCase):
    def test_limits_note_user_ceiling(self):
        lim = limits_plan(synth_config())
        self.assertEqual(lim["user_monetary_ceiling"], "explicitly_not_set_by_user")
        self.assertIn("ineffective_without_pricing", lim["agent_cost_limit_effective"])

    def test_retry_three_layers(self):
        rp = retry_policy()
        self.assertEqual(rp.attempt_limit, 1)
        self.assertEqual(rp.outer_auto_retry, 0)
        self.assertIn("MSWEA_MODEL_RETRY_STOP_AFTER_ATTEMPT", rp.sdk_retry_config)
        self.assertIn("cannot be confirmed", rp.sdk_retry_note)  # not claimed disabled offline


# ---------------- preflight degradation ----------------

class PreflightTests(unittest.TestCase):
    def test_degradation_handled(self):
        from agent_workload_characterization.collectors import preflight as pf
        import unittest.mock as mock
        # missing binary
        with mock.patch.object(pf.shutil, "which", return_value=None):
            self.assertEqual(pf.probe_perf()["status"], "unavailable")
        # permission denied: reader returns (None, "permission_denied")
        with mock.patch.object(pf, "_timed_read", lambda p: (None, "permission_denied")):
            self.assertEqual(pf.probe_cgroup()["status"], "permission_denied")
            self.assertEqual(pf.probe_perf()["status"], "permission_denied")
            self.assertEqual(pf.probe_process_visibility()["status"], "permission_denied")
        # remote docker context refused
        with mock.patch.dict(pf.os.environ, {"DOCKER_HOST": "tcp://remote:2375"}):
            r = pf.probe_docker()
            self.assertEqual(r["status"], "not_checked")
            self.assertIn("remote", r["detail"])
        # timeout path
        import subprocess as sp
        def slow(*a, **k):
            raise sp.TimeoutExpired(cmd="docker", timeout=5)
        with mock.patch.object(pf.shutil, "which", return_value="/usr/bin/docker"):
            with mock.patch.object(pf.Path, "exists", return_value=True):
                with mock.patch.object(pf.Path, "stat", lambda s: type("S", (), {"st_mode": 0o140000})()):
                    with mock.patch.object(sp, "run", slow):
                        self.assertEqual(pf.probe_docker()["status"], "unavailable")

    def test_one_failure_does_not_block_others(self):
        from agent_workload_characterization.collectors.preflight import run_preflight
        def boom():
            raise RuntimeError("probe blew up")
        results = run_preflight(Path("."), probes={"bad": boom, "py": lambda: {"status": "observed"}})
        self.assertEqual(results["bad"]["status"], "unavailable")
        self.assertEqual(results["py"]["status"], "observed")

    def test_bad_status_normalized(self):
        from agent_workload_characterization.collectors.preflight import run_preflight
        results = run_preflight(Path("."), probes={"weird": lambda: {"status": "banana"}})
        self.assertEqual(results["weird"]["status"], "not_checked")


# ---------------- output safety ----------------

class OutputSafetyTests(unittest.TestCase):
    def test_writer_refuses_protected_and_existing(self):
        from agent_workload_characterization.runners.report_writer import write_preparation_report
        payload = {"preparation": _prep_payload(), "preflight": None}
        import os
        with tempfile.TemporaryDirectory() as tmp:
            proj = Path(tmp) / "project"; proj.mkdir()
            (proj / "reports").mkdir()
            old_cwd = os.getcwd()
            os.chdir(proj)
            try:
                # outside reports/preparation
                with self.assertRaises(ValueError):
                    write_preparation_report(Path("elsewhere"), payload)
                # protected root
                (proj / "data").mkdir()
                with self.assertRaises(ValueError):
                    write_preparation_report(Path("data/catalog/x"), payload)
                # existing package refused
                write_preparation_report(Path("reports/preparation/batch-1"), payload)
                with self.assertRaises(ValueError):
                    write_preparation_report(Path("reports/preparation/batch-1"), payload)
            finally:
                os.chdir(old_cwd)

    def test_writer_manifest_covers_files(self):
        from agent_workload_characterization.runners.report_writer import write_preparation_report
        payload = {"preparation": _prep_payload(), "preflight": {"python": {"status": "observed"}}}
        with tempfile.TemporaryDirectory() as tmp:
            proj = Path(tmp) / "project"; proj.mkdir()
            import os
            old_cwd = os.getcwd()
            os.chdir(proj)
            try:
                out = write_preparation_report(Path("reports/preparation/batch-x"), payload)
            finally:
                os.chdir(old_cwd)
            m = json.loads((Path(out["path"]) / "manifest.json").read_text())
            self.assertIn("plan.json", m["files"])
            self.assertIn("preflight.json", m["files"])
            self.assertIn("offline_checks.json", m["files"])
            self.assertNotIn("execution_authorized", m)  # manifest makes no auth claim; plan.json carries it
            plan = json.loads((Path(out["path"]) / "plan.json").read_text())
            self.assertFalse(plan["execution_authorized"])
            self.assertEqual(plan["preparation_status"], "READY_FOR_REVIEW")


def _prep_payload():
    """Minimal preparation payload shaped like PreparationResult.__dict__."""
    record = synth_record()
    return {
        "preparation_status": "READY_FOR_REVIEW",
        "agent_view": agent_view(record),
        "environment_view": environment_view(record),
        "evaluator_view": evaluator_view(record),
        "image": {"mini_image": "x", "evaluator_image": "x", "match": True,
                  "mini_source": "derived_from_instance_id", "digest": None, "status": "unverified"},
        "task_route": local_task_input_route(Path("record.json"), "sha"),
        "limits": limits_plan(synth_config()),
        "retry": {"attempt_limit": 1, "outer_auto_retry": 0,
                  "sdk_retry_config": "env", "sdk_retry_note": "note"},
        "runtime_compatibility": ["x unverified"],
        "execution_authorized": False,
        "next_authorizations": ["install", "smoke", "run"],
    }


# ---------------- CLI ----------------

class PrepareCLITests(unittest.TestCase):
    run_python = skeleton.CLITests.run_python
    run_cli = skeleton.CLITests.run_cli

    def test_missing_config_fails(self):
        r = self.run_cli("prepare-pilot", "--config", "/nonexistent.yaml")
        self.assertEqual(r.returncode, 1)
        self.assertIn("INVALID", r.stderr)

    def test_help_shows_no_execute(self):
        r = self.run_cli("prepare-pilot", "--help")
        self.assertEqual(r.returncode, 0)
        self.assertNotIn("--execute", r.stdout)


if __name__ == "__main__":
    unittest.main()


# ---------------- B1: writer symlink escape (full-path regression) ----------------

class WriterSymlinkEscapeTests(unittest.TestCase):
    def _project(self, base: Path) -> Path:
        proj = base / "project"; proj.mkdir()
        (proj / "reports").mkdir()
        (proj / "data" / "catalog").mkdir(parents=True)
        (proj / "references").mkdir()
        return proj

    def test_reports_root_symlink_rejected(self):
        from agent_workload_characterization.runners.report_writer import write_preparation_report
        payload = {"preparation": _prep_payload(), "preflight": None}
        with tempfile.TemporaryDirectory() as tmp:
            proj = self._project(Path(tmp))
            # attacker: reports/preparation -> a legacy-source dir
            legacy = Path(tmp) / "legacy"
            legacy.mkdir()
            (proj / "reports" / "preparation").symlink_to(legacy)
            with self.assertRaises(ValueError):
                write_preparation_report(Path("reports/preparation/x"), payload,
                                         project_root=proj)

    def test_subdir_symlink_to_legacy_rejected(self):
        from agent_workload_characterization.runners.report_writer import write_preparation_report, guard
        payload = {"preparation": _prep_payload(), "preflight": None}
        with tempfile.TemporaryDirectory() as tmp:
            proj = self._project(Path(tmp))
            prep_root = proj / "reports" / "preparation"
            prep_root.mkdir()
            legacy = Path(tmp) / "legacy"
            legacy.mkdir()
            (prep_root / "escape").symlink_to(legacy)
            with self.assertRaises(ValueError):
                guard(proj, prep_root / "escape" / "batch")

    def test_catalog_legacy_roots_protected(self):
        """A destination equal to a catalog-registered legacy root is refused."""
        from agent_workload_characterization.runners.report_writer import guard
        with tempfile.TemporaryDirectory() as tmp:
            proj = self._project(Path(tmp))
            legacy = Path(tmp) / "old_benchmark"
            legacy.mkdir()
            (proj / "data" / "catalog" / "sources.yaml").write_text(yaml.safe_dump({
                "catalog_version": "1.1",
                "roots": {"benchmark": str(legacy), "project": str(proj)},
                "sources": [{"source_id": "x",
                             "locator": {"root": "benchmark", "path": "f.jsonl", "kind": "file"}}]}))
            # writing INTO the legacy root (even via a path inside reports/preparation
            # naming tricks) must fail; direct call:
            with self.assertRaises(ValueError):
                guard(proj, legacy / "new_report")

    def test_writer_full_path_success(self):
        from agent_workload_characterization.runners.report_writer import write_preparation_report
        payload = {"preparation": _prep_payload(), "preflight": None}
        with tempfile.TemporaryDirectory() as tmp:
            proj = self._project(Path(tmp))
            out = write_preparation_report(Path("reports/preparation/ok-batch"), payload,
                                           project_root=proj)
            self.assertTrue((Path(out["path"]) / "plan.json").is_file())


# ---------------- B2: credential/echo hardening ----------------

class CredentialHardeningTests(unittest.TestCase):
    def test_env_name_with_value_rejected(self):
        cfg = synth_config()
        cfg["environment"]["auth_env"] = "FAKE_CANARY=value"
        with self.assertRaises(PreparationError):
            check_model_config(cfg)

    def test_env_name_invalid_chars_rejected(self):
        for bad in ("1ABC", "A-B", "A B", "A;rm", ""):
            with self.subTest(bad=bad):
                cfg = synth_config()
                cfg["environment"]["api_base_env"] = bad
                with self.assertRaises(PreparationError):
                    check_model_config(cfg)

    def test_url_with_userinfo_rejected(self):
        cfg = synth_config()
        cfg["model"]["model_kwargs"]["hint_url"] = "https://user:pass@evil.example/v1"
        with self.assertRaises(PreparationError):
            check_model_config(cfg)

    def test_forward_env_payload_rejected(self):
        cfg = synth_config()
        cfg["environment"]["forward_env"] = ["PILOT_API_KEY=x"]
        with self.assertRaises(PreparationError):
            check_model_config(cfg)

    def test_usage_whitelist_projection(self):
        usage = {"prompt_tokens": 10, "completion_tokens": 5,
                 "echoed_api_key": "sk-SYNTHSECRET", "endpoint": "https://gw/v1"}
        r = record_call(usage, cost_fn=None)
        blob = json.dumps(r.__dict__)
        self.assertEqual(r.usage, {"prompt_tokens": 10, "completion_tokens": 5})
        self.assertNotIn("sk-SYNTHSECRET", blob)
        self.assertNotIn("endpoint", blob)

    def test_error_sanitized(self):
        r = record_call(None, cost_fn=None,
                        error="AuthenticationError: key sk-SYNTHSECRET rejected at https://gw/v1")
        self.assertIn("AuthenticationError", r.error)
        self.assertNotIn("sk-SYNTHSECRET", r.error)
        self.assertNotIn("https://", r.error)
        self.assertIn("<sanitized>", r.error)

    def test_request_id_preserved(self):
        r = record_call({"prompt_tokens": 1}, cost_fn=None, request_id="req-abc-123")
        self.assertEqual(r.request_id, "req-abc-123")

    def test_error_unknown_text_collapses_to_generic(self):
        """Arbitrary identifier-like text is NOT kept as an exception type."""
        r = record_call(None, cost_fn=None, error="FAKE_SECRET_CANARY_42")
        self.assertEqual(r.error, "error:<sanitized>")

    def test_error_whitelist_type_preserved(self):
        r = record_call(None, cost_fn=None,
                        error="AuthenticationError: key sk-SYNTHSECRET rejected")
        self.assertEqual(r.error, "AuthenticationError:<sanitized>")

    def test_usage_nested_arbitrary_key_dropped(self):
        """Nested dict keys must be in the fixed detail whitelist; a numeric
        value under an arbitrary (canary) key name is dropped."""
        usage = {"prompt_tokens": 3,
                 "prompt_tokens_details": {"FAKE_SECRET_CANARY_42": 1,
                                           "cached_tokens": 7}}
        r = record_call(usage, cost_fn=None)
        self.assertEqual(r.usage, {"prompt_tokens": 3,
                                   "prompt_tokens_details": {"cached_tokens": 7}})
        self.assertNotIn("FAKE_SECRET_CANARY_42", json.dumps(r.__dict__))

    def test_canary_end_to_end_through_report(self):
        """Canary usage/error echo must not survive into the report package."""
        from agent_workload_characterization.runners.report_writer import write_preparation_report
        canary_usage = {"prompt_tokens": 7, "api_key_echo": "sk-SYNTHEND2END",
                        "prompt_tokens_details": {"FAKE_SECRET_CANARY_42": 1,
                                                 "cached_tokens": 4}}
        rec = record_call(canary_usage, cost_fn=None,
                          error="FAKE_SECRET_CANARY_42: sk-SYNTHEND2END at https://u:p@gw/v1")
        prep = _prep_payload()
        prep["model_plan"] = {"model_name": "fake/m", "auth_env": "P",
                              "api_base_env": "B", "call_sample": rec.__dict__}
        payload = {"preparation": prep, "preflight": None}
        with tempfile.TemporaryDirectory() as tmp:
            proj = Path(tmp) / "project"; proj.mkdir()
            out = write_preparation_report(Path("reports/preparation/canary"), payload,
                                           project_root=proj)
            blob = ""
            for f in Path(out["path"]).iterdir():
                if f.is_file():
                    blob += f.read_text()
            self.assertNotIn("sk-SYNTHEND2END", blob)
            self.assertNotIn("api_key_echo", blob)
            self.assertNotIn("u:p@gw", blob)
            self.assertNotIn("FAKE_SECRET_CANARY_42", blob)
            # sanitized error must be the generic label, not the canary text
            self.assertIn('"error:<sanitized>"', blob)


# ---------------- S1: normalized image comparison ----------------

class ImageNormalizationTests(unittest.TestCase):
    def test_different_registry_same_tag_not_match(self):
        r = synth_record()
        r["image_name"] = "ghcr.io/other/sweb.eval.x86_64.synth_task:latest"
        r["docker_image"] = "ghcr.io/other/sweb.eval.x86_64.synth_task:latest"
        plan = image_plan(r)
        self.assertFalse(plan.match)

    def test_different_namespace_same_tag_not_match(self):
        r = synth_record()
        r["image_name"] = "swebench/other/sweb.eval:latest"
        r["docker_image"] = "swebench/other/sweb.eval:latest"
        self.assertFalse(image_plan(r).match)

    def test_dockerhub_prefix_equivalence_allowed(self):
        # mini derives (or reads) a docker.io-prefixed name; evaluator uses the
        # bare Docker-Hub form — normalization treats them as the same reference.
        r = synth_record()
        r["image_name"] = None
        r["docker_image"] = "docker.io/swebench/sweb.eval.x86_64.synth_task-0001:latest"
        r["image"] = "swebench/sweb.eval.x86_64.synth_task-0001:latest"
        self.assertTrue(image_plan(r).match)

    def test_tag_difference_not_match(self):
        r = synth_record()
        r["image_name"] = "swebench/img:v1"
        r["docker_image"] = "swebench/img:v1"
        r["image"] = "swebench/img:v2"
        self.assertFalse(image_plan(r).match)


# ---------------- S3: report evidence completeness ----------------

class ReportEvidenceTests(unittest.TestCase):
    def test_plan_includes_model_plan(self):
        prep = _prep_payload()
        prep["model_plan"] = {"model_name": "fake/deepseek-v4-flash",
                              "auth_env": "PILOT_API_KEY", "api_base_env": "PILOT_API_BASE",
                              "litellm_routing": "unverified"}
        payload = {"preparation": prep, "preflight": None}
        with tempfile.TemporaryDirectory() as tmp:
            proj = Path(tmp) / "project"; proj.mkdir()
            from agent_workload_characterization.runners.report_writer import write_preparation_report
            out = write_preparation_report(Path("reports/preparation/ev"), payload, project_root=proj)
            plan = json.loads((Path(out["path"]) / "plan.json").read_text())
            self.assertIn("model_plan", plan)
            self.assertEqual(plan["model_plan"]["litellm_routing"], "unverified")

    def test_offline_checks_derived_not_hardcoded(self):
        prep = _prep_payload()  # digest None -> digest_pinned False; routing absent -> False
        prep["model_plan"] = {"litellm_routing": "unverified"}
        payload = {"preparation": prep, "preflight": None}
        with tempfile.TemporaryDirectory() as tmp:
            proj = Path(tmp) / "project"; proj.mkdir()
            from agent_workload_characterization.runners.report_writer import write_preparation_report
            out = write_preparation_report(Path("reports/preparation/chk"), payload, project_root=proj)
            checks = json.loads((Path(out["path"]) / "offline_checks.json").read_text())
            self.assertFalse(checks["digest_pinned"])
            self.assertFalse(checks["litellm_routing_verified"])
            self.assertTrue(checks["agent_view_whitelist_only"])
            # derived flags respond to input: pin a digest and re-check
            prep2 = _prep_payload()
            prep2["image"]["digest"] = "sha256:abc"
            prep2["model_plan"] = {"litellm_routing": "confirmed_static"}
            out2 = write_preparation_report(Path("reports/preparation/chk2"),
                                            {"preparation": prep2, "preflight": None},
                                            project_root=proj)
            checks2 = json.loads((Path(out2["path"]) / "offline_checks.json").read_text())
            self.assertTrue(checks2["digest_pinned"])
            self.assertTrue(checks2["litellm_routing_verified"])
