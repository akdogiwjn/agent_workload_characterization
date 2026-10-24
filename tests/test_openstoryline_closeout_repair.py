from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "env/video/openstoryline/edit-pilot-02/runtime"))
import openstoryline_pilot_entry as entry  # noqa: E402


class FakeSampler:
    def __init__(self):
        self.stop_event = type("Event", (), {"set": lambda self: None})()
        self.rows = []
        self.joined = False

    def join(self, timeout=None):
        self.joined = True


class FakeRuntime:
    def __init__(self, *, stop_error=None, removal="removed", execute_result=None):
        self.stop_error = stop_error
        self.removal = removal
        self.stop_calls = 0
        self.execute_result = execute_result or {"returncode": 7, "timed_out": False,
                                                 "termination": "process_exit", "output": "agent output"}
        self.execute_calls = 0

    def execute(self, handle, command, timeout_s, output_limit):
        self.execute_calls += 1
        return self.execute_result

    def stop(self, handle, timeout_s):
        self.stop_calls += 1
        if self.stop_error:
            raise self.stop_error

    def verify_removal(self, handle, timeout_s):
        return self.removal


def make_paths(base: Path):
    raw = base / "raw"
    output = raw / "workspace/output"
    project = raw / "workspace/project"
    input_dir = base / "input"
    for path in (output, project, input_dir):
        path.mkdir(parents=True)
    return raw, output, project, input_dir


class OpenStorylineCloseoutRepairTests(unittest.TestCase):
    def test_host_report_is_independent_and_preserves_container_status_bytes(self):
        with tempfile.TemporaryDirectory() as temp:
            raw, output, project, input_dir = make_paths(Path(temp))
            status = output / "agent-result.json"
            original = b'{"status":"executing","render_artifact_id":"r1"}\n'
            status.write_bytes(original)

            def no_container_status_writes(path, value, **kwargs):
                if path == status:
                    raise PermissionError("simulated nobody-owned container state")
                return entry.atomic_write_json(path, value, **kwargs)

            report = entry.finalize_host_attempt(
                raw=raw, output=output, project=project,
                boundaries_before={"input": {"bytes": 0, "scan_status": "complete"}},
                report={"run_id": "test", "start_monotonic_ns": 10,
                        "agent_execution": {"status": "returned", "returncode": 0}},
                runtime=FakeRuntime(), handle=object(), sampler=None, input_dir=input_dir,
                report_writer=no_container_status_writes,
                postprocess=lambda: {"render_export": {"status": "not_run"},
                                     "cuts_export": {"status": "not_run"}},
            )
            self.assertEqual(status.read_bytes(), original)
            self.assertTrue((raw / "host-finalization.json").is_file())
            self.assertTrue((raw / "run-report.json").is_file())
            self.assertEqual(report["container_agent_result"]["status"], "executing")

    def test_report_failure_does_not_skip_cleanup_and_is_recorded(self):
        with tempfile.TemporaryDirectory() as temp:
            raw, output, project, input_dir = make_paths(Path(temp))
            runtime = FakeRuntime()
            def failing_report_writer(path, value, **kwargs):
                if path.name == "run-report.json":
                    raise PermissionError("simulated host report failure")
                return entry.atomic_write_json(path, value, **kwargs)
            entry.finalize_host_attempt(
                raw=raw, output=output, project=project, input_dir=input_dir,
                boundaries_before={}, report={"run_id": "test", "start_monotonic_ns": 20},
                runtime=runtime, handle=object(), sampler=None,
                report_writer=failing_report_writer,
            )
            self.assertEqual(runtime.stop_calls, 1)
            self.assertTrue(runtime.verify_removal)
            status = json.loads((raw / "report-generation-status.json").read_text())
            self.assertEqual(status["report_status"], "error")
            self.assertEqual(status["errors"][0]["type"], "PermissionError")
            self.assertTrue((raw / "manifest.json").is_file())

    def test_primary_and_cleanup_errors_are_saved_separately(self):
        with tempfile.TemporaryDirectory() as temp:
            raw, output, project, input_dir = make_paths(Path(temp))
            report = entry.finalize_host_attempt(
                raw=raw, output=output, project=project, input_dir=input_dir,
                boundaries_before={}, report={"run_id": "test", "start_monotonic_ns": 30},
                runtime=FakeRuntime(stop_error=OSError("stop failed")), handle=object(),
                sampler=None, primary_error=ValueError("execute failed"),
            )
            host = json.loads((raw / "host-finalization.json").read_text())
            self.assertEqual(host["primary_error"]["type"], "ValueError")
            self.assertEqual(host["cleanup_errors"][0]["scope"], "container_stop")
            self.assertEqual(report["termination_reason"]["type"], "ValueError")

    def test_saved_start_and_execute_return_survive_postprocess_failure(self):
        with tempfile.TemporaryDirectory() as temp:
            raw, output, project, input_dir = make_paths(Path(temp))
            started_ns = __import__("time").monotonic_ns()
            entry.atomic_write_json(raw / "run-start.json", {
                "attempt_start_monotonic_ns": started_ns, "budget": {"wall": 2700}}, exclusive=True)
            fake = FakeRuntime()
            result_value, execution = entry.execute_and_persist(
                fake, object(), "fake command", timeout_s=2, output_limit=1000, raw=raw)
            self.assertEqual(fake.execute_calls, 1)
            self.assertEqual(json.loads((raw / "agent-execution.json").read_text())["returncode"], 7)
            result = entry.finalize_host_attempt(
                raw=raw, output=output, project=project, input_dir=input_dir,
                boundaries_before={}, report={"run_id": "test", "start_monotonic_ns": started_ns,
                                              "agent_execution": execution},
                runtime=FakeRuntime(), handle=None, sampler=FakeSampler(),
                postprocess=lambda: (_ for _ in ()).throw(RuntimeError("postprocess failed")),
            )
            self.assertEqual(json.loads((raw / "run-start.json").read_text())["attempt_start_monotonic_ns"], started_ns)
            self.assertEqual(json.loads((raw / "agent-execution.json").read_text())["returncode"], 7)
            self.assertEqual(result["postprocess_error"]["type"], "RuntimeError")
            self.assertGreaterEqual(result["total_wall_s"], 0.0)

    def test_missing_historical_fields_stay_unknown(self):
        with tempfile.TemporaryDirectory() as temp:
            raw, output, project, input_dir = make_paths(Path(temp))
            result = entry.finalize_host_attempt(
                raw=raw, output=output, project=project, input_dir=input_dir,
                boundaries_before={}, report={"run_id": "historical", "start_monotonic_ns": None},
                runtime=FakeRuntime(), handle=None, sampler=None,
            )
            self.assertIsNone(result["total_wall_s"])
            self.assertNotIn("returncode", result.get("agent_execution", {}))
            self.assertEqual(result["directory_boundaries"]["input"]["before"]["scan_status"],
                             "not_persisted")

    def test_byte_to_gib_conversion_is_exact(self):
        self.assertAlmostEqual(entry.gibibytes(6517669888), 6.0700531005859375)
        self.assertAlmostEqual(entry.gibibytes(6944976896), 6.468013763427734)
        self.assertIsNone(entry.gibibytes(None))

    def test_main_rejects_cleanup_report_and_manifest_failures(self):
        with tempfile.TemporaryDirectory() as temp:
            for failure in ("cleanup", "report", "manifest", "postprocess"):
                with self.subTest(failure=failure):
                    raw, output, project, input_dir = make_paths(Path(temp) / failure)
                    runtime = FakeRuntime(stop_error=OSError("stop failed")
                                          if failure == "cleanup" else None)

                    def writer(path, value, **kwargs):
                        if failure == "report" and path.name == "run-report.json":
                            raise PermissionError("report failed")
                        return entry.atomic_write_json(path, value, **kwargs)

                    def manifest_writer(path):
                        if failure == "manifest":
                            raise OSError("manifest failed")
                        entry._write_manifest(path)

                    def postprocess():
                        if failure == "postprocess":
                            raise RuntimeError("postprocess failed")
                        return {}

                    result = entry.finalize_host_attempt(
                        raw=raw, output=output, project=project, input_dir=input_dir,
                        boundaries_before={}, report={"run_id": failure,
                            "start_monotonic_ns": __import__("time").monotonic_ns(),
                            "agent_returncode": 0, "agent_execution": {"returncode": 0}},
                        runtime=runtime, handle=object(), sampler=None,
                        report_writer=writer, manifest_writer=manifest_writer,
                        postprocess=postprocess,
                    )
                    with mock.patch.object(entry, "execute_once", return_value=result), \
                            mock.patch.object(sys, "argv", ["entry", "--execute"]):
                        self.assertEqual(entry.main(), 7)
                    self.assertEqual(runtime.stop_calls, 1)

    def test_clean_finalization_keeps_reward_zero_separate_from_exit_code(self):
        with tempfile.TemporaryDirectory() as temp:
            raw, output, project, input_dir = make_paths(Path(temp))
            result = entry.finalize_host_attempt(
                raw=raw, output=output, project=project, input_dir=input_dir,
                boundaries_before={}, report={"run_id": "clean", "agent_returncode": 0,
                    "agent_execution": {"returncode": 0},
                    "start_monotonic_ns": __import__("time").monotonic_ns()},
                runtime=FakeRuntime(), handle=object(), sampler=None,
            )
            result["verifier"] = {"status": "complete", "reward": 0.0}
            with mock.patch.object(entry, "execute_once", return_value=result), \
                    mock.patch.object(sys, "argv", ["entry", "--execute"]):
                self.assertEqual(entry.main(), 0)
            result["agent_returncode"] = 1
            self.assertEqual(entry.exit_code_for(result), 1)

    def test_final_wall_includes_archive_and_preserves_manifest_hashes(self):
        with tempfile.TemporaryDirectory() as temp:
            raw, output, project, input_dir = make_paths(Path(temp))
            clock = [10_000_000_000]

            def delayed_manifest(path):
                entry._write_manifest(path)
                clock[0] += 5_000_000_000

            with mock.patch.object(entry.time, "monotonic_ns", side_effect=lambda: clock[0]):
                result = entry.finalize_host_attempt(
                    raw=raw, output=output, project=project, input_dir=input_dir,
                    boundaries_before={}, report={"run_id": "archive-delay",
                        "start_monotonic_ns": clock[0]},
                    runtime=FakeRuntime(), handle=None, sampler=None,
                    manifest_writer=delayed_manifest,
                )
            host = json.loads((raw / "host-finalization.json").read_text())
            saved = json.loads((raw / "run-report.json").read_text())
            self.assertEqual(result["total_wall_s"], 5.0)
            self.assertEqual(host["total_wall_s"], 5.0)
            self.assertEqual(host["end_monotonic_ns"], result["end_monotonic_ns"])
            self.assertEqual(saved["pre_archive_wall_s"], 0.0)
            self.assertIsNone(saved["total_wall_s"])
            self.assertEqual(saved["total_wall_source"], "host-finalization.json")
            manifest = json.loads((raw / "manifest.json").read_text())
            for row in manifest["files"]:
                data = (raw / row["path"]).read_bytes()
                self.assertEqual(len(data), row["bytes"])
                self.assertEqual(hashlib.sha256(data).hexdigest(), row["sha256"])

    def _write_render_fixture(self, output: Path, *, selected: str, missing_selected_media=False):
        session = "session-1"
        (output / session / "render_video").mkdir(parents=True)
        (output / session / "plan_timeline_pro").mkdir(parents=True)
        (output / ".server_cache" / session).mkdir(parents=True)
        (output / "agent-context.json").write_text(json.dumps({"session_id": session}))
        (output / "agent-result.json").write_text(json.dumps({"status": "executing",
                                                               "render_artifact_id": selected}))
        (output / "session-status.json").write_text(json.dumps({"status": "executing",
                                                                  "render_artifact_id": selected}))
        timeline = {"tracks": {"video": [{"clip_id": "clip-a"}]}}
        timeline_record = {"artifact_id": "plan-new", "node_id": "plan_timeline_pro",
                           "session_id": session, "create_time": 20, "payload": timeline}
        (output / session / "plan_timeline_pro/plan-new.json").write_text(json.dumps(timeline_record))
        events = []
        for artifact_id, create_time, content in (("render-old", 10, b"old-render"),
                                                   ("render-selected", 30, b"selected-render")):
            artifact_dir = output / ".server_cache" / session / artifact_id
            artifact_dir.mkdir(parents=True)
            media = artifact_dir / "clip.mp4"
            if not (missing_selected_media and artifact_id == selected):
                media.write_bytes(content)
            record = {"artifact_id": artifact_id, "node_id": "render_video",
                      "session_id": session, "create_time": create_time,
                      "payload": {"output_path": f"/workspace/output/.server_cache/{session}/{artifact_id}/clip.mp4"}}
            (output / session / "render_video" / f"{artifact_id}.json").write_text(json.dumps(record))
            call_id = "call-" + artifact_id
            events += [{"event": "tool_call_started", "node_id": "render_video",
                        "artifact_id": artifact_id, "session_id": session,
                        "tool_call_id": call_id, "arguments": {"plan_timeline": timeline}},
                       {"event": "tool_call_finished", "tool_call_id": call_id, "is_error": False}]
        (output / "mcp-tool-events.jsonl").write_text("\n".join(json.dumps(x) for x in events) + "\n")
        return session

    def test_multiple_render_candidates_select_explicit_status_and_bind_hashes(self):
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp) / "output"
            output.mkdir()
            self._write_render_fixture(output, selected="render-selected")
            copied = entry.copy_selected_render_artifact(output)
            self.assertEqual(copied["selection"]["artifact"]["artifact_id"], "render-selected")
            self.assertEqual(copied["selection"]["timeline_artifact_id"], "plan-new")
            self.assertEqual(copied["source"]["sha256"], copied["submission"]["sha256"])
            self.assertEqual(copied["source"]["sha256"], hashlib.sha256(b"selected-render").hexdigest())

    def test_missing_media_and_hash_mismatch_never_claim_match(self):
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp) / "missing"
            output.mkdir()
            self._write_render_fixture(output, selected="render-selected", missing_selected_media=True)
            with self.assertRaisesRegex(RuntimeError, "media missing"):
                entry.copy_selected_render_artifact(output)
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp) / "mismatch"
            output.mkdir()
            self._write_render_fixture(output, selected="render-selected")
            def corrupt_copy(src, dst):
                Path(dst).write_bytes(b"different")
            with self.assertRaisesRegex(RuntimeError, "hash differs"):
                entry.copy_selected_render_artifact(output, copy_fn=corrupt_copy)

    def test_manifest_binds_selected_submission_and_does_not_hash_itself(self):
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp) / "output"
            output.mkdir()
            self._write_render_fixture(output, selected="render-selected")
            copied = entry.copy_selected_render_artifact(output)
            raw = output.parent
            entry._write_manifest(raw)
            manifest = json.loads((raw / "manifest.json").read_text())
            by_path = {item["path"]: item for item in manifest["files"]}
            submitted = copied["submission"]["path"]
            rel = str(Path(submitted).relative_to(raw))
            self.assertEqual(by_path[rel]["sha256"], copied["submission"]["sha256"])
            self.assertNotIn("manifest.json", by_path)


if __name__ == "__main__":
    unittest.main()
