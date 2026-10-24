#!/usr/bin/env python3
"""PILOT-04 thin entry: freeze a generic boundary policy, then one approved run."""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENTRY_START_NS = time.monotonic_ns()
sys.path[:0] = [str(ROOT / "scripts"), str(ROOT / "src")]
import video_use_edit_pilot_03 as pilot03  # noqa: E402

runner = pilot03.runner
TASK = "VIDEO-USE-EDIT-PILOT-04"
RUN_ID = "20261021T1450Z-video-use-edit-04"
PLAN_ROOT = ROOT / "env/video/video-use" / TASK
IDENTITY = PLAN_ROOT / "frozen-identity.json"
APPROVAL = PLAN_ROOT / "APPROVAL.json"
RAW_ROOT = ROOT / "data/raw/generated" / TASK / RUN_ID
REPORT_ROOT = ROOT / "reports/resource" / TASK
IMAGE = "video-use-task:arm64-codex-bailian-v6"
IMAGE_ID = "sha256:1a48c7b00da789ec99722ebb2be6e1df72aec9d37cc2a64e83c82e89ecf700c5"
PLATFORM = "linux/arm64"
TASK_COMMIT = "b2764ed4b2a4b5a1737026b63887b50bba62f793"

runner.TASK = TASK
runner.RUN_ID = RUN_ID
runner.IMAGE = IMAGE
runner.IMAGE_ID = IMAGE_ID
runner.PLAN_ROOT = PLAN_ROOT
runner._IDENTITY_FILE = IDENTITY
runner.RAW_ROOT = RAW_ROOT
runner.REPORT_ROOT = REPORT_ROOT
pilot03.TASK = TASK
pilot03.RUN_ID = RUN_ID
pilot03.IMAGE = IMAGE
pilot03.IMAGE_ID = IMAGE_ID
pilot03.PLAN_ROOT = PLAN_ROOT
pilot03.IDENTITY = IDENTITY
pilot03.APPROVAL = APPROVAL

POLICY = """

Cut-selection policy for this task:
1. Treat transcript timestamps as candidate locations, not exact cut boundaries.
2. Distinguish normal speech, conversational acknowledgements, repeated starts,
   and actual hesitation. Do not delete a whole transcript phrase merely because
   it contains a disfluency; retain ordinary content that carries meaning.
3. Make the smallest cut that removes the actual disruption while preserving
   meaningful speech.
4. Assess the proposed before and after boundaries separately. Use available
   word times, a local waveform, adjacent frames, and other tool evidence, and
   record why material on each side is retained or removed. A waveform or image
   alone does not establish spoken meaning.
5. Before rendering, keep cuts.json and the EDL synchronized to one edit plan;
   after rendering, verify output specifications and inspect continuity at the
   cut in the rendered output.
6. If the session has no actual audio-understanding evidence, explicitly state
   “audio semantic judgment not verified”; do not describe viewing a waveform or
   screenshots as having understood the audio.
7. Do not remove extra content to chase a score or make repeated blind edits.

Before writing the EDL, save a concise decision record to
`/workspace/project/edit/boundary-notes.md`: candidate region(s), the role of
the speech around each proposed edge, evidence actually inspected, what is kept
or removed, and any audio-semantic uncertainty. This is a process note, not an
additional submission. Do not infer a target time from examples or outside
information. The official task and its minimal-edit constraints remain in force.
"""


def digest(path: Path) -> dict:
    return runner.digest(path)


def starter_instruction() -> str:
    # The P3 constructor contains only the original task plus execution mapping
    # and generic tool instructions; it contains no P2/P3 outcome or diagnosis.
    return pilot03.starter_instruction() + POLICY


def frozen_inputs() -> list[Path]:
    return [
        Path(__file__), Path(pilot03.__file__), Path(runner.__file__),
        ROOT / "tests/test_video_use_edit_pilot_04.py",
        ROOT / "scripts/video_use_edit_pilot_03_boundary_review.py",
        ROOT / "env/video/video-use/codex-bailian-integration-01/config.toml",
        ROOT / "env/video/video-use/source/helpers/transcribe.py",
        ROOT / "env/video/video-use/source-manifest.json",
        ROOT / "references/repos/agentic-vbench/tasks/agentic_vbench_repair/exp-disfluency-interview-3-task01/steps/solve/instruction.md",
        runner.INPUT,
        ROOT / "env/video/video-use/VIDEO-USE-EDIT-PILOT-03/overlay/SKILL.md",
        ROOT / "env/video/video-use/VIDEO-USE-EDIT-PILOT-03/overlay/helpers/render.py",
        ROOT / "env/video/video-use/VIDEO-USE-EDIT-PILOT-03/overlay/helpers/timeline_view.py",
        ROOT / "env/video/video-use/VIDEO-USE-EDIT-PILOT-03/verifier/entry.py",
        ROOT / "env/video/video-use/VIDEO-USE-EDIT-PILOT-03/verifier/judge.py",
        ROOT / "env/video/video-use/VIDEO-USE-EDIT-PILOT-03/verifier/requirements.lock",
        ROOT / "env/video/video-use/VIDEO-USE-EDIT-PILOT-03/verifier/verifier-environment.json",
        PLAN_ROOT / "source-snapshot/manifest.json",
        PLAN_ROOT / "preflight-events.jsonl",
    ]


def route_config() -> dict:
    import tomllib
    path = ROOT / "env/video/video-use/codex-bailian-integration-01/config.toml"
    cfg = tomllib.loads(path.read_text())
    provider = cfg["model_providers"][cfg["model_provider"]]
    route = {"provider": cfg["model_provider"], "model": cfg["model"],
             "base_url": provider["base_url"], "wire_api": provider["wire_api"],
             "api_key_env": provider["env_key"],
             "request_max_retries": provider["request_max_retries"],
             "stream_max_retries": provider["stream_max_retries"]}
    if route != {"provider": "bailian", "model": "qwen3.7-plus",
                 "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
                 "wire_api": "responses", "api_key_env": "DASHSCOPE_API_KEY",
                 "request_max_retries": 0, "stream_max_retries": 0}:
        raise RuntimeError("existing verified Responses route changed")
    return route


def plan_data(image: dict) -> dict:
    return {
        "schema": "video-use-edit-pilot-04-environment-plan-v1",
        "task": {"name": TASK, "upstream_commit": TASK_COMMIT,
                 "instruction": "original AgenticVBench instruction; hash frozen",
                 "input": str(runner.INPUT.relative_to(ROOT))},
        "run_id": RUN_ID, "single_attempt": True, "architecture": PLATFORM,
        "image": {"tag": IMAGE, "id": IMAGE_ID, "platform": PLATFORM, **image},
        "model_route": route_config(),
        "asr": {"helper": "official video-use transcribe.py", "model": "scribe_v1",
                "max_client_posts": 1, "retries": 0,
                "cache": "attempt-local; exactly one transcription before Agent"},
        "verifier": {"judge": "unaltered official judge.py in isolated venv",
                     "python": str(pilot03.VERIFIER_PYTHON),
                     "environment": str(pilot03.VERIFIER_DIR / "verifier-environment.json"),
                     "private_materials_after_agent_container_removal": True},
        "budgets_s": {"total": 2700, "agent_max": 1800,
                      "verifier_max": 600, "cleanup_reserve": 300},
        "resources": {"cpus": 2, "memory_bytes": 4294967296,
                      "sample_interval_target_s": 0.5,
                      "cgroup_scope": "Agent container and child processes",
                      "network_scope": "shared container netns per interface; not API-specific",
                      "directory_boundaries_nonoverlapping": ["materials", "workspace", "output"]},
        "prompt": {"strategy": "generic minimal semantic-preservation boundary policy",
                   "prompt_sha256": hashlib.sha256(starter_instruction().encode()).hexdigest(),
                   "instruction_sha256": digest(runner.TASK_PATH / "steps/solve/instruction.md")["sha256"],
                   "boundary_notes_path": "/workspace/project/edit/boundary-notes.md",
                   "old_runs_scores_or_diagnostics_in_agent_context": False,
                   "golden_oracle_in_agent_context": False},
        "approval": "created only by the authorized execute invocation after identity checks",
    }


def prepare(refresh: bool = False) -> dict:
    prepared_files_exist = any((PLAN_ROOT / n).exists()
                               for n in ("environment-plan.json", "frozen-identity.json", "APPROVAL.json"))
    if prepared_files_exist and not refresh:
        raise RuntimeError("PILOT-04 plan/identity/approval already exists; refusing to overwrite")
    if refresh and (APPROVAL.exists() or RAW_ROOT.exists()):
        raise RuntimeError("cannot refresh PILOT-04 identity after approval or attempt start")
    raw_parent = ROOT / "data/raw/generated" / TASK
    if raw_parent.exists() and any(raw_parent.iterdir()):
        raise RuntimeError("PILOT-04 already has a raw attempt; refusing to create another")
    if digest(runner.INPUT)["sha256"] != runner.EXPECTED_INPUT:
        raise RuntimeError("registered input SHA-256 mismatch")
    if refresh:
        previous_plan = json.loads((PLAN_ROOT / "environment-plan.json").read_text())
        image = previous_plan.get("image", {})
    else:
        image = runner.image_check()
    if image.get("inspect") != f"{IMAGE_ID} arm64 linux" or "0.163.0" not in image.get("codex_version", ""):
        raise RuntimeError("task image identity/version mismatch")
    skill = runner.skill_preflight()
    if skill.get("upstream_commit") != "43cfc566833548093455c9d4a46bd69913b7e552":
        raise RuntimeError("video-use source identity mismatch")
    if runner.command("git", "-C", str(runner.TASK_SOURCE), "rev-parse", "HEAD")["stdout"] != TASK_COMMIT:
        raise RuntimeError("task repository commit mismatch")
    if not pilot03.VERIFIER_PYTHON.is_file():
        raise RuntimeError("dedicated verifier interpreter missing")
    verifier_meta = json.loads((pilot03.VERIFIER_DIR / "verifier-environment.json").read_text())
    if verifier_meta.get("python_executable") != str(pilot03.VERIFIER_PYTHON):
        raise RuntimeError("verifier interpreter does not match verified environment record")
    PLAN_ROOT.mkdir(parents=True, exist_ok=True)
    plan = plan_data(image)
    (PLAN_ROOT / "environment-plan.json").write_text(json.dumps(plan, ensure_ascii=False, indent=2) + "\n")
    files = {str(p.relative_to(ROOT)): digest(p) for p in frozen_inputs()}
    identity = {
        "schema": "video-use-edit-pilot-04-frozen-identity-v1", "task": TASK,
        "run_id": RUN_ID, "task_commit": TASK_COMMIT,
        "input": digest(runner.INPUT),
        # The shared runner compares this field byte-for-byte as a dict to its
        # local image_check() result. Keep extended registry identity separate.
        "image": {"inspect": image["inspect"], "codex_version": image["codex_version"]},
        "image_identity": {"tag": IMAGE, "id": IMAGE_ID, "platform": PLATFORM},
        "files": files, "environment_plan_sha256": digest(PLAN_ROOT / "environment-plan.json")["sha256"],
        "model_route": plan["model_route"], "transcription": plan["asr"],
        "verifier": plan["verifier"], "prompt_policy_sha256": plan["prompt"]["prompt_sha256"],
        "budgets_s": plan["budgets_s"], "resources": plan["resources"],
        "prepared_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "prepared_at_monotonic_ns": time.monotonic_ns(),
        "approval": "not yet recorded; user instruction authorizes only this frozen config",
    }
    (PLAN_ROOT / "frozen-identity.json").write_text(json.dumps(identity, ensure_ascii=False, indent=2) + "\n")
    return {"status": "prepared", "identity_sha256": digest(IDENTITY)["sha256"],
            "environment_plan_sha256": digest(PLAN_ROOT / "environment-plan.json")["sha256"],
            "image": image, "task_commit": TASK_COMMIT}


def _ffprobe_submission() -> dict:
    out = RAW_ROOT / "workspace/output"
    video, cuts = out / "output.mp4", out / "cuts.json"
    result = {"files_present": video.is_file() and cuts.is_file(),
              "ffprobe": "not_run", "full_decode": "not_run", "cuts_json": "not_run"}
    if not video.is_file() or not cuts.is_file():
        return result
    try:
        parsed_cuts = json.loads(cuts.read_text())
        result["cuts_json"] = {"status": "parseable", "cut_count": len(parsed_cuts.get("cuts", []))}
    except Exception as exc:
        result["cuts_json"] = {"status": "invalid", "error": type(exc).__name__}
    p = subprocess.run(["ffprobe", "-v", "error", "-show_streams", "-show_format",
                        "-of", "json", str(video)], capture_output=True, text=True, timeout=30)
    result["ffprobe_returncode"] = p.returncode
    if p.returncode == 0:
        data = json.loads(p.stdout)
        streams = data.get("streams", [])
        v = next((s for s in streams if s.get("codec_type") == "video"), {})
        a = next((s for s in streams if s.get("codec_type") == "audio"), {})
        result["ffprobe"] = {"status": "pass", "video_codec": v.get("codec_name"),
                              "width": v.get("width"), "height": v.get("height"),
                              "pixel_format": v.get("pix_fmt"), "frame_rate": v.get("r_frame_rate"),
                              "video_duration_s": v.get("duration"),
                              "audio_codec": a.get("codec_name"), "audio_channels": a.get("channels"),
                              "container_duration_s": (data.get("format") or {}).get("duration")}
    else:
        result["ffprobe"] = {"status": "failed", "stderr": p.stderr[-1000:]}
    source_probe = subprocess.run(["ffprobe", "-v", "error", "-show_streams", "-show_format",
                                   "-of", "json", str(runner.INPUT)],
                                  capture_output=True, text=True, timeout=30)
    if source_probe.returncode == 0 and result.get("ffprobe", {}).get("status") == "pass":
        source_data = json.loads(source_probe.stdout)
        source_v = next((s for s in source_data.get("streams", [])
                         if s.get("codec_type") == "video"), {})
        output_v = result["ffprobe"]
        result["source_video_spec"] = {"width": source_v.get("width"),
                                       "height": source_v.get("height"),
                                       "frame_rate": source_v.get("r_frame_rate")}
        result["matches_source_dimensions_and_rate"] = (
            output_v.get("width") == source_v.get("width")
            and output_v.get("height") == source_v.get("height")
            and output_v.get("frame_rate") == source_v.get("r_frame_rate"))
    else:
        result["matches_source_dimensions_and_rate"] = None
        result["source_ffprobe_returncode"] = source_probe.returncode
    d = subprocess.run(["ffmpeg", "-v", "error", "-i", str(video), "-f", "null", "-"],
                       capture_output=True, text=True, timeout=60)
    result["full_decode"] = {"status": "pass" if d.returncode == 0 else "failed",
                             "returncode": d.returncode, "stderr": d.stderr[-1000:]}
    return result


def run_verifier(report: dict, remaining: float) -> dict:
    validate_start = time.monotonic_ns()
    submission = _ffprobe_submission()
    validate_s = (time.monotonic_ns() - validate_start) / 1e9
    judge_budget = max(0.0, remaining - validate_s)
    result = pilot03.isolated_run_verifier(report, remaining=judge_budget)
    result["submission_validation"] = submission
    result["submission_validation_duration_s"] = validate_s
    return result


def _p4_summary(report: dict) -> None:
    rows = report.get("sampler_rows", [])
    stamps = [r.get("t_monotonic_ns") for r in rows if r.get("t_monotonic_ns") is not None]
    ivals = [(b-a)/1e9 for a,b in zip(stamps, stamps[1:])]
    wall = None
    if report.get("start", {}).get("monotonic_ns") and report.get("end", {}).get("monotonic_ns"):
        wall = (report["end"]["monotonic_ns"]-report["start"]["monotonic_ns"])/1e9
    phases = {p.get("phase"): p for p in report.get("phases", [])}
    v = report.get("verifier", {})
    checks = v.get("checks") or {}
    metrics = report.get("resource_metrics", {})
    roll = report.get("rollout_summary", {})
    cols = [
        ("测量完整性", f"attempt wall {wall if wall is not None else 'unknown'}s；采样 {len(rows)} 点/{max(0,len(rows)-1)} 邻接间隔，采样窗 {metrics.get('cpu_valid_interval_s','unknown')}s；目标 0.5s，实测中位 {sorted(ivals)[len(ivals)//2] if ivals else 'unknown'}s、最大 {max(ivals) if ivals else 'unknown'}s。CPU {metrics.get('cpu_core_seconds','unknown')} core-s，平均 {metrics.get('cpu_average_cores','unknown')} core；memory.current 峰值 {metrics.get('max_sampled_memory_current_bytes','unknown')} B，kernel peak {metrics.get('max_kernel_memory_peak_bytes','unknown')} B；cgroup I/O read/write {metrics.get('io_read_bytes','unknown')}/{metrics.get('io_write_bytes','unknown')} B。"),
        ("官方任务结果", f"judge RC {v.get('returncode','unknown')}；完整性 {v.get('evaluation_status','unknown')}/{v.get('evaluation_complete','unknown')}；reward {v.get('reward','unknown')}；剪切范围 {checks.get('cut_ranges','unknown')}，时长 {checks.get('duration','unknown')}，SSIM {checks.get('ssim','unknown')}，音频检查 {checks.get('audio_xcorr','unknown')}。提交核验：{json.dumps(v.get('submission_validation',{}),ensure_ascii=False)}。"),
        ("Agent终止", f"Agent RC {phases.get('agent',{}).get('returncode','unknown')}，timeout {phases.get('agent',{}).get('timed_out','unknown')}；工具调用/返回/协议错误 {roll.get('protocol_tool_call_events','unknown')}/{roll.get('protocol_tool_return_events','unknown')}/{roll.get('protocol_error_events','unknown')}；非零命令 {roll.get('observed_nonzero_process_exit_events','unknown')}。原生 rollout 归档。"),
        ("基础设施与归档", f"镜像 {IMAGE_ID} linux/arm64；清理 {report.get('removal_verification','unknown')}；网络为共享 netns 逐接口（非 API 专属）；raw manifest 见 {RAW_ROOT}/manifest.json。HTTP 次数与费用 unknown。"),
    ]
    lines=["# VIDEO-USE-EDIT-PILOT-04 执行报告", "", "| 测量完整性 | 官方任务结果 | Agent终止 | 基础设施与归档 |", "|---|---|---|---|", "| " + " | ".join(x.replace("|","\\|").replace("\n"," ") for _,x in cols) + " |", "", "## 单次尝试阶段", ""]
    for name,p in phases.items():
        lines.append(f"- {name}: returncode={p.get('returncode','unknown')}, duration={p.get('duration_s','unknown')}s, timeout={p.get('timed_out','unknown')}")
    lines.extend(["", "## 模型 usage 与网络", "",
                  f"- Codex rollout 工具调用 {roll.get('protocol_tool_call_events','unknown')}、返回 {roll.get('protocol_tool_return_events','unknown')}、协议错误 {roll.get('protocol_error_events','unknown')}；命令非零退出单独统计。",
                  f"- 保存响应 usage 事件 {len(roll.get('usage_events',[]))}；原生逐响应/累计用量见 raw，累计快照不重复相加；HTTP 请求次数 unknown。",
                  "- cgroup 覆盖容器及子进程，不归因到单工具；网络字节为共享 netns 逐接口值，不是 API 专属流量。", ""])
    (REPORT_ROOT / "summary.md").write_text("\n".join(lines))


def write_resource_report(report: dict) -> dict:
    base={"schema":"video-use-pilot04-report-generation-v1","run_id":RUN_ID,
          "agent_returncode":next((p.get("returncode") for p in report.get("phases",[]) if p.get("phase")=="agent"),None),
          "verifier_status":(report.get("verifier") or {}).get("evaluation_status","unknown"),
          "container_cleanup":report.get("removal_verification","unknown"),
          "raw_run_record_exists":(RAW_ROOT/"run-record.json").is_file(),
          "raw_manifest_exists":(RAW_ROOT/"manifest.json").is_file(),"raw_modified_by_report_writer":False}
    try:
        REPORT_ROOT.mkdir(parents=True,exist_ok=True)
        pilot03._BASE_RESOURCE_REPORT_WRITER(report)
        _p4_summary(report)
        status={**base,"report_status":"complete","error":None}
    except Exception as exc:
        status={**base,"report_status":"failed","error":{"type":type(exc).__name__,"message":str(exc)[:500]}}
    runner.write_json(REPORT_ROOT/"report-generation-status.json",status)
    return status


runner.frozen_inputs = frozen_inputs
runner.starter_instruction = starter_instruction
runner.run_verifier = run_verifier
runner.write_resource_report = write_resource_report


def execute() -> int:
    if not IDENTITY.is_file():
        raise SystemExit("PILOT-04 frozen identity missing")
    identity=json.loads(IDENTITY.read_text())
    if identity.get("run_id") != RUN_ID or identity.get("task") != TASK:
        raise SystemExit("PILOT-04 identity/run mismatch")
    for path in frozen_inputs():
        rel=str(path.relative_to(ROOT))
        if identity.get("files",{}).get(rel) != digest(path):
            raise SystemExit(f"frozen identity mismatch: {rel}")
    if identity.get("environment_plan_sha256") != digest(PLAN_ROOT/"environment-plan.json")["sha256"]:
        raise SystemExit("PILOT-04 environment plan changed")
    if (identity.get("input") != digest(runner.INPUT)
            or identity.get("image_identity",{}).get("id") != IMAGE_ID
            or identity.get("image_identity",{}).get("platform") != PLATFORM):
        raise SystemExit("PILOT-04 input/image identity mismatch")
    raw_parent = ROOT / "data/raw/generated" / TASK
    if RAW_ROOT.exists() or (raw_parent.exists() and any(raw_parent.iterdir())):
        raise SystemExit("PILOT-04 already has a raw attempt; refusing a second attempt")
    if not pilot03.VERIFIER_PYTHON.is_file():
        raise SystemExit("dedicated verifier interpreter disappeared")
    name_prefix=f"awc-{TASK.lower()}-{RUN_ID}-video_use_agent"
    occupied=runner.command("docker","ps","-a","--filter",f"name={name_prefix}","--format","{{.Names}}")
    if occupied["returncode"] or occupied["stdout"]:
        raise SystemExit("PILOT-04 namespace occupied; refusing to start")
    identity_sha=digest(IDENTITY)["sha256"]
    approval={"schema":"video-use-edit-pilot-04-approval-v1","run_id":RUN_ID,
              "task":TASK,"frozen_identity_sha256":identity_sha,
              "approved_by":"user instruction in this session",
              "scope":"one official Scribe request, one Codex+Bailian attempt, one independent official verifier",
              "recorded_at_utc":time.strftime("%Y-%m-%dT%H:%M:%SZ",time.gmtime()),
              "no_retry":True}
    APPROVAL.write_text(json.dumps(approval,ensure_ascii=False,indent=2)+"\n")
    reset_execution_clock()
    # Match the approved standard entry flags; the shared runner consumes them.
    sys.argv=[sys.argv[0],"--execute",f"--i-approve-{TASK.lower()}"]
    return runner.main()


def main() -> int:
    if "--prepare" in sys.argv:
        prepared=prepare()
        print(json.dumps(prepared,ensure_ascii=False))
        return 0
    if "--refresh-prepared" in sys.argv:
        prepared=prepare(refresh=True)
        print(json.dumps(prepared,ensure_ascii=False))
        return 0
    if "--execute" in sys.argv and f"--i-approve-{TASK.lower()}" in sys.argv:
        reset_execution_clock()
        return execute()
    raise SystemExit("use --prepare, or --execute --i-approve-video-use-edit-pilot-04")


def reset_execution_clock() -> None:
    """Use this process entry's monotonic origin; never restore prepare time."""
    runner.PROCESS_START_NS = ENTRY_START_NS


if __name__ == "__main__":
    raise SystemExit(main())
