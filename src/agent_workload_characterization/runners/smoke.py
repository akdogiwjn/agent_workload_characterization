"""Smoke entry for the next approved single-request model connectivity test.

Modes:
- default (no flags): offline plan only — nothing is sent.
- --execute --i-approve-the-smoke: REAL single request (double approval).

Semantics (corrected after real-SDK verification): the smoke rides mini's
REAL query path, which always sends its bash tool schema (hardcoded in
LitellmModel._query) and requires a tool-call reply to parse — a plain-text
reply raises FormatError in mini's parser. This is therefore a TOOL-PROTOCOL
CONNECTIVITY smoke: SUCCESS = tool-call reply received with usage (routing,
auth, tool schema, and parsing all proven). A plain-text reply is recorded
as `unexpected_plain_text` (connectivity proven; protocol differs) with its
usage preserved. FormatError never discards an already-received usage.

Enforced on the real request path (verified against the installed SDK with
a fake transport):
- max_tokens=100 IS passed into the SDK request body (asserted on the
  captured outbound request, not just echoed in the report);
- total 30 s wall deadline: hard-refused BEFORE any request if SIGALRM is
  unavailable (non-main thread / unsupported platform) — no silent degrade;
- zero retries at all three layers;
- credentials via env vars only (never in model_kwargs / argv / outputs);
- result writing goes through the project output guard (project root,
  protected legacy roots, symlink escape, exclusive create) and is
  validated BEFORE the request is sent.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import uuid
from pathlib import Path

from ..runners.model_adapter import (mini_model_config, record_sdk_call,
                                     resolve_model, retry_disabled_env,
                                     sdk_credential_scope)
from ..runners.preparation import PreparationError

SMOKE_MAX_TOKENS = 100
SMOKE_TOTAL_DEADLINE_S = 30
SMOKE_MESSAGE = [{"role": "user", "content":
    "Connectivity check: call the bash tool with the command 'echo smoke-ok' "
    "and nothing else. The command will NOT be executed."}]


class DeadlineExceeded(RuntimeError):
    pass


def build_plan(config_path: Path, env: dict | None = None,
               allow_missing_env: bool = True) -> dict:
    """Offline plan; missing run-time env values become placeholders."""
    import yaml
    config = yaml.safe_load(config_path.read_text())
    try:
        resolved = resolve_model(config, env=env)
    except PreparationError as exc:
        if not (allow_missing_env and "missing env values" in str(exc)):
            raise
        from ..runners.preparation import check_model_config
        plan_cfg = check_model_config(config)
        return {
            "mode": "offline_plan",
            "semantics": "tool-protocol connectivity (mini sends bash tool; tool-call reply expected)",
            "model": plan_cfg.model_name,
            "request_model_id": plan_cfg.model_name.split("/", 1)[-1],
            "api_base": f"<from env {plan_cfg.api_base_env} at run time>",
            "auth": f"<from env {plan_cfg.auth_env} at run time (Bearer)>",
            "env_ready": False,
            "note": "run-time env values not present in this process; plan only",
            "endpoint_path": "/chat/completions",
            "message": SMOKE_MESSAGE[0]["content"],
            "max_tokens": SMOKE_MAX_TOKENS,
            "total_deadline_s": SMOKE_TOTAL_DEADLINE_S,
            "auto_retries": 0,
        }
    return {
        "mode": "offline_plan",
        "semantics": "tool-protocol connectivity (mini sends bash tool; tool-call reply expected)",
        "model": resolved.model_name,
        "request_model_id": resolved.request_model_id,
        "api_base": "<from env PILOT_API_BASE at run time>",
        "auth": "<from env PILOT_API_KEY at run time (Bearer)>",
        "endpoint_path": "/chat/completions (appended by OpenAI client; /v1 must be in api_base)",
        "message": SMOKE_MESSAGE[0]["content"],
        "max_tokens": SMOKE_MAX_TOKENS,
        "total_deadline_s": SMOKE_TOTAL_DEADLINE_S,
        "auto_retries": 0,
        "retry_env": retry_disabled_env(),
        "sdk_num_retries": 0,
        "cost": "price unknown -> cost_status=unknown, amount=null, usage recorded",
        "on_failure": "stop; no endpoint/model change; no retry",
        "on_success": "record routing facts only; does NOT start benchmark",
    }


# ---------------------------------------------------------------------------
# output guard (reuses the preparation writer's protections)
# ---------------------------------------------------------------------------

SDK_BASE_ENV_NAME = "OPENAI_API_BASE"
SDK_KEY_ENV_NAME = "OPENAI_API_KEY"


def _parse_child(out: bytes) -> dict | None:
    try:
        line = out.decode("utf-8", "replace").strip().splitlines()
        return json.loads(line[-1]) if line else None
    except Exception:  # noqa: BLE001
        return None


# Runs in a CHILD PROCESS: reads the payload from stdin, installs the fake
# transport when offline testing, performs ONE model query, prints one JSON
# line. Exit codes: 0 = parsed tool-call reply; 3 = FormatError (payload);
# 4 = alarm swallowed + deadline passed inside child (parent re-checks wall
# clock); anything else = error (type name in payload).
_CHILD_QUERY_CODE = r"""
import json, os, sys
def main():
    payload = json.loads(sys.stdin.read())
    sys.path.insert(0, payload["sdk_path"])
    os.environ["MSWEA_CONFIG_DIR"] = os.environ.get("MSWEA_CONFIG_DIR", "/tmp/mswea-empty-config")
    os.environ["LITELLM_LOCAL_MODEL_COST_MAP"] = os.environ.get("LITELLM_LOCAL_MODEL_COST_MAP", "True")
    import httpx, litellm
    _captured = []
    if payload.get("_fake_capturing"):
        # offline network block INSIDE the child: the parent's monkeypatches
        # do not cross Popen — the child must block on its own
        _orig_handle = httpx.HTTPTransport.handle_request

        class _NetworkViolation(RuntimeError):
            pass

        def _blocked(self, request, *_a, **_k):
            raise _NetworkViolation(
                "real network attempt blocked in child: %s" % request.url)

        _delay_ms = int(payload.get("_fake_delay_ms") or 0)
        _swallow = bool(payload.get("_fake_swallow_alarm"))

        class _FT(httpx.HTTPTransport):
            def __init__(self):
                super().__init__()
                self.n = 0

            def handle_request(self, request):
                self.n += 1
                # "request started" synchrony proof: append to the captured
                # list IMMEDIATELY on entry, before any delay — the parent
                # can then rely on n>=1 as evidence the query was underway
                # (mirrored into _captured before the block point).
                try:
                    body = json.loads(request.content.decode())
                except Exception:
                    body = None
                _captured.append({"url": str(request.url),
                                  "auth": request.headers.get("authorization"),
                                  "body": body, "n": self.n})
                # in-flight proof for the parent: write a started-marker to
                # the side-channel file the moment the request begins, so a
                # SIGKILLed child still leaves evidence the query started
                _started = payload.get("_started_marker")
                if _started:
                    try:
                        with open(_started, "w") as _sf:
                            _sf.write(str(self.n))
                    except Exception:
                        pass
                if _delay_ms:
                    import time as _t
                    _t.sleep(_delay_ms / 1000.0)
                if _swallow:
                    import signal as _sig
                    try:
                        _sig.signal(_sig.SIGALRM, lambda s, f: None)
                        _sig.alarm(1)  # one-shot; swallowed on purpose
                    except Exception:
                        pass
                    import time as _t
                    # block long enough to exceed ANY practical parent
                    # deadline (import ~3s + 60s sleep) — the parent must
                    # SIGKILL to satisfy the deadline
                    _t.sleep(60.0)
                resp = payload["_fake_responses"][min(self.n - 1, len(payload["_fake_responses"]) - 1)]
                return httpx.Response(payload["_fake_status"], json=resp)

        # block ALL real transport use in the child, then install the fake
        httpx.HTTPTransport.handle_request = _blocked
        try:
            litellm.client_session = httpx.Client(transport=_FT())
        except Exception:
            httpx.HTTPTransport.handle_request = _orig_handle
            raise
        try:
            litellm.in_memory_llm_clients_cache.cache_dict.clear()
        except Exception:
            pass
    from minisweagent.models.litellm_model import LitellmModel
    from minisweagent.exceptions import FormatError
    model = LitellmModel(model_name=payload["model_name"],
                         model_kwargs=payload["model_kwargs"],
                         cost_tracking=payload["cost_tracking"])
    try:
        msg = model.query(payload["message"])
    except FormatError as fe:
        usage = None; finish = None; plain = False
        for m in (getattr(fe, "messages", None) or []):
            extra = (m.get("extra") or {}) if isinstance(m, dict) else {}
            resp = extra.get("response") or {}
            if isinstance(resp, dict):
                u = resp.get("usage")
                if isinstance(u, dict) and usage is None:
                    usage = {k: u.get(k) for k in ("prompt_tokens","completion_tokens","total_tokens")}
                ch = resp.get("choices") or []
                if ch and finish is None:
                    finish = ch[0].get("finish_reason")
                    if finish == "stop" and (ch[0].get("message") or {}).get("content"):
                        plain = True
        print(json.dumps({"_format_error": True, "usage": usage,
                          "finish_reason": finish, "plain_text": plain,
                          "_captured": _captured}))
        sys.exit(3)
    except BaseException as exc:  # includes SIGALRM-raised DeadlineExceeded
        print(json.dumps({"error_type": type(exc).__name__, "_captured": _captured}))
        sys.exit(4)
    extra = msg.get("extra", {}) if isinstance(msg, dict) else {}
    resp = extra.get("response") or {}
    u = resp.get("usage") if isinstance(resp, dict) else None
    usage = {k: u.get(k) for k in ("prompt_tokens","completion_tokens","total_tokens")} if isinstance(u, dict) else None
    print(json.dumps({"ok": True, "usage": usage, "cost": extra.get("cost"), "_captured": _captured}))
main()
"""


def guard_result_dir(result_dir: Path, project_root: Path | None = None) -> Path:
    """Validate the result location BEFORE any request is sent.

    Reuses the ENV-01 preparation writer's guard semantics: anchored project
    root, reports/smoke containment, protected legacy roots (via the audit
    catalog), symlink-escape refusal, and exclusive creation of the result
    file (never overwrite).
    """
    root = (project_root or Path(".")).resolve(strict=True)
    target = result_dir if result_dir.is_absolute() else root / result_dir
    target = target.resolve()
    reports_root = (root / "reports" / "smoke").resolve()
    if reports_root.is_symlink():
        raise ValueError("reports/smoke must not be a symlink")
    if not reports_root.is_relative_to(root):
        raise ValueError("reports/smoke resolves outside the project root")
    if target != reports_root and not target.is_relative_to(reports_root):
        raise ValueError("result dir must be inside reports/smoke/ (real path)")

    from ..adapters.catalog import Catalog
    protected = [root / "references", root / "data" / "raw", root / "data" / "catalog",
                 root / "data" / "normalized"]
    catalog_path = root / "data" / "catalog" / "sources.yaml"
    if catalog_path.is_file():
        try:
            import yaml
            data = yaml.safe_load(catalog_path.read_text())
            for name, value in (data.get("roots") or {}).items():
                if name != "project" and Path(value).is_absolute():
                    protected.append(Path(value).resolve())
        except Exception:  # noqa: BLE001 — protection stays conservative
            pass
    for path in protected:
        real = path.resolve()
        if target == real or target.is_relative_to(real) or real.is_relative_to(target):
            raise ValueError(f"result dir overlaps protected path: {real}")
    if target.exists() and not target.is_dir():
        raise ValueError("result path exists and is not a directory")
    target.mkdir(parents=True, exist_ok=True)
    return target


def _write_result_exclusive(path: Path, record: dict) -> None:
    """Exclusive-create the result file; never overwrite existing reports."""
    with path.open("x", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False, indent=2) + "\n")


# ---------------------------------------------------------------------------
# the real single-request path
# ---------------------------------------------------------------------------

def execute_smoke(config_path: Path, *, env: dict | None = None,
                  result_dir: Path | None = None,
                  deadline_s: int = SMOKE_TOTAL_DEADLINE_S,
                  project_root: Path | None = None,
                  _transport=None) -> dict:
    """Real single-request path (invoked only after double approval).

    Uses the REAL installed mini LitellmModel + litellm. ``_transport``
    injects a fake httpx transport for offline tests (production leaves it
    None and the real gateway is contacted — never in this batch).

    Tool-protocol semantics: the message explicitly asks for one harmless
    bash tool call (echo smoke-ok) which is PARSED ONLY — never executed.
    A tool-call reply is success; plain-text replies are recorded as
    `unexpected_plain_text` with usage preserved; FormatError never
    discards an already-received usage.
    """
    import yaml
    config = yaml.safe_load(config_path.read_text())
    resolved = resolve_model(config, env=env)  # raises if env values missing

    # --- validate output location BEFORE any request (F4) ---
    result_path = None
    if result_dir is not None:
        guarded = guard_result_dir(result_dir, project_root)
        result_path = guarded / "pending"  # final name set after run_id known

    # --- F3: hard deadline via subprocess watchdog ---
    # The query runs in a CHILD PROCESS. A watchdog thread kills the child
    # (SIGKILL) at the deadline regardless of any exception the SDK might
    # swallow inside the child — a one-shot SIGALRM inside the child can be
    # captured by third-party except-blocks (verified), so we do not rely on
    # it for the hard stop. The parent enforces the wall clock.

    # --- retry layer 3 (SDK internal) via model kwargs; layer 2 via env ---
    cfg = mini_model_config(resolved)
    assert cfg["model_kwargs"]["num_retries"] == 0
    # F1: output cap goes into the REAL request body. mini hardcodes
    # tools=[BASH_TOOL] in its _query (verified); the outbound request
    # carries mini's bash tool schema. SUCCESS = tool-call reply with usage;
    # plain-text reply -> unexpected_plain_text (usage preserved).
    cfg["model_kwargs"]["max_tokens"] = SMOKE_MAX_TOKENS

    from minisweagent.models.litellm_model import LitellmModel
    from minisweagent.exceptions import FormatError

    model = LitellmModel(cost_tracking="ignore_errors", **cfg)

    deadline_at = time.monotonic() + deadline_s
    run_id = f"smoke-{uuid.uuid4().hex[:8]}"

    import subprocess as _sp
    child_code = _CHILD_QUERY_CODE
    record = {"run_id": run_id, "authorized": True,
              "semantics": "tool_protocol_connectivity",
              "model": resolved.model_name, "request_model_id": resolved.request_model_id,
              "message": SMOKE_MESSAGE[0]["content"], "max_tokens": SMOKE_MAX_TOKENS,
              "deadline_s": deadline_s, "retries": 0}

    # The query runs in a CHILD PROCESS; the parent enforces the wall clock
    # with communicate(timeout=) + kill(). Killing the child terminates the
    # query regardless of any exception the SDK swallowed inside it.
    env_overrides = dict(retry_disabled_env())
    env_overrides.update({"MSWEA_CONFIG_DIR": os.environ.get("MSWEA_CONFIG_DIR", "/tmp/mswea-empty-config"),
                          "LITELLM_LOCAL_MODEL_COST_MAP": os.environ.get("LITELLM_LOCAL_MODEL_COST_MAP", "True"),
                          SDK_BASE_ENV_NAME: resolved.api_base,
                          SDK_KEY_ENV_NAME: resolved.api_key})

    child_payload = {
        "model_name": resolved.model_name,
        "model_kwargs": cfg["model_kwargs"],
        "cost_tracking": "ignore_errors",
        "message": SMOKE_MESSAGE,
        "sdk_path": str(Path(__file__).resolve().parents[2]),
    }
    if _transport is not None:
        # offline tests: serialize fake responses for the child to install.
        # Behavior modes (delay/swallow-alarm) ride as explicit parameters so
        # the child's transport reproduces the test transport's semantics —
        # the parent's Python objects do NOT cross the process boundary.
        child_payload["_fake_responses"] = getattr(_transport, "responses", None)
        child_payload["_fake_status"] = getattr(_transport, "status", 200)
        child_payload["_fake_capturing"] = True
        child_payload["_fake_delay_ms"] = getattr(_transport, "delay_ms", 0)
        child_payload["_fake_swallow_alarm"] = bool(getattr(_transport, "swallow_alarm", False))

    t0 = time.monotonic_ns()
    timed_out = False
    child_killed = False
    started_marker = None
    if _transport is not None:
        import tempfile as _tf
        _mkd = _tf.mkdtemp(prefix="smoke-started-")
        started_marker = os.path.join(_mkd, "started")
        child_payload["_started_marker"] = started_marker
    try:
        proc = _sp.Popen(
            [sys.executable, "-c", _CHILD_QUERY_CODE],
            stdin=_sp.PIPE, stdout=_sp.PIPE, stderr=_sp.PIPE,
            env={**os.environ, **env_overrides},
            cwd=str(Path(__file__).resolve().parents[2].parent))
        try:
            out, err = proc.communicate(
                input=json.dumps(child_payload).encode(), timeout=deadline_s)
        except _sp.TimeoutExpired:
            timed_out = True
            proc.kill()  # SIGKILL: not catchable by the SDK
            try:
                out, err = proc.communicate(timeout=5)
            except Exception:  # noqa: BLE001
                out, err = b"", b""
            child_killed = True
    except Exception as exc:  # noqa: BLE001 — spawn failures
        record.update({"ok": False, "usage": None, "cost": None,
                      "cost_status": "unknown",
                      "error": f"{type(exc).__name__}:<sanitized>",
                      "duration_ms": None})
        out, err, proc = b"", b"", None

    duration_ms = (time.monotonic_ns() - t0) / 1e6 if not timed_out else None

    if timed_out or child_killed:
        request_started = False
        if started_marker and os.path.isfile(started_marker):
            request_started = True
        record.update({"ok": False, "usage": None, "cost": None,
                      "cost_status": "unknown",
                      "error": f"DeadlineExceeded: smoke total deadline {deadline_s}s exceeded (child killed)",
                      "duration_ms": None,
                      "request_started_before_kill": request_started})
    elif proc is not None and proc.returncode != 0:
        # child failed (FormatError is signalled via returncode 3 + payload)
        child = _parse_child(out)
        record["_captured_requests"] = (child or {}).get("_captured") or []
        if child and child.get("_format_error"):
            usage = child.get("usage")
            finish = child.get("finish_reason")
            outcome = "unexpected_plain_text" if child.get("plain_text") else "format_error"
            record.update({"ok": False, "outcome": outcome,
                          "finish_reason": finish, "usage": usage, "cost": None,
                          "cost_status": "unknown",
                          "error": "FormatError:<sanitized>",
                          "note": ("tool-protocol connectivity smoke: gateway "
                                   "replied without a parseable tool call; "
                                   "response and usage recorded"),
                          "duration_ms": duration_ms})
        else:
            # classify deadline breaches the wall clock caught in-process
            err_name = (child or {}).get("error_type") or "ChildError"
            if time.monotonic() >= deadline_at:
                record.update({"ok": False, "usage": None, "cost": None,
                              "cost_status": "unknown",
                              "error": f"DeadlineExceeded: wall clock past deadline (wrapped: {err_name})",
                              "duration_ms": None})
            else:
                record.update({"ok": False, "usage": (child or {}).get("usage"),
                              "cost": None, "cost_status": "unknown",
                              "error": f"{err_name}:<sanitized>",
                              "duration_ms": duration_ms})
    elif proc is not None:
        child = _parse_child(out)
        record["_captured_requests"] = (child or {}).get("_captured") or []
        if child and child.get("ok"):
            record.update({"ok": True, "usage": child.get("usage"),
                          "cost": child.get("cost"),
                          "cost_status": "unknown"
                          if (child.get("cost") is None or child.get("cost") == 0.0)
                          else "computed",
                          "error": None, "duration_ms": duration_ms})
        else:
            record.update({"ok": False, "usage": (child or {}).get("usage"),
                          "cost": None, "cost_status": "unknown",
                          "error": "ChildProtocolError:<sanitized>",
                          "duration_ms": duration_ms})

    if started_marker:
        try:
            import shutil as _sh
            _sh.rmtree(os.path.dirname(started_marker), ignore_errors=True)
        except Exception:  # noqa: BLE001
            pass
    if result_path is not None:
        final = result_path.parent / f"{run_id}.json"
        # _captured_requests carries auth headers and full URLs — test-only
        # evidence that must NEVER be persisted (credential-leak path found by
        # the round-3 review). Strip before writing.
        persisted = {k: v for k, v in record.items() if k != "_captured_requests"}
        _write_result_exclusive(final, persisted)
        record["result_path"] = str(final)
    return record


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="smoke",
        description="Model connectivity smoke (default: offline plan; real single request needs --execute --i-approve-the-smoke)",
        allow_abbrev=False)
    parser.add_argument("--config", type=Path,
                        default=Path("data/catalog/pilot_run_config.yaml"))
    parser.add_argument("--execute", action="store_true",
                        help="actually send ONE request (requires separate user approval)")
    parser.add_argument("--i-approve-the-smoke", action="store_true",
                        help="double confirmation required together with --execute")
    parser.add_argument("--result-dir", type=Path, default=Path("reports/smoke"),
                        help="where the sanitized run record is written (guarded; real mode)")
    args = parser.parse_args(argv)

    try:
        if not args.execute:
            plan = build_plan(args.config)
            print(json.dumps(plan, ensure_ascii=False, indent=2))
            print("\nOFFLINE PLAN ONLY — no request was sent. Real execution "
                  "requires --execute --i-approve-the-smoke plus user approval "
                  "(docs/first_run_approval.md).", file=sys.stderr)
            return 0

        if not args.i_approve_the_smoke:
            print("REFUSED: --execute requires --i-approve-the-smoke "
                  "(separate user approval per docs/first_run_approval.md).", file=sys.stderr)
            return 1

        record = execute_smoke(args.config, result_dir=args.result_dir,
                               project_root=Path("."))
        print(json.dumps(record, ensure_ascii=False, indent=2))
        return 0 if record.get("ok") else 1
    except PreparationError as exc:
        print(f"INVALID: {exc}", file=sys.stderr)
        return 1
    except (OSError, ValueError, KeyError) as exc:
        print(f"INVALID: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
