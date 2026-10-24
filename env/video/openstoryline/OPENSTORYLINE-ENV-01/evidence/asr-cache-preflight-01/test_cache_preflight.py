import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

SOURCE = Path(__file__).parents[2] / "source/asr_adapter/cache_preflight.py"
spec = importlib.util.spec_from_file_location("cache_preflight", SOURCE)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class CachePreflightTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / "models"
        self.contract = Path(self.tmp.name) / "contract.json"
        self.spec = {
            "container_model_root": str(self.root),
            "model_dirs": {"asr": "asr", "vad": "vad", "punc": "punc"},
            "required_files": {"asr": ["configuration.json", "model.pt", "tokens.json", "bpe.model", "am.mvn"],
                               "vad": ["configuration.json", "model.pt", "am.mvn"],
                               "punc": ["configuration.json", "model.pt", "tokens.json"]},
        }
        self.contract.write_text(json.dumps(self.spec))
        for model, files in self.spec["required_files"].items():
            directory = self.root / model
            directory.mkdir(parents=True)
            for filename in files:
                (directory / filename).write_bytes(b"present")

    def test_complete_cache_is_readable(self):
        records = module.validate_asr_cache(model_root=self.root, contract_path=self.contract)
        self.assertEqual(len(records), sum(map(len, self.spec["required_files"].values())))
        self.assertTrue(all(item["readable"] for item in records))

    def test_missing_mount_fails_before_model_import(self):
        with self.assertRaisesRegex(RuntimeError, "before model initialization"):
            module.validate_asr_cache(model_root=Path(self.tmp.name) / "missing", contract_path=self.contract)

    def test_wrong_path_fails_with_exact_missing_asset(self):
        (self.root / "asr" / "configuration.json").unlink()
        with self.assertRaisesRegex(RuntimeError, "asr/configuration.json"):
            module.validate_asr_cache(model_root=self.root, contract_path=self.contract)


if __name__ == "__main__":
    unittest.main()
