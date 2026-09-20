import hashlib
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from scripts.p3_01_audit import run_audit


PROJECT = Path(__file__).resolve().parents[1]
REPORT_ROOT = PROJECT / "reports" / "replay"


class P301AuditTests(unittest.TestCase):
    def fixture(self, *, command="printf ok", event_mode="normal"):
        root = Path(tempfile.mkdtemp(prefix="p301-source-"))
        command_hash = hashlib.sha256(command.encode()).hexdigest()
        ident = "call_fixture"
        events = [
            {"event": "open", "event_id": "event_fixture", "tool_call_id": ident,
             "seq": 1, "command_view": {"sha256": command_hash, "length": len(command)}, "t_start_ns": 10},
            {"event": "closed", "event_id": "event_fixture", "tool_call_id": ident,
             "seq": 1, "returncode": 0, "output_length": 3, "t_start_ns": 10, "t_end_ns": 20},
        ]
        if event_mode == "missing":
            events.pop()
        elif event_mode == "duplicate":
            events.append(dict(events[-1]))
        elif event_mode == "orphan":
            events[-1]["tool_call_id"] = "other"
        (root / "mini_tool_events.jsonl").write_text("\n".join(json.dumps(x) for x in events) + "\n")
        trajectory = {"info": {"mini_version": "2.4.6", "config": {"model": {"model_name": "fake/model"}}},
                      "messages": [
                          {"role": "assistant", "tool_calls": [{"id": ident, "type": "function",
                           "function": {"name": "bash", "arguments": json.dumps({"command": command})}}]},
                          {"role": "tool", "tool_call_id": ident, "content": "ok"}],
                      "trajectory_format": "test"}
        (root / "mini_trajectory.json").write_text(json.dumps(trajectory))
        (root / "metadata.json").write_text(json.dumps({"run_id": "fixture", "attempt_id": "fixture-a1", "task_id": "t", "source_type": "synthetic"}))
        (root / "candidate.patch").write_text("")
        files = {}
        for path in (root / "candidate.patch", root / "metadata.json", root / "mini_trajectory.json", root / "mini_tool_events.jsonl"):
            files[path.name] = hashlib.sha256(path.read_bytes()).hexdigest()
        (root / "manifest.json").write_text(json.dumps({"files": files}))
        return root

    def run_fixture(self, source):
        out = Path(tempfile.mkdtemp(prefix="P3-01-test-", dir=REPORT_ROOT))
        shutil.rmtree(out)
        try:
            result = run_audit(source, out)
            return result
        finally:
            shutil.rmtree(out, ignore_errors=True)

    def test_actual_entry_records_command_and_projection(self):
        source = self.fixture()
        try:
            result = self.run_fixture(source)
            self.assertTrue(result["assessment"]["command_hashes_all_match"])
            self.assertEqual(result["calls"][0]["command"]["structured_argv"]["status"], "unknown")
            self.assertEqual(result["calls"][0]["output"]["truncation"]["status"], "unknown")
        finally:
            shutil.rmtree(source)

    def test_actual_entry_reports_hash_and_association_counterexamples(self):
        for mode in ("missing", "duplicate", "orphan"):
            source = self.fixture(event_mode=mode)
            try:
                result = self.run_fixture(source)
                self.assertNotEqual(result["calls"][0]["association"]["status"], "recorded")
                self.assertFalse(result["assessment"]["association_integrity"])
            finally:
                shutil.rmtree(source)
        source = self.fixture(command="printf changed")
        try:
            # Keep the hook projection for printf ok while trajectory changes.
            event_path = source / "mini_tool_events.jsonl"
            rows = [json.loads(x) for x in event_path.read_text().splitlines()]
            rows[0]["command_view"]["sha256"] = hashlib.sha256(b"printf ok").hexdigest()
            rows[0]["command_view"]["length"] = len("printf ok")
            event_path.write_text("\n".join(json.dumps(x) for x in rows) + "\n")
            files = json.loads((source / "manifest.json").read_text())["files"]
            files["mini_tool_events.jsonl"] = hashlib.sha256(event_path.read_bytes()).hexdigest()
            (source / "manifest.json").write_text(json.dumps({"files": files}))
            self.assertFalse(self.run_fixture(source)["assessment"]["command_hashes_all_match"])
        finally:
            shutil.rmtree(source)

    def test_registered_plan_fields_are_derived_not_observed(self):
        from scripts.p3_01_audit import analyze_run
        run_dir = PROJECT / "data/raw/generated/RUN-02/20260915T012427Z-2d75aa"
        result = analyze_run(run_dir, schema="p3-01-audit-v3")
        self.assertEqual(result["identity"]["image"]["status"], "derived")
        self.assertEqual(result["calls"][0]["fields"]["cwd"]["status"], "derived")
        self.assertEqual(result["calls"][0]["fields"]["interpreter"]["status"], "derived")
        self.assertEqual(result["identity"]["image"]["actual_observed"], "unknown")

    def test_same_input_is_repeatable_except_output_paths(self):
        source = self.fixture()
        outs = []
        try:
            for _ in range(2):
                out = Path(tempfile.mkdtemp(prefix="P3-01-repeat-", dir=REPORT_ROOT))
                shutil.rmtree(out)
                run_audit(source, out)
                outs.append(out)
            for name in ("inventory.json", "summary.md", "corrections.md"):
                self.assertEqual((outs[0] / name).read_bytes(), (outs[1] / name).read_bytes())
        finally:
            shutil.rmtree(source)
            for out in outs:
                shutil.rmtree(out, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
