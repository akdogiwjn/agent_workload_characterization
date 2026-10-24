"""Thin policy adapter around ViMax's native JSONL Agent entry.

This file is mounted read-only into the registered image. It removes tools
outside the planning-only authorization and adds the observed-total-token
soft gate to the image's shared request ledger before the first turn.
"""
from __future__ import annotations

import asyncio
import json
import os
import signal
import sys
import threading
import time
from pathlib import Path
from typing import Any

from agent_runtime.request_ledger import BudgetExceeded

WORK = Path("/workspace/attempt")
TASK_PATH = Path("/workspace/task-input.txt")
SCRIPT_PATH = Path("/workspace/registered-script.txt")
REQUIREMENTS_PATH = Path("/workspace/task-requirements.txt")
STYLE_PATH = Path("/workspace/task-style.txt")
SESSION_ID = "planning-validation-02"
EVENT_PATH = WORK / "agent-events.jsonl"


class Tee:
    def __init__(self, *streams):
        self.streams = streams

    def write(self, value):
        for stream in self.streams:
            stream.write(value)
        return len(value)

    def flush(self):
        for stream in self.streams:
            stream.flush()


def install_planning_policy(build_runtime):
    def build(*args, **kwargs):
        runtime = build_runtime(*args, **kwargs)
        registry = runtime.tool_registry
        permitted = {
            "read_file", "read_json", "list_files", "glob_files",
            "search_text", "memory_read", "todo_read",
            "vimax_narrative_planning",
        }
        registry._specs = {k: v for k, v in registry._specs.items()
                           if k in permitted}
        registry._aliases = {a: n for a, n in registry._aliases.items()
                             if n in permitted}
        forbidden = {"run_shell", "write_json", "vimax_render_video",
                     "vimax_novel_planning", "view_image", "memory_write",
                     "todo_write", "sleep"}
        if forbidden.intersection(registry._specs):
            raise RuntimeError("planning policy failed to remove forbidden tools")
        if "vimax_narrative_planning" not in registry._specs:
            raise RuntimeError("native narrative planning tool is unavailable")
        WORK.mkdir(parents=True, exist_ok=True)
        (WORK / "tool-policy.json").write_text(json.dumps({
            "allowed_tools": sorted(registry._specs),
            "blocked_tools": sorted(forbidden),
            "media_generation_cap": 0,
            "render_tool_registered": False,
            "run_shell_registered": False,
        }, indent=2) + "\n", encoding="utf-8")

        ledger = runtime.llm.ledger
        if ledger.path is None:
            raise RuntimeError("request ledger path is not configured")
        expected = {
            "llm_calls": 40,
            "llm_attempts": 40,
            "single_request_output_tokens": 8192,
            "image_generations": 0,
            "video_creates": 0,
        }
        for key, value in expected.items():
            if ledger.caps().get(key) != value:
                raise RuntimeError(f"unexpected {key} cap")
        if abs(float(ledger._deadline or 0) - 1800.0) > 0.001:
            raise RuntimeError("shared ledger deadline is not 1800 seconds")
        soft = int(os.environ.get(
            "VIMAX_BAILIAN_BUDGET_OBSERVED_TOTAL_TOKENS", "0"))
        if soft != 250_000:
            raise RuntimeError("observed total-token threshold is not frozen")

        usage_lock = threading.Lock()
        usage_total = {"total_tokens": 0, "unknown": False}
        original_close = ledger.close
        original_guard = ledger.guard
        original_reserve = ledger.reserve_and_open
        original_open = ledger.open

        def observe_close(request_id: str, status: str = "ok", **fields: Any):
            opened = ledger._open.get(request_id, {})
            result = original_close(request_id, status, **fields)
            usage = fields.get("usage")
            total = usage.get("total_tokens") if isinstance(usage, dict) else None
            if isinstance(total, int) and total >= 0:
                with usage_lock:
                    usage_total["total_tokens"] += total
            elif opened.get("op") == "llm_chat":
                with usage_lock:
                    usage_total["unknown"] = True
            return result

        def check_total_tokens():
            with usage_lock:
                observed = usage_total["total_tokens"]
                unknown = usage_total["unknown"]
            if unknown:
                raise BudgetExceeded(
                    "observed_total_tokens_unavailable", soft,
                    "a completed model response omitted total_tokens")
            if observed >= soft:
                raise BudgetExceeded(
                    "observed_total_tokens_soft", soft,
                    f"already_returned_total_tokens={observed}")

        def guarded_guard(key: str, n: int = 1):
            check_total_tokens()
            return original_guard(key, n)

        def guarded_reserve(kind: str, reservations: dict[str, int], **fields):
            check_total_tokens()
            return original_reserve(kind, reservations, **fields)

        def strict_open(kind: str, **fields):
            before = ledger.failure_state()["ledger_write_failures"]
            request_id = original_open(kind, **fields)
            after = ledger.failure_state()["ledger_write_failures"]
            if after != before:
                with ledger._lock:
                    ledger._open.pop(request_id, None)
                from agent_runtime.request_ledger import LedgerWriteError
                raise LedgerWriteError(
                    "outer request ledger open could not be persisted")
            return request_id

        ledger.close = observe_close
        ledger.guard = guarded_guard
        ledger.reserve_and_open = guarded_reserve
        ledger.open = strict_open
        original_failure_state = ledger.failure_state

        def enriched_failure_state():
            state = original_failure_state()
            with usage_lock:
                state["observed_total_tokens"] = usage_total["total_tokens"]
                state["observed_total_tokens_threshold"] = soft
                state["observed_total_tokens_unknown"] = usage_total["unknown"]
            return state

        ledger.failure_state = enriched_failure_state
        return runtime

    return build


def self_check() -> int:
    import agent_runtime
    original = agent_runtime.build_runtime
    agent_runtime.build_runtime = install_planning_policy(original)
    os.environ.setdefault("VIMAX_LLM_API_KEY", "offline-fake-key")
    os.environ.setdefault("VIMAX_LLM_MODEL", "qwen3.7-plus")
    os.environ.setdefault("VIMAX_LLM_BASE_URL",
                          "https://dashscope.aliyuncs.com/compatible-mode/v1")
    os.environ.setdefault("VIMAX_BAILIAN_EVENT_LOG", "/tmp/policy-check.jsonl")
    os.environ.setdefault("VIMAX_BAILIAN_BUDGET_LLM_CALLS", "40")
    os.environ.setdefault("VIMAX_BAILIAN_BUDGET_LLM_ATTEMPTS", "40")
    os.environ.setdefault("VIMAX_BAILIAN_BUDGET_SINGLE_REQUEST_OUTPUT_TOKENS", "8192")
    os.environ.setdefault("VIMAX_NARRATIVE_MAX_TOKENS", "8192")
    os.environ.setdefault("VIMAX_BAILIAN_BUDGET_IMAGE_GENERATIONS", "0")
    os.environ.setdefault("VIMAX_BAILIAN_BUDGET_VIDEO_CREATES", "0")
    os.environ.setdefault("VIMAX_BAILIAN_BUDGET_DEADLINE_SECONDS", "1800")
    os.environ.setdefault("VIMAX_BAILIAN_BUDGET_OBSERVED_TOTAL_TOKENS", "250000")
    runtime = agent_runtime.build_runtime("/workspace")
    names = {item["name"] for item in runtime.tool_registry.list_tools()}
    assert "vimax_narrative_planning" in names
    assert "vimax_render_video" not in names
    assert "run_shell" not in names and "write_json" not in names
    ledger = runtime.llm.ledger
    ledger.close("offline-self-check", "ok", usage={"total_tokens": 250_000})
    try:
        ledger.guard("llm_calls")
    except BudgetExceeded as exc:
        assert exc.key == "observed_total_tokens_soft"
    else:
        raise AssertionError("observed total-token threshold did not block")
    ledger.flush_state()
    if not ledger.path.is_file() or not ledger.path.with_suffix(
            ledger.path.suffix + ".state").is_file():
        raise AssertionError("ledger JSONL/state did not persist")
    print(json.dumps({"ok": True, "tool_names": sorted(names),
                      "observed_total_tokens":
                          ledger.failure_state()["observed_total_tokens"]}))
    return 0


async def run_native() -> int:
    import agent_runtime
    original = agent_runtime.build_runtime
    agent_runtime.build_runtime = install_planning_policy(original)
    import main_agent

    if not TASK_PATH.is_file() or not SCRIPT_PATH.is_file():
        raise RuntimeError("frozen task input or registered script is missing")
    prompt = TASK_PATH.read_text(encoding="utf-8")
    script_bytes = SCRIPT_PATH.read_bytes()
    expected_script_hash = os.environ.get("VIMAX_FROZEN_SCRIPT_SHA256", "")
    import hashlib
    actual_script_hash = hashlib.sha256(script_bytes).hexdigest()
    if not expected_script_hash or actual_script_hash != expected_script_hash:
        raise RuntimeError("registered script hash does not match frozen identity")
    requirements = REQUIREMENTS_PATH.read_text(encoding="utf-8")
    style = STYLE_PATH.read_text(encoding="utf-8")
    from agent_runtime.session_index import SessionIndex
    index = SessionIndex(".")
    if index.get(SESSION_ID) is not None:
        raise RuntimeError("fresh planning session already exists; refusing reuse")
    index.create(
        script=script_bytes.decode("utf-8"),
        planning_mode="script",
        user_requirement=requirements,
        style=style,
        session_id=SESSION_ID,
        project_name="VIMAX-PLANNING-VALIDATE-02",
    )
    os.environ["VIMAX_FIXED_SCRIPT_SESSION_ID"] = SESSION_ID
    os.environ["VIMAX_FIXED_SCRIPT_PATH"] = str(SCRIPT_PATH)
    WORK.mkdir(parents=True, exist_ok=True)
    (WORK / "session-initialized.json").write_text(json.dumps({
        "session_id": SESSION_ID, "planning_mode": "script",
        "script_sha256": actual_script_hash,
        "user_requirement_sha256": hashlib.sha256(requirements.encode("utf-8")).hexdigest(),
        "style_sha256": hashlib.sha256(style.encode("utf-8")).hexdigest(),
        "source_loaded_before_agent": True,
    }, indent=2) + "\n", encoding="utf-8")
    WORK.mkdir(parents=True, exist_ok=True)
    with EVENT_PATH.open("a", encoding="utf-8") as event_file:
        tee = Tee(sys.stdout, event_file)
        sys.stdout = tee
        try:
            rc = await main_agent.amain([
                "--jsonl", "--session", SESSION_ID, "--once", prompt,
            ])
            from plan_verifier import verify
            try:
                plan_result = verify(Path("/workspace"))
            except Exception as exc:
                plan_result = {"ok": False, "error_type": type(exc).__name__,
                               "error": str(exc)[:1000]}
            (WORK / "plan-check.json").write_text(
                json.dumps(plan_result, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8")
        finally:
            sys.stdout = tee.streams[0]
            try:
                from agent_runtime.request_ledger import get_ledger
                ledger = get_ledger()
                ledger.flush_state()
                (WORK / "ledger-state.json").write_text(json.dumps(
                    ledger.failure_state(), indent=2) + "\n")
            except Exception as exc:
                (WORK / "ledger-finalization-error.json").write_text(
                    json.dumps({"error_type": type(exc).__name__,
                                "message": str(exc)[:1000]}, indent=2) + "\n")
        (WORK / "COMPLETE").write_text(json.dumps({
            "status": "agent_finished", "returncode": rc,
            "t_monotonic": time.monotonic()}) + "\n")
        return int(rc)


def main() -> int:
    if "--self-check" in sys.argv:
        return self_check()
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(143))
    return asyncio.run(run_native())


if __name__ == "__main__":
    raise SystemExit(main())
