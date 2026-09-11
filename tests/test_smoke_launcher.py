"""SMOKE-01 launcher tests: synthetic configs and fake keys ONLY.

Never reads the real user config, never contacts any network. The child-spawn
path is tested with a stub executable, not the real smoke subprocess.
"""

import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from agent_workload_characterization.runners import smoke_launcher as L
import test_skeleton as skeleton


FAKE_KEY = "sk-SYNTHLAUNCH-001"


def synth_opencode(provider_name="火山AI网关", model_key="deepseek-v4-flash",
                   base="https://fake-gw.example/v1", key=FAKE_KEY,
                   display="DeepSeek-V4-Flash", extra_providers=None):
    providers = {
        provider_name: {
            "name": provider_name,
            "npm": "@ai-sdk/openai-compatible",
            "options": {"baseURL": base, "apiKey": key},
            "models": {model_key: {"name": display, "maxInputTokens": 256000,
                                    "maxOutputTokens": 8192}},
        }
    }
    if extra_providers:
        providers.update(extra_providers)
    return {"$schema": "x", "provider": providers}


def write_cfg(base_dir: Path, cfg, jsonc=False):
    p = base_dir / "opencode.json"
    text = json.dumps(cfg, ensure_ascii=False, indent=2)
    if jsonc:
        text = "// user config\n" + text + "\n/* trailing */\n"
    p.write_text(text, encoding="utf-8")
    return p


class LoadCredentialsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="launcher-t-")
        self.addCleanup(self.tmp.cleanup)
        self.dir = Path(self.tmp.name)

    def test_valid_json(self):
        p = write_cfg(self.dir, synth_opencode())
        base, key = L.load_credentials(p)
        self.assertEqual(base, "https://fake-gw.example/v1")
        self.assertEqual(key, FAKE_KEY)

    def test_valid_jsonc_comments_outside_strings(self):
        p = write_cfg(self.dir, synth_opencode(), jsonc=True)
        base, key = L.load_credentials(p)
        self.assertEqual(base, "https://fake-gw.example/v1")
        # comment stripper must not alter values
        self.assertEqual(key, FAKE_KEY)

    def test_url_with_slash_in_value_survives_jsonc(self):
        # a URL-looking string containing // must NOT be treated as a comment
        cfg = synth_opencode(base="https://fake-gw.example/v1//x")
        p = write_cfg(self.dir, cfg, jsonc=True)
        base, _ = L.load_credentials(p)
        self.assertEqual(base, "https://fake-gw.example/v1//x")

    def test_missing_provider(self):
        p = write_cfg(self.dir, {"provider": {}})
        with self.assertRaises(L.LauncherError) as cm:
            L.load_credentials(p)
        self.assertEqual(str(cm.exception), "E_PROVIDER_MISSING")

    def test_missing_model(self):
        cfg = synth_opencode()
        del cfg["provider"]["火山AI网关"]["models"]["deepseek-v4-flash"]
        p = write_cfg(self.dir, cfg)
        with self.assertRaises(L.LauncherError) as cm:
            L.load_credentials(p)
        self.assertEqual(str(cm.exception), "E_MODEL_MISSING")

    def test_missing_credentials(self):
        cfg = synth_opencode()
        cfg["provider"]["火山AI网关"]["options"] = {}
        p = write_cfg(self.dir, cfg)
        with self.assertRaises(L.LauncherError) as cm:
            L.load_credentials(p)
        self.assertEqual(str(cm.exception), "E_CREDENTIALS_MISSING")

    def test_reference_credential_rejected(self):
        # unsupported reference formats (always rejected)
        for ref in ("${ENV:KEY}", "env:VOLC_KEY", "{secret:KEY}", "{op:KEY}"):
            with self.subTest(ref=ref[:12]):
                cfg = synth_opencode(key=ref)
                p = write_cfg(self.dir, cfg)
                with self.assertRaises(L.LauncherError) as cm:
                    L.load_credentials(p)
                self.assertEqual(str(cm.exception), "E_CREDENTIAL_REFERENCE_UNSUPPORTED")

    def test_env_reference_unresolvable_reports_empty(self):
        # {env:...} formats are RESOLVABLE — unset var reports E_ENV_VAR_EMPTY
        import os
        for ref in ("{env:VOLC_KEY}", "{ENV:VOLC_KEY}"):
            with self.subTest(ref=ref):
                os.environ.pop(ref.split(":")[1].rstrip("}"), None)
                cfg = synth_opencode(key=ref)
                p = write_cfg(self.dir, cfg)
                with self.assertRaises(L.LauncherError) as cm:
                    L.load_credentials(p)
                self.assertEqual(str(cm.exception), "E_ENV_VAR_EMPTY")

    def test_env_reference_resolved_from_environ(self):
        import os
        cfg = synth_opencode(key="{env:TEST_VOLC_KEY}")
        p = write_cfg(self.dir, cfg)
        os.environ["TEST_VOLC_KEY"] = "sk-RESOLVED-XYZ"
        try:
            base, key = L.load_credentials(p)
            self.assertEqual(key, "sk-RESOLVED-XYZ")
        finally:
            os.environ.pop("TEST_VOLC_KEY", None)

    def test_env_reference_empty_var_rejected(self):
        import os
        cfg = synth_opencode(key="{env:TEST_EMPTY_KEY}")
        p = write_cfg(self.dir, cfg)
        os.environ.pop("TEST_EMPTY_KEY", None)
        with self.assertRaises(L.LauncherError) as cm:
            L.load_credentials(p)
        self.assertEqual(str(cm.exception), "E_ENV_VAR_EMPTY")

    def test_env_reference_case_insensitive(self):
        import os
        cfg = synth_opencode(key="{ENV:TEST_VOLC_KEY}")
        p = write_cfg(self.dir, cfg)
        os.environ["TEST_VOLC_KEY"] = "sk-OK"
        try:
            base, key = L.load_credentials(p)
            self.assertEqual(key, "sk-OK")
        finally:
            os.environ.pop("TEST_VOLC_KEY", None)

    def test_http_base_rejected(self):
        cfg = synth_opencode(base="http://insecure.example/v1")
        p = write_cfg(self.dir, cfg)
        with self.assertRaises(L.LauncherError) as cm:
            L.load_credentials(p)
        self.assertEqual(str(cm.exception), "E_BASE_NOT_HTTPS")

    def test_userinfo_base_rejected(self):
        cfg = synth_opencode(base="https://user:pass@gw.example/v1")
        p = write_cfg(self.dir, cfg)
        with self.assertRaises(L.LauncherError) as cm:
            L.load_credentials(p)
        self.assertEqual(str(cm.exception), "E_BASE_USERINFO_REJECTED")

    def test_non_absolute_base_rejected(self):
        cfg = synth_opencode(base="fake-gw.example/v1")
        p = write_cfg(self.dir, cfg)
        with self.assertRaises(L.LauncherError) as cm:
            L.load_credentials(p)
        self.assertEqual(str(cm.exception), "E_BASE_NOT_ABSOLUTE_URL")

    def test_display_name_mismatch_rejected(self):
        cfg = synth_opencode(display="DeepSeek-V4-Pro")
        p = write_cfg(self.dir, cfg)
        with self.assertRaises(L.LauncherError) as cm:
            L.load_credentials(p)
        self.assertEqual(str(cm.exception), "E_MODEL_ENTRY_MISMATCH")

    def test_malformed_json(self):
        p = self.dir / "opencode.json"
        p.write_text("{not json", encoding="utf-8")
        with self.assertRaises(L.LauncherError) as cm:
            L.load_credentials(p)
        self.assertEqual(str(cm.exception), "E_CONFIG_MALFORMED")

    def test_unreadable_config(self):
        with self.assertRaises(L.LauncherError) as cm:
            L.load_credentials(self.dir / "nope.json")
        self.assertEqual(str(cm.exception), "E_CONFIG_UNREADABLE")

    def test_other_providers_ignored(self):
        cfg = synth_opencode(extra_providers={
            "other": {"name": "other", "npm": "x",
                      "options": {"baseURL": "https://o.example/v1", "apiKey": "k"},
                      "models": {"deepseek-v4-flash": {"name": "DeepSeek-V4-Flash"}}}})
        p = write_cfg(self.dir, cfg)
        base, key = L.load_credentials(p)
        self.assertEqual(base, "https://fake-gw.example/v1")


class RestrictedEnvTests(unittest.TestCase):
    def test_no_proxy_inheritance_and_pins(self):
        import os
        os.environ["https_proxy"] = "http://127.0.0.1:22111"  # simulate leak
        try:
            env = L.build_restricted_env("https://b/v1", "k")
        finally:
            os.environ.pop("https_proxy", None)
        for var in ("http_proxy", "https_proxy", "HTTP_PROXY", "HTTPS_PROXY",
                    "ALL_PROXY", "all_proxy"):
            self.assertNotIn(var, env)
        self.assertEqual(env["LITELLM_LOCAL_MODEL_COST_MAP"], "True")
        self.assertEqual(env["MSWEA_MODEL_RETRY_STOP_AFTER_ATTEMPT"], "1")
        self.assertEqual(env["PILOT_API_BASE"], "https://b/v1")
        self.assertEqual(env["PILOT_API_KEY"], "k")
        self.assertIn("src", env["PYTHONPATH"])
        # minimal env: no unrelated cloud credentials leak by default
        self.assertNotIn("OPENAI_API_KEY", env)
        self.assertNotIn("ANTHROPIC_API_KEY", env)

    def test_approved_explicit_proxy_set_when_env_var_present(self):
        import os
        os.environ["SMOKE_APPROVED_PROXY"] = "http://127.0.0.1:22111"
        try:
            env = L.build_restricted_env("https://b/v1", "k")
        finally:
            os.environ.pop("SMOKE_APPROVED_PROXY", None)
        self.assertEqual(env.get("https_proxy"), "http://127.0.0.1:22111")
        self.assertEqual(env.get("HTTPS_PROXY"), "http://127.0.0.1:22111")
        # still no other proxy vars
        self.assertNotIn("http_proxy", env)
        self.assertNotIn("ALL_PROXY", env)

    def test_no_proxy_when_approval_var_absent(self):
        import os
        os.environ.pop("SMOKE_APPROVED_PROXY", None)
        os.environ["HTTP_PROXY"] = "http://leak.example:1"  # must NOT inherit
        try:
            env = L.build_restricted_env("https://b/v1", "k")
        finally:
            os.environ.pop("HTTP_PROXY", None)
        self.assertNotIn("HTTP_PROXY", env)
        self.assertNotIn("https_proxy", env)


class ExtractLastJsonTests(unittest.TestCase):
    """_extract_last_json_object: banners before, pretty/multi-line records,
    trailing text — all must parse; garbage must return None."""

    def test_banner_then_single_line(self):
        out = "litellm banner\nanother line\n{\"ok\": true}\n"
        self.assertEqual(L._extract_last_json_object(out), {"ok": True})

    def test_banner_then_pretty_multiline(self):
        record = json.dumps({"ok": False, "usage": {"total_tokens": 5}}, indent=2)
        out = "banner\n" + record + "\n"
        self.assertEqual(L._extract_last_json_object(out),
                         {"ok": False, "usage": {"total_tokens": 5}})

    def test_trailing_text_after_record(self):
        out = "banner\n{\"ok\": true, \"n\": 1}\ntrailing warning\n"
        self.assertEqual(L._extract_last_json_object(out), {"ok": True, "n": 1})

    def test_only_record(self):
        self.assertEqual(L._extract_last_json_object('{"a": 1}\n'), {"a": 1})

    def test_empty_and_garbage(self):
        self.assertIsNone(L._extract_last_json_object(""))
        self.assertIsNone(L._extract_last_json_object("no json at all"))
        self.assertIsNone(L._extract_last_json_object("[1,2]"))

    def test_last_object_wins(self):
        out = '{"first": 1}\nbanner\n{"second": 2}\n'
        self.assertEqual(L._extract_last_json_object(out), {"second": 2})


class SpawnTests(unittest.TestCase):
    """Child spawn is tested with a STUB interpreter script — the real venv
    python is never invoked and no network happens."""

    def _stub(self, base_dir: Path, stdout_json, rc=0):
        stub = base_dir / "stubpython"
        payload = json.dumps(stdout_json) if stdout_json is not None else ""
        stub.write_text(
            "#!/bin/sh\n"
            f"printf '%s\\n' '{payload}'\n"
            f"exit {rc}\n")
        stub.chmod(0o755)
        return stub

    def test_launch_returns_record(self):
        with tempfile.TemporaryDirectory(prefix="launcher-s-") as tmp:
            d = Path(tmp)
            stub = self._stub(d, {"ok": True, "usage": {"total_tokens": 5}})
            orig = L.VENV_PY
            L.VENV_PY = stub
            try:
                rc, rec = L.launch_smoke(Path("cfg.yaml"), d / "out",
                                          "https://b/v1", "k")
            finally:
                L.VENV_PY = orig
            self.assertEqual(rc, 0)
            self.assertTrue(rec["ok"])

    def test_launch_no_record(self):
        with tempfile.TemporaryDirectory(prefix="launcher-s2-") as tmp:
            d = Path(tmp)
            stub = self._stub(d, None)
            stub.write_text("#!/bin/sh\nexit 1\n")
            orig = L.VENV_PY
            L.VENV_PY = stub
            try:
                rc, rec = L.launch_smoke(Path("cfg.yaml"), d / "out",
                                          "https://b/v1", "k")
            finally:
                L.VENV_PY = orig
            self.assertEqual(rc, 1)
            self.assertIsNone(rec)


if __name__ == "__main__":
    unittest.main()
