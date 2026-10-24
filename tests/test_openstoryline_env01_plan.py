import json
import tomllib
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ENV = ROOT / "env/video/openstoryline/OPENSTORYLINE-ENV-01"


class OpenStorylineEnv01PlanTests(unittest.TestCase):
    def test_route_and_retry_policy_are_explicit(self):
        cfg = tomllib.loads((ENV / "source/config.toml").read_text())
        self.assertEqual(cfg["llm"]["model"], "qwen3.7-plus")
        self.assertEqual(cfg["vlm"]["model"], "qwen3.7-plus")
        self.assertEqual(cfg["llm"]["base_url"], "https://dashscope.aliyuncs.com/compatible-mode/v1")
        self.assertEqual(cfg["vlm"]["base_url"], cfg["llm"]["base_url"])
        self.assertEqual(cfg["llm"]["max_retries"], 0)
        self.assertEqual(cfg["vlm"]["max_retries"], 0)
        self.assertEqual(cfg["local_mcp_server"]["server_transport"], "streamable-http")

    def test_task_scope_uses_native_nodes_and_keeps_effect_nodes_out(self):
        cfg = tomllib.loads((ENV / "source/config.toml").read_text())
        nodes = set(cfg["local_mcp_server"]["available_nodes"])
        self.assertTrue({"LoadMediaNode", "SplitShotsNode", "LocalASRNode",
                         "SpeechRoughCutNode", "PlanTimelineProNode", "RenderVideoNode"} <= nodes)
        self.assertFalse({"GenerateVoiceoverNode", "SelectBGMNode", "GenerateAITransitionNode",
                          "SearchMediaNode"} & nodes)
        reg = (ENV / "source/src/open_storyline/mcp/register_tools.py").read_text()
        self.assertIn("plan_timeline_pro.PlanTimelineProNode.meta.default_require_prior_kind", reg)
        self.assertNotIn("NODE_REGISTRY.scan_package(pkg)", reg)

    def test_skill_uses_zero_gap_and_explicit_no_effects_policy(self):
        skill = (ENV / "source/.storyline/skills/speech_rough_cut_skill/SKILL.md").read_text()
        for required in ("gap_threshold=0", "include_video_audio=true", "is_speech_rough_cut=true",
                         "Do not add titles", "cuts.json", "audio meaning"):
            self.assertIn(required, skill)

    def test_one_shot_entry_keeps_native_agent_and_scrubs_mcp_env(self):
        entry = (ENV / "source/openstoryline_task_entry.py").read_text()
        self.assertIn("from open_storyline.agent import ClientContext, build_agent", entry)
        self.assertIn("agent.ainvoke(", entry)
        self.assertIn("server_env.pop(API_KEY_ENV, None)", entry)
        self.assertIn('"max_retries": 0', entry)
        self.assertNotIn("input(", entry)

    def test_status_does_not_claim_built_or_ready(self):
        status = json.loads((ENV / "preparation-status.json").read_text())
        self.assertEqual(status["image_build"], "cancelled_before_completion")
        self.assertIsNone(status["image_id"])
        self.assertFalse(status["formal_execution_ready"])
        self.assertEqual(status["bailian_logical_calls"], 0)


if __name__ == "__main__":
    unittest.main()
