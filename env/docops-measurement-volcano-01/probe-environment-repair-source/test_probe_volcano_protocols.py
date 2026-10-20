from __future__ import annotations

import asyncio
import json
import os
import socket
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("LITELLM_LOCAL_MODEL_COST_MAP", "True")
ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "scripts"), str(ROOT / "src"),
               str(ROOT / "references/repos/DocOps/harnesses")]

import httpx
import openai._base_client as openai_base_client
import probe_volcano_protocols as probes
from docops_measurement_validate_01_entry import VOLCANO_PROFILE as OFFICE_PROFILE, configured_route
from toolsandbox_resource_pilot_01_entry import VOLCANO_PROFILE as ASSISTANT_PROFILE, route_for

ORIGINAL_ASYNCIO_RUN = asyncio.run


def openai_response(request, *, content=None, tool_calls=None, model="probe-response"):
    message = {"role": "assistant"}
    if tool_calls is None:
        message["content"] = content
        finish = "stop"
    else:
        message["tool_calls"] = tool_calls
        finish = "tool_calls"
    return httpx.Response(200, request=request, json={
        "id": "chatcmpl-synthetic", "object": "chat.completion", "created": 1,
        "model": model,
        "choices": [{"index": 0, "message": message, "finish_reason": finish}],
        "usage": {"prompt_tokens": 11, "completion_tokens": 7, "total_tokens": 18},
    })


class ProbeProtocolTests(unittest.TestCase):
    def setUp(self):
        def forbidden(*_args, **_kwargs):
            raise AssertionError("offline test attempted socket access")
        for target, name in ((socket, "getaddrinfo"),
                             (socket.socket, "connect"),
                             (socket.socket, "connect_ex")):
            patcher = patch.object(target, name, side_effect=forbidden)
            patcher.start()
            self.addCleanup(patcher.stop)

    def credentials(self, route):
        return lambda: (route["api_base"], "synthetic-secret-must-not-persist")

    @staticmethod
    def bounded_asyncio_run(coro):
        async def bounded():
            task = asyncio.create_task(coro)
            done, _ = await asyncio.wait({task}, timeout=3)
            if task not in done:
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)
                raise TimeoutError("offline fake transport was not reached")
            return task.result()
        return ORIGINAL_ASYNCIO_RUN(bounded())

    def test_office_real_agent_path_preserves_binding_and_parses_finish(self):
        route = configured_route(OFFICE_PROFILE)
        async def fake_httpx(_client, request):
            return openai_response(request, content=json.dumps({
                "thought": "probe", "action": "finish", "tool_name": None,
                "arguments": {}, "final_message": "protocol probe"}))
        def fake_sync(_client, request):
            return openai_response(request, content=json.dumps({
                "thought": "probe", "action": "finish", "tool_name": None,
                "arguments": {}, "final_message": "protocol probe"}))
        with tempfile.TemporaryDirectory(prefix="probe-office-e2e-") as tmp, \
                patch.object(probes.asyncio, "run", self.bounded_asyncio_run), \
                patch.object(httpx.AsyncClient, "_send_single_request", fake_httpx), \
                patch.object(httpx.Client, "_send_single_request", fake_sync), \
                patch.object(openai_base_client.httpx2.AsyncClient,
                             "_send_single_request", fake_httpx), \
                patch.object(openai_base_client.httpx2.Client,
                             "_send_single_request", fake_sync):
            out = Path(tmp) / "office.json"
            result = probes.office_probe(out, credential_loader=self.credentials(route))
            saved = json.loads(out.read_text())
        self.assertEqual(result["status"], "passed", result)
        self.assertTrue(result["method_binding_preserved"])
        self.assertEqual(result["parsed_action"], "finish")
        self.assertEqual(result["recorder_action_points"], 1)
        self.assertEqual(saved["send_observation"]["transport_attempts_entered"], 1)
        self.assertEqual(saved["client_send_attempts"], 1)
        self.assertEqual(saved["send_observation"]["responses_received"], 1)
        self.assertEqual(saved["send_observation"]["remote_service_receipt"], "unknown")
        self.assertNotIn("synthetic-secret", json.dumps(saved))

    def test_assistant_real_sync_client_path_records_one_send_and_tool_call(self):
        route = route_for(ASSISTANT_PROFILE)
        async def unexpected_async(*_):
            raise AssertionError("sync assistant path unexpectedly used async transport")
        def fake_send(_client, request):
            return openai_response(request, tool_calls=[{
                "id": "call_synthetic", "type": "function",
                "function": {"name": "probe_noop", "arguments": '{"ok":true}'},
            }])
        with tempfile.TemporaryDirectory(prefix="probe-assistant-e2e-") as tmp, \
                patch.object(httpx.Client, "_send_single_request", fake_send), \
                patch.object(openai_base_client.httpx2.Client,
                             "_send_single_request", fake_send), \
                patch.object(httpx.AsyncHTTPTransport, "handle_async_request", unexpected_async):
            out = Path(tmp) / "assistant.json"
            result = probes.assistant_probe(out, credential_loader=self.credentials(route))
            saved = json.loads(out.read_text())
        self.assertEqual(result["status"], "passed", result)
        self.assertEqual(result["tool_call"]["function_name"], "probe_noop")
        self.assertEqual(saved["send_observation"]["transport_attempts_entered"], 1)
        self.assertEqual(saved["send_observation"]["responses_received"], 1)
        self.assertNotIn("synthetic-secret", json.dumps(saved))

    def test_office_pre_send_type_error_is_saved_as_proven_zero(self):
        route = configured_route(OFFICE_PROFILE)
        import litellm
        async def fail_before_transport(*_args, **_kwargs):
            raise TypeError("synthetic-secret and body must not be recorded")
        with tempfile.TemporaryDirectory(prefix="probe-presend-") as tmp, \
                patch.object(litellm, "acompletion", fail_before_transport):
            out = Path(tmp) / "failure.json"
            result = probes.office_probe(out, credential_loader=self.credentials(route))
            saved = json.loads(out.read_text())
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["stage"], "office_json_request")
        self.assertEqual(result["client_send_attempts"], 0)
        self.assertEqual(result["send_observation"]["transport_attempts_entered"], 0)
        self.assertEqual(result["parse_status"], "not_completed")
        self.assertEqual(saved["error"]["exception_type"], "TypeError")
        self.assertNotIn("synthetic-secret", json.dumps(saved))

    def test_async_connection_failure_keeps_attempt_and_unknown_remote_receipt(self):
        route = configured_route(OFFICE_PROFILE)
        async def fail_httpx(_client, request):
            raise httpx.ConnectError("synthetic-secret hidden", request=request)
        def fail_sync(_client, request):
            raise httpx.ConnectError("synthetic-secret hidden", request=request)
        with tempfile.TemporaryDirectory(prefix="probe-connect-error-") as tmp, \
                patch.object(httpx.AsyncClient, "_send_single_request", fail_httpx), \
                patch.object(httpx.Client, "_send_single_request", fail_sync), \
                patch.object(openai_base_client.httpx2.AsyncClient,
                             "_send_single_request", fail_httpx), \
                patch.object(openai_base_client.httpx2.Client,
                             "_send_single_request", fail_sync):
            out = Path(tmp) / "failure.json"
            result = probes.office_probe(out, credential_loader=self.credentials(route))
            saved = json.loads(out.read_text())
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["client_send_attempts"], 1)
        self.assertEqual(result["send_observation"]["transport_attempts_entered"], 1)
        self.assertEqual(result["send_observation"]["responses_received"], 0)
        self.assertEqual(result["send_observation"]["remote_service_receipt"], "unknown")
        self.assertNotIn("synthetic-secret", json.dumps(saved))

    def test_response_then_invalid_json_keeps_counts_and_parse_failure(self):
        route = configured_route(OFFICE_PROFILE)
        async def fake_httpx(_client, request):
            return openai_response(request, content="not-json")
        def fake_sync(_client, request):
            return openai_response(request, content="not-json")
        with tempfile.TemporaryDirectory(prefix="probe-parse-error-") as tmp, \
                patch.object(httpx.AsyncClient, "_send_single_request", fake_httpx), \
                patch.object(httpx.Client, "_send_single_request", fake_sync), \
                patch.object(openai_base_client.httpx2.AsyncClient,
                             "_send_single_request", fake_httpx), \
                patch.object(openai_base_client.httpx2.Client,
                             "_send_single_request", fake_sync):
            out = Path(tmp) / "failure.json"
            result = probes.office_probe(out, credential_loader=self.credentials(route))
            saved = json.loads(out.read_text())
        self.assertEqual(result["stage"], "office_action_parse")
        self.assertEqual(result["parse_status"], "failed")
        self.assertEqual(result["client_send_attempts"], 1)
        self.assertEqual(result["send_observation"]["responses_received"], 1)
        self.assertEqual(result["response_received"], True)
        self.assertNotIn("error_detail", result)

    def test_empty_content_is_saved_as_parse_failure(self):
        route = configured_route(OFFICE_PROFILE)
        async def fake_httpx(_client, request):
            return openai_response(request, content="")
        def fake_sync(_client, request):
            return openai_response(request, content="")
        with tempfile.TemporaryDirectory(prefix="probe-empty-content-") as tmp, \
                patch.object(httpx.AsyncClient, "_send_single_request", fake_httpx), \
                patch.object(httpx.Client, "_send_single_request", fake_sync), \
                patch.object(openai_base_client.httpx2.AsyncClient,
                             "_send_single_request", fake_httpx), \
                patch.object(openai_base_client.httpx2.Client,
                             "_send_single_request", fake_sync):
            result = probes.office_probe(Path(tmp) / "failure.json",
                                         credential_loader=self.credentials(route))
        self.assertEqual(result["parse_status"], "failed")
        self.assertEqual(result["client_send_attempts"], 1)
        self.assertEqual(result["send_observation"]["responses_received"], 1)

    def test_second_transport_entry_is_blocked_before_forwarding(self):
        forwarded = []
        def fake_send(request):
            forwarded.append(request)
            return httpx.Response(200, request=request)
        def transport_send(request):
            return fake_send(request)
        with httpx.Client(transport=httpx.MockTransport(transport_send)) as client:
            counter = probes.SendCounter("probe.invalid", max_attempts=1)
            with counter:
                with self.assertRaises(probes.ProbeSendLimitExceeded):
                    client.get("https://probe.invalid/one")
                    client.get("https://probe.invalid/two")
            snap = counter.snapshot()
        self.assertEqual(len(forwarded), 1)
        self.assertEqual(snap["transport_attempts_entered"], 2)
        self.assertEqual(snap["blocked_before_forwarding"], 1)

    def test_transport_and_environment_patches_are_restored_after_exception(self):
        route = configured_route(OFFICE_PROFILE)
        import litellm
        before_sync = httpx.Client.send
        before_async = httpx.AsyncClient.send
        before_sync2 = openai_base_client.httpx2.Client.send
        before_async2 = openai_base_client.httpx2.AsyncClient.send
        before_acompletion = litellm.acompletion
        previous = os.environ.get("OPENAI_API_KEY")
        async def fail(*_args, **_kwargs):
            raise TypeError("synthetic")
        with tempfile.TemporaryDirectory(prefix="probe-restoration-") as tmp, \
                patch.object(litellm, "acompletion", fail):
            probes.office_probe(Path(tmp) / "failure.json",
                                credential_loader=self.credentials(route))
        self.assertIs(httpx.Client.send, before_sync)
        self.assertIs(httpx.AsyncClient.send, before_async)
        self.assertIs(openai_base_client.httpx2.Client.send, before_sync2)
        self.assertIs(openai_base_client.httpx2.AsyncClient.send, before_async2)
        self.assertIs(litellm.acompletion, before_acompletion)
        self.assertEqual(os.environ.get("OPENAI_API_KEY"), previous)

    def test_result_and_failure_logs_are_confined_to_temp_root(self):
        route = configured_route(OFFICE_PROFILE)
        with tempfile.TemporaryDirectory(prefix="probe-isolation-") as tmp:
            out = Path(tmp) / "nested" / "probe.json"
            result = probes.office_probe(out, credential_loader=lambda: ("https://wrong.invalid/v1", "synthetic"))
            self.assertEqual(result["status"], "failed")
            self.assertTrue(out.exists())
            self.assertEqual(list(Path(tmp).rglob("*.json")), [out])
            self.assertNotIn("synthetic", out.read_text())


if __name__ == "__main__":
    unittest.main()
