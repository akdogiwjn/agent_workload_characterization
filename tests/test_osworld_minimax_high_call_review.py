import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
try:
    SPEC = importlib.util.spec_from_file_location("high_call_review", SCRIPTS / "osworld_minimax_high_call_review.py")
    MOD = importlib.util.module_from_spec(SPEC)
    SPEC.loader.exec_module(MOD)
finally:
    sys.path.pop(0)


class HighCallReviewTest(unittest.TestCase):
    def test_structure_does_not_export_arguments(self):
        result = MOD.record_structure("pyautogui.press('private'); pyautogui.press('private'); pyautogui.click(1, 2)")
        self.assertEqual(result["ast_call_count"], 3)
        self.assertEqual(result["distinct_statement_ast_count"], 2)
        self.assertEqual(result["max_consecutive_identical_statements"], 2)
        self.assertNotIn("private", json.dumps(result))

    def test_ranking_is_by_jsonl_line_not_task_total(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            paths = []
            for task, counts in (("001", [3, 3, 3]), ("002", [5])):
                path = root / task / "traj.jsonl"
                path.parent.mkdir()
                path.write_text("\n".join(json.dumps({"step_num": i, "action": "pyautogui.click();" * n}) for i, n in enumerate(counts)))
                paths.append(path)
            result = MOD.scan_records(paths, root)
            self.assertEqual(result["parsed_source_ast_call_total"], 14)
            self.assertEqual([(r["task_key"], r["jsonl_line"]) for r in result["top_jsonl_records"]], [("002", 1), ("001", 1), ("001", 2)])
            self.assertEqual(result["top3_jsonl_share"], 11 / 14)
