#!/usr/bin/env python3
"""VIDEO-USE-CODEX-BAILIAN-INTEGRATION-01: one real in-container Codex CLI
session on the Bailian route — verifying tool-call loop, CLI image viewing
(view_image) and native rollout persistence.

Prior verified facts (NOT re-tested): image/cgroup/sampling chain
(VIDEO-USE-ENV-01); Bailian Responses + qwen3.7-plus single-image
understanding (BAILIAN-VISION-SMOKE-01). This round adds: Bailian tool-call
loop through the REAL Codex CLI inside the task image, view_image usage, and
rollout wiring.

Budgets/guards: ONE real CLI session, wall <=300s; retries/stream-reconnect
disabled in the provider config (request_max_retries=0, stream_max_retries=0);
credential loaded from the registered file ONLY for the container env at
runtime — never into the image, workspace or reports; network needed only
for dashscope.aliyuncs.com (default bridge); no ElevenLabs, no video tasks,
no model/provider switch. Logical requests vs actual HTTP attempts: HTTP
count is NOT observable through the CLI -> recorded as unknown (never
faked); token usage from rollout token_count events is not a bill.

Judgement (semantic, not character-format): PASS requires REAL tool
execution evidence (exec event running probe_input.py + receipt.json on
disk + receipt echoed in the final answer), REAL view_image evidence
(rollout call with the image path) and a semantically correct image
description (colors/shapes/counts/sides, zh+en parsers). A final answer
without tool/view evidence never passes.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'scripts'), str(ROOT / 'src')]
import video_use_volcano_capability_01 as v01  # noqa: E402
import video_use_volcano_vision_01 as vision01  # noqa: E402
import bailian_vision_smoke_01 as bailian  # noqa: E402

INTEGRATION_DIR = ROOT / "env/video/video-use/codex-bailian-integration-01"
SESSION_DIR = INTEGRATION_DIR / "session-01"
REPORT_PATH = INTEGRATION_DIR / "verification.json"
IMAGE_TAG = "video-use-task:arm64-codex-bailian-v1"
BASE_IMAGE_TAG = "video-use-task:arm64-v1"
CREDENTIAL_FILE = Path("/home/lcq/.config/agent-workload-characterization/bailian.env")
CREDENTIAL_ENV = "DASHSCOPE_API_KEY"
SESSION_WALL_S = 300.0
SAMPLE_INTERVAL_S = 0.5
COLLECTION = "VIDEO-USE-CODEX-BAILIAN-INTEGRATION-01"

INSTRUCTION = (
    "In /task there is a script probe_input.py and an image at "
    "input/neutral-test.png. Do exactly this: "
    "1) Run the script with: python3 /task/probe_input.py — it writes a "
    "receipt file under /task/output/ and prints a receipt value. "
    "2) View the image /task/input/neutral-test.png using your view_image "
    "tool (do NOT read the image file as text or base64 yourself). "
    "3) Then answer with: (a) the exact receipt value printed by the "
    "script, and (b) a description of the image: the colors, shapes, the "
    "count of each kind, and which side (left or right) each kind is on. "
    "Do not modify anything outside /task.")

PROBE_SCRIPT = '''import json, time, uuid
from pathlib import Path
receipt = uuid.uuid4().hex
out = Path("/task/output/receipt.json")
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps({"receipt": receipt, "written_at_monotonic": time.monotonic()}))
print("RECEIPT:", receipt)
'''

_DANGEROUS_PATTERNS = (
    re.compile(r"(?i)\brm\s+-rf\s+/(?!task)"), re.compile(r"(?i)\bapt(-get)?\s+"),
    re.compile(r"(?i)\byum\s+install"), re.compile(r"(?i)\bsudo\b"),
    re.compile(r"(?i)\bcurl\b|\bwget\b"), re.compile(r"(?i)\bchmod\s+777\s+/"),
    re.compile(r"(?i)\bmkfs|\bdd\s+if="), re.compile(r"(?i)\bshutdown|\breboot"),
)


# --------------------------------------------------------------------------- #
# pure helpers (offline-testable)
# --------------------------------------------------------------------------- #

def build_codex_command() -> str:
    return ("codex exec --skip-git-repo-check --cd /task "
            "--dangerously-bypass-approvals-and-sandbox "
            "--model qwen3.7-plus --json "
            f"-o /task/final_message.txt -- {INSTRUCTION!r}")


_EXEC_TOOL_NAMES = {"exec_command", "shell", "exec", "local_shell",
                    "unified_exec"}


def parse_rollout(path: Path) -> dict:
    """Parse a native codex rollout JSONL into evidence groups (0.163
    shape: command execution appears as function_call name=exec_command;
    older shapes with event_msg exec_command_begin kept for compat)."""
    tool_calls, commands, messages, token_counts, session_meta = [], [], [], [], None
    if not path.is_file():
        return {"exists": False, "tool_calls": tool_calls, "commands": commands,
                "messages": messages, "token_counts": token_counts,
                "session_meta": session_meta}
    for line in path.read_text(errors="replace").splitlines():
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        rtype = record.get("type")
        payload = record.get("payload") or {}
        if rtype == "session_meta":
            session_meta = payload
        elif rtype in ("event_msg",):
            etype = payload.get("type")
            if etype in ("exec_command_begin", "exec_begin", "command_execution",
                         "unified_exec_begin"):
                commands.append(payload)
            if etype in ("token_count",):
                token_counts.append(payload)
        elif rtype in ("token_usage_record",):
            token_counts.append(payload)
        elif rtype == "response_item":
            if payload.get("type") == "function_call":
                name = payload.get("name", "")
                args_raw = payload.get("arguments") or "{}"
                try:
                    args = json.loads(args_raw)
                except json.JSONDecodeError:
                    args = {"raw": args_raw}
                tool_calls.append({"name": name, "arguments": args})
                if name in _EXEC_TOOL_NAMES:
                    commands.append({"tool": name, **args})
            if payload.get("type") == "message":
                texts = [c.get("text", "") for c in payload.get("content") or []
                         if isinstance(c, dict)]
                if texts:
                    messages.append({"role": payload.get("role"), "text": "\n".join(texts)})
    return {"exists": True, "tool_calls": tool_calls, "commands": commands,
            "messages": messages, "token_counts": token_counts,
            "session_meta": session_meta}


def find_rollout(sessions_dir: Path) -> Path | None:
    found = sorted(sessions_dir.rglob("rollout-*.jsonl"))
    return found[-1] if found else None


def tool_execution_evidence(rollout: dict, receipt_file_value: str | None,
                            final_text: str) -> dict:
    commands = [json.dumps(c, ensure_ascii=False) for c in rollout.get("commands", [])]
    ran_probe = any("probe_input.py" in c for c in commands)
    receipt_in_answer = bool(
        receipt_file_value and receipt_file_value in (final_text or ""))
    return {
        "exec_events_total": len(commands),
        "probe_script_execution_seen": ran_probe,
        "receipt_file_exists_with_value": bool(receipt_file_value),
        "receipt_echoed_in_final_answer": receipt_in_answer,
        "verdict": "PASS" if (ran_probe and receipt_file_value
                              and receipt_in_answer) else "FAIL",
    }


def image_viewing_evidence(rollout: dict, final_text: str, truth: dict) -> dict:
    view_calls = [tc for tc in rollout.get("tool_calls", [])
                  if tc["name"] == "view_image"
                  and "neutral-test.png" in str(tc["arguments"].get("path", ""))]
    described = describe_check(final_text or "", truth)
    return {
        "view_image_calls": [{"path": tc["arguments"].get("path")}
                             for tc in view_calls],
        "view_image_used": bool(view_calls),
        "description_check": described,
        "verdict": "PASS" if (view_calls and described["all_correct"]) else "FAIL",
    }


_EN_RES = (
    re.compile(r"(?i)(\d+)\s*(red|blue)\s*(circle|square)s?"),
    re.compile(r"(?i)(red|blue)\s*(circle|square)s?\D{0,16}?(\d+)"),
    re.compile(r"(?i)(red)\s+(?:circles?|shapes?)[^.]{0,30}?\b(left|right)\b"
               r"|(left|right)[^.]{0,20}?(red)\s+circles?"),
)


def describe_check(text: str, truth: dict) -> dict:
    """Semantic check of the image description (zh parser reused from
    BAILIAN-VISION-SMOKE-01 + en parser). Extra words never fail."""
    checks = {"red_count": None, "blue_count": None, "red_side": None}
    zh = bailian.parse_chinese_reply(text)
    if zh["red"] is not None and zh["blue"] is not None:
        checks["red_count"] = zh["red"] == truth["red_circles"]
        checks["blue_count"] = zh["blue"] == truth["blue_squares"]
    if zh["red_side"] is not None:
        checks["red_side"] = zh["red_side"] == truth["red_side"]
    if any(v is None for v in checks.values()):
        counts = {}
        for m in _EN_RES[0].finditer(text):
            counts.setdefault(m.group(2).lower(), int(m.group(1)))
        for m in _EN_RES[1].finditer(text):
            counts.setdefault(m.group(1).lower(), int(m.group(3)))
        if counts.get("red") is not None:
            checks["red_count"] = counts["red"] == truth["red_circles"]
        if counts.get("blue") is not None:
            checks["blue_count"] = counts["blue"] == truth["blue_squares"]
        if checks["red_side"] is None:
            # PRIMARY: "<side> side: [N] <color> <shape>" prefix structure —
            # the side label introduces its own color/shape (regression for
            # "Left side: 1 red circle / Right side: 3 blue squares")
            for m in re.finditer(r"(?i)\b(left|right)\s*side\s*[:\-]?\s*"
                                 r"(?:\*\*)?\s*(?:\d+\s+)?(?:\*\*)?\s*"
                                 r"(red|blue)\s+(?:circle|square)", text):
                side, color = m.group(1).lower(), m.group(2).lower()
                if color == "red":
                    checks["red_side"] = side == truth["red_side"]
                else:
                    checks["red_side"] = side != truth["red_side"]
                break
        if checks["red_side"] is None:
            for m in re.finditer(r"(?i)\b(red|blue)\s+(?:circles?|squares?)"
                                 r"[^.]{0,30}?\b(left|right)\b", text):
                side = m.group(2).lower()
                if m.group(1).lower() == "red":
                    checks["red_side"] = side == truth["red_side"]
                else:
                    checks["red_side"] = (side != truth["red_side"])
                break
    all_correct = all(v is True for v in checks.values())
    return {"checks": checks, "all_correct": all_correct,
            "note": "semantic; extra words never fail; unparseable -> not correct"}


def dangerous_command_audit(rollout: dict) -> dict:
    hits = []
    for c in rollout.get("commands", []):
        blob = json.dumps(c, ensure_ascii=False)
        for pattern in _DANGEROUS_PATTERNS:
            m = pattern.search(blob)
            if m:
                hits.append(v01.redact(blob)[:200])
                break
    return {"dangerous_pattern_hits": hits, "clean": not hits}


def load_credential() -> str:
    try:
        text = CREDENTIAL_FILE.read_text(encoding="utf-8")
    except OSError as exc:
        raise SystemExit(f"credential file unreadable: {type(exc).__name__}")
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("export "):
            line = line[7:]
        if line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        if key.strip() == CREDENTIAL_ENV:
            value = value.strip().strip('"').strip("'")
            if value:
                return value
    raise SystemExit(f"{CREDENTIAL_ENV} not found in credential file")


def load_credential_safely_for_spec() -> dict:
    """Env dict for ContainerSpec — the value exists only in the docker -e
    injection at runtime; it is never written to any file or report."""
    return {CREDENTIAL_ENV: load_credential()}


# --------------------------------------------------------------------------- #
# execution
# --------------------------------------------------------------------------- #

def _write_json(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=1, ensure_ascii=False) + "\n")


def _docker_cp(args: list[str], timeout_s: float = 120.0) -> dict:
    """Thin adapter over `docker cp` (volume mounts are intentionally NOT
    added to the shared ContainerSpec framework)."""
    import subprocess
    proc = subprocess.run(["docker", "cp", *args],
                          capture_output=True, text=True, timeout=timeout_s)
    return {"returncode": proc.returncode,
            "stderr": v01.redact(proc.stderr)[:300]}


def execute() -> int:
    from agent_workload_characterization.runners.container_runtime import (
        ContainerSpec, DockerCliRuntime)
    from video_use_env01_validation import ContainerScopeSampler, summarize_intervals, \
        mem_gauge_summary

    SESSION_DIR.mkdir(parents=True, exist_ok=True)
    (SESSION_DIR / "input").mkdir(exist_ok=True)

    png, gt = vision01.generate_test_image()
    truth = bailian.normalize_truth(gt)
    (SESSION_DIR / "input" / "neutral-test.png").write_bytes(png)
    _write_json(INTEGRATION_DIR / "expected-answer.json", {
        "task": COLLECTION, **truth,
        "image_sha256": hashlib.sha256(png).hexdigest(),
        "note": "host-side only; never copied into the container workdir "
                "beyond the neutral image itself"})
    (SESSION_DIR / "probe_input.py").write_text(PROBE_SCRIPT)

    runtime = DockerCliRuntime(authorized=True, collection=COLLECTION)
    spec = ContainerSpec(
        run_id="codex-bailian-01", scope="codex_cli_session", image=IMAGE_TAG,
        cwd="/task", env=load_credential_safely_for_spec(), timeout_s=60,
        network="bridge",  # needs dashscope.aliyuncs.com only
        mem_limit="6g")
    handle = runtime.start(spec)
    cid = handle.container_id
    report = {
        "schema": "video-use-codex-bailian-integration-01-v1",
        "task": COLLECTION,
        "executed_at_local": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "image": IMAGE_TAG,
        "base_image": BASE_IMAGE_TAG,
        "codex_cli_version": "0.163.0 (rust-v0.163.0 official arm64 musl)",
        "instruction": INSTRUCTION,
        "container_id": cid,
        "limits": {"session_wall_s": SESSION_WALL_S,
                   "retries": "disabled in provider config",
                   "http_attempt_count": "unknown — not observable through "
                                          "the CLI; never faked"},
    }
    try:
        # stage inputs via docker cp (no host mounts, no framework change)
        for src, dst in ((str(SESSION_DIR / "probe_input.py"), f"{cid}:/task/probe_input.py"),
                         (str(SESSION_DIR / "input"), f"{cid}:/task/input")):
            cp = _docker_cp([src, dst])
            if cp["returncode"] != 0:
                report["status"] = "staging_failed"
                report["staging"] = cp
                return _finalize(report, runtime, handle, None)
        check = runtime.execute(handle, "ls /task /task/input", timeout_s=30)
        if check.get("returncode") != 0:
            report["status"] = "preflight_failed"
            report["preflight_output"] = check.get("output", "")[:500]
            return _finalize(report, runtime, handle, None)
        report["preflight_ok"] = True

        sampler = ContainerScopeSampler(handle, runtime, SAMPLE_INTERVAL_S)
        session_result: dict = {}

        def _session():
            try:
                session_result.update(runtime.execute(
                    handle, build_codex_command(),
                    timeout_s=SESSION_WALL_S, output_limit=16_000_000))
            except Exception as exc:  # noqa: BLE001
                session_result["exception"] = type(exc).__name__

        sampler.start()
        thread = threading.Thread(target=_session)
        thread.start()
        thread.join(timeout=SESSION_WALL_S + 30)
        sampler.stop_event.set()
        sampler.join(timeout=10)
        report["session"] = {k: v for k, v in session_result.items()
                             if k != "output"}
        report["session"]["stdout_excerpt_tail"] = v01.redact(
            (session_result.get("output") or "")[-4000:])
        report["sampler_rows"] = sampler.rows
        report["rate_summary"] = summarize_intervals(sampler.rows)
        report["mem_gauge_summary"] = mem_gauge_summary(sampler.rows)

        # export rollouts into /task then copy EVERYTHING out BEFORE removal
        export = runtime.execute(
            handle,
            "mkdir -p /task/rollouts && "
            "if [ -d \"$CODEX_HOME/sessions\" ]; then "
            "cp -R \"$CODEX_HOME/sessions\"/. /task/rollouts/; fi && "
            "find /task/rollouts -name 'rollout-*.jsonl' | head -5 && "
            "ls /task/output/ 2>/dev/null; ls /task/final_message.txt 2>/dev/null",
            timeout_s=60)
        report["rollout_export"] = {"returncode": export.get("returncode"),
                                    "output": v01.redact(
                                        (export.get("output") or ""))[:1000]}
        cp_out = _docker_cp([f"{cid}:/task/.", str(SESSION_DIR)])
        report["artifacts_export"] = cp_out
        return _finalize(report, runtime, handle, truth)
    finally:
        runtime.stop(handle)
        report["removal_verification"] = runtime.verify_removal(handle)
        # re-persist AFTER cleanup so the report always carries the final
        # removal verification (the in-run _finalize ran before finally)
        report["cleanup"] = {
            "container_removed": report["removal_verification"] == "removed",
            "image_retained": True}
        if report.get("verdicts"):
            ok = (report["verdicts"].get("tool_execution") == "PASS"
                  and report["verdicts"].get("cli_image_viewing") == "PASS"
                  and report.get("audit", {}).get("clean")
                  and report["cleanup"]["container_removed"]
                  and len(report.get("sampler_rows", [])) > 0)
            report["overall"] = ("Codex＋百炼＋工具＋看图兼容性已验证"
                                 if ok else "fail_or_partial")
        _write_json(REPORT_PATH, report)


def _finalize(report: dict, runtime, handle, truth) -> int:
    verdicts = {}
    receipt_value = None
    receipt_path = SESSION_DIR / "output" / "receipt.json"
    if receipt_path.is_file():
        try:
            receipt_value = json.loads(receipt_path.read_text()).get("receipt")
        except (json.JSONDecodeError, OSError):
            receipt_value = None
    report["receipt_file_value"] = receipt_value
    final_path = SESSION_DIR / "final_message.txt"
    final_text = final_path.read_text(errors="replace") if final_path.is_file() else ""

    rollout_path = find_rollout(SESSION_DIR / "rollouts")
    rollout = parse_rollout(rollout_path) if rollout_path else {"exists": False}
    report["rollout"] = {"path": str(rollout_path.relative_to(ROOT))
                         if rollout_path else None,
                         "exists": rollout.get("exists"),
                         "session_meta": rollout.get("session_meta"),
                         "sha256": hashlib.sha256(
                             rollout_path.read_bytes()).hexdigest()
                         if rollout_path else None}
    report["audit"] = dangerous_command_audit(rollout)

    if truth:
        tool = tool_execution_evidence(rollout, receipt_value, final_text)
        view = image_viewing_evidence(rollout, final_text, truth)
        verdicts = {
            "tool_execution": tool["verdict"],
            "tool_result_return": tool["verdict"],  # receipt echo = loop closed
            "cli_image_viewing": view["verdict"],
        }
        report["evidence"] = {"tool_execution": tool, "image_viewing": view,
                              "final_message_excerpt": v01.redact(
                                  final_text[:600])}
        report["token_counts"] = rollout.get("token_counts", [])[:10]
    report["verdicts"] = verdicts
    report["cleanup"] = {
        "container_removed": report.get("removal_verification") == "removed",
        "image_retained": True,
    }
    ok = (verdicts.get("tool_execution") == "PASS"
          and verdicts.get("cli_image_viewing") == "PASS"
          and report["audit"]["clean"]
          and report["cleanup"]["container_removed"]
          and len(report.get("sampler_rows", [])) > 0)
    report["overall"] = ("Codex＋百炼＋工具＋看图兼容性已验证"
                         if ok else "fail_or_partial")
    _write_json(REPORT_PATH, report)
    print(json.dumps({"overall": report["overall"], "verdicts": verdicts,
                      "report": str(REPORT_PATH)}, ensure_ascii=False))
    return 0 if ok else 7


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--execute", action="store_true")
    ap.add_argument("--i-approve-video-use-codex-bailian-integration-01",
                    action="store_true")
    args = ap.parse_args(argv)
    if args.execute:
        if not args.i_approve_video_use_codex_bailian_integration_01:
            print("refusing: --execute requires "
                  "--i-approve-video-use-codex-bailian-integration-01")
            return 2
        if REPORT_PATH.exists():
            print("refusing: existing results; never overwrite")
            return 3
        return execute()
    print("offline mode")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
