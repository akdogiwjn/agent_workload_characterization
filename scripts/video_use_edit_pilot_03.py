#!/usr/bin/env python3
"""Prepare or run one separately approved PILOT-03 attempt via the shared runner."""
from __future__ import annotations

import hashlib
import json
import re
import shlex
import signal
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "scripts"), str(ROOT / "src")]
import video_use_edit_pilot_01 as runner  # noqa: E402

TASK = "VIDEO-USE-EDIT-PILOT-03"
RUN_ID = "20261021T1310Z-video-use-edit-03"
IMAGE = "video-use-task:arm64-codex-bailian-v6"
IMAGE_ID = "sha256:1a48c7b00da789ec99722ebb2be6e1df72aec9d37cc2a64e83c82e89ecf700c5"
PLAN_ROOT = ROOT / "env/video/video-use" / TASK
IDENTITY = PLAN_ROOT / "frozen-identity.json"
OVERLAY = PLAN_ROOT / "overlay"
VERIFIER_DIR = PLAN_ROOT / "verifier"
VERIFIER_VENV = Path("/home/lcq/.venvs/video-use-pilot03-verifier")
VERIFIER_PYTHON = VERIFIER_VENV / "bin/python"
SYNTHETIC_VALIDATION = PLAN_ROOT / "validation/synthetic_validation.py"
APPROVAL = PLAN_ROOT / "APPROVAL.json"
PRIVATE = (ROOT / "data/raw/public/agentic_vbench/b2764ed4b2a4b5a1737026b63887b50bba62f793/"
           "exp-disfluency-interview-3-task01/verifier_only/golden")

runner.TASK = TASK
runner.RUN_ID = RUN_ID
runner.IMAGE = IMAGE
runner.IMAGE_ID = IMAGE_ID
runner.PLAN_ROOT = PLAN_ROOT
runner._IDENTITY_FILE = IDENTITY
runner.RAW_ROOT = ROOT / "data/raw/generated" / TASK / RUN_ID
runner.REPORT_ROOT = ROOT / "reports/resource" / TASK
_BASE_RESOURCE_REPORT_WRITER = runner.write_resource_report


def digest(path: Path) -> dict:
    b = path.read_bytes()
    return {"bytes": len(b), "sha256": hashlib.sha256(b).hexdigest()}


def starter_instruction() -> str:
    original = (runner.TASK_PATH / "steps/solve/instruction.md").read_text()
    # Remove numeric values from any illustrative cut examples generically.
    original = re.sub(r'("(?:start_ms|end_ms)"\s*:\s*)\d+', r"\1<integer>", original)
    return original + """

Execution mapping: input is `/workspace/materials/source.mp4`; deliver exactly
`/workspace/output/output.mp4` and `/workspace/output/cuts.json`. Work under
`/workspace/project/edit`. The official Scribe transcript is already cached at
`/workspace/project/edit/transcripts/source.json`; read it and never transcribe
again. Treat transcript timestamps as candidate regions, inspect adjacent
source content using `/opt/video-use/helpers/timeline_view.py`, and determine
both cut boundaries yourself. No answer time, EDL, score, oracle, or prior-run
diagnosis is provided. Follow this task's minimal-edit requirements: no grade,
captions, music, animation, transition, loudness normalization, fades, or other
deletions. Create your own EDL, then call the registered video-use render helper
with `--preserve-source-spec --no-grade --no-audio-fades --no-loudnorm
--no-subtitles`; this production helper preserves the displayed source size and
frame rate and applies identical EDL intervals to video and audio. Render to
the required output path. Use ffprobe to verify output dimensions, frame rate,
duration and parseability. Inspect actual output screenshots at the chosen cut
and check both adjacent contexts; keep screenshots in
`/workspace/project/edit/verify`. Do not inspect external repositories,
archives, verifier files, scores, or credentials. Do not rerun ASR.
"""


def frozen_inputs() -> list[Path]:
    return [
        Path(__file__), Path(runner.__file__),
        ROOT / "tests/test_video_use_edit_pilot_03.py",
        ROOT / "env/video/video-use/codex-bailian-integration-02/Dockerfile",
        ROOT / "env/video/video-use/codex-bailian-integration-01/config.toml",
        ROOT / "env/video/video-use/source/helpers/transcribe.py",
        ROOT / "env/video/video-use/source-manifest.json",
        runner.TASK_PATH / "steps/solve/instruction.md", runner.INPUT,
        ROOT / "env/video/video-use/VIDEO-USE-EDIT-PILOT-03/Dockerfile",
        PLAN_ROOT / "baselines.json",
        OVERLAY / "helpers/render.py", OVERLAY / "helpers/timeline_view.py",
        OVERLAY / "SKILL.md", SYNTHETIC_VALIDATION,
        VERIFIER_DIR / "entry.py", VERIFIER_DIR / "requirements.in",
        VERIFIER_DIR / "requirements.lock", VERIFIER_DIR / "judge.py",
        VERIFIER_DIR / "verifier-environment.json",
    ]


runner.frozen_inputs = frozen_inputs
runner.starter_instruction = starter_instruction


def rollout_summary(root: Path) -> dict:
    models, usage, calls, returns, protocol_errors = set(), [], [], [], []
    for path in sorted(root.rglob("rollout-*.jsonl")):
        for line in path.read_text(errors="replace").splitlines():
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            payload = event.get("payload") or {}
            if not isinstance(payload, dict):
                continue
            for obj in (event, payload, payload.get("response"), payload.get("info"),
                        payload.get("usage")):
                if isinstance(obj, dict):
                    for key in ("model", "model_id", "response_model"):
                        if isinstance(obj.get(key), str):
                            models.add(obj[key])
            if event.get("type") in ("token_usage_record", "event_msg") and (
                    "token" in str(payload.get("type", "")).lower()
                    or "usage" in event.get("type", "")):
                usage.append(payload)
            if event.get("type") == "response_item":
                typ = payload.get("type")
                if typ == "function_call":
                    calls.append({"name": payload.get("name"), "call_id": payload.get("call_id"),
                                  "arguments": payload.get("arguments")})
                elif typ == "function_call_output":
                    returns.append({"call_id": payload.get("call_id"), "output": payload.get("output")})
                elif typ in ("error", "function_call_error"):
                    protocol_errors.append(payload)

    by_call = {item["call_id"]: item for item in returns if item.get("call_id")}
    exit_observations = []
    for call in calls:
        returned = by_call.get(call.get("call_id"), {})
        output = returned.get("output")
        text = output if isinstance(output, str) else json.dumps(output, ensure_ascii=False)
        match = re.search(r"Process exited with code (-?\d+)", text)
        if match:
            code = int(match.group(1))
            if code != 0:
                exit_observations.append({"call_id": call.get("call_id"),
                                          "tool": call.get("name"), "exit_code": code})
    exec_calls = [c for c in calls if c.get("name") == "exec_command"]
    return {
        "protocol_tool_call_events": len(calls),
        "protocol_tool_return_events": len(returns),
        "protocol_error_events": len(protocol_errors),
        "calls_without_return": sum(c.get("call_id") not in by_call for c in calls),
        "exec_command_tool_events": len(exec_calls),
        "observed_nonzero_process_exit_events": len(exit_observations),
        "nonzero_process_exit_observations": exit_observations,
        "exit_status_unobserved_calls": sum(c.get("call_id") in by_call and
            not re.search(r"Process exited with code (-?\d+)",
                          (by_call[c.get("call_id")].get("output") if isinstance(
                              by_call[c.get("call_id")].get("output"), str) else
                           json.dumps(by_call[c.get("call_id")].get("output"), ensure_ascii=False)))
            for c in calls),
        "tool_calls": calls, "tool_returns": returns, "protocol_errors": protocol_errors,
        "usage_events": usage, "response_models": sorted(models),
        "http_attempts": "unknown; native Codex rollout does not expose reliable HTTP counts",
    }


runner.rollout_summary = rollout_summary


def isolated_run_verifier(report: dict, remaining: float = runner.VERIFIER_BUDGET_S) -> dict:
    if not any(p.get("phase") == "agent" for p in report.get("phases", [])):
        return {"status": "not_started", "evaluation_status": "not_started",
                "evaluation_complete": False, "reason": "agent_not_started"}
    output = runner.RAW_ROOT / "workspace/output"
    if not (output / "output.mp4").is_file() or not (output / "cuts.json").is_file():
        return {"status": "not_started_missing_submission", "evaluation_status": "partial",
                "evaluation_complete": False, "reason": "required submission file missing",
                "checks": {"audio_xcorr": "not_evaluated", "ssim": "not_evaluated"}}
    private_cuts = PRIVATE / "cuts.json"
    judge = VERIFIER_DIR / "judge.py"
    if not private_cuts.is_file() or not judge.is_file() or not VERIFIER_PYTHON.is_file():
        return {"status": "evaluation_error", "evaluation_status": "evaluation_error",
                "evaluation_complete": False, "reason": "isolated verifier inputs/interpreter missing"}
    private_dir = runner.RAW_ROOT / "verifier_private"
    private_dir.mkdir()
    local_cuts = private_dir / "gt-cuts.json"
    local_judge = private_dir / "judge.py"
    local_cuts.write_bytes(private_cuts.read_bytes())
    local_judge.write_bytes(judge.read_bytes())
    reward = private_dir / "judge-reward.json"
    reward_txt = private_dir / "judge-reward.txt"
    status_path = private_dir / "evaluation-status.json"
    args = [str(VERIFIER_PYTHON), str(VERIFIER_DIR / "entry.py"),
            "--judge", str(local_judge), "--source-mp4", str(runner.INPUT),
            "--output-mp4", str(output / "output.mp4"),
            "--output-cuts", str(output / "cuts.json"), "--gt-cuts", str(local_cuts),
            "--reward-json", str(reward), "--reward-txt", str(reward_txt),
            "--status-json", str(status_path), "--expected-venv", str(VERIFIER_VENV),
            "--judge-sha256", hashlib.sha256(judge.read_bytes()).hexdigest(),
            "--timeout-s", str(max(1, remaining))]
    begin = runner.clock()
    proc = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            text=True, start_new_session=True)
    try:
        stdout, stderr = proc.communicate(timeout=max(1, remaining) + 15)
    except subprocess.TimeoutExpired:
        __import__("os").killpg(proc.pid, signal.SIGTERM)
        try:
            stdout, stderr = proc.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            __import__("os").killpg(proc.pid, signal.SIGKILL)
            stdout, stderr = proc.communicate()
        return {"status": "timeout", "evaluation_status": "evaluation_error",
                "evaluation_complete": False, "start": begin, "end": runner.clock(),
                "wrapper_returncode": proc.returncode, "stdout": stdout[-3000:],
                "stderr": stderr[-3000:], "process_group_terminated": True}
    try:
        status = json.loads(status_path.read_text())
    except (OSError, json.JSONDecodeError):
        status = {"evaluation_status": "evaluation_error", "evaluation_complete": False,
                  "evaluation_issue": "verifier wrapper did not save status"}
    return {
        "status": status.get("evaluation_status"),
        "evaluation_status": status.get("evaluation_status"),
        "evaluation_complete": status.get("evaluation_complete", False),
        "evaluation_issue": status.get("evaluation_issue"),
        "wrapper_returncode": proc.returncode,
        "returncode": status.get("official_judge_returncode"),
        "judge_reward": status.get("judge_emitted_reward"),
        "reward": status.get("task_score"),
        "checks": status.get("checks"),
        "start": begin, "end": runner.clock(), "stdout": stdout[-3000:],
        "stderr": stderr[-3000:], "verifier_python": status.get("verifier_python"),
        "verifier_prefix": status.get("verifier_prefix"),
        "versions": status.get("versions"),
        "judge_sha256": hashlib.sha256(local_judge.read_bytes()).hexdigest(),
        "source_judge_sha256": hashlib.sha256(judge.read_bytes()).hexdigest(),
        "judge_identity_match": hashlib.sha256(local_judge.read_bytes()).hexdigest()
            == hashlib.sha256(judge.read_bytes()).hexdigest(),
        "private_material_scope": "host-only isolated verifier after Agent container removal",
    }


runner.run_verifier = isolated_run_verifier


def emit_manifest(root: Path) -> None:
    files = {}
    for path in sorted(root.rglob("*")):
        if path.is_file() and path.name != "manifest.json":
            files[path.relative_to(root).as_posix()] = digest(path)
    runner.write_json(root / "manifest.json", {
        "schema": "video-use-edit-pilot-03-raw-manifest-v1",
        "files": files, "self_hash": "omitted"})


runner.emit_manifest = emit_manifest


def _write_pilot03_summary(report: dict) -> None:
    # Reuse the shared SVG sampling/reporting path via the captured base
    # function; this helper only writes the P3-specific prose summary.
    rows = report.get("sampler_rows", [])
    intervals = [(b["t_monotonic_ns"] - a["t_monotonic_ns"]) / 1e9
                 for a, b in zip(rows, rows[1:])
                 if b.get("t_monotonic_ns") and a.get("t_monotonic_ns")]
    metrics = report.get("resource_metrics", {})
    verifier = report.get("verifier", {})
    agent = next((p for p in report.get("phases", []) if p.get("phase") == "agent"), {})
    asr = next((p for p in report.get("phases", [])
                if p.get("phase") == "official_elevenlabs_transcribe"), {})
    tools = report.get("rollout_summary", {})
    lines = [
        "# VIDEO-USE-EDIT-PILOT-03 执行报告", "",
        f"- run_id `{report.get('run_id')}`; 单次 attempt。",
        f"- 采样目标 0.5s；{len(rows)} 点，实际区间中位 {sorted(intervals)[len(intervals)//2] if intervals else 'unknown'}s、最大 {max(intervals) if intervals else 'unknown'}s；资源区间及 gap 详见 raw run-record。",
        f"- CPU {metrics.get('cpu_core_seconds')} core-s / 平均 {metrics.get('cpu_average_cores')} cores；memory.current {metrics.get('max_sampled_memory_current_bytes')} B、kernel peak {metrics.get('max_kernel_memory_peak_bytes')} B；I/O read/write {metrics.get('io_read_bytes')}/{metrics.get('io_write_bytes')} B。",
        f"- ASR returncode `{asr.get('returncode','unknown')}`，请求数 `{asr.get('request_count','unknown')}`；Agent returncode `{agent.get('returncode','unknown')}`，timeout `{agent.get('timed_out','unknown')}`。",
        f"- 工具协议事件：calls {tools.get('protocol_tool_call_events','unknown')}、returns {tools.get('protocol_tool_return_events','unknown')}、protocol errors {tools.get('protocol_error_events','unknown')}；exec_command events {tools.get('exec_command_tool_events','unknown')}；观察到的非零进程退出 {tools.get('observed_nonzero_process_exit_events','unknown')}。这些指标不互相代替。HTTP 次数 unknown。",
        f"- 官方 judge 进程 returncode `{verifier.get('returncode','unknown')}`；verifier wrapper returncode `{verifier.get('wrapper_returncode','unknown')}`；评分状态 `{verifier.get('evaluation_status','unknown')}`，完整性 `{verifier.get('evaluation_complete','unknown')}`；judge emitted reward `{verifier.get('judge_reward','unknown')}`，完整评分 task_score `{verifier.get('reward','unknown')}`。",
        f"- 核验 Python `{verifier.get('verifier_python','not_run')}`；judge SHA 身份匹配 `{verifier.get('judge_identity_match','unknown')}`；容器清理 `{report.get('removal_verification','unknown')}`。",
        "- 共享容器 netns 逐接口网络计数不是 API 专属流量；完整原生 rollout 和事件索引保留。",
        "",
    ]
    (runner.REPORT_ROOT / "summary.md").write_text("\n".join(lines))


def write_resource_report(report: dict) -> dict:
    """Generate report artifacts and record report status without touching raw evidence."""
    report_root = runner.REPORT_ROOT
    run_id = report.get("run_id")
    base = {
        "schema": "video-use-pilot03-report-generation-v1",
        "run_id": run_id,
        "agent_returncode": next((p.get("returncode") for p in report.get("phases", [])
                                  if p.get("phase") == "agent"), None),
        "verifier_status": (report.get("verifier") or {}).get("evaluation_status", "unknown"),
        "verifier_returncode": (report.get("verifier") or {}).get("returncode"),
        "container_cleanup": report.get("removal_verification", "unknown"),
        "raw_run_record_exists": (runner.RAW_ROOT / "run-record.json").is_file(),
        "raw_manifest_exists": (runner.RAW_ROOT / "manifest.json").is_file(),
        "raw_modified_by_report_writer": False,
    }
    try:
        report_root.mkdir(parents=True, exist_ok=True)
        _BASE_RESOURCE_REPORT_WRITER(report)
        _write_pilot03_summary(report)
        status = {**base, "report_status": "complete", "error": None}
    except Exception as exc:
        status = {**base, "report_status": "failed",
                  "error": {"type": type(exc).__name__, "message": str(exc)[:500]}}
    runner.write_json(report_root / "report-generation-status.json", status)
    return status


runner.write_resource_report = write_resource_report


def prepare_plan_and_identity() -> None:
    plan_path = PLAN_ROOT / "environment-plan.json"
    identity_path = PLAN_ROOT / "frozen-identity.json"
    plan = json.loads(plan_path.read_text())
    plan["approval"] = "separate explicit approval required; no APPROVAL/ATTEMPT/raw created"
    plan["render_adaptation"] = {
        "overlay": "project-owned derivative copied into /opt/video-use and exposed through the registered skill symlink",
        "preserve_source_spec": "--preserve-source-spec disables hard-coded scaling and preserves the probed source rate",
        "no_enhancements": "--no-grade --no-audio-fades --no-loudnorm --no-subtitles",
        "production_command_contract": "native render.py in the task image; synthetic tests invoke this same file",
        "timeline_boundary": "timeline_view probes duration/frame rate and clamps sample timestamps to valid frames",
    }
    plan["verifier"] = {
        "judge": "unmodified official judge.py; hash-checked before invocation",
        "python": str(VERIFIER_PYTHON),
        "venv_prefix": str(VERIFIER_VENV),
        "dependencies": str(VERIFIER_DIR / "requirements.lock"),
        "ffmpeg": "host ffmpeg/ffprobe; versions frozen in verifier-environment.json",
        "status_model": "judge process rc, evaluation completeness/status, and task score are separate fields",
        "oracle_validation": "one isolated official-golden oracle chain check; never exposed to Agent",
    }
    plan["prompt_constraints"] = {
        "timestamp_semantics": "transcript timestamps are candidate regions only; Agent determines both cut boundaries",
        "diagnostics_isolated": True,
        "prior_scores_or_goldens_mounted": False,
    }
    plan["future_approval_command"] = (
        "python3 scripts/video_use_edit_pilot_03.py --execute --i-approve-video-use-edit-pilot-03")
    runner.write_json(plan_path, plan)
    identity = json.loads(identity_path.read_text())
    identity["approval"] = plan["approval"]
    identity["environment_plan_sha256"] = digest(plan_path)["sha256"]
    identity["runtime_and_evaluation"] = {
        "image": IMAGE, "image_id": IMAGE_ID, "platform": "linux/arm64",
        "verifier_environment": str(VERIFIER_DIR / "verifier-environment.json"),
        "official_judge_sha256": digest(VERIFIER_DIR / "judge.py")["sha256"],
        "render_adaptation_sha256": {
            "render.py": digest(OVERLAY / "helpers/render.py")["sha256"],
            "timeline_view.py": digest(OVERLAY / "helpers/timeline_view.py")["sha256"],
            "SKILL.md": digest(OVERLAY / "SKILL.md")["sha256"],
        },
        "prompt_constraints_sha256": hashlib.sha256(starter_instruction().encode()).hexdigest(),
    }
    runner.write_json(identity_path, identity)
    # The identity binds the final plan digest; the plan deliberately does not
    # embed the identity digest, avoiding a circular hash relationship.


def main() -> int:
    if IMAGE_ID == "TO_BE_FROZEN_AFTER_LOCAL_BUILD":
        raise SystemExit("PILOT-03 image identity not frozen")
    if "--execute" in sys.argv:
        if not APPROVAL.is_file():
            raise SystemExit("PILOT-03 has no separate APPROVAL.json; preparation cannot execute an attempt")
        approval = json.loads(APPROVAL.read_text())
        frozen_hash = digest(IDENTITY)["sha256"]
        if approval.get("frozen_identity_sha256") != frozen_hash:
            raise SystemExit("approval does not match PILOT-03 frozen identity")
    if "--prepare" in sys.argv:
        result = runner.main()
        if result == 0:
            prepare_plan_and_identity()
            print(json.dumps({"status": "prepared_no_attempt", "approval_exists": APPROVAL.exists(),
                              "run_id": RUN_ID, "identity_sha256": digest(IDENTITY)["sha256"],
                              "plan_sha256": digest(PLAN_ROOT / "environment-plan.json")["sha256"]},
                             ensure_ascii=False))
        return result
    runner.PROCESS_START_NS = time.monotonic_ns()
    return runner.main()


if __name__ == "__main__":
    raise SystemExit(main())
