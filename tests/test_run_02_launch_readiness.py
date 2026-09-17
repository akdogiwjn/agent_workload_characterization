"""READY-01 A-stage tests: synthetic config and no Docker/model access."""

import hashlib
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from agent_workload_characterization.runners import run_02_launch_readiness as R
from agent_workload_characterization.runners import smoke_launcher as L


def synthetic_config(path: Path, key="{env:VOLCANO_API_KEY}") -> Path:
    path.write_text(json.dumps({
        "provider": {L.PROVIDER_NAME: {
            "options": {"baseURL": "https://fake-gateway.invalid/v1",
                        "apiKey": key},
            "models": {L.MODEL_KEY: {"name": "DeepSeek-V4-Flash"}},
        }}
    }), encoding="utf-8")
    return path


class Ready01Tests(unittest.TestCase):
    def test_plan_is_zero_side_effect_and_does_not_call_external_paths(self):
        with mock.patch.object(L, "load_credentials",
                               side_effect=AssertionError("credentials")), \
             mock.patch.object(R, "_write_report",
                               side_effect=AssertionError("report")):
            plan = R.build_plan()
        self.assertFalse(plan["side_effects"]["docker"])
        self.assertFalse(plan["side_effects"]["network"])
        self.assertFalse(plan["side_effects"]["credentials_read"])
        self.assertEqual(plan["authorization"]["read_only_check_approval"], "pending")
        self.assertEqual(plan["identity"]["credential_route"]["reference"],
                         "{env:VOLCANO_API_KEY}")

    def test_synthetic_reference_missing_empty_and_unresolved_are_safe(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            for key, env_value, expected in [
                ("{env:READY_KEY}", "sk-SYNTH-READY", None),
                ("{env:READY_KEY}", None, "E_ENV_VAR_EMPTY"),
                ("${READY_KEY}", "sk-SYNTH-READY", "E_CREDENTIAL_REFERENCE_UNSUPPORTED"),
                ("env:READY_KEY", "sk-SYNTH-READY", "E_CREDENTIAL_REFERENCE_UNSUPPORTED"),
            ]:
                path = synthetic_config(root / "opencode.json", key)
                with mock.patch.dict(os.environ,
                                     ({"READY_KEY": env_value} if env_value is not None else {}),
                                     clear=True):
                    if expected is None:
                        base, value = L.load_credentials(path)
                        self.assertEqual(base, "https://fake-gateway.invalid/v1")
                        self.assertEqual(value, env_value)
                    else:
                        with self.assertRaises(L.LauncherError) as cm:
                            L.load_credentials(path)
                        self.assertEqual(str(cm.exception), expected)

    def test_real_short_child_receives_only_restricted_boolean_observation(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            config = synthetic_config(root / "opencode.json")
            report_root = root / "reports/preparation"
            report_root.mkdir(parents=True)
            with mock.patch.object(R, "PROJECT_ROOT", root), \
                 mock.patch.object(R, "DEFAULT_CONFIG", config), \
                 mock.patch.dict(os.environ, {"VOLCANO_API_KEY": "sk-SYNTH-CANARY"},
                                 clear=True), \
                 mock.patch.object(R, "_validate_parent_environment",
                                   return_value={"docker_host_fixed_or_unset": True,
                                                 "docker_context_local_or_unset": True,
                                                 "proxy_unset": True}), \
                 mock.patch("agent_workload_characterization.runners.run_02_entry._docker_preflight",
                            return_value={"context": "default", "endpoint": "unix:///var/run/docker.sock",
                                          "architecture": "arm64", "os": "linux"}):
                result = R.run_check()
            self.assertEqual(result["status"], "READY_FOR_APPROVAL")
            summary = json.loads((Path(result["report_dir"]) / "summary.json").read_text())
            text = json.dumps(summary)
            self.assertNotIn("SYNTH-CANARY", text)
            self.assertTrue(summary["checks"]["child_environment"]["key_present"])
            self.assertTrue(summary["checks"]["child_environment"]["argv_safe"])

    def test_unapproved_parent_environment_stops_before_docker(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "reports/preparation").mkdir(parents=True)
            with mock.patch.object(R, "PROJECT_ROOT", root), \
                 mock.patch.object(R, "_validate_parent_environment",
                                   return_value={"docker_host_fixed_or_unset": False,
                                                 "docker_context_local_or_unset": True,
                                                 "proxy_unset": True}), \
                 mock.patch("agent_workload_characterization.runners.run_02_entry._docker_preflight") as docker:
                result = R.run_check()
            self.assertEqual(result["status"], "NOT_READY")
            self.assertIn("unapproved_parent_environment", result["categories"])
            docker.assert_not_called()

    def test_safe_error_category_has_no_raw_exception(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            config = synthetic_config(root / "opencode.json")
            (root / "reports/preparation").mkdir(parents=True)
            canary = "SECRET-CANARY-DO-NOT-REPORT"
            with mock.patch.object(R, "PROJECT_ROOT", root), \
                 mock.patch.object(R, "DEFAULT_CONFIG", config), \
                 mock.patch.dict(os.environ, {"VOLCANO_API_KEY": "sk-SYNTH"}, clear=True), \
                 mock.patch.object(R, "_validate_parent_environment",
                                   return_value={"docker_host_fixed_or_unset": True,
                                                 "docker_context_local_or_unset": True,
                                                 "proxy_unset": True}), \
                 mock.patch.object(R, "_child_probe_env",
                                   side_effect=PermissionError(canary)):
                result = R.run_check()
            self.assertEqual(result["categories"], ["permission_denied"])
            report = Path(result["report_dir"]) / "summary.json"
            self.assertNotIn(canary, report.read_text())

    def test_timeout_is_the_only_timeout_category(self):
        self.assertEqual(R._safe_category(subprocess.TimeoutExpired("x", 1)),
                         "timeout")
        self.assertEqual(R._safe_category(OSError("not a timeout")), "unknown")

    def test_run_check_rejects_false_or_non_boolean_child_results(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            config = synthetic_config(root / "opencode.json")
            (root / "reports/preparation").mkdir(parents=True)
            for child_result in ({"base_present": False, "key_present": True,
                                  "proxy_absent": True, "docker_host_absent": True,
                                  "argv_safe": True},
                                 {"base_present": "true", "key_present": True,
                                  "proxy_absent": True, "docker_host_absent": True,
                                  "argv_safe": True}):
                with self.subTest(child_result=child_result), \
                     mock.patch.object(R, "PROJECT_ROOT", root), \
                     mock.patch.object(R, "DEFAULT_CONFIG", config), \
                     mock.patch.dict(os.environ, {"VOLCANO_API_KEY": "sk-SYNTH"}, clear=True), \
                     mock.patch.object(R, "_validate_parent_environment",
                                       return_value={"docker_host_fixed_or_unset": True,
                                                     "docker_context_local_or_unset": True,
                                                     "proxy_unset": True}), \
                     mock.patch.object(R, "_child_probe_env", return_value=child_result), \
                     mock.patch("agent_workload_characterization.runners.run_02_entry._docker_preflight") as docker:
                    result = R.run_check()
                self.assertEqual(result["status"], "NOT_READY")
                self.assertIn(result["categories"][-1],
                              {"child_environment_not_ready",
                               "child_probe_invalid_result"})
                docker.assert_not_called()

    def test_run_check_rejects_inline_key_even_when_loader_would_accept(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            config = synthetic_config(root / "opencode.json", key="sk-INLINE-CANARY")
            (root / "reports/preparation").mkdir(parents=True)
            with mock.patch.object(R, "PROJECT_ROOT", root), \
                 mock.patch.object(R, "DEFAULT_CONFIG", config), \
                 mock.patch.dict(os.environ, {}, clear=True), \
                 mock.patch.object(R, "_validate_parent_environment",
                                   return_value={"docker_host_fixed_or_unset": True,
                                                 "docker_context_local_or_unset": True,
                                                 "proxy_unset": True}), \
                 mock.patch.object(L, "load_credentials",
                                   side_effect=AssertionError("route must reject first")):
                result = R.run_check()
            self.assertEqual(result["status"], "NOT_READY")
            self.assertEqual(result["categories"], ["credential_route_not_selected"])
            self.assertNotIn("INLINE-CANARY", json.dumps(result))

    def test_run_check_rejects_false_docker_requirement(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            config = synthetic_config(root / "opencode.json")
            (root / "reports/preparation").mkdir(parents=True)
            child = {"base_present": True, "key_present": True,
                     "proxy_absent": True, "docker_host_absent": True,
                     "argv_safe": True}
            with mock.patch.object(R, "PROJECT_ROOT", root), \
                 mock.patch.object(R, "DEFAULT_CONFIG", config), \
                 mock.patch.dict(os.environ, {"VOLCANO_API_KEY": "sk-SYNTH"}, clear=True), \
                 mock.patch.object(R, "_validate_parent_environment",
                                   return_value={"docker_host_fixed_or_unset": True,
                                                 "docker_context_local_or_unset": True,
                                                 "proxy_unset": True}), \
                 mock.patch.object(R, "_child_probe_env", return_value=child), \
                 mock.patch("agent_workload_characterization.runners.run_02_entry._docker_preflight",
                            return_value={"context": "default",
                                          "endpoint": "unix:///var/run/docker.sock",
                                          "architecture": "amd64", "os": "linux"}):
                result = R.run_check()
            self.assertEqual(result["status"], "NOT_READY")
            self.assertEqual(result["categories"], ["docker_preflight_not_ready"])

    def test_report_symlink_and_overwrite_are_rejected(self):
        with tempfile.TemporaryDirectory() as td, tempfile.TemporaryDirectory() as outside:
            root = Path(td)
            (root / "reports").symlink_to(Path(outside), target_is_directory=True)
            with self.assertRaises(ValueError):
                R._write_report(root, {"status": "NOT_READY"}, "x")
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "reports/preparation").mkdir(parents=True)
            R._write_report(root, {"status": "NOT_READY"}, "x")
            with self.assertRaises(ValueError):
                R._write_report(root, {"status": "NOT_READY"}, "x")

    def test_original_run02_failure_files_are_unchanged(self):
        expected = {
            "APPROVAL.txt": "cf744bf09ac4ba334cf0010dd0be0afdd7859c84046a763bb869f7ef26becd9a",
            "ATTEMPT_STARTED.json": "8279e463198d9130496e3f5f43b0aad1d7fa6e42a9e9cfee0a9581f34fa8b437",
            "PREFLIGHT_DIAGNOSTIC.json": "ed911efcc6a74cf8f8245b7c47ba6c44e51651bb50b21d8a52ee8bf428db2bdc",
        }
        base = Path("reports/resource/RUN-02")
        actual = {name: hashlib.sha256((base / name).read_bytes()).hexdigest()
                  for name in expected}
        self.assertEqual(actual, expected)


if __name__ == "__main__":
    unittest.main()
