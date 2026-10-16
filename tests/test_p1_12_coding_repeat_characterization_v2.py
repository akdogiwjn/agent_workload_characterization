"""Targeted tests for the CODING-REPEAT-01 characterization v2 analyzer.
All fixtures in temp dirs; production directories verified unchanged."""
import hashlib
import json
import shutil
import tempfile
import unittest
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from p1_12_coding_repeat_characterization_v2 import (
    classify_command, split_top_level, merge_intervals_ns, union_ns,
    intersection_ns, median_iqr, MIB, MARKER, associate_calls,
)
ROOT = Path(__file__).resolve().parents[1]


class SplitTests(unittest.TestCase):
    def test_quoted_semicolon_not_split(self):
        cmd = 'python -c "import os; print(os.path)"'
        parts = split_top_level(cmd)
        self.assertEqual(len(parts), 1)

    def test_real_and_split(self):
        parts = split_top_level("grep foo bar && python -m pytest")
        self.assertEqual(len(parts), 2)

    def test_heredoc_not_split(self):
        cmd = "cat > /tmp/f.py <<'EOF'\nimport sys; sys.exit(1)\nEOF"
        parts = split_top_level(cmd)
        self.assertEqual(len(parts), 1)

    def test_unparseable_returns_whole(self):
        parts = split_top_level("echo 'unclosed && quote")
        self.assertEqual(len(parts), 1)


class ClassificationTests(unittest.TestCase):
    def test_submit_marker(self):
        r = classify_command(f"cd /testbed && echo {MARKER} && cat patch.txt")
        self.assertEqual(r["label"], "Submit-marker")

    def test_python_with_pytest_is_test(self):
        r = classify_command("cd /testbed && python -m pytest x.py")
        self.assertEqual(r["label"], "Test")

    def test_python_without_pytest_is_interpreter(self):
        r = classify_command("cd /testbed && python -c 'print(1)'")
        self.assertEqual(r["label"], "Interpreter/Execute")

    def test_explicit_test_invocations_still_test(self):
        for cmd in ("cd /testbed && python -m pytest test_x.py",
                    "cd /testbed && pytest -q",
                    "cd /testbed && python tests/runtests.py template_tests",
                    "cd /testbed && timeout 30 python -m pytest x.py",
                    "cd /testbed && python -m unittest test_mod"):
            r = classify_command(cmd)
            self.assertEqual(r["label"], "Test", cmd)

    def test_grep_with_pytest_keyword_is_not_test(self):
        r = classify_command("grep pytest README.md")
        self.assertEqual(r["label"], "Read/Search")

    def test_echo_pytest_is_not_test(self):
        r = classify_command("echo pytest")
        self.assertEqual(r["label"], "Echo")

    def test_python_print_pytest_is_not_test(self):
        r = classify_command('python -c \'print("pytest")\'')
        self.assertEqual(r["label"], "Interpreter/Execute")

    def test_mixed_read_and_interpreter(self):
        r = classify_command("cd /testbed && grep foo && python -c 'x'")
        self.assertEqual(r["label"], "Mixed")

    def test_unknown_part_makes_partial(self):
        r = classify_command("cd /testbed && grep foo && weirdcmd --flag")
        self.assertEqual(r["label"], "Partially-known")
        self.assertEqual(r["coverage"], "partial")

    def test_pure_unknown(self):
        r = classify_command("weirdcmd --flag")
        self.assertEqual(r["label"], "Unknown")
        self.assertEqual(r["coverage"], "unknown")


class IntervalTests(unittest.TestCase):
    def test_decomposition_conservation(self):
        req = [(0, 100)]
        tool = [(50, 150)]
        window = 150
        ru, tu = union_ns(req), union_ns(tool)
        ov = intersection_ns(req, tool)
        unc = window - ru - tu + ov
        self.assertEqual((ru - ov) + (tu - ov) + ov + unc, window)

    def test_union(self):
        self.assertEqual(union_ns([(0, 10), (5, 15)]), 15)


class AssociationTests(unittest.TestCase):
    def _msgs(self, tid, cmd):
        return [{"role": "assistant", "tool_calls": [
            {"id": tid, "function": {"name": "bash",
             "arguments": json.dumps({"command": cmd})}}]}]

    def _hook(self, tid, cmd, t0=100, t1=200, eid="e1"):
        sha = hashlib.sha256(cmd.encode()).hexdigest()
        return [
            {"event": "open", "tool_call_id": tid, "t_start_ns": t0,
             "event_id": eid,
             "command_view": {"sha256": sha, "length": len(cmd)}},
            {"event": "closed", "tool_call_id": tid, "t_start_ns": t0,
             "t_end_ns": t1, "returncode": 0, "event_id": eid},
        ]

    def test_valid_link(self):
        records, diag = associate_calls(
            self._msgs("c1", "grep foo"), self._hook("c1", "grep foo"))
        self.assertEqual(diag["valid_linked"], 1)
        self.assertEqual(diag["rejected"], 0)
        self.assertTrue(records[0]["valid"])

    def test_hash_mismatch_rejected(self):
        hooks = self._hook("c1", "grep foo")
        hooks[0]["command_view"]["sha256"] = "0" * 64
        records, diag = associate_calls(self._msgs("c1", "grep foo"), hooks)
        self.assertEqual(diag["hash_mismatch"], 1)
        self.assertEqual(diag["rejected"], 1)
        self.assertFalse(records[0]["valid"])

    def test_length_mismatch_rejected(self):
        hooks = self._hook("c1", "grep foo")
        hooks[0]["command_view"]["length"] = 999
        records, diag = associate_calls(self._msgs("c1", "grep foo"), hooks)
        self.assertEqual(diag["length_mismatch"], 1)
        self.assertFalse(records[0]["valid"])

    def test_duplicate_trajectory_id_rejected(self):
        msgs = self._msgs("c1", "grep foo") + self._msgs("c1", "other")
        records, diag = associate_calls(msgs, self._hook("c1", "grep foo"))
        self.assertEqual(diag["traj_duplicate_ids"], 1)
        self.assertEqual(diag["rejected"], 1)

    def test_multi_terminal_rejected(self):
        hooks = self._hook("c1", "grep foo")
        hooks.append({"event": "closed", "tool_call_id": "c1",
                      "t_start_ns": 100, "t_end_ns": 300, "returncode": 0})
        records, diag = associate_calls(self._msgs("c1", "grep foo"), hooks)
        self.assertEqual(diag["multi_terminal"], 1)
        self.assertFalse(records[0]["valid"])

    def test_submitted_terminal_is_valid(self):
        cmd = f"echo {MARKER}"
        hooks = [
            {"event": "open", "tool_call_id": "c1", "t_start_ns": 100,
             "event_id": "e1",
             "command_view": {"sha256": hashlib.sha256(cmd.encode()).hexdigest(),
                              "length": len(cmd)}},
            {"event": "error", "tool_call_id": "c1", "t_start_ns": 100,
             "t_end_ns": 150, "exception_type": "Submitted", "event_id": "e1"},
        ]
        records, diag = associate_calls(self._msgs("c1", cmd), hooks)
        self.assertEqual(diag["valid_linked"], 1)
        self.assertTrue(records[0]["valid"])
        self.assertEqual(records[0]["terminal_exception"], "Submitted")

    def test_no_open_rejected(self):
        cmd = "grep foo"
        hooks = [{"event": "closed", "tool_call_id": "c1", "t_start_ns": 100,
                  "t_end_ns": 200, "returncode": 0, "event_id": "e1"}]
        records, diag = associate_calls(self._msgs("c1", cmd), hooks)
        self.assertEqual(diag["no_open"], 1)
        self.assertFalse(records[0]["valid"])

    def test_multi_open_rejected(self):
        cmd = "grep foo"
        hooks = self._hook("c1", cmd) + self._hook("c1", cmd, eid="e2")
        # the second hook adds another open; remove its terminal to test multi-open
        hooks = hooks[:1] + [hooks[2]] + [hooks[3]]
        records, diag = associate_calls(self._msgs("c1", cmd), hooks)
        self.assertEqual(diag["multi_open"], 1)
        self.assertFalse(records[0]["valid"])

    def test_event_id_mismatch_rejected(self):
        cmd = "grep foo"
        hooks = self._hook("c1", cmd)
        hooks[1]["event_id"] = "different"
        records, diag = associate_calls(self._msgs("c1", cmd), hooks)
        self.assertEqual(diag["event_id_mismatch"], 1)
        self.assertFalse(records[0]["valid"])

    def test_t_start_mismatch_rejected(self):
        cmd = "grep foo"
        hooks = self._hook("c1", cmd)
        hooks[1]["t_start_ns"] = 999
        records, diag = associate_calls(self._msgs("c1", cmd), hooks)
        self.assertEqual(diag["t_start_mismatch"], 1)
        self.assertFalse(records[0]["valid"])

    def test_missing_hash_rejected(self):
        cmd = "grep foo"
        hooks = self._hook("c1", cmd)
        del hooks[0]["command_view"]["sha256"]
        records, diag = associate_calls(self._msgs("c1", cmd), hooks)
        self.assertEqual(diag["missing_hash"], 1)
        self.assertFalse(records[0]["valid"])

    def test_missing_length_rejected(self):
        cmd = "grep foo"
        hooks = self._hook("c1", cmd)
        del hooks[0]["command_view"]["length"]
        records, diag = associate_calls(self._msgs("c1", cmd), hooks)
        self.assertEqual(diag["missing_length"], 1)
        self.assertFalse(records[0]["valid"])

    def test_missing_event_id_rejected(self):
        cmd = "grep foo"
        hooks = self._hook("c1", cmd)
        del hooks[0]["event_id"]
        records, diag = associate_calls(self._msgs("c1", cmd), hooks)
        self.assertEqual(diag["missing_event_id"], 1)
        self.assertFalse(records[0]["valid"])

    def test_bool_timestamp_rejected(self):
        cmd = "grep foo"
        hooks = self._hook("c1", cmd)
        hooks[0]["t_start_ns"] = True
        hooks[1]["t_start_ns"] = True
        hooks[1]["t_end_ns"] = True
        records, diag = associate_calls(self._msgs("c1", cmd), hooks)
        self.assertEqual(diag["invalid_times"], 1)
        self.assertFalse(records[0]["valid"])


class NineRunFixtureTest(unittest.TestCase):
    """Full end-to-end: a complete 3×3 synthetic batch through analyze()."""

    def _make_batch(self, tmp, *, wall_base=100.0):
        root = Path(tmp)
        report = root / "reports/resource/P1-12/repeats/CODING-REPEAT-01"
        (report / "batch").mkdir(parents=True)
        raw_root = root / "data/raw/generated/P1-12-CODING-REPEAT-01"
        identity = {"collection": "P1-12-CODING-REPEAT-01"}
        (report / "APPROVAL.json").write_text(json.dumps(
            {"checklist_identity": identity}))
        (report / "ATTEMPT_STARTED.json").write_text(json.dumps(
            {"identity": identity}))
        (report / "PREFLIGHT.json").write_text("{}")
        tasks = ["taskA__a-1", "taskB__b-2", "taskC__c-3"]
        attempts = []
        for r in range(3):
            for t in tasks:
                run_id = f"20fix{r}{tasks.index(t)}00000Z-aaaa{r}{tasks.index(t)}"
                rd = raw_root / run_id
                rd.mkdir(parents=True)
                self._make_run(rd, t, r, wall_base)
                attempts.append({"round": r, "instance_id": t, "run_id": run_id,
                                 "status": "executed", "execution_status": "ok",
                                 "evaluation_status": "ok", "archive_status": "complete",
                                 "cleanup_status": "ok", "resolved": r % 2 == 0})
        (report / "batch/summary.json").write_text(json.dumps(
            {"status": "complete", "budget_overrun": False, "wall_min": 30,
             "archive_status": "complete", "attempts": attempts}))
        (report / "batch/manifest.json").write_text(json.dumps(
            {"identity": identity, "outputs": {}}))
        return root, report, raw_root

    def _make_run(self, rd: Path, task: str, round_: int, wall_base: float):
        resolved = round_ % 2 == 0
        term = "Submitted" if round_ < 2 else "LimitsExceeded"
        meta = {"task_id": task, "resolved": resolved,
                "budget_usage": {"elapsed_total_s": wall_base + round_ * 10}}
        (rd / "metadata.json").write_text(json.dumps(meta))
        # two requests
        status = [
            {"n_calls": i + 1, "t_start_ns": 1000 + i * 5000,
             "t_end_ns": 2000 + i * 5000, "ok": True,
             "usage": {"prompt_tokens": 100, "completion_tokens": 50}}
            for i in range(2)]
        (rd / "mini_status.jsonl").write_text("\n".join(json.dumps(s) for s in status))
        # two tool calls: one grep, one pytest
        cmds = ["cd /testbed && grep foo bar.py", "cd /testbed && python -m pytest test_x.py"]
        if term == "Submitted":
            cmds.append(f"echo {MARKER}")
        tools = []
        t = 3000
        for i, cmd in enumerate(cmds):
            tid = f"c{i}"
            sha = hashlib.sha256(cmd.encode()).hexdigest()
            eid = f"ev{i}"
            tools.append({"event": "open", "tool_call_id": tid, "t_start_ns": t,
                          "event_id": eid,
                          "command_view": {"sha256": sha, "length": len(cmd)}})
            if MARKER in cmd:
                tools.append({"event": "error", "tool_call_id": tid, "t_start_ns": t,
                              "t_end_ns": t + 100, "exception_type": "Submitted",
                              "event_id": eid})
            else:
                tools.append({"event": "closed", "tool_call_id": tid, "t_start_ns": t,
                              "t_end_ns": t + 500, "returncode": 0,
                              "event_id": eid})
            t += 1000
        (rd / "mini_tool_events.jsonl").write_text("\n".join(json.dumps(x) for x in tools))
        # trajectory
        msgs = [{"role": "system", "content": "s"}, {"role": "user", "content": "u"}]
        for i, cmd in enumerate(cmds):
            msgs.append({"role": "assistant", "tool_calls": [
                {"id": f"c{i}", "function": {"name": "bash",
                 "arguments": json.dumps({"command": cmd})}}]})
        trj = {"info": {"exit_status": term}, "messages": msgs}
        (rd / "mini_trajectory.json").write_text(json.dumps(trj))
        # samples
        samples = {
            "scopes": {f"{rd.name}-agent-sandbox": {
                "cpu_core_seconds": 10.0 + round_ * 5,
                "wall_s": wall_base - 5 + round_ * 10,
                "memory_kernel_peak_bytes": 100 * MIB + round_ * 10 * MIB,
                "memory_sampled_max_bytes": 90 * MIB,
            }},
            "evidence": {f"{rd.name}-agent-sandbox": {
                "boundary_start": {"t_monotonic_ns": 500, "cpu_usage_usec": 0,
                                    "mem_current_bytes": 10 * MIB},
                "boundary_end": {"t_monotonic_ns": 90000, "cpu_usage_usec": 10000000,
                                  "mem_current_bytes": 50 * MIB},
                "samples": [
                    {"t_monotonic_ns": 1000 + j * 500, "cpu_usage_usec": 1000000 * (j + 1),
                     "mem_current_bytes": 20 * MIB + j * MIB}
                    for j in range(5)],
            }},
        }
        (rd / "samples.json").write_text(json.dumps(samples))
        (rd / "manifest.json").write_text(json.dumps({"files": {}}))

    def test_full_nine_run_analysis(self):
        import p1_12_coding_repeat_characterization_v2 as mod
        with tempfile.TemporaryDirectory() as tmp:
            root, report, raw = self._make_batch(tmp)
            out = root / "reports/analysis/v2test"
            result = mod.analyze(root=root, report_root=report, raw_root=raw, out=out)
            self.assertEqual(len(result["selected_run_ids"]), 9)
            self.assertTrue((out / "summary.json").is_file())
            self.assertTrue((out / "summary.md").is_file())
            self.assertTrue((out / "corrections.md").is_file())
            m = json.loads((out / "manifest.json").read_text())
            self.assertNotIn("manifest.json", m["outputs"])
            # verify derived values
            for r in result["runs"]:
                self.assertEqual(r["identity_association"]["valid_linked"],
                                 r["identity_association"]["traj_total"])
                self.assertEqual(r["identity_association"]["rejected"], 0)
            # Submitted runs have a Submit-marker call
            for r in result["runs"]:
                if r["termination"] == "Submitted":
                    self.assertIn("Submit-marker", r["tools"]["category_counts"])

    def test_input_change_changes_output(self):
        import p1_12_coding_repeat_characterization_v2 as mod
        with tempfile.TemporaryDirectory() as tmp1, tempfile.TemporaryDirectory() as tmp2:
            root1, rep1, raw1 = self._make_batch(tmp1, wall_base=100.0)
            root2, rep2, raw2 = self._make_batch(tmp2, wall_base=200.0)
            out1 = root1 / "reports/analysis/o1"
            out2 = root2 / "reports/analysis/o2"
            r1 = mod.analyze(root=root1, report_root=rep1, raw_root=raw1, out=out1)
            r2 = mod.analyze(root=root2, report_root=rep2, raw_root=raw2, out=out2)
            # the attempt_wall_s values must differ
            w1 = [r["attempt_wall_s"] for r in r1["runs"]]
            w2 = [r["attempt_wall_s"] for r in r2["runs"]]
            self.assertNotEqual(w1, w2)
            # md files must differ
            self.assertNotEqual((out1 / "summary.md").read_text(),
                                (out2 / "summary.md").read_text())

    def test_production_dirs_unchanged(self):
        """Before/after hash comparison of production evidence."""
        import p1_12_coding_repeat_characterization_v2 as mod
        protected = [
            ROOT / "reports/resource/P1-12/repeats/CODING-REPEAT-01",
            ROOT / "data/raw/generated/P1-12-CODING-REPEAT-01",
            ROOT / "reports/analysis/P1-12-CODING-REPEAT-01-review-v1",
            ROOT / "reports/analysis/P1-12-CODING-REPEAT-01-characterization-v1",
        ]
        before = {}
        for d in protected:
            if d.is_dir():
                for p in sorted(d.rglob("*")):
                    if p.is_file():
                        before[str(p.relative_to(ROOT))] = (
                            p.stat().st_size, hashlib.sha256(p.read_bytes()).hexdigest())
        with tempfile.TemporaryDirectory() as tmp:
            root, report, raw = self._make_batch(tmp)
            out = root / "reports/analysis/v2test"
            mod.analyze(root=root, report_root=report, raw_root=raw, out=out)
        after = {}
        for d in protected:
            if d.is_dir():
                for p in sorted(d.rglob("*")):
                    if p.is_file():
                        after[str(p.relative_to(ROOT))] = (
                            p.stat().st_size, hashlib.sha256(p.read_bytes()).hexdigest())
        self.assertEqual(before, after)


class ResourceTests(unittest.TestCase):
    def test_mib_conversion(self):
        self.assertAlmostEqual(136136704 / MIB, 129.83, places=1)

    def test_median_iqr(self):
        r = median_iqr([])
        self.assertIsNone(r["median"])
        r = median_iqr([5.0])
        self.assertEqual(r["iqr"], 0.0)


if __name__ == "__main__":
    unittest.main()
