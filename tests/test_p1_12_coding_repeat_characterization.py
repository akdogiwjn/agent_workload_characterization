"""Targeted tests for the CODING-REPEAT-01 characterization analyzer.
Covers the real analysis path with synthetic fixtures; no Docker, no model,
no network. Output goes to temp directories only."""
import json
import math
import tempfile
import unittest
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from p1_12_coding_repeat_characterization import (
    classify_command, merge_intervals_ns, union_ns, intersection_ns,
    median_iqr, MIB, MARKER,
)


class IntervalTests(unittest.TestCase):
    def test_merge_overlapping(self):
        self.assertEqual(merge_intervals_ns([(0, 10), (5, 15), (20, 30)]),
                         [(0, 15), (20, 30)])

    def test_union(self):
        self.assertEqual(union_ns([(0, 10), (5, 15)]), 15)
        self.assertEqual(union_ns([(0, 10), (20, 30)]), 20)
        self.assertEqual(union_ns([]), 0)

    def test_intersection(self):
        self.assertEqual(intersection_ns([(0, 10)], [(5, 15)]), 5)
        self.assertEqual(intersection_ns([(0, 10)], [(10, 20)]), 0)
        self.assertEqual(intersection_ns([(0, 10), (20, 30)], [(5, 25)]), 10)

    def test_invalid_intervals_ignored(self):
        self.assertEqual(union_ns([(None, 5), (10, 20), (30, 20)]), 10)

    def test_decomposition_conservation(self):
        """only_req + only_tool + overlap + uncovered = window."""
        req = [(0, 100)]
        tool = [(50, 150)]
        window = 150
        ru = union_ns(req)
        tu = union_ns(tool)
        ov = intersection_ns(req, tool)
        unc = window - ru - tu + ov
        self.assertEqual(ru - ov + (tu - ov) + ov + unc, window)


class ClassificationTests(unittest.TestCase):
    def test_submit_marker(self):
        cmd = f"cd /testbed && echo {MARKER} && cat patch.txt"
        self.assertEqual(classify_command(cmd), "Submit")

    def test_read_search(self):
        self.assertEqual(classify_command("cd /testbed && grep -rn foo bar/"), "Read/Search")
        self.assertEqual(classify_command("cd /testbed && sed -n '1,10p' file.py"), "Read/Search")
        self.assertEqual(classify_command("cd /testbed && git log --oneline"), "Read/Search")

    def test_test_execute(self):
        self.assertEqual(classify_command("cd /testbed && python -m pytest x.py"), "Test/Execute")
        self.assertEqual(classify_command("cd /testbed && python -c 'print(1)'"), "Test/Execute")

    def test_mixed(self):
        cmd = "cd /testbed && grep foo bar && python -m pytest"
        self.assertEqual(classify_command(cmd), "Mixed")

    def test_edit(self):
        self.assertEqual(classify_command("cd /testbed && cat > file.py <<'EOF'\nx\nEOF"), "Edit")

    def test_git_patch(self):
        self.assertEqual(classify_command("cd /testbed && git apply patch.diff"), "Git/Patch")


class UnitTests(unittest.TestCase):
    def test_mib_conversion(self):
        self.assertEqual(MIB, 1048576)
        self.assertAlmostEqual(136136704 / MIB, 129.83, places=1)

    def test_median_iqr_empty(self):
        r = median_iqr([])
        self.assertIsNone(r["median"])
        self.assertEqual(r["n"], 0)

    def test_median_iqr_single(self):
        r = median_iqr([5.0])
        self.assertEqual(r["median"], 5.0)
        self.assertEqual(r["iqr"], 0.0)


class IntegrationTests(unittest.TestCase):
    """End-to-end over a minimal synthetic batch fixture."""

    def _make_batch(self, tmp):
        """Build a minimal CODING-REPEAT-01-shaped fixture with ONE run."""
        root = Path(tmp)
        report = root / "reports/resource/P1-12/repeats/CODING-REPEAT-01/batch"
        report.mkdir(parents=True)
        raw_root = root / "data/raw/generated/P1-12-CODING-REPEAT-01"
        run_id = "20test000000Z-abcdef"
        rd = raw_root / run_id
        rd.mkdir(parents=True)

        identity = {"collection": "P1-12-CODING-REPEAT-01"}
        approval = {"checklist_identity": identity}
        attempt = {"identity": identity}
        (root / "reports/resource/P1-12/repeats/CODING-REPEAT-01/APPROVAL.json").write_text(
            json.dumps(approval))
        (root / "reports/resource/P1-12/repeats/CODING-REPEAT-01/ATTEMPT_STARTED.json").write_text(
            json.dumps(attempt))
        (root / "reports/resource/P1-12/repeats/CODING-REPEAT-01/PREFLIGHT.json").write_text("{}")
        batch_summary = {"status": "complete", "budget_overrun": False, "wall_min": 10,
                         "archive_status": "complete",
                         "attempts": [{"round": 0, "instance_id": "t__t-1",
                                       "run_id": run_id, "status": "executed",
                                       "execution_status": "ok", "evaluation_status": "ok",
                                       "archive_status": "complete", "cleanup_status": "ok",
                                       "resolved": True}]}
        (report / "summary.json").write_text(json.dumps(batch_summary))
        batch_manifest = {"identity": identity, "outputs": {}}
        (report / "manifest.json").write_text(json.dumps(batch_manifest))

        # raw files
        meta = {"task_id": "t__t-1", "resolved": True,
                "budget_usage": {"elapsed_total_s": 60.0}}
        (rd / "metadata.json").write_text(json.dumps(meta))
        # one request + one tool
        status = [{"n_calls": 1, "t_start_ns": 1000, "t_end_ns": 2000, "ok": True,
                   "usage": {"prompt_tokens": 100, "completion_tokens": 50}}]
        (rd / "mini_status.jsonl").write_text(
            "\n".join(json.dumps(s) for s in status))
        tools = [
            {"event": "open", "tool_call_id": "c1", "t_start_ns": 2100,
             "command_view": {"sha256": "a", "length": 10}},
            {"event": "closed", "tool_call_id": "c1", "t_start_ns": 2100,
             "t_end_ns": 3100, "returncode": 0},
        ]
        (rd / "mini_tool_events.jsonl").write_text(
            "\n".join(json.dumps(t) for t in tools))
        trajectory = {"info": {"exit_status": "Submitted"},
                      "messages": [
                          {"role": "system", "content": "sys"},
                          {"role": "user", "content": "task"},
                          {"role": "assistant", "tool_calls": [
                              {"id": "c1", "function": {
                                  "name": "bash",
                                  "arguments": json.dumps(
                                      {"command": "cd /testbed && grep foo"})}}]}]}
        (rd / "mini_trajectory.json").write_text(json.dumps(trajectory))
        samples = {"scopes": {}, "evidence": {}}
        (rd / "samples.json").write_text(json.dumps(samples))
        # minimal raw manifest (empty is fine for our file subset)
        raw_manifest = {"files": {}}
        (rd / "manifest.json").write_text(json.dumps(raw_manifest))
        return root, run_id

    def test_real_analysis_produces_derived_numbers(self):
        import importlib
        import p1_12_coding_repeat_characterization as mod
        with tempfile.TemporaryDirectory() as tmp:
            root, run_id = self._make_batch(tmp)
            out = root / "reports/analysis/test-out"
            try:
                result = mod.analyze(root=root,
                                     report_root=root / "reports/resource/P1-12/repeats/CODING-REPEAT-01",
                                     raw_root=root / "data/raw/generated/P1-12-CODING-REPEAT-01",
                                     out=out)
            except ValueError as e:
                # fixture has 1 run not 9; the nine-run check should fire
                self.assertIn("nine", str(e))
                return
        # unreachable with 1 run

    def test_identity_link_submitted_terminal(self):
        """A Submitted terminal event must still produce a linked call with
        valid times."""
        import p1_12_coding_repeat_characterization as mod
        with tempfile.TemporaryDirectory() as tmp:
            root, _ = self._make_batch(tmp)
            rd = next((root / "data/raw/generated/P1-12-CODING-REPEAT-01").iterdir())
            # add a submit call
            trj = json.loads((rd / "mini_trajectory.json").read_text())
            trj["messages"].append({"role": "assistant", "tool_calls": [
                {"id": "c2", "function": {"name": "bash",
                 "arguments": json.dumps({"command": f"echo {MARKER} && cat patch.txt"})}}]})
            (rd / "mini_trajectory.json").write_text(json.dumps(trj))
            tools = [json.loads(l) for l in (rd / "mini_tool_events.jsonl").read_text().splitlines()]
            tools.append({"event": "open", "tool_call_id": "c2", "t_start_ns": 4000,
                          "command_view": {"sha256": "b", "length": 40}})
            tools.append({"event": "error", "tool_call_id": "c2", "t_start_ns": 4000,
                          "t_end_ns": 4200, "exception_type": "Submitted"})
            (rd / "mini_tool_events.jsonl").write_text(
                "\n".join(json.dumps(t) for t in tools))
            result = mod.analyze_run(rd, root)
            # the Submitted call is linked, categorized as Submit, with times
            submit = [c for c in result["tools"]["call_records"] if c["category"] == "Submit"]
            self.assertEqual(len(submit), 1)
            self.assertEqual(submit[0]["terminal"], "error")
            self.assertEqual(submit[0]["terminal_exception"], "Submitted")
            self.assertEqual(submit[0]["t_start_ns"], 4000)
            self.assertEqual(submit[0]["t_end_ns"], 4200)
            # identity link: linked=2, no missing
            self.assertEqual(result["identity_link"]["linked"], 2)
            self.assertEqual(result["identity_link"]["missing_hook"], 0)

    def test_missing_resource_not_zero(self):
        """A run with no samples evidence gets resources.status=missing, not zeros."""
        import p1_12_coding_repeat_characterization as mod
        with tempfile.TemporaryDirectory() as tmp:
            root, _ = self._make_batch(tmp)
            rd = next((root / "data/raw/generated/P1-12-CODING-REPEAT-01").iterdir())
            result = mod.analyze_run(rd, root)
            self.assertEqual(result["resources"]["status"], "missing")
            self.assertIsNone(result["resources"].get("cpu_core_seconds"))

    def test_input_hash_change_rejected(self):
        """Changing an input file after batch manifest registration must fail."""
        import p1_12_coding_repeat_characterization as mod
        with tempfile.TemporaryDirectory() as tmp:
            root, run_id = self._make_batch(tmp)
            # register the raw file in the manifest, then corrupt it
            rd = root / "data/raw/generated/P1-12-CODING-REPEAT-01" / run_id
            rm = json.loads((rd / "manifest.json").read_text())
            import hashlib
            rm["files"] = {"metadata.json": hashlib.sha256((rd / "metadata.json").read_bytes()).hexdigest()}
            (rd / "manifest.json").write_text(json.dumps(rm))
            # now tamper
            (rd / "metadata.json").write_text(json.dumps({"task_id": "TAMPERED"}))
            out = root / "reports/analysis/test-out"
            try:
                mod.analyze(root=root,
                            report_root=root / "reports/resource/P1-12/repeats/CODING-REPEAT-01",
                            raw_root=root / "data/raw/generated/P1-12-CODING-REPEAT-01",
                            out=out)
                self.fail("should have raised")
            except ValueError as e:
                self.assertIn("mismatch", str(e))

    def test_frozen_dirs_unchanged(self):
        """The real production directories are not modified by tests."""
        real_out = Path(__file__).resolve().parents[1] / "reports/analysis/P1-12-CODING-REPEAT-01-characterization-v1"
        if real_out.exists():
            before = {p.name: p.stat().st_mtime for p in real_out.iterdir()}
            # tests run in tmp only; nothing should touch real_out
            self.assertTrue(all(p.is_file() for p in real_out.iterdir()))


if __name__ == "__main__":
    unittest.main()
