#!/usr/bin/env python3
"""One-send, secret-safe probes for the real Office and Assistant client paths."""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))
os.environ.setdefault("LITELLM_LOCAL_MODEL_COST_MAP", "True")


class ProbeSendLimitExceeded(RuntimeError):
    """Raised before a request beyond the probe's authorized send limit."""


class SendCounter:
    """Count target-host HTTP client sends and returned responses.

    The send method is the shared dispatch boundary for direct OpenAI and
    LiteLLM clients. It avoids counting nested wrappers twice. Neither a client
    send nor a returned response proves what the remote service received.
    """

    def __init__(self, host: str, *, max_attempts: int = 1):
        import httpx

        self.host = host
        self.max_attempts = max_attempts
        self.transport_attempts_entered = 0
        self.responses_received = 0
        self.blocked_before_forwarding = 0
        self.unexpected_hosts_blocked = 0
        self.coverage = {"sync": True, "async": True}
        self._httpx = httpx
        # OpenAI 1.17 in this frozen environment exposes its client through
        # httpx2; LiteLLM uses httpx. Count each client send invocation once.
        import openai._base_client as openai_base_client
        modules = (httpx, openai_base_client.httpx2)
        self._client_methods = []
        seen = set()
        for module in modules:
            for client_type, is_async in ((module.Client, False),
                                          (module.AsyncClient, True)):
                method_name = "send"
                key = (client_type, method_name)
                if key not in seen:
                    seen.add(key)
                    self._client_methods.append((client_type, method_name,
                        getattr(client_type, method_name), is_async))
        self._installed = False

    def __enter__(self):
        counter = self
        for client_type, method_name, original, is_async in self._client_methods:
            if is_async:
                async def counted(client, request, *args, _original=original, **kwargs):
                    counter._before_send(request)
                    response = await _original(client, request, *args, **kwargs)
                    counter.responses_received += 1
                    return response
            else:
                def counted(client, request, *args, _original=original, **kwargs):
                    counter._before_send(request)
                    response = _original(client, request, *args, **kwargs)
                    counter.responses_received += 1
                    return response
            setattr(client_type, method_name, counted)
        self._installed = True
        return self

    def _before_send(self, request) -> None:
        if request.url.host != self.host:
            self.unexpected_hosts_blocked += 1
            raise ProbeSendLimitExceeded("unexpected_probe_destination")
        self.transport_attempts_entered += 1
        if self.transport_attempts_entered > self.max_attempts:
            self.blocked_before_forwarding += 1
            raise ProbeSendLimitExceeded("probe_send_limit_reached")

    def __exit__(self, *_):
        if self._installed:
            for client_type, method_name, original, _is_async in self._client_methods:
                setattr(client_type, method_name, original)
            self._installed = False

    def snapshot(self) -> dict:
        return {
            "boundary_coverage": {"httpx_sync_client_send": True,
                                  "httpx_async_client_send": True,
                                  "openai_httpx2_sync_async": True},
            "transport_attempts_entered": self.transport_attempts_entered,
            "responses_received": self.responses_received,
            "blocked_before_forwarding": self.blocked_before_forwarding,
            "unexpected_hosts_blocked": self.unexpected_hosts_blocked,
            "remote_service_receipt": "unknown",
        }


def _usage(response) -> dict:
    usage = response.get("usage") if isinstance(response, dict) else getattr(response, "usage", None)
    if usage is None:
        return {}
    if not isinstance(usage, dict):
        usage = getattr(usage, "model_dump", lambda: {})()
    keys = ("prompt_tokens", "completion_tokens", "total_tokens",
            "prompt_cache_hit_tokens", "prompt_cache_miss_tokens",
            "cache_read_input_tokens", "cache_creation_input_tokens")
    return {k: usage[k] for k in keys if type(usage.get(k)) is int}


def _safe_exception(exc: BaseException, *, stage: str) -> dict:
    frames = traceback.extract_tb(exc.__traceback__) if exc.__traceback__ else []
    frame = frames[-1] if frames else None
    return {
        "stage": stage,
        "exception_type": type(exc).__name__,
        "origin": ({"file": Path(frame.filename).name, "function": frame.name,
                    "line": frame.lineno} if frame else None),
    }


def _initial_result(probe: str) -> dict:
    return {
        "probe": probe,
        "status": "failed",
        "stage": "initialization",
        "response_received": False,
        "parse_status": "not_started",
        "send_observation": {
            "boundary_coverage": {"sync": False, "async": False},
            "transport_attempts_entered": None,
            "responses_received": None,
            "blocked_before_forwarding": 0,
            "unexpected_hosts_blocked": 0,
            "remote_service_receipt": "unknown",
        },
    }


def _write_result(output: Path, result: dict) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")


def _load_real_credentials():
    from agent_workload_characterization.runners.smoke_launcher import load_credentials

    return load_credentials(provider_name="火山AI网关", model_key="deepseek-v4-flash",
                            model_display_name="DeepSeek-V4-Flash")


def office_probe(output: Path, *, credential_loader=None) -> dict:
    import httpx
    import litellm
    from docops_measurement_validate_01_entry import VOLCANO_PROFILE, configured_route
    import docops_word_resource_01_entry as word
    from tenacity import stop_after_attempt

    result = _initial_result("office_json_action")
    counter = None
    old_openai_env = {k: os.environ.get(k) for k in ("OPENAI_API_KEY", "OPENAI_API_BASE")}
    old_litellm_retries = getattr(litellm, "num_retries", None)
    old_acompletion = litellm.acompletion
    start = time.monotonic()
    stage = "route_and_credentials"
    try:
        route = configured_route(VOLCANO_PROFILE)
        api_base, api_key = (credential_loader or _load_real_credentials)()
        if api_base != route["api_base"]:
            raise RuntimeError("route_changed")
        os.environ["OPENAI_API_KEY"] = api_key
        os.environ["OPENAI_API_BASE"] = api_base
        counter = SendCounter(httpx.URL(api_base).host, max_attempts=1)
        counter.__enter__()

        stage = "agent_construction"
        task = ROOT / "references/repos/DocOps/tasks/atomic__excel_001_budget_bucket_totals_seed"
        agent = word.build_agent(output.parent / "probe-log", {
            "task_dir": str(task), "max_steps": 40, "max_tokens": 1024,
            "model_route": {"api_base": api_base,
                            "request_model": route["request_model"]}})
        inner = agent.llm._inner
        bound_call = inner.call
        if getattr(bound_call, "__self__", None) is not inner or not hasattr(bound_call, "retry"):
            raise RuntimeError("framework_retry_cap_unavailable")
        # Change only this probe instance's Tenacity policy; retain its bound method.
        bound_call.retry.stop = stop_after_attempt(1)
        if inner.call.__self__ is not inner:
            raise RuntimeError("bound_method_not_preserved")
        result["method_binding_preserved"] = True
        litellm.num_retries = 0
        response_observed = {}

        async def observe(*args, **kwargs):
            response = await old_acompletion(*args, **kwargs)
            try:
                choice = response["choices"][0]
                response_observed.update({
                    "response_model": response.get("model"),
                    "finish_reason": choice.get("finish_reason"),
                    "usage": _usage(response),
                })
            except (KeyError, IndexError, TypeError, AttributeError):
                response_observed["response_shape"] = "unrecognized"
            return response

        class RecorderContext:
            def __init__(self):
                self.points = []

            def point(self, name, attrs=None):
                self.points.append({"name": name, "attrs": attrs or {}})

        # _parse_action is the project's real parser and writes its result to recorder.
        agent.recorder = RecorderContext()
        prompt = ('Return exactly one JSON object using this schema: '
                  '{"thought":"string","action":"finish","tool_name":null,'
                  '"arguments":{},"final_message":"string"}. '
                  'Use final_message "protocol probe".')
        stage = "office_json_request"
        litellm.acompletion = observe
        llm_response = asyncio.run(agent.llm.call(
            prompt=prompt, message_history=[], max_tokens=1024,
            timeout=30, num_retries=0, temperature=0))
        result["response_received"] = counter.responses_received > 0
        result.update(response_observed)

        stage = "office_action_parse"
        result["parse_status"] = "started"
        content = getattr(llm_response, "content", None)
        parsed = agent._parse_action(content)
        result["parse_status"] = "complete"
        result["parsed_action"] = getattr(parsed, "action", None)
        result["parsed_tool_name"] = getattr(parsed, "tool_name", None)
        result["recorder_action_points"] = sum(
            1 for point in agent.recorder.points if point["name"] == "agent_action")
        result["status"] = ("passed" if result["parsed_action"] == "finish"
                            and counter.transport_attempts_entered == 1
                            and counter.responses_received == 1 else "failed")
        result["stage"] = "complete" if result["status"] == "passed" else stage
    except BaseException as exc:
        result["stage"] = stage
        result["error"] = _safe_exception(exc, stage=stage)
        if stage == "office_action_parse":
            result["parse_status"] = "failed"
        elif stage in {"office_json_request", "office_action_parse"}:
            result["parse_status"] = "not_completed"
    finally:
        result["latency_s"] = round(time.monotonic() - start, 6)
        result["timeout_s"] = 30
        result["max_tokens"] = 1024
        result["retry_policy"] = {"litellm_num_retries": 0,
                                  "framework_attempts": 1}
        if counter is not None:
            counter.__exit__(None, None, None)
            result["send_observation"] = counter.snapshot()
            result["response_received"] = counter.responses_received > 0
        else:
            result["send_observation"]["boundary_coverage"] = {
                "sync": True, "async": True}
            result["send_observation"]["transport_attempts_entered"] = 0
            result["send_observation"]["responses_received"] = 0
            result["send_observation"]["remote_service_receipt"] = "unknown"
            result["send_observation"]["zero_basis"] = "probe_failed_before_transport_installation"
        result["client_send_attempts"] = result["send_observation"]["transport_attempts_entered"]
        result["api_base"] = locals().get("api_base")
        result["request_model"] = locals().get("route", {}).get("request_model")
        litellm.acompletion = old_acompletion
        litellm.num_retries = old_litellm_retries
        for key, value in old_openai_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        _write_result(output, result)
    return result


def assistant_probe(output: Path, *, credential_loader=None) -> dict:
    import httpx
    from toolsandbox_resource_pilot_01_entry import VOLCANO_PROFILE, route_for
    from agent_workload_characterization.runners.toolsandbox_worker import construct_openai_role_clients
    import openai

    result = _initial_result("assistant_native_tool_calls")
    counter = None
    clients = ()
    start = time.monotonic()
    stage = "route_and_credentials"
    try:
        route = route_for(VOLCANO_PROFILE)
        api_base, api_key = (credential_loader or _load_real_credentials)()
        if api_base != route["api_base"]:
            raise RuntimeError("route_changed")
        counter = SendCounter(httpx.URL(api_base).host, max_attempts=1)
        counter.__enter__()
        stage = "client_construction"
        clients = construct_openai_role_clients(
            openai, base_url=api_base, api_key=api_key)
        start = time.monotonic()
        stage = "assistant_tool_calls_request"
        response = clients[0].chat.completions.create(
                model=route["request_model_raw_client"],
                messages=[{"role": "user", "content":
                    "This is a protocol-only check. Call probe_noop with {\"ok\":true}."}],
                tools=[{"type": "function", "function": {"name": "probe_noop",
                    "description": "Synthetic protocol check; do not execute.",
                    "parameters": {"type": "object", "properties": {
                        "ok": {"type": "boolean"}}, "required": ["ok"],
                        "additionalProperties": False}}}],
                tool_choice={"type": "function", "function": {"name": "probe_noop"}},
                max_tokens=1024, timeout=30)
        result["response_received"] = counter.responses_received > 0

        stage = "assistant_tool_call_parse"
        result["parse_status"] = "started"
        choice = response.choices[0]
        calls = choice.message.tool_calls or []
        parsed_args = json.loads(calls[0].function.arguments) if len(calls) == 1 else None
        result["parse_status"] = "complete"
        result.update({
            "request_model": route["request_model_raw_client"],
            "response_model": response.model,
            "finish_reason": choice.finish_reason,
            "tool_call": ({"id": calls[0].id,
                           "function_name": calls[0].function.name,
                           "arguments": parsed_args} if len(calls) == 1 else None),
            "usage": _usage(response.model_dump()),
        })
        valid = (choice.finish_reason == "tool_calls" and len(calls) == 1
                 and calls[0].function.name == "probe_noop"
                 and isinstance(parsed_args, dict))
        result["status"] = ("passed" if valid and counter.transport_attempts_entered == 1
                            and counter.responses_received == 1 else "failed")
        result["stage"] = "complete" if result["status"] == "passed" else stage
    except BaseException as exc:
        result["stage"] = stage
        result["error"] = _safe_exception(exc, stage=stage)
        if stage == "assistant_tool_call_parse":
            result["parse_status"] = "failed"
    finally:
        result["latency_s"] = round(time.monotonic() - start, 6)
        result["timeout_s"] = 30
        result["max_tokens"] = 1024
        result["retry_policy"] = {"sdk_max_retries": 0,
                                  "framework_attempts": 1}
        if counter is not None:
            counter.__exit__(None, None, None)
            result["send_observation"] = counter.snapshot()
            result["response_received"] = counter.responses_received > 0
        elif stage not in {"route_and_credentials"}:
            result["send_observation"].update({
                "boundary_coverage": {"sync": True, "async": True},
                "transport_attempts_entered": 0,
                "responses_received": 0,
                "zero_basis": "client_construction_failed_before_transport_installation",
            })
        result["client_send_attempts"] = result["send_observation"]["transport_attempts_entered"]
        if "request_model" not in result:
            result["request_model"] = locals().get("route", {}).get("request_model_raw_client")
        result["api_base"] = locals().get("api_base")
        for client in clients:
            try:
                client.close()
            except Exception as exc:
                result.setdefault("cleanup_errors", []).append(type(exc).__name__)
        _write_result(output, result)
    return result


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(allow_abbrev=False)
    parser.add_argument("probe", choices=("office", "assistant"))
    parser.add_argument("--output", required=True)
    args = parser.parse_args(argv)
    output = Path(args.output)
    result = (office_probe if args.probe == "office" else assistant_probe)(output)
    print(json.dumps({k: v for k, v in result.items()
                      if k not in {"tool_call", "usage"}}, ensure_ascii=False))
    return 0 if result.get("status") == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
