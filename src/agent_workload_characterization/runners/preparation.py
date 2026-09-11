"""Pilot preparation layer: safe task projection, config checks, run plan.

PREP-01 scope: pure functions + dependency-injected checks. Never installs,
never imports mini/litellm, never contacts the network, never executes task
scripts. Credentials are never accepted into any structure this module emits.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

import hashlib
import json
import re

# Fields the agent is allowed to see (whitelist). Everything else in the task
# record — including patch, test_patch, FAIL_TO_PASS, hints — must never reach
# the agent view, templates, or generic logs.
AGENT_VIEW_FIELDS = ("instance_id", "problem_statement")

# Fields needed to prepare the execution environment (checkout / image).
ENV_VIEW_FIELDS = ("instance_id", "repo", "base_commit", "version",
                   "environment_setup_commit", "image")

# Evaluator view: presence/type validation only; content stays in the record
# file and is read independently by the evaluator at run time.
EVALUATOR_CHECK_FIELDS = ("instance_id", "image", "eval_script", "eval_type",
                          "log_parser", "FAIL_TO_PASS", "PASS_TO_PASS")

# Sensitive-by-definition record fields that must never leak into agent output.
FORBIDDEN_AGENT_FIELDS = ("patch", "test_patch", "hints_text",
                          "FAIL_TO_PASS", "PASS_TO_PASS", "eval_script")

SENSITIVE_CONFIG_KEYS = ("api_key", "apikey", "token", "password",
                         "authorization", "secret", "x-api-key")


class PreparationError(ValueError):
    """Raised for any invalid task record, config, or projection input."""


def _check_no_secrets(node: Any, path: str = "") -> None:
    """Recursively reject sensitive keys anywhere in a config structure."""
    if isinstance(node, dict):
        for key, value in node.items():
            key_l = str(key).lower()
            if any(s in key_l for s in SENSITIVE_CONFIG_KEYS):
                raise PreparationError(
                    f"sensitive config key rejected at {path}.{key}; "
                    "credentials must be injected as environment variables at run time")
            _check_no_secrets(value, f"{path}.{key}")
    elif isinstance(node, list):
        for i, value in enumerate(node):
            _check_no_secrets(value, f"{path}[{i}]")


# ---------------------------------------------------------------------------
# A1: task projection
# ---------------------------------------------------------------------------

def load_task_record(record_path: Path, *,
                     expected_instance_id: str,
                     expected_sha256: str | None = None) -> dict:
    """Load and validate the fixed pilot task record (read-only)."""
    raw = record_path.read_bytes()
    if expected_sha256 is not None:
        actual = hashlib.sha256(raw).hexdigest()
        if actual != expected_sha256:
            raise PreparationError(
                f"record sha256 mismatch: expected {expected_sha256[:16]}..., "
                f"got {actual[:16]}...")
    record = json.loads(raw)
    if record.get("instance_id") != expected_instance_id:
        raise PreparationError(
            f"instance_id mismatch: expected {expected_instance_id!r}, "
            f"got {record.get('instance_id')!r}")
    if not isinstance(record.get("problem_statement"), str) or not record["problem_statement"].strip():
        raise PreparationError("problem_statement missing or empty")
    return record


def agent_view(record: dict) -> dict:
    """Whitelist projection of the record for agent consumption.

    Only AGENT_VIEW_FIELDS survive; any new record field is excluded by
    default. Canaries in forbidden fields must never appear here.
    """
    view = {k: record[k] for k in AGENT_VIEW_FIELDS if k in record}
    leaked = [f for f in FORBIDDEN_AGENT_FIELDS if f in view]
    if leaked:  # structural guard; whitelist makes this unreachable
        raise PreparationError(f"forbidden fields leaked into agent view: {leaked}")
    return view


def environment_view(record: dict) -> dict:
    """Fields needed to prepare the execution environment (not agent input)."""
    return {k: record[k] for k in ENV_VIEW_FIELDS if k in record}


def evaluator_view(record: dict) -> dict:
    """Validation-only view: field presence/type results plus record locator.

    Never copies gold patch / test patch / eval script content into reports.
    """
    checks = {}
    checks["instance_id"] = {"present": "instance_id" in record,
                             "type": type(record.get("instance_id")).__name__}
    for f in ("image", "eval_script", "eval_type", "log_parser"):
        checks[f] = {"present": f in record,
                     "type": type(record.get(f)).__name__,
                     "nonempty": bool(str(record.get(f, "")).strip())}
    for f in ("FAIL_TO_PASS", "PASS_TO_PASS"):
        v = record.get(f)
        checks[f] = {"present": f in record,
                     "type": type(v).__name__,
                     "is_list_of_str": isinstance(v, list)
                     and all(isinstance(x, str) for x in v),
                     "count": len(v) if isinstance(v, list) else None}
    return {"instance_id": record.get("instance_id"),
            "field_checks": checks}


def reject_startup_command(config: dict) -> None:
    """env_startup_command renders the ENTIRE instance dict (incl. reference
    answers) into Jinja context; the pilot must keep it unset."""
    if (config.get("run", {}) or {}).get("env_startup_command"):
        raise PreparationError(
            "run.env_startup_command must stay unset: it renders the whole "
            "instance record (including reference answers) into templates")


# ---------------------------------------------------------------------------
# A2: image field adaptation
# ---------------------------------------------------------------------------

@dataclass
class ImagePlan:
    mini_image: str
    evaluator_image: str
    match: bool
    mini_source: str  # "image_name" | "docker_image" | "derived_from_instance_id"
    digest: str | None = None  # None until pinned/verified; never fabricated
    status: str = "unverified"  # unverified | mismatch | ready


def derive_mini_image(record: dict) -> tuple[str, str]:
    """Replicate mini 2.4.6 get_swebench_docker_image_name semantics.

    Reads image_name then docker_image; derives from instance_id otherwise.
    Conflicting values in both fields are rejected.
    """
    image_name = record.get("image_name")
    docker_image = record.get("docker_image")
    if image_name is not None and docker_image is not None and image_name != docker_image:
        raise PreparationError(
            f"conflicting image_name/docker_image: {image_name!r} vs {docker_image!r}")
    if image_name:
        return str(image_name), "image_name"
    if docker_image:
        return str(docker_image), "docker_image"
    iid = record.get("instance_id") or ""
    if not iid:
        raise PreparationError("cannot derive image: instance_id missing")
    derived = f"docker.io/swebench/sweb.eval.x86_64.{iid.replace('__', '_1776_')}:latest".lower()
    return derived, "derived_from_instance_id"


def _normalize_image_ref(ref: str) -> str:
    """Normalize a full image reference for comparison.

    Only one implicit-prefix equivalence is allowed: docker.io/ is the Docker
    Hub default and may be absent. Registry host + namespace + repo + tag
    must otherwise match exactly.
    """
    ref = ref.strip().lower()
    if ref.startswith("docker.io/"):
        ref = ref[len("docker.io/"):]
    # docker hub official images: single-segment repo implies library/
    first = ref.split("/", 1)[0]
    if "." not in first and ":" not in first and "/" not in ref:
        ref = "library/" + ref
    return ref


def image_plan(record: dict) -> ImagePlan:
    mini_image, source = derive_mini_image(record)
    evaluator_image = record.get("image")
    if not isinstance(evaluator_image, str) or not evaluator_image.strip():
        raise PreparationError("record lacks evaluator image field")
    # Full-reference comparison (registry+namespace+repo+tag); only the
    # docker.io default-prefix equivalence is allowed. Digest pinning stays
    # an explicit first-run prerequisite regardless of name equality.
    match = (_normalize_image_ref(mini_image) == _normalize_image_ref(evaluator_image))
    return ImagePlan(mini_image=mini_image, evaluator_image=evaluator_image,
                     match=match, mini_source=source,
                     digest=None, status="unverified")


def local_task_input_route(record_path: Path, record_sha256: str) -> dict:
    """Fixed local single-task input route.

    mini's CLI consumes HF datasets; the pilot must not re-download the full
    dataset. The route therefore targets a minimal local dataset-shaped file
    (a wrapper concern at run time) OR swebench_single-style single-instance
    entry. Interface recorded; no wrapper is implemented in this batch.
    """
    return {
        "route": "local_single_record_wrapper",
        "record_locator": str(record_path),
        "record_sha256": record_sha256,
        "wrapper_status": "not_implemented_this_batch",
        "interface": ("future wrapper loads the validated record and exposes "
                      "problem_statement to mini's agent; mini's dataset "
                      "loading path is bypassed; no HF re-download"),
        "env_startup_command": "must_stay_unset",
    }


# ---------------------------------------------------------------------------
# A3: model / cost / retry policy (synthetic-config checks)
# ---------------------------------------------------------------------------

@dataclass
class ModelPlan:
    model_name: str
    provider_protocol_class: str
    api_base_env: str  # NAME of env var only; value never handled here
    auth_env: str      # NAME of env var only
    model_kwargs_allowed: tuple[str, ...] = ("drop_params",)
    litellm_routing: str = "unverified"
    forward_env_allowlist: tuple[str, ...] = field(default_factory=tuple)


_ENV_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_URL_USERINFO_RE = re.compile(r"^[a-zA-Z][a-zA-Z0-9+.-]*://[^/@\s]+@")
_URL_SCHEME_RE = re.compile(r"^[a-zA-Z][a-zA-Z0-9++.-]*://")


def _validate_env_name(value: str, label: str) -> str:
    """Env-var references must be valid NAMES — 'NAME=value' or other payload
    content is rejected: values belong to run-time injection, never here."""
    if not isinstance(value, str) or not _ENV_NAME_RE.match(value):
        raise PreparationError(
            f"environment.{label} must be a valid environment variable NAME "
            f"(got payload-like or invalid value); run-time values are injected separately")
    return value


def _reject_url_values(node: Any, path: str = "") -> None:
    """Reject strings that look like URLs carrying userinfo (user:pass@host)."""
    if isinstance(node, str):
        if _URL_USERINFO_RE.match(node):
            raise PreparationError(
                f"URL with userinfo rejected at {path}; endpoint details are "
                "run-time env injections, never inline values")
    elif isinstance(node, dict):
        for k, v in node.items():
            _reject_url_values(v, f"{path}.{k}")
    elif isinstance(node, list):
        for i, v in enumerate(node):
            _reject_url_values(v, f"{path}[{i}]")


def check_model_config(config: dict) -> ModelPlan:
    """Validate a credential-free model config (synthetic in tests).

    Rejects any sensitive key anywhere in the structure; api_base and auth
    must be env-var references (names), never inline values.
    """
    _check_no_secrets(config)
    model = config.get("model", {})
    name = model.get("model_name")
    if not isinstance(name, str) or not name.strip():
        raise PreparationError("model.model_name missing")
    kwargs = model.get("model_kwargs", {})
    if not isinstance(kwargs, dict):
        raise PreparationError("model.model_kwargs must be a mapping")
    for k in kwargs:
        if k not in ("drop_params", "parallel_tool_calls"):
            raise PreparationError(
                f"model_kwargs key {k!r} not in allowed set; api_base/api_key "
                "belong to run-time env injection, not model_kwargs")
    _reject_url_values(config)
    env = config.get("environment", {})
    api_base_env = _validate_env_name(env.get("api_base_env"), "api_base_env")
    auth_env = _validate_env_name(env.get("auth_env"), "auth_env")
    for fwd in env.get("forward_env", []):
        _validate_env_name(fwd, "forward_env entry")
    if config.get("run", {}).get("env_startup_command"):
        raise PreparationError("run.env_startup_command must stay unset")
    forward = env.get("forward_env", [])
    if not isinstance(forward, list) or len(forward) != len(set(forward)):
        raise PreparationError("environment.forward_env must be a list of unique env var names")
    return ModelPlan(
        model_name=name,
        provider_protocol_class=config.get("provider_protocol_class", "openai_compatible"),
        api_base_env=api_base_env, auth_env=auth_env,
        model_kwargs_allowed=tuple(sorted(kwargs)),
        litellm_routing=model.get("litellm_routing", "unverified"),
        forward_env_allowlist=tuple(sorted(forward)),
    )


# Usage fields safe to persist: numeric counters only. Raw usage dicts from
# third-party responses may echo credentials or endpoint details in arbitrary
# keys — those never reach records/reports.
USAGE_WHITELIST = ("prompt_tokens", "completion_tokens", "total_tokens",
                   "input_tokens", "output_tokens", "cached_tokens",
                   "reasoning_tokens", "completion_tokens_details",
                   "prompt_tokens_details")

_ERROR_TYPE_WHITELIST = frozenset({
    "AuthenticationError", "PermissionDeniedError", "NotFoundError",
    "RateLimitError", "TimeoutError", "TimeoutExpired", "ConnectionError",
    "APIConnectionError", "APIStatusError", "InternalServerError",
    "BadRequestError", "UnprocessableEntityError", "ContextWindowExceededError",
    "UnsupportedParamsError", "ValueError", "TypeError", "KeyError",
    "RuntimeError", "OSError", "JSONDecodeError", "FormatError",
    "LimitsExceeded", "TimeExceeded", "RepeatedFormatError",
})

# Nested usage detail keys safe to keep (OpenAI-style token detail shapes).
USAGE_DETAIL_WHITELIST = ("cached_tokens", "reasoning_tokens",
                          "accepted_prediction_tokens",
                          "rejected_prediction_tokens",
                          "audio_tokens", "text_tokens")


def _sanitize_usage(usage: dict | None) -> dict | None:
    """Whitelist-project usage; top-level AND nested keys use fixed sets.

    Arbitrary nested key names (potential credential/payload echoes) are
    dropped even when their values are numeric.
    """
    if not isinstance(usage, dict):
        return None
    out = {}
    for k in USAGE_WHITELIST:
        v = usage.get(k)
        if isinstance(v, (int, float)) and not isinstance(v, bool):
            out[k] = v
        elif isinstance(v, dict):
            sub = {kk: v[kk] for kk in USAGE_DETAIL_WHITELIST
                   if isinstance(v.get(kk), (int, float)) and not isinstance(v.get(kk), bool)}
            if sub:
                out[k] = sub
    return out or None


def _sanitize_error(error: str | None) -> str | None:
    """Fixed-whitelist error classification; never extract from raw text.

    Unrecognized errors (including arbitrary strings that merely look like
    identifiers) collapse to a generic 'error' label.
    """
    if not error:
        return None
    head = error.split(":", 1)[0].strip() if ":" in error else error.strip()
    # exact match against the known-exception whitelist only
    cls = head if head in _ERROR_TYPE_WHITELIST else None
    return (cls or "error") + ":<sanitized>"


@dataclass
class CallRecord:
    """One model call recorded by the fake transport (for tests/records)."""
    request_id: str
    ok: bool
    usage: dict | None
    cost: float | None          # None means unknown — never coerced to 0
    cost_status: str            # "unknown" | "computed" | "error"
    error: str | None = None


def record_call(response_usage: dict | None, *,
                cost_fn: Callable[[], float] | None,
                error: str | None = None,
                request_id: str = "") -> CallRecord:
    """Record one call preserving unknowns.

    request_id is supplied by the caller (transport/loop) and preserved.
    usage is whitelist-projected; error is sanitized to a type-level summary.
    Native cost=0.0 is kept as a source value with cost_status='computed';
    it is never reinterpreted as 'free'. Missing usage stays None. A failed
    cost calculation must not discard an already-obtained response/usage.
    """
    ok = error is None
    cost = None
    cost_status = "unknown"
    if cost_fn is not None and ok:
        try:
            cost = cost_fn()
            cost_status = "computed"
        except Exception:  # noqa: BLE001 — record, don't discard
            cost = None
            cost_status = "error"
    return CallRecord(request_id=request_id or "", ok=ok,
                      usage=_sanitize_usage(response_usage),
                      cost=cost, cost_status=cost_status,
                      error=_sanitize_error(error))


@dataclass
class RetryPolicy:
    attempt_limit: int          # task-level attempts (pilot: 1)
    outer_auto_retry: int       # our wrapper's automatic retries (pilot: 0)
    sdk_retry_config: str       # mini/litellm internal retry — location noted
    sdk_retry_note: str


def retry_policy() -> RetryPolicy:
    """Three-layer retry disposition with implementation locations.

    mini 2.4.6 defaults to tenacity stop_after_attempt(10) via
    MSWEA_MODEL_RETRY_STOP_AFTER_ATTEMPT. Writing outer auto_retries=0 does
    NOT disable that; the env var must be set at run time — an explicit
    pre-run check item, not something this batch can confirm offline.
    """
    return RetryPolicy(
        attempt_limit=1,
        outer_auto_retry=0,
        sdk_retry_config="MSWEA_MODEL_RETRY_STOP_AFTER_ATTEMPT=1 (proposed; unverified offline)",
        sdk_retry_note=("mini default is 10 attempts (tenacity, models/utils/retry.py "
                        "F-RETRY-001); disabling requires the env var at run time; "
                        "cannot be confirmed without installation"),
    )


def limits_plan(config: dict) -> dict:
    """Aggregate limits; bundled cost_limit is mini's default, NOT a user budget.

    User declined a monetary ceiling; unknown price => cost tracking cannot
    enforce limits (F-COST-001) — recorded as 'ineffective_without_pricing'.
    """
    agent = config.get("agent", {})
    return {
        "agent_step_limit": agent.get("step_limit", 250),
        "agent_cost_limit_source": "mini bundled default 3.0 USD (not a user budget)",
        "agent_cost_limit_effective": "ineffective_without_pricing"
        if config.get("model", {}).get("cost_tracking") == "ignore_errors"
        else "depends_on_registry_pricing",
        "wall_time_limit_seconds": agent.get("wall_time_limit_seconds", 0),
        "per_command_timeout_s": config.get("environment", {}).get("timeout", 60),
        "global_limits": {"MSWEA_GLOBAL_COST_LIMIT": "unset (proposed None)",
                          "MSWEA_GLOBAL_CALL_LIMIT": "unset (proposed None)"},
        "user_monetary_ceiling": "explicitly_not_set_by_user",
        "cost_status_policy": "unknown -> amount=null, status=unknown, usage recorded",
    }


# ---------------------------------------------------------------------------
# Preparation result assembly
# ---------------------------------------------------------------------------

@dataclass
class PreparationResult:
    preparation_status: str
    agent_view: dict
    environment_view: dict
    evaluator_view: dict
    image: ImagePlan
    task_route: dict
    model_plan: ModelPlan | None
    limits: dict
    retry: RetryPolicy
    runtime_compatibility: list[str]      # unverified items
    execution_authorized: bool = False
    next_authorizations: list[str] = field(default_factory=list)


def prepare(record_path: Path, config: dict, *,
            expected_instance_id: str,
            expected_sha256: str | None = None) -> PreparationResult:
    """Full offline preparation over the fixed task record + synthetic config."""
    record = load_task_record(record_path,
                              expected_instance_id=expected_instance_id,
                              expected_sha256=expected_sha256)
    reject_startup_command(config)
    plan = check_model_config(config)
    img = image_plan(record)
    route = local_task_input_route(record_path, expected_sha256 or "")
    unverified = [
        f"litellm routing for gateway ({plan.litellm_routing})",
        "image digest not pinned (both tools on :latest tags)",
        "image field equality is tag-level only" if not img.match
        else "image names match at tag level; digest still unpinned",
        "mini internal retry disabled only via env var at run time",
        "credential persistence by third-party logs unverified dynamically",
        "Docker daemon / image availability not checked here",
    ]
    return PreparationResult(
        preparation_status="READY_FOR_REVIEW",
        agent_view=agent_view(record),
        environment_view=environment_view(record),
        evaluator_view=evaluator_view(record),
        image=img, task_route=route, model_plan=plan,
        limits=limits_plan(config), retry=retry_policy(),
        runtime_compatibility=unverified,
        execution_authorized=False,
        next_authorizations=[
            "install mini-swe-agent 2.4.6 + deps in isolated env",
            "model connectivity smoke (1 request, no task content)",
            "real run django__django-16485 (single attempt)",
        ],
    )
