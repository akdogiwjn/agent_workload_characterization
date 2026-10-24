import importlib.util
import unittest
from pathlib import Path

SOURCE = Path(__file__).parents[2] / "source/src/open_storyline/utils/prompts.py"
spec = importlib.util.spec_from_file_location("openstoryline_prompts", SOURCE)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class PromptPathTests(unittest.TestCase):
    def test_prompt_bundle_resolves_from_installed_source(self):
        expected = Path(__file__).parents[2] / "source/prompts/tasks"
        self.assertEqual(module.PROMPTS_DIR, expected.resolve())
        text = module.get_prompt("speech_rough_cut.system", lang="zh")
        self.assertIn("视频剪辑助手", text)


if __name__ == "__main__":
    unittest.main()
