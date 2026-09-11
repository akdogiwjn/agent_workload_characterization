"""Model adapter: connect PREP-01 env-var design to the installed mini/litellm SDK.

ENV-01 scope. All routing facts below were established OFFLINE against the
installed versions (mini-swe-agent 2.4.6, litellm 1.100.1, openai 2.54.0)
using an intercepting httpx transport — no real endpoints contacted:

- mini's LitellmModel expands ``model_kwargs`` into the
  ``litellm.completion(...)`` call, but litellm 1.100.1 **ignores**
  ``api_base``/``api_key`` arriving inside model_kwargs (verified: requests
  fall back to api.openai.com and fail with missing credentials).
- Credential mechanisms that DO work (verified end-to-end through mini):
  (a) top-level completion kwargs — unavailable to mini's config surface;
  (b) the ``litellm.api_base``/``litellm.api_key`` module globals;
  (c) the ``OPENAI_API_BASE``/``OPENAI_API_KEY`` environment variables.
  The adapter uses (c) for the real SDK path (and (b) as an explicit
  alternative), set only for the duration of a call, never persisted.
- Consequently ``model_kwargs`` can stay credential-free: mini's trajectory
  serialization (LitellmModelConfig dump) no longer carries secrets — the
  PREP-01 blocker is resolved by routing mechanism, not by filtering alone.
- URL behavior: the OpenAI client appends ``/chat/completions`` to
  base_url without adding ``/v1``; the ``openai/`` prefix is stripped from
  the request body model field. PILOT_API_BASE must therefore include the
  ``/v1`` suffix (no duplication was observed with it present).
- Retry: mini's tenacity loop defaults to 10 attempts with exponential
  backoff (verified: a 500 response retried with 4/8/16/32/60s waits).
  ``MSWEA_MODEL_RETRY_STOP_AFTER_ATTEMPT=1`` pins it to a single attempt
  (verified: exactly one transport hit per failed call).
"""

from __future__ import annotations

import os
import time
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any, Callable

from ..runners.preparation import (PreparationError, _sanitize_error,
                                   _sanitize_usage, check_model_config)

# SDK env vars litellm actually reads for the openai-compatible path
# (verified; see module docstring).
SDK_BASE_ENV = "OPENAI_API_BASE"
SDK_KEY_ENV = "OPENAI_API_KEY"


@dataclass
class ResolvedModel:
    """Everything the SDK call needs — resolved in memory, never persisted."""
    model_name: str                 # litellm form, e.g. openai/<id>
    request_model_id: str           # what the gateway sees (prefix stripped)
    api_base: str
    api_key: str
    model_kwargs_public: dict       # credential-free subset (goes to mini config)


def resolve_model(config: dict, env: dict[str, str] | None = None) -> ResolvedModel:
    """Resolve PILOT_API_BASE / PILOT_API_KEY env references to values.

    ``config`` is the PREP-01 style synthetic config (env var NAMES only).
    ``env`` is an explicit mapping (tests inject fakes; the smoke entry
    resolves os.environ only at call time — never persisted, never printed).
    """
    plan = check_model_config(config)  # validates names, rejects secrets/URLs
    env = os.environ if env is None else env
    api_base = env.get(plan.api_base_env)
    api_key = env.get(plan.auth_env)
    if not api_base or not api_key:
        missing = [n for n, v in ((plan.api_base_env, api_base),
                                   (plan.auth_env, api_key)) if not v]
        raise PreparationError(f"missing env values at run time: {missing}")
    if "://" not in api_base:
        raise PreparationError("api_base must be an absolute URL")
    if "@" in api_base.split("://", 1)[-1].split("/", 1)[0]:
        raise PreparationError("api_base must not carry userinfo")
    model_name = plan.model_name
    request_model_id = model_name.split("/", 1)[1] if "/" in model_name else model_name
    public = {k: v for k, v in (config.get("model", {}).get("model_kwargs") or {}).items()}
    for forbidden in ("api_key", "api_base"):
        if forbidden in public:
            raise PreparationError(
                f"model_kwargs must not carry {forbidden}; credentials are "
                "injected via SDK env vars for the call duration only")
    return ResolvedModel(model_name=model_name, request_model_id=request_model_id,
                         api_base=api_base, api_key=api_key,
                         model_kwargs_public=public)


@contextmanager
def sdk_credential_scope(resolved: ResolvedModel):
    """Expose credentials to the SDK for the duration of one call.

    Sets OPENAI_API_BASE / OPENAI_API_KEY (the mechanism litellm actually
    reads; verified) and restores previous values afterwards. The credentials
    never enter model_kwargs, mini config objects, or anything serialized.
    """
    prev_base = os.environ.get(SDK_BASE_ENV)
    prev_key = os.environ.get(SDK_KEY_ENV)
    os.environ[SDK_BASE_ENV] = resolved.api_base
    os.environ[SDK_KEY_ENV] = resolved.api_key
    try:
        yield
    finally:
        if prev_base is None:
            os.environ.pop(SDK_BASE_ENV, None)
        else:
            os.environ[SDK_BASE_ENV] = prev_base
        if prev_key is None:
            os.environ.pop(SDK_KEY_ENV, None)
        else:
            os.environ[SDK_KEY_ENV] = prev_key


def mini_model_config(resolved: ResolvedModel) -> dict:
    """Constructor kwargs for mini's LitellmModel — credential-free by design.

    The SDK credentials are provided separately via sdk_credential_scope
    around the actual query call. num_retries=0 disables litellm/openai-SDK
    internal retries (verified: without it a 500 response is attempted 3
    times by the OpenAI client default max_retries=2 — the third retry layer
    beyond task-attempt and mini-tenacity).
    """
    return {"model_name": resolved.model_name,
            "model_kwargs": {**resolved.model_kwargs_public, "num_retries": 0}}


def retry_disabled_env() -> dict[str, str]:
    """Env overlay that pins mini's tenacity to a single attempt."""
    return {"MSWEA_MODEL_RETRY_STOP_AFTER_ATTEMPT": "1"}


# ---------------------------------------------------------------------------
# Call recording (bridge to PREP-01 CallRecord semantics)
# ---------------------------------------------------------------------------

@dataclass
class SdkCallRecord:
    request_id: str
    ok: bool
    model: str
    usage: dict | None
    cost: float | None
    cost_status: str
    error: str | None
    t_start_ns: int
    t_end_ns: int


def record_sdk_call(call: Callable[[], Any], *,
                    request_id: str | None = None,
                    model: str = "",
                    cost_tracking: str = "default") -> SdkCallRecord:
    """Run one SDK call (injected), recording sanitized outcome.

    Usage is whitelist-projected and errors type-classified exactly as in
    PREP-01. A cost-tracking failure does NOT discard an already-received
    response's usage. The callable is the *entire* mini/litellm query so the
    record reflects the real SDK path.
    """
    rid = request_id or uuid.uuid4().hex
    t0 = time.monotonic_ns()
    try:
        message = call()
        usage = getattr(message, "usage", None)
        usage_d = None
        if usage is not None:
            usage_d = {"prompt_tokens": getattr(usage, "prompt_tokens", None),
                       "completion_tokens": getattr(usage, "completion_tokens", None),
                       "total_tokens": getattr(usage, "total_tokens", None)}
        extra = message.get("extra", {}) if isinstance(message, dict) else {}
        # mini 2.4.6 persists usage inside extra.response.usage (no top-level
        # usage key; verified). Cost errors must not discard it.
        resp_dump = (extra or {}).get("response") or {}
        resp_usage = resp_dump.get("usage") if isinstance(resp_dump, dict) else None
        u = (extra or {}).get("usage") or resp_usage or usage_d
        cost = (extra or {}).get("cost")
        # With cost_tracking=ignore_errors, litellm pricing failures are
        # swallowed to 0.0 — a 0.0 in that mode is NOT evidence of pricing
        # (source value only). Record it as unknown-priced; keep the value.
        if cost_tracking == "ignore_errors" and (cost is None or cost == 0.0):
            cost_status = "unknown"
        else:
            cost_status = "computed" if cost is not None else "unknown"
        return SdkCallRecord(request_id=rid, ok=True, model=model,
                             usage=_sanitize_usage(u), cost=cost,
                             cost_status=cost_status, error=None,
                             t_start_ns=t0, t_end_ns=time.monotonic_ns())
    except Exception as exc:  # noqa: BLE001 — sanitize and record, never echo
        return SdkCallRecord(request_id=rid, ok=False, model=model,
                             usage=None, cost=None, cost_status="unknown",
                             error=_sanitize_error(f"{type(exc).__name__}: {exc}"),
                             t_start_ns=t0, t_end_ns=time.monotonic_ns())
