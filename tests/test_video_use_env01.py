"""VIDEO-USE-ENV-01 offline unit tests.

Covers the pure helpers of the no-model validation entry (EDL/command
construction, model-route rejection, ffprobe verification, rate-interval
projection, task-spec hygiene) plus a fake-runtime membership observation.
No Docker, no model, no network."""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
sys.path.insert(0, str(ROOT / 'src'))

import video_use_env01_validation as v  # noqa: E402

SAVED_REPORT = ROOT / 'env/video/video-use/validation/env01-validation.json'


class ModelRouteTests(unittest.TestCase):
    def test_missing_fields_rejected_explicitly(self):
        for missing in ({}, {"api_base": "https://x"}, {"api_base": "https://x", "model": "m"}):
            with self.assertRaises(ValueError) as ctx:
                v.validate_model_route(missing)
            self.assertIn("refusing", str(ctx.exception))
            self.assertIn("api_key_env" if "api_key_env" not in missing
                          else sorted(set(("api_base", "model")) - set(missing))[0],
                          str(ctx.exception))

    def test_credential_values_rejected_in_route(self):
        with self.assertRaises(ValueError) as ctx:
            v.validate_model_route({"api_base": "https://x", "model": "m",
                                    "api_key_env": "K", "api_key": "secret"})
        self.assertIn("credential", str(ctx.exception))

    def test_complete_route_passes_and_no_fallback_field(self):
        out = v.validate_model_route({"api_base": "https://x/v1", "model": "m",
                                      "api_key_env": "MODEL_API_KEY"})
        self.assertEqual(out, {"api_base": "https://x/v1", "model": "m",
                               "api_key_env": "MODEL_API_KEY"})
        self.assertNotIn("fallback", out)

    def test_model_route_file_has_no_values_and_declares_contract(self):
        route = json.loads((ROOT / 'env/video/video-use/model-route.json').read_text())
        self.assertEqual(route["status"], "not_configured_no_model_calls_authorized")
        self.assertIsNone(route["current_values"]["api_base"])
        self.assertIsNone(route["current_values"]["model"])
        self.assertIsNone(route["current_values"]["api_key_env"])
        self.assertIn("api_key_env", route["contract"]["required_fields"])


class CommandConstructionTests(unittest.TestCase):
    def test_synthesis_commands_are_cpu_lavfi_no_downloads(self):
        cmds = v.synthesis_commands()
        self.assertEqual(cmds[0]["name"], "mkdir_task_dirs")
        self.assertIn("mkdir -p /task/sources /task/edit", cmds[0]["shell"])
        for c in cmds[1:]:
            self.assertIn("-f lavfi", c["shell"])
            self.assertIn("libx264", c["shell"])
            self.assertIn("aac", c["shell"])
            self.assertNotIn("http", c["shell"])

    def test_edl_matches_render_py_contract(self):
        edl = v.build_edl()
        self.assertIn("sources", edl)
        self.assertIn("ranges", edl)
        for r in edl["ranges"]:
            self.assertIn(r["source"], edl["sources"])
            self.assertLess(0.0, r["end"] - r["start"])
        # segment windows stay inside the synthetic clip durations
        self.assertLessEqual(edl["ranges"][0]["end"], v.SYNTH_SECONDS_A)
        self.assertLessEqual(edl["ranges"][1]["end"], v.SYNTH_SECONDS_B)
        # grade is a raw ffmpeg filter (contains '='), not a preset name
        self.assertIn("=", edl["grade"])

    def test_expected_duration_is_sum_of_segments(self):
        edl = v.build_edl()
        total = sum(r["end"] - r["start"] for r in edl["ranges"])
        self.assertEqual(total, v.EXPECTED_TOTAL_S)
        self.assertAlmostEqual(total, 5.5, places=6)

    def test_edl_write_command_roundtrips(self):
        import shlex
        cmd = v.edl_write_command(v.build_edl())
        self.assertIn("/task/edit/edl.json", cmd)
        payload = shlex.split(cmd)[-1]
        self.assertEqual(json.loads(payload), v.build_edl())

    def test_render_command_uses_repo_helper_and_venv(self):
        cmd = v.render_command()
        self.assertIn(v.VENV_PYTHON, cmd)
        self.assertIn("/opt/video-use/helpers/render.py", cmd)
        self.assertIn("--no-subtitles", cmd)

    def test_timeout_encode_is_long_by_design(self):
        self.assertIn("duration=600", v.timeout_encode_command())

    def test_hash_and_probe_commands_target_artifacts(self):
        self.assertIn("final.mp4", v.ffprobe_command("/task/edit/final.mp4"))
        self.assertIn("sha256sum", v.hash_command(["/task/edit/final.mp4"]))


class FfprobeValidationTests(unittest.TestCase):
    def _probe(self, duration="5.500"):
        return {"streams": [
            {"codec_type": "video", "codec_name": "h264", "width": 1920, "height": 1080},
            {"codec_type": "audio", "codec_name": "aac"}],
            "format": {"duration": duration, "format_name": "mov,mp4"}}

    def test_valid_output_passes(self):
        result = v.validate_ffprobe(self._probe())
        self.assertTrue(result["ok"], result["problems"])
        self.assertAlmostEqual(result["observed_duration_s"], 5.5, places=3)

    def test_duration_drift_fails(self):
        result = v.validate_ffprobe(self._probe("7.2"))
        self.assertFalse(result["ok"])
        self.assertTrue(any("duration" in p for p in result["problems"]))

    def test_missing_audio_or_wrong_resolution_fail(self):
        bad = self._probe()
        bad["streams"] = [s for s in bad["streams"] if s["codec_type"] != "audio"]
        self.assertFalse(v.validate_ffprobe(bad)["ok"])
        wide = self._probe()
        wide["streams"][0]["width"] = 640
        self.assertFalse(v.validate_ffprobe(wide)["ok"])


class TaskSpecTests(unittest.TestCase):
    def test_spec_is_offline_and_credential_free(self):
        spec = v.build_task_spec("run1", "video_use_task")
        self.assertEqual(spec.network, "none")
        self.assertEqual(spec.env, {})
        self.assertEqual(spec.image, v.TASK_IMAGE)
        self.assertEqual(spec.cwd, "/task")
        self.assertEqual(spec.mem_limit, "4g")


class RateSummaryTests(unittest.TestCase):
    def _rows(self):
        def row(t, cpu, io_r, io_w):
            return {"t_monotonic_ns": t, "container": {
                "container_id": "c1", "cpu_usage_usec": cpu,
                "io_read_bytes": io_r, "io_write_bytes": io_w,
                "mem_current_bytes": 1000,
                "read_status": {"cpuacct.usage": "ok_ns_converted_to_usec",
                                "io": "ok_summed_devices:x"}}}
        return [row(0, 0, 0, 0), row(500_000_000, 400_000, 10, 20),
                row(1_000_000_000, 900_000, 10, 20),
                row(1_500_000_000, None, 30, 40)]  # missing cpu at the end

    def test_summary_counts_valid_and_gap_intervals(self):
        summary = v.summarize_intervals(self._rows())
        self.assertEqual(summary["cpu"]["interval_count"], 3)
        self.assertEqual(summary["cpu"]["valid"], 2)
        self.assertEqual(summary["cpu"]["gap"], 1)
        self.assertAlmostEqual(summary["cpu"]["total_delta"], 0.9, places=6)
        self.assertEqual(summary["cpu"]["unit"], "core_s")
        self.assertEqual(summary["io_read"]["valid"], 3)
        self.assertEqual(summary["io_read"]["total_delta"], 30)
        self.assertEqual(summary["io_write"]["total_delta"], 40)

    def test_gap_reasons_are_kept_not_faked(self):
        summary = v.summarize_intervals(self._rows())
        self.assertTrue(summary["cpu"]["gap_reasons"])

    def test_mem_gauge_summary_never_sums(self):
        s = v.mem_gauge_summary(self._rows())
        self.assertEqual(s["samples_with_current"], 4)
        self.assertEqual(s["max_sampled_current_bytes"], 1000)
        self.assertIn("never summed", s["note"])


class MembershipObservationTests(unittest.TestCase):
    def test_reads_cgroup_procs_from_host(self):
        with tempfile.TemporaryDirectory() as tmp:
            cgroup_dir = Path(tmp)
            # our own pid exists in /proc; comm must be observable read-only
            (cgroup_dir / "cgroup.procs").write_text(f"{os.getpid()}\n")
            obs = v.cgroup_membership_observation(None, cgroup_dir)
            self.assertEqual(obs["status"]["cgroup.procs"], "ok")
            self.assertEqual(obs["pid_count"], 1)
            self.assertIn(str(os.getpid()), obs["comm_by_pid"])
            self.assertEqual(obs["ffmpeg_pids"], [])

    def test_missing_cgroup_files_recorded(self):
        with tempfile.TemporaryDirectory() as tmp:
            obs = v.cgroup_membership_observation(None, Path(tmp))
            self.assertEqual(obs["pid_count"], 0)
            self.assertIn("FileNotFoundError", obs["status"]["cgroup.procs"])


class ManifestIntegrityTests(unittest.TestCase):
    def test_source_manifest_matches_staging(self):
        import hashlib
        manifest = json.loads(
            (ROOT / 'env/video/video-use/source-manifest.json').read_text())
        self.assertEqual(manifest["upstream_commit"], v.UPSTREAM_COMMIT)
        self.assertTrue(manifest["all_files_match_reference_at_commit_check"])
        staged = ROOT / manifest["staging_path"]
        for entry in manifest["files"]:
            data = (staged / entry["path"]).read_bytes()
            self.assertEqual(hashlib.sha256(data).hexdigest(), entry["sha256"])

    def test_no_env_or_git_staged(self):
        staged = ROOT / 'env/video/video-use/source'
        self.assertFalse((staged / '.git').exists())
        self.assertFalse((staged / '.env').exists())
        for p in staged.rglob('*'):
            self.assertNotEqual(p.name, '.env', p)

    def test_env_manifest_records_identities_and_exclusions(self):
        m = json.loads((ROOT / 'env/video/video-use/env-manifest.json').read_text())
        self.assertEqual(m["image"]["tag"], v.TASK_IMAGE)
        self.assertEqual(m["image"]["architecture"], "arm64")
        self.assertEqual(m["upstream"]["commit"], v.UPSTREAM_COMMIT)
        self.assertEqual(m["image"]["base"]["tag"], v.BASE_IMAGE)
        self.assertFalse(m["outer_agent"]["installed_in_this_image"])
        self.assertTrue(m["not_included"]["credentials_or_env_files"])
        self.assertIn("ElevenLabs", " ".join(m["not_tested_this_round"]))

    def test_requirements_frozen_covers_declared_top_level(self):
        text = (ROOT / 'env/video/video-use/requirements-frozen.txt').read_text()
        for pkg in ("requests", "librosa", "matplotlib", "pillow", "numpy"):
            self.assertTrue(any(l.lower().startswith(pkg + "==") for l in text.splitlines()),
                            pkg)


class AcceptanceGatingTests(unittest.TestCase):
    """Regression: missing/partial evidence must FAIL, never silently pass."""

    @classmethod
    def setUpClass(cls):
        cls.report = json.loads(SAVED_REPORT.read_text())

    def test_saved_live_report_passes_strict_acceptance(self):
        self.assertEqual(v.acceptance_failures(self.report), [])

    def test_missing_sampler_rows_fail(self):
        r = json.loads(json.dumps(self.report))
        del r["success_case"]["sampler_rows"]
        problems = v.acceptance_failures(r)
        self.assertTrue(any("no sampler rows" in p for p in problems))

    def test_rows_without_container_reads_fail(self):
        r = json.loads(json.dumps(self.report))
        for row in r["success_case"]["sampler_rows"]:
            row.pop("container", None)
        problems = v.acceptance_failures(r)
        self.assertTrue(any("container counter read" in p for p in problems))

    def test_missing_memory_and_disk_evidence_fail(self):
        r = json.loads(json.dumps(self.report))
        r["success_case"]["mem_gauge_summary"] = {"samples_with_current": 0}
        r["success_case"]["render_footprint"] = {"paths": []}
        problems = v.acceptance_failures(r)
        self.assertTrue(any("memory gauge samples" in p for p in problems))
        self.assertTrue(any("delta not observed" in p for p in problems))

    def test_no_valid_cpu_intervals_fail(self):
        r = json.loads(json.dumps(self.report))
        r["success_case"]["rate_summary"]["cpu"]["valid"] = 0
        r["success_case"]["rate_summary"]["cpu"]["gap"] = 5
        self.assertTrue(any("cpu intervals incomplete" in p
                            for p in v.acceptance_failures(r)))

    def test_partial_cpu_gaps_fail(self):
        r = json.loads(json.dumps(self.report))
        # 6 rows -> 5 intervals; only 1 valid with 4 gaps must FAIL
        r["success_case"]["rate_summary"]["cpu"]["valid"] = 1
        r["success_case"]["rate_summary"]["cpu"]["gap"] = 4
        problems = v.acceptance_failures(r)
        self.assertTrue(any("cpu intervals incomplete" in p for p in problems))
        self.assertIn("valid=1 gap=4 expected_valid=5",
                      next(p for p in problems if "cpu intervals" in p))

    def test_legal_zero_cpu_delta_still_passes(self):
        r = json.loads(json.dumps(self.report))
        # zero deltas are VALID intervals, not gaps — must stay a pass
        r["success_case"]["rate_summary"]["cpu"]["total_delta"] = 0.0
        self.assertEqual(v.acceptance_failures(r), [])

    def test_interval_count_must_match_rows(self):
        r = json.loads(json.dumps(self.report))
        r["success_case"]["rate_summary"]["cpu"]["interval_count"] = 99
        self.assertTrue(any("interval count" in p for p in v.acceptance_failures(r)))

    def test_missing_hashes_and_unconfirmed_termination_fail(self):
        r = json.loads(json.dumps(self.report))
        r["success_case"]["artifact_hashes"] = {}
        r["timeout_case"].pop("termination_explicit")
        problems = v.acceptance_failures(r)
        self.assertTrue(any("artifact hash" in p for p in problems))
        self.assertTrue(any("termination not confirmed" in p for p in problems))

    def test_malformed_hash_value_fails(self):
        r = json.loads(json.dumps(self.report))
        r["success_case"]["artifact_hashes"]["/task/edit/final.mp4"] = "not-a-sha256"
        problems = v.acceptance_failures(r)
        self.assertTrue(any("not valid sha-256" in p for p in problems))

    def test_unconfirmed_termination_fails(self):
        r = json.loads(json.dumps(self.report))
        r["timeout_case"]["termination_explicit"] = {
            "confirmed": False, "method": "docker_stop", "container_alive": False}
        self.assertTrue(any("termination not confirmed" in p
                            for p in v.acceptance_failures(r)))

    def test_image_identity_problems_fail_acceptance(self):
        r = json.loads(json.dumps(self.report))
        r["image_identity_problems"] = {
            "images_before": ["x: image id mismatch observed=1 registered=2"]}
        problems = v.acceptance_failures(r)
        self.assertTrue(any("image identity (images_before)" in p for p in problems))


class ImageIdentityTests(unittest.TestCase):
    def test_expected_identities_from_manifests(self):
        exp = v.expected_image_identities()
        self.assertEqual(exp[v.TASK_IMAGE]["image_id"],
                         "sha256:d14e6415db40eaecccb6540defc0c686df5dfde47801a1c692f4df5d5b187887")
        self.assertEqual(exp[v.BASE_IMAGE]["image_id"],
                         "sha256:d414b4270fec6ec2dd245982a522099d8941d8cd114ccd5ec2c6730815f3a706")
        self.assertEqual(exp[v.TASK_IMAGE]["architecture"], "arm64")
        self.assertEqual(exp[v.BASE_IMAGE]["os"], "linux")

    def test_matching_identities_pass(self):
        exp = v.expected_image_identities()
        actual = [{"reference": ref, "present": True, **fields}
                  for ref, fields in exp.items()]
        self.assertEqual(v.verify_image_identities(actual, exp), [])

    def test_changed_image_id_rejected(self):
        exp = v.expected_image_identities()
        actual = [{"reference": v.TASK_IMAGE, "present": True,
                   "image_id": "sha256:0000000000000000", "architecture": "arm64",
                   "os": "linux"}]
        problems = v.verify_image_identities(actual, exp)
        self.assertTrue(any("image id mismatch" in p for p in problems))

    def test_changed_architecture_rejected(self):
        exp = v.expected_image_identities()
        actual = [{"reference": v.TASK_IMAGE, "present": True,
                   "image_id": exp[v.TASK_IMAGE]["image_id"],
                   "architecture": "amd64", "os": "linux"}]
        self.assertTrue(any("architecture mismatch" in p
                            for p in v.verify_image_identities(actual, exp)))

    def test_missing_or_unregistered_images_rejected(self):
        exp = v.expected_image_identities()
        self.assertTrue(any("image missing" for p in v.verify_image_identities(
            [{"reference": v.TASK_IMAGE, "present": False}], exp)))
        self.assertTrue(any("not registered" for p in v.verify_image_identities(
            [{"reference": "unknown:tag", "present": True, "image_id": "x",
              "architecture": "arm64", "os": "linux"}], exp)))

    def test_failed_identity_query_is_explicit_failure(self):
        exp = v.expected_image_identities()
        bad = [{"reference": v.TASK_IMAGE, "present": None,
                "query_error": "TimeoutExpired"}]
        problems = v.verify_image_identities(bad, exp)
        self.assertTrue(any("identity query failed" in p for p in problems))
        # and it fails overall acceptance too
        r = json.loads(SAVED_REPORT.read_text())
        r["image_identity_problems"] = {"images_before": problems}
        self.assertTrue(any("image identity (images_before)" in p
                            for p in v.acceptance_failures(r)))

    def test_image_identity_never_raises(self):
        import subprocess
        with patch("subprocess.run",
                   side_effect=subprocess.TimeoutExpired("docker", 30)):
            ident = v.image_identity(v.TASK_IMAGE)
        self.assertIsNone(ident["present"])
        self.assertEqual(ident["query_error"], "TimeoutExpired")
        with patch("subprocess.run", return_value=subprocess.CompletedProcess(
                args=[], returncode=0, stdout="garbage-line")):
            ident = v.image_identity(v.TASK_IMAGE)
        self.assertEqual(ident["query_error"], "malformed_inspect_output")

    def test_saved_report_images_match_manifests(self):
        report = json.loads(SAVED_REPORT.read_text())
        exp = v.expected_image_identities()
        self.assertEqual(v.verify_image_identities(report["images_before"], exp), [])
        self.assertEqual(
            v.verify_image_identities(report["cleanup"]["images_after"], exp), [])


class ExceptionLifecycleTests(unittest.TestCase):
    """Regression: exceptions must stop the sampler, keep evidence, clean up
    the container and still land the report on disk."""

    def _fake_runtime(self):
        from agent_workload_characterization.runners.container_runtime import \
            FakeContainerRuntime

        class _CgroupFakeRuntime(FakeContainerRuntime):
            def start(self, spec, timeout_s=60):
                handle = super().start(spec, timeout_s)
                handle.cgroup_dir = Path("/tmp/fake-cgroup-does-not-exist")
                handle.cgroup_version = "v1"
                return handle

        return _CgroupFakeRuntime(clock=None)

    def test_sampler_stopped_and_evidence_kept_on_exception(self):
        runtime = self._fake_runtime()
        with patch.object(v, "cgroup_membership_observation",
                          side_effect=RuntimeError("boom")):
            record = v.run_success_case(runtime, "run-exc")
        self.assertEqual(record["status"], "exception:RuntimeError")
        self.assertIn("exception_detail", record)
        # sampler received the stop signal: boundary_end row was recorded
        rows = record["sampler_rows"]
        self.assertTrue(rows)
        self.assertEqual(rows[-1]["role"], "boundary_end")
        # evidence collected before the exception is preserved
        self.assertIn("rate_summary", record)
        self.assertIn("mem_gauge_summary", record)
        self.assertEqual(record["membership_observations"], [])
        # render command result still recorded (ran in its own thread)
        self.assertTrue(any(c.get("name") == "render_edl"
                            for c in record["commands"]))
        # container cleanup still verified
        self.assertEqual(record["removal_verification"], "removed")

    def test_execute_writes_report_even_when_case_raises(self):
        exp = v.expected_image_identities()
        ident = [{"reference": ref, "present": True, **fields}
                 for ref, fields in exp.items()]
        with tempfile.TemporaryDirectory() as tmp:
            report_path = Path(tmp) / "report.json"
            with patch.object(v, "REPORT_PATH", report_path), \
                 patch.object(v, "image_identity",
                              side_effect=lambda ref: next(
                                  i for i in ident if i["reference"] == ref)), \
                 patch.object(v, "run_success_case",
                              side_effect=RuntimeError("boom")), \
                 patch.object(v, "run_timeout_case",
                              return_value={"status": "stub"}):
                rc = v.execute()
            self.assertEqual(rc, 7)
            report = json.loads(report_path.read_text())
            self.assertEqual(report["success_case"]["status"], "exception:RuntimeError")
            self.assertEqual(report["overall"], "fail_or_partial")
            self.assertTrue(report["acceptance_failures"])

    def test_render_thread_start_failure_stops_sampler(self):
        """Regression: render_thread.start() failing after the sampler
        started must still stop the sampler, record the failure and clean
        up the container."""
        import threading as real_threading
        runtime = self._fake_runtime()
        real_thread_cls = real_threading.Thread  # captured BEFORE patching

        def thread_factory(*args, **kwargs):
            target = kwargs.get("target") or (args[0] if args else None)
            if getattr(target, "__name__", "") == "_render":
                class _StartFailsThread(real_thread_cls):
                    def start(self):
                        raise RuntimeError("cannot start new thread")
                return _StartFailsThread(*args, **kwargs)
            return real_thread_cls(*args, **kwargs)

        with patch.object(v.threading, "Thread", thread_factory):
            record = v.run_success_case(runtime, "run-tsf")
        self.assertEqual(record["status"], "exception:RuntimeError")
        # sampler was stopped (boundary_end recorded), not leaked
        rows = record["sampler_rows"]
        self.assertTrue(rows)
        self.assertEqual(rows[-1]["role"], "boundary_end")
        # the start failure is recorded explicitly, not silently dropped
        self.assertIn({"name": "render_edl", "error": "render_thread_start_failed"},
                      record["commands"])
        self.assertEqual(record["removal_verification"], "removed")

    def test_execute_writes_report_on_image_query_error(self):
        """Regression: docker inspect timeout must become a failure record
        and the report must still be written."""
        bad = [{"reference": ref, "present": None, "query_error": "TimeoutExpired"}
               for ref in (v.BASE_IMAGE, v.TASK_IMAGE)]
        with tempfile.TemporaryDirectory() as tmp:
            report_path = Path(tmp) / "report.json"
            with patch.object(v, "REPORT_PATH", report_path), \
                 patch.object(v, "image_identity",
                              side_effect=lambda ref: next(
                                  i for i in bad if i["reference"] == ref)), \
                 patch.object(v, "run_success_case",
                              side_effect=AssertionError("must not start")), \
                 patch.object(v, "run_timeout_case",
                              side_effect=AssertionError("must not start")):
                rc = v.execute()
            self.assertEqual(rc, 7)
            report = json.loads(report_path.read_text())
            self.assertTrue(report["preflight_refused"])
            self.assertTrue(any("identity query failed" in p
                                for p in report["acceptance_failures"]))
            self.assertEqual(report["overall"], "fail_or_partial")

    def test_execute_outer_guard_writes_report_on_unexpected_error(self):
        """Regression: ANY residual exception inside execute() still lands
        the report with an execute_error record."""
        exp = v.expected_image_identities()
        ident = [{"reference": ref, "present": True, **fields}
                 for ref, fields in exp.items()]
        with tempfile.TemporaryDirectory() as tmp:
            report_path = Path(tmp) / "report.json"
            with patch.object(v, "REPORT_PATH", report_path), \
                 patch.object(v, "image_identity",
                              side_effect=lambda ref: next(
                                  i for i in ident if i["reference"] == ref)), \
                 patch.object(v, "expected_image_identities",
                              side_effect=RuntimeError("boom")):
                rc = v.execute()
            self.assertEqual(rc, 7)
            report = json.loads(report_path.read_text())
            self.assertEqual(report["execute_error"], "RuntimeError")
            self.assertEqual(report["overall"], "fail_or_partial")
            self.assertTrue(report["acceptance_failures"])

    def test_execute_refuses_to_start_on_identity_mismatch(self):
        exp = v.expected_image_identities()
        bad = [{"reference": v.TASK_IMAGE, "present": True,
                "image_id": "sha256:wrong" * 8, "architecture": "arm64",
                "os": "linux"},
               {"reference": v.BASE_IMAGE, "present": True,
                "image_id": exp[v.BASE_IMAGE]["image_id"],
                "architecture": "arm64", "os": "linux"}]
        with tempfile.TemporaryDirectory() as tmp:
            report_path = Path(tmp) / "report.json"
            with patch.object(v, "REPORT_PATH", report_path), \
                 patch.object(v, "image_identity",
                              side_effect=lambda ref: next(
                                  i for i in bad if i["reference"] == ref)), \
                 patch.object(v, "run_success_case",
                              side_effect=AssertionError("must not start")), \
                 patch.object(v, "run_timeout_case",
                              side_effect=AssertionError("must not start")):
                rc = v.execute()
            self.assertEqual(rc, 7)
            report = json.loads(report_path.read_text())
            self.assertTrue(report["preflight_refused"])
            self.assertNotIn("success_case", report)
            self.assertNotIn("timeout_case", report)
            self.assertTrue(any("image id mismatch" in p
                                for p in report["acceptance_failures"]))


class OfflineMainTests(unittest.TestCase):
    def test_offline_mode_is_default_and_safe(self):
        self.assertEqual(v.main([]), 0)


if __name__ == '__main__':
    unittest.main()
