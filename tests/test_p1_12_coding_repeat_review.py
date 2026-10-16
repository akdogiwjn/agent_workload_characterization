import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts.p1_12_coding_repeat_review import analyze, median_iqr


class CodingRepeatReviewTests(unittest.TestCase):
    def test_linear_iqr_and_missing_are_not_zero(self):
        self.assertEqual(median_iqr([])["median"], None)
        self.assertEqual(median_iqr([1, 2, 3, 4])["iqr"], 1.5)

    def test_refuses_existing_output(self):
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "out"
            out.mkdir()
            with self.assertRaises(FileExistsError):
                analyze(out=out)

    def test_rejects_hash_mismatch_before_output(self):
        # Patch only the registered batch manifest read; no production files
        # or formal report directory are written by this test.
        import scripts.p1_12_coding_repeat_review as mod
        real = mod._json
        def altered(path):
            value = real(path)
            if str(path).endswith("batch/manifest.json"):
                value = json.loads(json.dumps(value))
                value["outputs"]["summary.json"]["sha256"] = "0" * 64
            return value
        with tempfile.TemporaryDirectory() as td:
            with patch.object(mod, "_json", side_effect=altered):
                with self.assertRaises(ValueError):
                    analyze(out=Path(td) / "out")


if __name__ == "__main__":
    unittest.main()
