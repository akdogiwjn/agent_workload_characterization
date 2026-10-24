"""VIDEO-USE-CODEX-BAILIAN-INTEGRATION-01 offline tests (no network, no real
credential, no docker)."""
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
sys.path.insert(0, str(ROOT / 'src'))

import video_use_codex_bailian_integration_01 as v  # noqa: E402

INTEGRATION = ROOT / 'env/video/video-use/codex-bailian-integration-01'


class ConfigTests(unittest.TestCase):
    def test_config_explicit_no_fallback(self):
        import tomllib
        cfg = tomllib.loads((INTEGRATION / 'config.toml').read_text())
        self.assertEqual(cfg['model'], 'qwen3.7-plus')
        self.assertEqual(cfg['model_provider'], 'bailian')
        p = cfg['model_providers']['bailian']
        self.assertEqual(p['base_url'],
                         'https://dashscope.aliyuncs.com/compatible-mode/v1')
        self.assertEqual(p['env_key'], 'DASHSCOPE_API_KEY')
        self.assertEqual(p['wire_api'], 'responses')
        self.assertEqual(p['request_max_retries'], 0)
        self.assertEqual(p['stream_max_retries'], 0)
        # no default provider fallback, no ephemeral
        self.assertNotIn('fallback', json.dumps(cfg))
        self.assertNotIn('ephemeral', json.dumps(cfg))
        # no credential VALUE anywhere in config or Dockerfile
        for f in ('config.toml', 'Dockerfile'):
            text = (INTEGRATION / f).read_text()
            self.assertNotIn('sk-', text)

    def test_dockerfile_shape(self):
        text = (INTEGRATION / 'Dockerfile').read_text()
        self.assertIn('FROM video-use-task:arm64-v1', text)
        self.assertNotIn('FROM video-common-base', text)  # derives from task image
        self.assertNotIn('DASHSCOPE_API_KEY=', text.replace('env_key', ''))
        self.assertIn('CODEX_HOME=/opt/codex-home', text)
        self.assertIn('codex --version', text)  # build-time version check

    def test_command_construction(self):
        cmd = v.build_codex_command()
        self.assertIn('codex exec', cmd)
        self.assertIn('--json', cmd)
        self.assertIn('--skip-git-repo-check', cmd)
        self.assertIn('-o /task/final_message.txt', cmd)
        self.assertIn('--model qwen3.7-plus', cmd)
        self.assertNotIn('--ephemeral', cmd)
        self.assertNotIn('--model openai/', cmd)
        # instruction contains no local answers (counts/positions)
        for banned in ('red_circles', 'blue_squares'):
            self.assertNotIn(banned, v.INSTRUCTION)


class CredentialTests(unittest.TestCase):
    def test_load_from_fake_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            cred = Path(tmp) / 'bailian.env'
            cred.write_text("# comment\nexport DASHSCOPE_API_KEY=fake-value-123\n")
            with patch.object(v, 'CREDENTIAL_FILE', cred):
                self.assertEqual(v.load_credential(), 'fake-value-123')
            cred.write_text("OTHER=x\n")
            with patch.object(v, 'CREDENTIAL_FILE', cred):
                with self.assertRaises(SystemExit):
                    v.load_credential()


class RolloutParsingTests(unittest.TestCase):
    def _rollout(self, lines):
        tmp = tempfile.mkdtemp()
        self.addCleanup(lambda: __import__('shutil').rmtree(tmp, ignore_errors=True))
        p = Path(tmp) / 'rollout-2026-10-21T00-00-00-abc.jsonl'
        p.write_text("\n".join(json.dumps(x) for x in lines) + "\n")
        return p, v.parse_rollout(p)

    def test_parse_tool_calls_commands_messages(self):
        lines = [
            {"type": "session_meta", "payload": {"session_id": "s1",
                                                 "cli_version": "0.163.0"}},
            {"type": "event_msg", "payload": {"type": "exec_command_begin",
                                              "command": "python3 /task/probe_input.py"}},
            {"type": "response_item", "payload": {
                "type": "function_call", "name": "view_image",
                "arguments": json.dumps({"path": "/task/input/neutral-test.png"})}},
            {"type": "response_item", "payload": {
                "type": "message", "role": "assistant",
                "content": [{"type": "output_text", "text": "RECEIPT: abc"}]}},
            {"type": "event_msg", "payload": {"type": "token_count",
                                              "info": {"total_token_usage": {}}}},
        ]
        path, rollout = self._rollout(lines)
        self.assertTrue(rollout["exists"])
        self.assertEqual(rollout["session_meta"]["session_id"], "s1")
        self.assertEqual(len(rollout["commands"]), 1)
        self.assertIn("probe_input.py", rollout["commands"][0]["command"])
        self.assertEqual(rollout["tool_calls"][0]["name"], "view_image")
        self.assertEqual(rollout["tool_calls"][0]["arguments"]["path"],
                         "/task/input/neutral-test.png")
        self.assertEqual(len(rollout["messages"]), 1)
        self.assertEqual(len(rollout["token_counts"]), 1)
        self.assertEqual(v.find_rollout(path.parent), path)

    def test_missing_rollout(self):
        self.assertIsNone(v.find_rollout(Path('/nonexistent')))


class VerdictTests(unittest.TestCase):
    TRUTH = {"red_circles": 2, "blue_squares": 1, "red_side": "left"}

    def _rollout_dict(self, *, probe=True, view=True):
        commands = ([{"tool": "exec_command",
                      "cmd": "python3 /task/probe_input.py", "workdir": "/task"}]
                    if probe else [])
        tool_calls = ([{"name": "view_image",
                        "arguments": {"path": "/task/input/neutral-test.png"}}]
                      if view else [])
        return {"exists": True, "commands": commands, "tool_calls": tool_calls,
                "messages": [], "token_counts": []}

    def test_parse_rollout_0163_exec_command_shape(self):
        # regression: 0.163 rollouts record command execution as
        # function_call name=exec_command (not event_msg exec_command_begin)
        lines = [
            {"type": "response_item", "payload": {
                "type": "function_call", "name": "exec_command",
                "arguments": json.dumps(
                    {"cmd": "python3 /task/probe_input.py", "workdir": "/task"})}},
            {"type": "response_item", "payload": {
                "type": "function_call", "name": "view_image",
                "arguments": json.dumps(
                    {"path": "/task/input/neutral-test.png"})}},
            {"type": "token_usage_record", "payload": {"usage": {"input_tokens": 5}}},
        ]
        tmp = tempfile.mkdtemp()
        self.addCleanup(lambda: __import__('shutil').rmtree(tmp, ignore_errors=True))
        p = Path(tmp) / 'rollout-x.jsonl'
        p.write_text("\n".join(json.dumps(x) for x in lines) + "\n")
        rollout = v.parse_rollout(p)
        self.assertEqual(len(rollout["commands"]), 1)
        self.assertIn("probe_input.py", rollout["commands"][0]["cmd"])
        self.assertEqual(rollout["tool_calls"][1]["name"], "view_image")
        self.assertEqual(len(rollout["token_counts"]), 1)

    def test_describe_check_side_prefix_structure(self):
        # regression: the REAL final answer used "Left side: 1 red circle /
        # Right side: 3 blue squares" — the side label owns its color
        truth = {"red_circles": 1, "blue_squares": 3, "red_side": "left"}
        check = v.describe_check(
            "**(b) Image description:**\n\n- **Left side:** 1 red circle\n"
            "- **Right side:** 3 blue squares", truth)
        self.assertTrue(check["all_correct"], check)
        flipped = v.describe_check(
            "- **Left side:** 1 blue square\n- **Right side:** 3 red circles",
            truth)
        self.assertFalse(flipped["all_correct"])

    def test_tool_execution_pass(self):
        r = v.tool_execution_evidence(
            self._rollout_dict(), "abc123", "The receipt is abc123.")
        self.assertEqual(r["verdict"], "PASS")

    def test_tool_execution_fails_without_evidence(self):
        # no exec event -> FAIL even if the receipt is echoed in the answer
        r = v.tool_execution_evidence(
            self._rollout_dict(probe=False), "abc123", "receipt abc123")
        self.assertEqual(r["verdict"], "FAIL")
        # no receipt file -> FAIL
        r2 = v.tool_execution_evidence(self._rollout_dict(), None, "abc123")
        self.assertEqual(r2["verdict"], "FAIL")

    def test_image_viewing_requires_view_image_call(self):
        desc = "左侧有2个红色圆形,右侧有1个蓝色方形,红色圆形在左侧。"
        with_view = v.image_viewing_evidence(
            self._rollout_dict(), desc, self.TRUTH)
        self.assertEqual(with_view["verdict"], "PASS")
        without_view = v.image_viewing_evidence(
            self._rollout_dict(view=False), desc, self.TRUTH)
        self.assertEqual(without_view["verdict"], "FAIL")

    def test_image_viewing_requires_correct_description(self):
        wrong = v.image_viewing_evidence(
            self._rollout_dict(), "左侧有5个红色圆形,右侧有1个蓝色方形,红色在左。",
            self.TRUTH)
        self.assertEqual(wrong["verdict"], "FAIL")

    def test_describe_check_english(self):
        text = ("The image shows 2 red circles on the left and 1 blue "
                "square on the right. Red circles are on the left side.")
        check = v.describe_check(text, self.TRUTH)
        self.assertTrue(check["all_correct"], check)

    def test_describe_check_extra_words_ok_unparseable_not_correct(self):
        check = v.describe_check(
            "Sure! 左侧有2个红色圆形,右侧有1个蓝色方形,红色圆形在左侧。希望有帮助!",
            self.TRUTH)
        self.assertTrue(check["all_correct"])
        vague = v.describe_check("There are some shapes in the image.", self.TRUTH)
        self.assertFalse(vague["all_correct"])

    def test_dangerous_command_audit(self):
        clean = v.dangerous_command_audit(self._rollout_dict())
        self.assertTrue(clean["clean"])
        bad = v.dangerous_command_audit({
            "commands": [{"command": "sudo rm -rf /etc"}]})
        self.assertFalse(bad["clean"])


class ImageNeutralityTests(unittest.TestCase):
    def test_generated_image_and_answers_kept_apart(self):
        # expected-answer.json (if a previous run exists) must stay OUTSIDE
        # the session dir that is copied into the container
        self.assertEqual((ROOT / 'env/video/video-use/codex-bailian-integration-01'
                          / 'expected-answer.json').parent.name,
                         'codex-bailian-integration-01')
        self.assertNotEqual(
            (ROOT / 'env/video/video-use/codex-bailian-integration-01'
             / 'expected-answer.json').parent.name, 'session-01')


if __name__ == "__main__":
    unittest.main()
