"""Offline safety and wiring checks; these tests never access Docker/network."""
import hashlib
import json
import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "src"))
import video_use_edit_pilot_01 as pilot  # noqa: E402


class PilotOfflineTests(unittest.TestCase):
    def test_fixed_identity_and_caps(self):
        self.assertEqual(pilot.IMAGE_ID, "sha256:a46db2143d8aa69a299b419152c6ca036e09f619d3f771aeace64e08ed729402")
        self.assertEqual((pilot.ATTEMPT_BUDGET_S, pilot.AGENT_BUDGET_S,
                          pilot.VERIFIER_BUDGET_S), (2700, 1800, 600))
        self.assertEqual(pilot.SAMPLE_S, 0.5)

    def test_instruction_maps_original_paths_and_preserves_preapproval_truthfully(self):
        s = pilot.starter_instruction()
        for p in ("/workspace/materials/source.mp4", "/workspace/output/output.mp4",
                  "/workspace/output/cuts.json", "preauthorization, not a fabricated chat confirmation"):
            self.assertIn(p, s)
        self.assertNotIn('"start_ms": 12480', s)
        self.assertNotIn("golden", s.lower().split("do not inspect")[0])

    def test_official_test_sh_download_is_avoided(self):
        src = (pilot.TASK_PATH / "steps/solve/tests/test.sh").read_text()
        self.assertIn("curl", src)
        # The independent verifier invokes the original judge directly from the staged copy.
        import inspect
        body = inspect.getsource(pilot.run_verifier)
        self.assertIn("judge.py", body)
        self.assertNotIn('"curl"', body)
        self.assertIn("verifier_only/golden", body)

    def test_asr_uses_official_single_post_cached_by_transcript_file(self):
        src = (ROOT / "env/video/video-use/source/helpers/transcribe.py").read_text()
        self.assertIn('model_id": "scribe_v1"', src)
        self.assertEqual(src.count("requests.post("), 1)
        self.assertIn("if out_path.exists():", src)
        self.assertIn("timeout=1800", src)
        self.assertNotIn("Retry(", src)

    def test_asr_production_cache_makes_at_most_one_mocked_send(self):
        path = ROOT / "env/video/video-use/source/helpers/transcribe.py"
        spec = importlib.util.spec_from_file_location("video_use_official_transcribe", path)
        transcribe = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(transcribe)
        class Response:
            status_code = 200
            def json(self):
                return {"text": "mock transcript", "words": []}
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            video = base / "source.mp4"
            video.write_bytes(b"fixture")
            edit = base / "edit"
            def extract(_video, dest, _track=0):
                dest.write_bytes(b"wav-fixture")
            with patch.object(transcribe, "extract_audio", side_effect=extract), \
                 patch.object(transcribe, "peak_dbfs", return_value=-12.0), \
                 patch.object(transcribe.requests, "post", return_value=Response()) as post:
                first = transcribe.transcribe_one(video, edit, "fake-key", verbose=False)
                second = transcribe.transcribe_one(video, edit, "fake-key", verbose=False)
                self.assertEqual(first, second)
                self.assertEqual(post.call_count, 1)
                self.assertEqual(json.loads(first.read_text())["text"], "mock transcript")

    def test_credentials_loaded_by_variable_name_and_never_serialized(self):
        with tempfile.TemporaryDirectory() as td:
            f = Path(td) / "secret.env"
            f.write_text("export DASHSCOPE_API_KEY=fake-a\nELEVENLABS_API_KEY=fake-b\n")
            self.assertEqual(pilot.safe_credential(f, "ELEVENLABS_API_KEY"), "fake-b")
            self.assertEqual(pilot.safe_credential(f, "DASHSCOPE_API_KEY"), "fake-a")
            # No credential file is staged/copied to the task container.
            main = inspect_source(pilot.main)
            self.assertNotIn('"bailian.env"', main.split("staging =", 1)[1])
            self.assertNotIn('"elevenlabs.env"', main.split("staging =", 1)[1])

    def test_agent_has_no_verifier_mount_or_host_project(self):
        source = inspect_source(pilot.main)
        self.assertNotIn("verifier_only", source.split("def run_verifier")[0])
        self.assertIn('"docker", "cp"', source)
        self.assertIn("--pull=never", inspect_source(pilot.image_check))

    def test_timeout_and_cleanup_are_explicit(self):
        source = inspect_source(pilot.main)
        self.assertIn("finally:", source)
        self.assertIn("runtime.stop(handle)", source)
        self.assertIn("runtime.verify_removal(handle)", source)
        self.assertIn("timeout_s=agent_budget", source)
        self.assertIn("remaining=verifier_budget", source)

    def test_manifest_excludes_itself(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "x").write_bytes(b"x")
            expected = hashlib.sha256(b"x").hexdigest()
            pilot.emit_manifest(root)
            m = json.loads((root / "manifest.json").read_text())
            self.assertEqual(m["files"]["x"]["sha256"], expected)
            self.assertNotIn("manifest.json", m["files"])

    def test_native_rollout_index_keeps_call_return_usage_and_model(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "rollout-one.jsonl").write_text("\n".join([
                json.dumps({"type": "response_item", "payload": {"type": "function_call",
                    "name": "exec_command", "call_id": "c1", "arguments": "{}"}}),
                json.dumps({"type": "response_item", "payload": {"type": "function_call_output",
                    "call_id": "c1", "output": "done"}}),
                json.dumps({"type": "token_usage_record", "payload": {"model": "qwen3.7-plus",
                    "usage": {"input_tokens": 5, "output_tokens": 2}}}),
            ]) + "\n")
            index = pilot.index_rollouts(root)
            self.assertEqual([e["call_id"] for e in index["events"] if e.get("call_id")], ["c1", "c1"])
            summary = pilot.rollout_summary(root)
            self.assertEqual(summary["tool_call_count"], 1)
            self.assertEqual(summary["tool_return_count"], 1)
            self.assertEqual(summary["response_models"], ["qwen3.7-plus"])
            self.assertEqual(summary["usage_events"][0]["usage"]["input_tokens"], 5)

    def test_resource_missing_values_stay_null_and_rates_use_elapsed_time(self):
        rows = [
            {"t_monotonic_ns": 0, "cgroup": {"cpu_usage_usec": 1000000,
             "mem_current_bytes": 7, "mem_peak_bytes": 9, "io_read_bytes": 10,
             "io_write_bytes": 20}},
            {"t_monotonic_ns": 2_000_000_000, "cgroup": {"cpu_usage_usec": 3000000,
             "mem_current_bytes": 5, "mem_peak_bytes": 9, "io_read_bytes": 50,
             "io_write_bytes": 60}},
            {"t_monotonic_ns": 4_000_000_000, "cgroup": {"cpu_usage_usec": None,
             "mem_current_bytes": None, "mem_peak_bytes": None, "io_read_bytes": None,
             "io_write_bytes": None}},
        ]
        m = pilot.resource_metrics(rows)
        self.assertEqual(m["cpu_core_seconds"], 2.0)
        self.assertEqual(m["cpu_average_cores"], 1.0)
        self.assertEqual(m["io_read_Bps"], 20.0)
        self.assertEqual(m["max_sampled_memory_current_bytes"], 7)


def inspect_source(fn):
    import inspect
    return inspect.getsource(fn)


if __name__ == "__main__":
    unittest.main()
