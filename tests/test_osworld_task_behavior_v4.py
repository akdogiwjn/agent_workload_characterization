import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest

from scripts import osworld_static_actions_v4 as parser
from scripts import osworld_task_behavior_v4 as runner


class ParserTests(unittest.TestCase):
    def test_actual_gpt_import_shape_and_new_function_names(self):
        result = parser.static_calls("import pyautogui\npyautogui.hotkey('enter')\npyautogui.typewrite('abc')")
        self.assertEqual(result["status"], "known")
        self.assertEqual([c["category"] for c in result["calls"]], ["text_or_key", "text_or_key"])
        self.assertEqual(result["source_call_syntax_count"], 2)
        result = parser.static_calls("import time\ntime.sleep(0.1)")
        self.assertEqual(result["calls"][0]["canonical_name"], "time.sleep")

    def test_aliases_and_from_imports(self):
        source = "import pyautogui as pg\nfrom pyautogui import click as c, hotkey as h\npg.scroll(1)\nc(1, 2)\nh('enter')"
        result = parser.static_calls(source)
        self.assertEqual(result["status"], "known")
        self.assertEqual([c["canonical_name"] for c in result["calls"]],
                         ["pyautogui.scroll", "pyautogui.click", "pyautogui.hotkey"])

    def test_literal_declarations_are_not_operations_or_evaluated_strings(self):
        result = parser.static_calls("text='pyautogui.click(1,2)'\nxy=(1,-2)\npyautogui.write(text)")
        self.assertEqual(len(result["calls"]), 1)
        self.assertEqual(result["source_call_syntax_count"], 1)
        self.assertEqual(result["metadata_statements"]["literal_assignment"], 2)

    def test_shadowed_module_and_function_aliases_are_not_resolved(self):
        result = parser.static_calls("import pyautogui as pg\npg=0\npg.click(1,2)\npyautogui.press('a')")
        self.assertEqual([c["canonical_name"] for c in result["calls"]], ["pyautogui.press"])
        self.assertEqual(result["status"], "partial")
        result = parser.static_calls("from pyautogui import click as c\nc=lambda: 0\nc()")
        self.assertEqual(result["calls"], [])
        result = parser.static_calls("pyautogui.click=custom\npyautogui.click(1,2)")
        self.assertEqual(result["calls"], [])

    def test_unsupported_import_cannot_spoof_pyautogui(self):
        result = parser.static_calls("import unknown as pyautogui\npyautogui.click(1,2)")
        self.assertEqual(result["calls"], [])
        self.assertIn("unsupported_import", result["reason_counts"])
        result = parser.static_calls("from pyautogui import *\npyautogui.click(1,2)")
        self.assertEqual(result["calls"], [])
        result = parser.static_calls("import pyautogui as pg\nfrom unknown import pg\npg.click(1,2)")
        self.assertEqual(result["calls"], [])

    def test_calls_inside_control_flow_functions_and_comprehensions_not_expanded(self):
        for source in ["for i in range(1000):\n pyautogui.click(i,i)",
                       "if flag:\n pyautogui.click(1,2)",
                       "try:\n pyautogui.click(1,2)\nexcept Exception:\n pass",
                       "def f():\n pyautogui.click(1,2)",
                       "[pyautogui.click(i,i) for i in range(3)]"]:
            with self.subTest(source=source):
                result = parser.static_calls(source)
                self.assertEqual(result["calls"], [])
                self.assertGreater(result["source_call_syntax_count"], 0)
                self.assertEqual(result["tokens"], [None])

    def test_partial_keeps_known_calls_and_unknown_breaks_transitions(self):
        result = parser.static_calls("pyautogui.click(1,2)\nunknown()\npyautogui.scroll(1)")
        self.assertEqual(result["status"], "partial")
        self.assertEqual(result["tokens"], ["click", None, "scroll"])
        sequence = parser.Sequence()
        for token in result["tokens"]:
            sequence.add(token)
        self.assertEqual(sequence.finish()["transition_counts"], {})

    def test_nested_calls_and_dynamic_code_are_boundaries_and_never_run(self):
        with tempfile.TemporaryDirectory() as tmp:
            marker = Path(tmp) / "must-not-exist"
            source = f"exec(\"open({str(marker)!r}, 'w').write('bad')\")\npyautogui.click(1,2)"
            result = parser.static_calls(source)
            self.assertFalse(marker.exists())
            self.assertEqual(result["calls"], [])
        for source in ["pyautogui.click(nested(),2)",
                       "getattr(pyautogui, 'click')(1,2)",
                       "pyautogui.click((pyautogui:=fake),2)"]:
            self.assertEqual(parser.static_calls(source)["calls"], [])

    def test_annotation_call_is_not_neutral_metadata(self):
        result = parser.static_calls("x: unknown() = 1\npyautogui.click(1,2)")
        self.assertEqual(result["status"], "partial")
        self.assertEqual(result["source_call_syntax_count"], 2)
        self.assertEqual(len(result["calls"]), 1)

    def test_metadata_only_syntax_error_and_missing_are_separate(self):
        self.assertEqual(parser.static_calls("import pyautogui\nx=1")["status"], "metadata_only")
        self.assertIn("syntax_error", parser.static_calls("pyautogui.click(")["reason_counts"])
        self.assertIn("command_not_string", parser.static_calls(None)["reason_counts"])

    def test_sequence_counts_repetitions_and_category_switches(self):
        sequence = parser.Sequence()
        for token in ["click", "click", "scroll", None, "scroll", "scroll"]:
            sequence.add(token)
        result = sequence.finish()
        self.assertEqual(result["transition_counts"], {"click->click": 1, "click->scroll": 1, "scroll->scroll": 1})
        self.assertEqual(result["segment_length_counts"], {"click:2": 1, "scroll:1": 1, "scroll:2": 1})


class BatchAndEntryTests(unittest.TestCase):
    def test_batch_groups_preserve_duplicate_indices_and_incomplete_groups(self):
        result = runner.batch_summary({
            "a": [{"batch_size": 2, "batch_index": 0, "batch_last": False}, {"batch_size": 2, "batch_index": 1, "batch_last": True}],
            "b": [{"batch_size": 1, "batch_index": 0, "batch_last": True}] * 2,
            "c": [{"batch_size": 2, "batch_index": 1, "batch_last": True}],
            "d": [{"batch_size": -1, "batch_index": 0, "batch_last": True}],
        })
        self.assertEqual(result["complete_batch_groups"], 1)
        self.assertEqual(result["incomplete_or_ambiguous_groups"], 3)
        self.assertEqual(result["duplicate_batch_index_records"], 1)
        self.assertEqual(result["records_in_call_id_groups"], 6)

    def fixture(self, base):
        root, old = base / "raw", base / "v3"
        task = root / "website_demo" / "fixture-model" / "tasks" / "001"
        task.mkdir(parents=True)
        source = "import pyautogui\npyautogui.click(1,2)\nunknown()\npyautogui.hotkey('enter')"
        records = [{"step_num": 1, "action": None},
                   {"step_num": 2, "action": {"command": source, "call_id": "c", "batch_index": 0, "batch_size": 1, "batch_last": True}},
                   {"step_num": 3, "action": {"command": "pyautogui.scroll(1)", "call_id": "c", "batch_index": 0, "batch_size": 1, "batch_last": True}}]
        (task / "traj.jsonl").write_text("".join(json.dumps(r) + "\n" for r in records))
        (task / "result.txt").write_text("0\n")
        inventory = base / "OSWORLD-OFFICIAL-LIGHT-inventory-v1" / "inventory.json"
        inventory.parent.mkdir()
        inventory.write_text(json.dumps({"requested_revision": runner.legacy.REVISION,
                                        "files": [{**runner.hash_record(p), "path": str(p.relative_to(root))} for p in task.iterdir()]}))
        baseline = {"model": "fixture-model", "task_key": "001", "source_file": str((task / "traj.jsonl").relative_to(root)),
                    "record_count": 3, "command_record_count": 2, "unknown_reason_counts": {"known": 1},
                    "supported_static_call_count": 1, "native_representation_status": "applicable", "native_action_record_count": 2,
                    "native_unknown_action_count": 2, "native_action_category_counts": {"unknown": 2}, "native_sequence": {"transition_counts": {}},
                    "results": {"result_txt": {"status": "present"}}, "done_counts": {}, "reward": {}, "task_label": ["fixture"]}
        old.mkdir()
        (old / "per_trajectory.jsonl").write_text(json.dumps(baseline) + "\n")
        (old / "summary.json").write_text(json.dumps({"inputs": {"trajectory_count": 1}}))
        manifest = {"inputs": [runner.hash_record(inventory), *[runner.hash_record(p) for p in task.iterdir()]],
                    "analysis_code": [], "outputs": [{**runner.hash_record(p), "path": p.name} for p in old.iterdir()]}
        (old / "manifest.json").write_text(json.dumps(manifest))
        return root, old, task, baseline

    def test_complete_entry_provenance_counts_native_separation_and_no_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, old, _, _ = self.fixture(Path(tmp))
            frozen = {p: p.read_bytes() for p in [*root.rglob("*.jsonl"), *old.iterdir()]}
            output = Path(tmp) / "v4"
            summary = runner.run(root, old, output, plots=False)
            row = json.loads((output / "per_trajectory.jsonl").read_text())
            self.assertEqual(row["supported_static_call_count"], 3)
            self.assertEqual(row["command_status_counts"], {"partial": 1, "known": 1})
            self.assertEqual(row["native_v3"]["native_unknown_action_count"], 2)
            self.assertEqual(row["static_sequence"]["transition_counts"], {"text_or_key->scroll": 1})
            self.assertEqual(row["saved_protocol"]["batch_id_groups"]["duplicate_batch_index_records"], 1)
            self.assertEqual(len((output / "command_records.jsonl").read_text().splitlines()), 2)
            self.assertEqual(summary["trajectory_count"], 1)
            for path, content in frozen.items():
                self.assertEqual(path.read_bytes(), content)
            with self.assertRaisesRegex(ValueError, "refusing overwrite"):
                runner.run(root, old, output, plots=False)

    def test_frozen_input_mismatch_rejected_before_new_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, old, task, _ = self.fixture(Path(tmp))
            (task / "traj.jsonl").write_text("{}\n")
            output = Path(tmp) / "v4"
            with self.assertRaisesRegex(ValueError, "frozen evidence mismatch"):
                runner.run(root, old, output, plots=False)
            self.assertFalse(output.exists())

    def test_invalid_json_breaks_actual_saved_sequence(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, old, task, baseline = self.fixture(Path(tmp))
            baseline.update(record_count=2, command_record_count=2)
            (task / "traj.jsonl").write_text(json.dumps({"action": "pyautogui.click(1,2)"}) + "\nmalformed\n" + json.dumps({"action": "pyautogui.scroll(1)"}) + "\n")
            row = runner.analyze_trajectory(task / "traj.jsonl", root, baseline, io.StringIO())
            self.assertEqual(row["invalid_json_lines"], 1)
            self.assertEqual(row["static_sequence"]["transition_counts"], {})


if __name__ == "__main__":
    unittest.main()
