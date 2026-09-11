"""ENV-01 offline integration tests — run with the ENV-01 venv interpreter.

Separate from the default project unittest: imports the installed
mini/litellm; requires .venvs/mini-swe-agent-2.4.6-env01/bin/python.

    PYTHONPATH=src .venvs/mini-swe-agent-2.4.6-env01/bin/python \
        -m unittest tests.integration_env01 -v

Network is blocked at the httpx transport layer (fake transport); proxy env
vars are unset by this module.

CORRECTION (round 2 review): an earlier conclusion "litellm ignores
api_base/api_key inside model_kwargs" was WRONG — it was an artifact of the
old test passing model_kwargs as a NESTED kwarg to litellm.completion
directly. mini's LitellmModel expands model_kwargs into TOP-LEVEL
completion kwargs, where api_base/api_key DO work (verified: R8-style
mini + fake transport). The adapter still routes credentials via
OPENAI_API_BASE/OPENAI_API_KEY env vars — NOT because model_kwargs is
ineffective, but because mini serializes model_kwargs verbatim into
trajectory info.config (at-rest leak prevention; see S3 tests below).
"""

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

for v in ("http_proxy", "https_proxy", "HTTP_PROXY", "HTTPS_PROXY"):
    os.environ.pop(v, None)
os.environ["MSWEA_CONFIG_DIR"] = "/tmp/mswea-empty-config"
os.makedirs("/tmp/mswea-empty-config", exist_ok=True)
os.environ["LITELLM_LOCAL_MODEL_COST_MAP"] = "True"

import httpx  # noqa: E402
from agent_workload_characterization.runners import model_adapter as ma  # noqa: E402
from agent_workload_characterization.runners import smoke as smoke_mod  # noqa: E402
from agent_workload_characterization.runners.preparation import PreparationError  # noqa: E402

CANARY_KEY = "sk-SYNTHKEY-END01"
CANARY_BASE = "https://fake-end01.example/v1"

TOOL_CALL_RESP = {
    "id": "x", "object": "chat.completion", "created": 0, "model": "deepseek-v4-flash",
    "choices": [{"index": 0, "message": {"role": "assistant", "content": "",
                 "tool_calls": [{"id": "call_1", "type": "function",
                                 "function": {"name": "bash",
                                              "arguments": json.dumps({"command": "echo hi"})}}]},
                 "finish_reason": "tool_calls"}],
    "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}}


class FakeTransport(httpx.HTTPTransport):
    def __init__(self, responses=None, status=200):
        super().__init__()
        self.captured = []
        self.responses = responses or [TOOL_CALL_RESP]
        self.status = status
        self.n = 0

    def handle_request(self, request):
        self.captured.append({"url": str(request.url),
                              "auth": request.headers.get("authorization"),
                              "body": json.loads(request.content.decode())})
        resp = self.responses[min(self.n, len(self.responses) - 1)]
        self.n += 1
        return httpx.Response(self.status, json=resp)


def synth_config():
    return {
        "provider_protocol_class": "openai_compatible",
        "model": {"model_name": "openai/deepseek-v4-flash",
                  "model_kwargs": {"drop_params": True},
                  "cost_tracking": "ignore_errors",
                  "litellm_routing": "verified_this_batch"},
        "agent": {"step_limit": 250, "cost_limit": 3.0},
        "environment": {"timeout": 60, "api_base_env": "PILOT_API_BASE",
                        "auth_env": "PILOT_API_KEY",
                        "forward_env": ["PILOT_API_BASE", "PILOT_API_KEY"]},
        "run": {"env_startup_command": None}}


def fake_env():
    return {"PILOT_API_BASE": CANARY_BASE, "PILOT_API_KEY": CANARY_KEY}


def litellm_with(transport):
    """Fresh client_session per call; never close the previous one.

    Closing a prior session corrupted litellm's internally cached openai
    client in-process (observed: subsequent LitellmModel queries bypassed
    client_session entirely and hit the network). Leaving old sessions for
    GC keeps every test on its own FakeTransport.
    """
    import litellm
    litellm.client_session = httpx.Client(transport=transport)
    return litellm


class EnvCleanupTestCase(unittest.TestCase):
    """Isolation + hard network block for every test.

    The network block monkeypatches httpx.HTTPTransport.handle_request at the
    class level: any request NOT going through a FakeTransport raises
    NetworkViolation (covers import/init/query paths litellm might take with
    its own clients, per the ENV-01 handoff).
    """

    def setUp(self):
        for v in (ma.SDK_BASE_ENV, ma.SDK_KEY_ENV, "MSWEA_MODEL_RETRY_STOP_AFTER_ATTEMPT"):
            os.environ.pop(v, None)
        self._orig_handle = httpx.HTTPTransport.handle_request

        def _blocked(self, request, *_a, **_k):
            raise NetworkViolation(
                f"real network attempt blocked: {request.url!s} "
                "(tests must inject FakeTransport)")

        httpx.HTTPTransport.handle_request = _blocked
        # litellm caches OpenAI SDK clients in-memory keyed by init params
        # (llms/openai/common_utils.py BaseOpenAILLM); without clearing, a
        # later test with the same key silently reuses the FIRST test's
        # FakeTransport-backed client (root cause of cross-test leakage).
        import litellm as _litellm
        try:
            _litellm.in_memory_llm_clients_cache.cache_dict.clear()
        except Exception:
            pass
        self.addClassCleanup(self._restore)

    def _restore(self):
        httpx.HTTPTransport.handle_request = self._orig_handle


class NetworkViolation(RuntimeError):
    pass


class RoutingTests(EnvCleanupTestCase):
    def test_url_auth_model_via_real_sdk(self):
        """openai/ prefix routing through real litellm + credential scope."""
        t = FakeTransport()
        litellm = litellm_with(t)
        r = ma.resolve_model(synth_config(), env=fake_env())
        with ma.sdk_credential_scope(r):
            litellm.completion(model=r.model_name, messages=[{"role": "user", "content": "ping"}],
                               model_kwargs=dict(r.model_kwargs_public), num_retries=0)
        c = t.captured[-1]
        self.assertEqual(c["url"], CANARY_BASE + "/chat/completions")
        self.assertEqual(c["auth"], "Bearer " + CANARY_KEY)
        self.assertEqual(c["body"]["model"], "deepseek-v4-flash")

    def test_model_kwargs_credentials_DO_work_via_mini(self):
        """CORRECTION test: mini expands model_kwargs to top-level completion
        kwargs, where api_base/api_key take effect. The earlier 'ignored'
        conclusion was a test bug (nested passing). Kept as regression so the
        correction is pinned. The adapter still prefers env vars — reason:
        at-rest trajectory leak prevention (see MiniChain leak tests)."""
        from minisweagent.models.litellm_model import LitellmModel
        t = FakeTransport()
        litellm_with(t)
        m = LitellmModel(model_name="openai/deepseek-v4-flash",
                         model_kwargs={"drop_params": True, "num_retries": 0,
                                      "api_base": CANARY_BASE, "api_key": CANARY_KEY},
                         cost_tracking="ignore_errors")
        msg = m.query([{"role": "user", "content": "p"}])
        c = t.captured[-1]
        self.assertEqual(c["url"], CANARY_BASE + "/chat/completions")
        self.assertEqual(c["auth"], "Bearer " + CANARY_KEY)

    def test_credential_scope_restores_env(self):
        r = ma.resolve_model(synth_config(), env=fake_env())
        os.environ.pop(ma.SDK_BASE_ENV, None)
        os.environ.pop(ma.SDK_KEY_ENV, None)
        with ma.sdk_credential_scope(r):
            self.assertEqual(os.environ[ma.SDK_KEY_ENV], CANARY_KEY)
        self.assertNotIn(ma.SDK_BASE_ENV, os.environ)
        self.assertNotIn(ma.SDK_KEY_ENV, os.environ)


class MiniChainTests(EnvCleanupTestCase):
    def _mini(self, transport, cost_tracking="ignore_errors"):
        from minisweagent.models.litellm_model import LitellmModel
        litellm_with(transport)
        r = ma.resolve_model(synth_config(), env=fake_env())
        m = LitellmModel(cost_tracking=cost_tracking, **ma.mini_model_config(r))
        with ma.sdk_credential_scope(r):
            msg = m.query([{"role": "user", "content": "do"}])
        return msg, r, transport

    def test_mini_tools_usage_and_clean_config(self):
        t = FakeTransport()
        msg, r, _ = self._mini(t)
        tools = t.captured[-1]["body"].get("tools")
        self.assertTrue(tools and tools[0]["function"]["name"] == "bash")
        self.assertEqual(msg["extra"]["actions"][0]["command"], "echo hi")
        # mini's own serialized config now carries NO credentials
        # (credentials lived only in process env during the call)
        self.assertNotIn(CANARY_KEY, json.dumps(msg))
        self.assertNotIn(CANARY_BASE, json.dumps(msg))

    def test_mini_default_cost_tracking_raises_on_unknown_price(self):
        t = FakeTransport()
        with self.assertRaises(RuntimeError):
            self._mini(t, cost_tracking="default")

    def test_usage_recorded_despite_ignore_errors_cost(self):
        """ignore_errors keeps the response; usage must survive into the record."""
        def call():
            msg, _, _ = self._mini(FakeTransport())
            return msg
        rec = ma.record_sdk_call(call, request_id="req-u", model="openai/deepseek-v4-flash",
                                 cost_tracking="ignore_errors")
        self.assertTrue(rec.ok)
        self.assertEqual(rec.usage["total_tokens"], 15)
        self.assertEqual(rec.cost_status, "unknown")
        self.assertEqual(rec.cost, 0.0)  # source value preserved, not "accounted"


class RetryTests(EnvCleanupTestCase):
    def test_single_failure_single_request_with_retry_disabled(self):
        from minisweagent.models.litellm_model import LitellmModel
        os.environ.update(ma.retry_disabled_env())
        try:
            t = FakeTransport(status=500)
            litellm_with(t)
            r = ma.resolve_model(synth_config(), env=fake_env())
            m = LitellmModel(cost_tracking="ignore_errors", **ma.mini_model_config(r))
            with ma.sdk_credential_scope(r):
                rec = ma.record_sdk_call(
                    lambda: m.query([{"role": "user", "content": "x"}]),
                    request_id="req-1", model="openai/deepseek-v4-flash")
            self.assertFalse(rec.ok)
            self.assertEqual(t.n, 1, "retry disabled must yield exactly one request")
            self.assertEqual(rec.request_id, "req-1")
            self.assertIsNotNone(rec.error)
            self.assertNotIn(CANARY_KEY, rec.error or "")
        finally:
            os.environ.pop("MSWEA_MODEL_RETRY_STOP_AFTER_ATTEMPT", None)


class RecordTests(EnvCleanupTestCase):
    def test_error_sanitized_through_real_sdk_exception(self):
        """Real SDK 401 body (echoing the canary base) sanitized in record."""
        litellm = litellm_with(FakeTransport(status=401,
                                   responses=[{"error": {"message": "bad key " + CANARY_KEY}}]))
        r = ma.resolve_model(synth_config(), env=fake_env())

        def call():
            with ma.sdk_credential_scope(r):
                return litellm.completion(model=r.model_name,
                                          messages=[{"role": "user", "content": "p"}],
                                          model_kwargs=dict(r.model_kwargs_public), num_retries=0)
        rec = ma.record_sdk_call(call, request_id="req-e")
        self.assertFalse(rec.ok)
        self.assertNotIn(CANARY_KEY, rec.error or "")
        self.assertNotIn("fake-end01", rec.error or "")

    def test_missing_env_rejected(self):
        with self.assertRaises(PreparationError):
            ma.resolve_model(synth_config(), env={})

    def test_userinfo_base_rejected(self):
        env = {"PILOT_API_BASE": "https://u:p@fake.example/v1", "PILOT_API_KEY": "k"}
        with self.assertRaises(PreparationError):
            ma.resolve_model(synth_config(), env=env)

    def test_credentials_in_model_kwargs_rejected(self):
        cfg = synth_config()
        cfg["model"]["model_kwargs"]["api_key"] = CANARY_KEY
        with self.assertRaises(PreparationError):
            ma.resolve_model(cfg, env=fake_env())




# ---------------- S1: smoke execute path (REAL SDK + fake transport) ----------------

PLAIN_TEXT_RESP = {
    "id": "x", "object": "chat.completion", "created": 0, "model": "deepseek-v4-flash",
    "choices": [{"index": 0, "message": {"role": "assistant", "content": "ready"},
                 "finish_reason": "stop"}],
    "usage": {"prompt_tokens": 6, "completion_tokens": 2, "total_tokens": 8}}


class SmokeRealSdkTests(EnvCleanupTestCase):
    """execute_smoke against the REAL installed mini/litellm with a fake
    httpx transport. Assertions run on the captured OUTBOUND request body —
    not on echoed report fields."""

    def _config_file(self):
        import yaml as _y
        f = tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False)
        f.write(_y.safe_dump(synth_config()))
        f.close()
        return Path(f.name)

    def test_max_tokens_in_real_request_body_and_success(self):
        """F1: the output cap must reach the SDK request body (asserted on
        the captured outbound request). F2 semantics: tool-protocol
        connectivity — a tool-call reply is SUCCESS."""
        t = FakeTransport(responses=[TOOL_CALL_RESP])
        cfg = self._config_file()
        rec = smoke_mod.execute_smoke(cfg, env=fake_env(), result_dir=None,
                                      _transport=t)
        # the query runs in a child process; its captured outbound requests
        # are returned via the child payload (parent transport sees nothing)
        captured = rec.get("_captured_requests") or []
        self.assertTrue(captured, "child must return captured requests")
        body = captured[-1]["body"]
        self.assertEqual(body.get("max_tokens"), 100,
                         "max_tokens must be in the outbound request body")
        tools = body.get("tools") or []
        self.assertTrue(any(t_.get("function", {}).get("name") == "bash" for t_ in tools),
                        "mini's real request carries its bash tool schema")
        self.assertTrue(rec["ok"], "tool-call reply = connectivity success")
        self.assertEqual(rec["usage"]["total_tokens"], 15)

    def test_plain_text_reply_recorded_with_usage_preserved(self):
        """F2: a plain-text reply cannot be parsed by mini's tool-call
        parser (verified against the installed SDK) -> FormatError. The
        smoke records unexpected_plain_text and PRESERVES usage — not a
        bare usage=null failure."""
        t = FakeTransport(responses=[PLAIN_TEXT_RESP])
        rec = smoke_mod.execute_smoke(self._config_file(), env=fake_env(),
                                      result_dir=None, _transport=t)
        self.assertFalse(rec["ok"])
        self.assertEqual(rec["outcome"], "unexpected_plain_text")
        self.assertIsNotNone(rec["usage"], "usage must survive a FormatError")
        self.assertEqual(rec["usage"]["total_tokens"], 8)

    def test_gateway_error_stops_no_retry(self):
        t = FakeTransport(status=401, responses=[{"error": {"message": "nope"}}])
        rec = smoke_mod.execute_smoke(self._config_file(), env=fake_env(),
                                      result_dir=None, _transport=t)
        self.assertFalse(rec["ok"])
        n_req = len(rec.get("_captured_requests") or [])
        self.assertEqual(n_req, 1, "failure stops; no retry at any layer")

    def test_result_file_written_sanitized_and_exclusive(self):
        with tempfile.TemporaryDirectory() as tmp:
            proj = Path(tmp) / "project"
            (proj / "reports").mkdir(parents=True)
            t = FakeTransport(responses=[TOOL_CALL_RESP])
            rec = smoke_mod.execute_smoke(self._config_file(), env=fake_env(),
                                          result_dir=Path("reports/smoke"),
                                          project_root=proj, _transport=t)
            self.assertTrue(rec["ok"])  # tool-call reply = success path
            self.assertIn("result_path", rec)
            blob = Path(rec["result_path"]).read_text()
            self.assertNotIn(CANARY_KEY, blob)
            self.assertNotIn(CANARY_BASE, blob)
            with self.assertRaises(FileExistsError):
                smoke_mod._write_result_exclusive(Path(rec["result_path"]), rec)

    def test_result_dir_guard_rejects_outside_and_protected(self):
        """F4: arbitrary dirs / protected roots / symlink escapes refused."""
        with tempfile.TemporaryDirectory() as tmp:
            proj = Path(tmp) / "project"
            (proj / "reports").mkdir(parents=True)
            (proj / "data" / "catalog").mkdir(parents=True)
            (proj / "references").mkdir()
            with self.assertRaises(ValueError):
                smoke_mod.guard_result_dir(Path("elsewhere"), project_root=proj)
            with self.assertRaises(ValueError):
                smoke_mod.guard_result_dir(Path("data/catalog/x"), project_root=proj)
            with self.assertRaises(ValueError):
                smoke_mod.guard_result_dir(Path("references/x"), project_root=proj)
            legacy = Path(tmp) / "legacy"; legacy.mkdir()
            (proj / "reports" / "smoke").symlink_to(legacy)
            with self.assertRaises(ValueError):
                smoke_mod.guard_result_dir(Path("reports/smoke/run"), project_root=proj)

    def test_guard_validates_before_request(self):
        """F4: an invalid result dir must raise BEFORE any request is sent."""
        t = FakeTransport(responses=[PLAIN_TEXT_RESP])
        with tempfile.TemporaryDirectory() as tmp:
            proj = Path(tmp) / "project"; proj.mkdir()
            with self.assertRaises(ValueError):
                smoke_mod.execute_smoke(self._config_file(), env=fake_env(),
                                        result_dir=Path("outside"), project_root=proj,
                                        _transport=t)
            self.assertEqual(t.n, 0, "no request may be sent when the output "
                                     "location is invalid")

    def test_deadline_hard_stop_when_child_swallows_alarm(self):
        """F3 (reviewer scenario, reproduced in-child): the child's fake
        transport SWALLOWS a one-shot SIGALRM and keeps blocking past the
        deadline. The parent watchdog SIGKILLs it anyway. Evidence chain:
        started-marker proves the request began; killed error proves the
        hard stop; ok must never be True."""
        t = FakeTransport(responses=[TOOL_CALL_RESP])
        # 10s deadline (covers ~3s child import); the child swallows a 1s
        # one-shot alarm and keeps blocking ~3s more — well past deadline.
        t.swallow_alarm = True
        rec = smoke_mod.execute_smoke(self._config_file(), env=fake_env(),
                                      result_dir=None, deadline_s=10,
                                      _transport=t)
        self.assertFalse(rec["ok"],
                         "swallowed alarm must not turn into ok=True")
        self.assertIn("DeadlineExceeded", rec["error"])
        self.assertIn("killed", rec["error"])
        self.assertTrue(rec.get("request_started_before_kill"),
                        "the query must provably START (marker) before the "
                        "kill — not die during SDK import")

    def test_deadline_actually_fires_offline(self):
        """F3: a genuinely slow request (child-side delay) hits the wall
        deadline. The delay runs INSIDE the child's fake transport (mode
        serialized via _fake_delay_ms), and the started-marker proves the
        query was underway before the kill — not just SDK import time."""
        t = FakeTransport(responses=[TOOL_CALL_RESP])
        # deadline must exceed the child's SDK import (~2-3s cold start),
        # otherwise the kill lands during import and the marker honestly
        # reports request_started=False. 10s deadline + 12s in-child delay:
        # import(~3s) -> request starts (marker) -> blocks -> killed at 10s.
        t.delay_ms = 12000
        rec = smoke_mod.execute_smoke(self._config_file(), env=fake_env(),
                                      result_dir=None, deadline_s=10,
                                      _transport=t)
        self.assertFalse(rec["ok"])
        self.assertIn("DeadlineExceeded", rec["error"])
        self.assertIn("killed", rec["error"])
        self.assertTrue(rec.get("request_started_before_kill"),
                        "started-marker must prove the request began before "
                        "the kill (not import-time exhaustion)")

    def test_cli_refuses_execute_without_double_flag(self):
        from agent_workload_characterization.runners.smoke import main
        self.assertEqual(main(["--execute"]), 1)
        self.assertEqual(main([]), 0)  # offline plan


if __name__ == "__main__":
    unittest.main()


# ---------------- S3 (restored): full serialization & exception-echo canary ----------------

class SerializationLeakTests(EnvCleanupTestCase):
    """Canary must not survive m.serialize(), persisted records, or the full
    exception output of the REAL SDK path (not just the returned message)."""

    def _mini_with_creds_in_kwargs(self, transport):
        """Mini with credentials in model_kwargs (the leak-risk path)."""
        from minisweagent.models.litellm_model import LitellmModel
        litellm_with(transport)
        return LitellmModel(model_name="openai/deepseek-v4-flash",
                            model_kwargs={"drop_params": True, "num_retries": 0,
                                          "api_base": CANARY_BASE,
                                          "api_key": CANARY_KEY},
                            cost_tracking="ignore_errors")

    def test_serialize_leaks_with_creds_in_kwargs(self):
        """Documented third-party behavior: m.serialize() embeds model_kwargs
        verbatim -> credentials at rest. Justifies the adapter env-var route."""
        t = FakeTransport()
        m = self._mini_with_creds_in_kwargs(t)
        m.query([{"role": "user", "content": "p"}])
        blob = json.dumps(m.serialize())
        self.assertIn(CANARY_KEY, blob)
        self.assertIn(CANARY_BASE, blob)

    def test_serialize_clean_with_env_var_route(self):
        """The adapter route: env vars during the call; model_kwargs clean.
        m.serialize() then carries no credentials — REAL serialization path."""
        from minisweagent.models.litellm_model import LitellmModel
        t = FakeTransport()
        litellm_with(t)
        r = ma.resolve_model(synth_config(), env=fake_env())
        m = LitellmModel(cost_tracking="ignore_errors", **ma.mini_model_config(r))
        with ma.sdk_credential_scope(r):
            msg = m.query([{"role": "user", "content": "p"}])
        blob = json.dumps(m.serialize())
        self.assertNotIn(CANARY_KEY, blob)
        self.assertNotIn(CANARY_BASE, blob)
        self.assertNotIn(CANARY_KEY, json.dumps(msg))

    def test_exception_echo_canary_not_in_owned_outputs(self):
        """Gateway error body echoing key/base must not survive our records
        or mini's own serialization; scope note: raw litellm tracebacks may
        echo gateway text (third-party), and must not be pasted into reports."""
        from minisweagent.models.litellm_model import LitellmModel
        t = FakeTransport(status=401,
                          responses=[{"error": {"message": "invalid key " + CANARY_KEY
                                                + " for " + CANARY_BASE}}])
        litellm_with(t)
        r = ma.resolve_model(synth_config(), env=fake_env())
        m = LitellmModel(cost_tracking="ignore_errors", **ma.mini_model_config(r))

        def call():
            with ma.sdk_credential_scope(r):
                return m.query([{"role": "user", "content": "p"}])
        rec = ma.record_sdk_call(call, request_id="req-x",
                                 model="openai/deepseek-v4-flash",
                                 cost_tracking="ignore_errors")
        self.assertNotIn(CANARY_KEY, json.dumps(rec.__dict__))
        self.assertNotIn(CANARY_BASE, json.dumps(rec.__dict__))
        self.assertNotIn(CANARY_KEY, json.dumps(m.serialize()))
