#!/usr/bin/env python3
"""One bounded VIDEO-USE-EDIT-PILOT-01 run using the frozen task image."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import signal
import shutil
import shlex
import subprocess
import sys
import threading
import time
import uuid
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "scripts"), str(ROOT / "src")]
import video_use_env01_validation as env01  # noqa: E402

TASK = "VIDEO-USE-EDIT-PILOT-01"
_IDENTITY_FILE = (Path(__file__).resolve().parents[1] / "env/video/video-use" /
                  TASK / "frozen-identity.json")
RUN_ID = "20261021T0822Z-video-use-edit-01"
IMAGE = "video-use-task:arm64-codex-bailian-v1"
IMAGE_ID = "sha256:a46db2143d8aa69a299b419152c6ca036e09f619d3f771aeace64e08ed729402"
EXPECTED_INPUT = "a9bce74a50b5380d7c1aa1d9980f1d159e8633fbff00986504a363a3d18525bb"
TASK_DIR = ROOT / "data/workloads/video/editing/avb-disfluency-interview-3-v1"
INPUT = TASK_DIR / "input/source.mp4"
TASK_SOURCE = ROOT / "references/repos/agentic-vbench"
TASK_PATH = TASK_SOURCE / "tasks/agentic_vbench_repair/exp-disfluency-interview-3-task01"
RAW_ROOT = ROOT / "data/raw/generated" / TASK / RUN_ID
REPORT_ROOT = ROOT / "reports/resource" / TASK
PLAN_ROOT = ROOT / "env/video/video-use" / TASK
ATTEMPT_BUDGET_S = 2700
AGENT_BUDGET_S = 1800
VERIFIER_BUDGET_S = 600
SAMPLE_S = 0.5
PROCESS_START_NS = time.monotonic_ns()
if _IDENTITY_FILE.is_file():
    try:
        PROCESS_START_NS = int(json.loads(_IDENTITY_FILE.read_text()).get(
            "prepared_at_monotonic_ns", PROCESS_START_NS))
    except (ValueError, OSError, json.JSONDecodeError):
        pass

from agent_workload_characterization.runners.container_runtime import (  # noqa: E402
    ContainerSpec, DockerCliRuntime,
)


def digest(path: Path) -> dict:
    h = hashlib.sha256()
    n = 0
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            n += len(block)
            h.update(block)
    return {"bytes": n, "sha256": h.hexdigest()}


def clock() -> dict:
    return {"wall_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "monotonic_ns": time.monotonic_ns()}


def command(*argv: str, timeout: int = 30) -> dict:
    p = subprocess.run(list(argv), capture_output=True, text=True, timeout=timeout)
    return {"returncode": p.returncode, "stdout": p.stdout.strip(),
            "stderr": p.stderr.strip()[-1000:]}


def safe_credential(path: Path, name: str) -> str:
    for line in path.read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if s.startswith("export "):
            s = s[7:]
        if not s or s.startswith("#") or "=" not in s:
            continue
        k, _, v = s.partition("=")
        if k.strip() == name:
            return v.strip().strip('"').strip("'")
    raise RuntimeError(f"{name} missing")


def image_check() -> dict:
    r = command("docker", "inspect", IMAGE, "--format", "{{.Id}} {{.Architecture}} {{.Os}}")
    if r["returncode"]:
        raise RuntimeError("frozen task image missing; will not pull/build")
    parts = r["stdout"].split()
    if len(parts) != 3 or parts[0] != IMAGE_ID or parts[1:] != ["arm64", "linux"]:
        raise RuntimeError("frozen image identity/platform mismatch; will not substitute")
    ver = command("docker", "run", "--rm", "--network", "none", "--pull=never",
                  IMAGE, "codex", "--version")
    if ver["returncode"] or "0.163.0" not in ver["stdout"]:
        raise RuntimeError("in-image Codex CLI identity mismatch")
    return {"inspect": r["stdout"], "codex_version": ver["stdout"]}


def skill_preflight() -> dict:
    checks = {
        "upstream_commit": json.loads((ROOT / "env/video/video-use/source-manifest.json").read_text())["upstream_commit"],
        "skill": (ROOT / "env/video/video-use/source/SKILL.md").is_file(),
        "transcribe": (ROOT / "env/video/video-use/source/helpers/transcribe.py").is_file(),
        "render": (ROOT / "env/video/video-use/source/helpers/render.py").is_file(),
        "timeline_view": (ROOT / "env/video/video-use/source/helpers/timeline_view.py").is_file(),
    }
    if checks["upstream_commit"] != "43cfc566833548093455c9d4a46bd69913b7e552":
        raise RuntimeError("video-use source commit mismatch")
    if not all(checks[k] for k in ("skill", "transcribe", "render", "timeline_view")):
        raise RuntimeError("required video-use helper missing")
    return checks


def frozen_inputs() -> list[Path]:
    return [Path(__file__), ROOT / "tests/test_video_use_edit_pilot_01.py",
            ROOT / "env/video/video-use/codex-bailian-integration-01/config.toml",
            ROOT / "env/video/video-use/source/helpers/transcribe.py",
            ROOT / "env/video/video-use/source-manifest.json",
            TASK_PATH / "steps/solve/instruction.md", INPUT]


def starter_instruction() -> str:
    original = (TASK_PATH / "steps/solve/instruction.md").read_text()
    # The upstream instruction includes an illustrative timestamp; remove it so
    # it cannot anchor the agent's independent search.
    original = original.replace(
        '{"cuts": [{"start_ms": 12480, "end_ms": 12720, "reason": "hesitation"}]}',
        '{"cuts": [{"start_ms": <integer>, "end_ms": <integer>, "reason": "hesitation"}]}')
    return original + """

Execution mapping (same task semantics): the supplied input is available at
/workspace/materials/source.mp4 and you must deliver exactly
/workspace/output/output.mp4 and /workspace/output/cuts.json. The video-use
skill and its native helper scripts are available under /opt/video-use; its
Codex skill registration is active. Your private work/edit directory is
/workspace/project/edit. The transcript has already been created once by the
official video-use helpers/transcribe.py using ElevenLabs Scribe; read the
cached transcript and do not call transcription again. You have authority
from the user to locate the hesitation and make the one compliant cut; this
is preauthorization, not a fabricated chat confirmation. Follow the task's
minimal-edit requirements over default creative styling: no grade, captions,
music, animation, transition, or other deletions. Independently choose the
cut from the transcript and source; no cut time or EDL is provided. Use
video-use's render helper to produce the output. Inspect actual timeline
screenshots from the rendered video with view_image and keep those screenshots
in /workspace/project/edit/verify. Preserve the untouched source content.
Do not inspect external task repositories, archives, golden files, verifier
material, or answers. Do not access credential files. Do not rerun ASR.
"""


class Sampler(threading.Thread):
    def __init__(self, runtime, handle):
        super().__init__(daemon=True)
        self.runtime, self.handle = runtime, handle
        self.rows = []
        self.stop_event = threading.Event()
        self.lock = threading.Lock()

    def sample(self, role):
        t = time.monotonic_ns()
        row = {"t_monotonic_ns": t, "clock_domain": "system_monotonic", "role": role}
        try:
            cgroup = self.runtime.read_counters(self.handle, t).to_dict()
            cgroup.update(container_id=self.handle.container_id,
                          cgroup_version=self.handle.cgroup_version)
            row["cgroup"] = cgroup
        except Exception as e:
            row["cgroup_error"] = type(e).__name__
        # In-namespace interface counters are explicitly container-netns scoped.
        try:
            r = self.runtime.execute(self.handle, "cat /proc/net/dev", timeout_s=5, output_limit=20000)
            row["netns_proc_net_dev"] = {"scope": "container network namespace interfaces",
                                         "returncode": r.get("returncode"),
                                         "raw": r.get("output", "")}
        except Exception as e:
            row["netns_error"] = type(e).__name__
        with self.lock:
            self.rows.append(row)

    def run(self):
        self.sample("boundary_start")
        while not self.stop_event.wait(SAMPLE_S):
            self.sample("sample")
        self.sample("boundary_end")


def record_phase(runtime, handle, label, cmd, timeout):
    t0 = clock()
    try:
        res = runtime.execute(handle, cmd, timeout_s=timeout, output_limit=16_000_000)
        return {"phase": label, "start": t0, "end": clock(),
                "duration_s": (time.monotonic_ns() - t0["monotonic_ns"]) / 1e9,
                "returncode": res.get("returncode"), "timed_out": res.get("timed_out", False),
                "termination": res.get("termination"), "output": res.get("output", "")[-8000:]}
    except Exception as e:
        return {"phase": label, "start": t0, "end": clock(), "error": type(e).__name__}


def write_json(path: Path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, ensure_ascii=False) + "\n")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--prepare", action="store_true")
    ap.add_argument("--execute", action="store_true")
    approval_flag = f"--i-approve-{TASK.lower()}"
    ap.add_argument(approval_flag, action="store_true", dest="approved")
    args = ap.parse_args()
    REPORT_ROOT.mkdir(parents=True, exist_ok=True)
    PLAN_ROOT.mkdir(parents=True, exist_ok=True)
    if not INPUT.is_file() or digest(INPUT)["sha256"] != EXPECTED_INPUT:
        raise SystemExit("input hash missing/mismatch")
    ident = image_check()
    skill = skill_preflight()
    config_path = ROOT / "env/video/video-use/codex-bailian-integration-01/config.toml"
    cfg = tomllib.loads(config_path.read_text())
    provider = cfg["model_providers"][cfg["model_provider"]]
    route = {"provider": cfg["model_provider"], "model": cfg["model"],
             "base_url": provider["base_url"], "wire_api": provider["wire_api"],
             "api_key_env": provider["env_key"],
             "request_max_retries": provider["request_max_retries"],
             "stream_max_retries": provider["stream_max_retries"]}
    if (route["model"] != "qwen3.7-plus" or route["provider"] != "bailian"
            or route["wire_api"] != "responses" or route["request_max_retries"] != 0
            or route["stream_max_retries"] != 0):
        raise RuntimeError("explicit verified route mismatch")
    name_prefix = f"awc-{TASK.lower()}-{RUN_ID}-video_use_agent"
    occupied = command("docker", "ps", "-a", "--filter", f"name={name_prefix}", "--format", "{{.Names}}")
    if occupied["returncode"] or occupied["stdout"]:
        raise RuntimeError("this run namespace is already occupied; refusing to start")
    if not args.execute:
        plan = {"schema": f"{TASK.lower()}-environment-plan-v1", "task": TASK,
                "single_attempt": True, "architecture": "linux/arm64", "cpus": 2,
                "memory_bytes": 4 * 1024**3, "network": "bridge (shared; not API-specific)",
                "sample_interval_s": SAMPLE_S, "budgets_s": {"total": ATTEMPT_BUDGET_S,
                "agent_max": AGENT_BUDGET_S, "verifier_max": VERIFIER_BUDGET_S,
                "cleanup_reserve": 300},
                "sampling_config": {"interval_s": SAMPLE_S,
                    "container_scope": "agent container cgroup and its child processes",
                    "counters": ["cumulative CPU and interval average cores",
                                 "memory.current and kernel memory peak separately",
                                 "cgroup disk I/O cumulative bytes and valid interval rates",
                                 "per-interface bytes in the container network namespace"],
                    "network_scope": "shared bridge namespace; not API-specific",
                    "directory_boundaries": ["mounted input", "agent workspace", "output"]},
                "python_wiring": {"ordinary_shell": "Docker ENV PATH begins with /opt/video-use-venv/bin",
                    "login_shell": "/etc/profile restores venv PATH after its system PATH reset",
                    "codex_tools": "DockerCliRuntime executes bash -lc; login-shell equivalence validated offline"},
                "task": {"upstream_commit": "b2764ed4b2a4b5a1737026b63887b50bba62f793",
                         "instruction": "original task instruction; hash is in frozen identity",
                         "input_path": str(INPUT.relative_to(ROOT))},
                "model_route": route,
                "asr": {"helper": "official transcribe.py", "model": "scribe_v1",
                        "max_client_posts": 1, "retries": 0,
                        "cache": "transcripts/source.json; absent before call"},
                "image": ident, "skill_commit": skill["upstream_commit"],
                "approval": "separate explicit approval required before any attempt; no approval recorded"}
        write_json(PLAN_ROOT / "environment-plan.json", plan)
        frozen = frozen_inputs()
        identity = {"schema": f"{TASK.lower()}-frozen-identity-v1",
                    "run_id": RUN_ID, "task_commit": command("git", "-C", str(TASK_SOURCE), "rev-parse", "HEAD")["stdout"],
                    "input": digest(INPUT), "files": {str(p.relative_to(ROOT)): digest(p) for p in frozen},
                    "image": ident, "model_route": plan["model_route"], "transcription": plan["asr"],
                    "limits_s": plan["budgets_s"], "sampling_interval_s": SAMPLE_S,
                    "sampling_config": plan["sampling_config"],
                    "prepared_at_monotonic_ns": time.monotonic_ns(),
                    "prepared_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                    "approval": plan["approval"]}
        write_json(PLAN_ROOT / "frozen-identity.json", identity)
        if not identity["task_commit"].startswith("b2764ed4b2a4b5a1737026b63887b50bba62f793"):
            raise RuntimeError("task repository commit mismatch")
        print(json.dumps({"preflight": "PASS", "image": ident, "skill": skill,
                          "identity": identity}, indent=2))
        return 0
    if not args.approved:
        raise SystemExit("execution requires explicit approval flag")
    if not _IDENTITY_FILE.is_file():
        raise SystemExit("frozen identity missing")
    frozen_identity = json.loads(_IDENTITY_FILE.read_text())
    if frozen_identity.get("run_id") != RUN_ID:
        raise SystemExit("frozen run_id mismatch")
    for path in frozen_inputs():
        rel = str(path.relative_to(ROOT))
        actual = digest(path)
        if frozen_identity.get("files", {}).get(rel) != actual:
            raise SystemExit(f"frozen identity mismatch: {rel}")
    if frozen_identity.get("input") != digest(INPUT) or frozen_identity.get("image") != ident:
        raise SystemExit("frozen input/image mismatch")
    if RAW_ROOT.exists():
        raise SystemExit("run directory exists; refusing to overwrite or rerun")
    RAW_ROOT.mkdir(parents=True)
    start = clock()
    report = {"schema": f"{TASK.lower()}-raw-v1", "task": TASK,
              "run_id": RUN_ID, "attempt": 1, "approved_by": "user instruction in this session",
              "start": start, "limits_s": {"total": ATTEMPT_BUDGET_S,
              "agent": AGENT_BUDGET_S, "verifier": VERIFIER_BUDGET_S, "cleanup_reserve": 300},
              "image": ident, "source": digest(INPUT), "phases": [], "sampler_rows": [],
              "frozen_identity": str(_IDENTITY_FILE.relative_to(ROOT)),
              "model": {"provider": "Bailian Responses", "requested_model": "qwen3.7-plus",
                        "http_attempts": "unknown", "retries": 0}}
    (RAW_ROOT / "instruction.md").write_text(starter_instruction())
    # Distinct namespaces, and refuse if prior run names are present.
    runtime = DockerCliRuntime(authorized=True, collection=TASK)
    spec = ContainerSpec(run_id=RUN_ID, scope="video_use_agent", image=IMAGE,
                         cwd="/workspace", timeout_s=AGENT_BUDGET_S,
                         env={"DASHSCOPE_API_KEY": safe_credential(
                             Path("/home/lcq/.config/agent-workload-characterization/bailian.env"),
                             "DASHSCOPE_API_KEY"),
                              "ELEVENLABS_API_KEY": safe_credential(
                             Path("/home/lcq/.config/agent-workload-characterization/elevenlabs.env"),
                             "ELEVENLABS_API_KEY")},
                         mem_limit="4g", cpu_limit="2", network="bridge", pull="never")
    handle = None
    sampler = None
    try:
        handle = runtime.start(spec)
        report["container"] = {"id": handle.container_id, "name": spec.run_id,
                                "network_scope": "shared bridge network namespace; not API-specific",
                                "cpu_limit": 2, "memory_limit_bytes": 4 * 1024**3}
        for p in ("/workspace/materials", "/workspace/output", "/workspace/project/edit",
                  "/workspace/project/edit/transcripts", "/workspace/project/edit/verify"):
            res = record_phase(runtime, handle, "mkdir", f"mkdir -p {p}", 10)
            if res.get("returncode") != 0:
                raise RuntimeError("workspace setup failed")
        staging = [(INPUT, f"{handle.container_id}:/workspace/materials/source.mp4"),
                   (RAW_ROOT / "instruction.md", f"{handle.container_id}:/workspace/instruction.md")]
        for src, dst in staging:
            c = subprocess.run(["docker", "cp", str(src), dst], capture_output=True, text=True, timeout=60)
            report.setdefault("staging", []).append({"source_role": src.name, "returncode": c.returncode})
            if c.returncode:
                raise RuntimeError("staging failed")
        pre = record_phase(runtime, handle, "preflight", "test -r /workspace/materials/source.mp4 && test -w /workspace/output && test -L /opt/codex-home/skills/video-use && command -v ffmpeg && command -v ffprobe", 20)
        report["phases"].append(pre)
        if pre.get("returncode") != 0:
            raise RuntimeError("container path/skill preflight failed")
        report.setdefault("directory_boundaries", {})["before_agent"] = container_directory_boundaries(handle, runtime)
        # Explicit cache absence, then one official Scribe call; helper itself is inspected above.
        asr_cmd = ("test ! -e /workspace/project/edit/transcripts/source.json && "
                   "cd /opt/video-use && python3 helpers/transcribe.py /workspace/materials/source.mp4 "
                   "--edit-dir /workspace/project/edit")
        sampler = Sampler(runtime, handle)
        sampler.start()
        asr_start = clock()
        asr_budget = min(300, max(1, ATTEMPT_BUDGET_S - elapsed_s() - 900))
        asr = runtime.execute(handle, asr_cmd, timeout_s=asr_budget, output_limit=20000)
        report["phases"].append({"phase": "official_elevenlabs_transcribe", "start": asr_start,
                                  "end": clock(), "returncode": asr.get("returncode"),
                                  "timed_out": asr.get("timed_out", False),
                                  "output": asr.get("output", "")[-4000:],
                                  "request_count": 1 if asr.get("returncode") == 0 else "unknown; helper does one call and retries are absent"})
        if asr.get("returncode") != 0:
            if asr.get("timed_out"):
                report["asr_termination"] = runtime.terminate_workload(handle, timeout_s=15)
            raise RuntimeError("ASR failed; one-send policy stops attempt")
        agent_text = "codex exec --skip-git-repo-check --cd /workspace --dangerously-bypass-approvals-and-sandbox --model qwen3.7-plus --json -o /workspace/final_message.txt -- " + shlex.quote(starter_instruction())
        agent_budget = min(AGENT_BUDGET_S, max(1, ATTEMPT_BUDGET_S - elapsed_s() - 900))
        agent_start = clock()
        agent = runtime.execute(handle, agent_text, timeout_s=agent_budget, output_limit=16_000_000)
        report["phases"].append({"phase": "agent", "start": agent_start, "end": clock(),
                                  "allocated_timeout_s": agent_budget,
                                  "returncode": agent.get("returncode"),
                                  "timed_out": agent.get("timed_out", False),
                                  "termination": agent.get("termination"),
                                  "output_tail": agent.get("output", "")[-4000:]})
        if agent.get("timed_out"):
            report["agent_termination"] = runtime.terminate_workload(handle, timeout_s=15)
        # Stop and remove the agent container before opening private verifier assets.
        export = record_phase(runtime, handle, "export_native_rollouts",
                              "mkdir -p /workspace/export/rollouts && cp -R /opt/codex-home/sessions/. /workspace/export/rollouts/", 30)
        report["phases"].append(export)
        cp = subprocess.run(["docker", "cp", f"{handle.container_id}:/workspace/.", str(RAW_ROOT / "workspace")],
                            capture_output=True, text=True, timeout=120)
        report["export"] = {"returncode": cp.returncode, "stderr": cp.stderr[-1000:]}
        if cp.returncode:
            raise RuntimeError("artifact export failed")
        if sampler:
            sampler.stop_event.set(); sampler.join(timeout=10)
        report["sampler_rows"] = sampler.rows if sampler else []
        report["resource_summary"] = env01.summarize_intervals(resource_rows(
            report["sampler_rows"], handle.container_id))
        report["memory_summary"] = env01.mem_gauge_summary(resource_rows(
            report["sampler_rows"], handle.container_id))
        report["rollout_index"] = index_rollouts(RAW_ROOT / "workspace/export/rollouts")
        report["rollout_summary"] = rollout_summary(RAW_ROOT / "workspace/export/rollouts")
        report.setdefault("directory_boundaries", {})["after_agent"] = container_directory_boundaries(handle, runtime)
        runtime.stop(handle)
        report["removal_verification"] = runtime.verify_removal(handle)
        handle = None
        report["net_summary"] = network_summary(report["sampler_rows"])
    except BaseException as e:
        report["termination_reason"] = {"type": type(e).__name__, "message": str(e)[:500]}
        if handle:
            try:
                runtime.execute(handle,
                    "mkdir -p /workspace/export/rollouts && if [ -d /opt/codex-home/sessions ]; then cp -R /opt/codex-home/sessions/. /workspace/export/rollouts/; fi",
                    timeout_s=20, output_limit=1000)
                partial = subprocess.run(["docker", "cp", f"{handle.container_id}:/workspace/.",
                                          str(RAW_ROOT / "workspace")],
                                         capture_output=True, text=True, timeout=60)
                report["partial_export"] = {"returncode": partial.returncode,
                                             "stderr": partial.stderr[-1000:]}
            except Exception as export_error:
                report["partial_export"] = {"error": type(export_error).__name__}
        if sampler:
            sampler.stop_event.set(); sampler.join(timeout=10)
            report["sampler_rows"] = sampler.rows
    finally:
        if handle:
            try:
                runtime.stop(handle)
                report["removal_verification"] = runtime.verify_removal(handle)
            except Exception as e:
                report["removal_verification"] = f"check_failed:{type(e).__name__}"
    if report.get("sampler_rows"):
        cid = (report.get("container") or {}).get("id")
        report["resource_summary"] = env01.summarize_intervals(resource_rows(
            report["sampler_rows"], cid))
        report["memory_summary"] = env01.mem_gauge_summary(resource_rows(
            report["sampler_rows"], cid))
        report["net_summary"] = network_summary(report["sampler_rows"])
        report["resource_metrics"] = resource_metrics(report["sampler_rows"])
    # The official judge runs once after the agent is finished and its container
    # is removed, even if the attempt ended without deliverables.
    verifier_budget = min(VERIFIER_BUDGET_S, max(0.0, ATTEMPT_BUDGET_S - elapsed_s() - 300))
    report["verifier"] = verifier_after_agent(report, remaining=verifier_budget)
    report["end"] = clock()
    write_json(RAW_ROOT / "run-record.json", report)
    emit_manifest(RAW_ROOT)
    write_resource_report(report)
    print(json.dumps({"run": str(RAW_ROOT), "termination": report.get("termination_reason"),
                      "verifier": report.get("verifier", {}).get("status"),
                      "removal": report.get("removal_verification")}, ensure_ascii=False))
    return 0


def run_verifier(report, remaining=VERIFIER_BUDGET_S):
    # Uses only pre-downloaded verifier_only/golden data. Never runs test.sh (which curls MATERIALS_URL).
    private = ROOT / "data/raw/public/agentic_vbench/b2764ed4b2a4b5a1737026b63887b50bba62f793/exp-disfluency-interview-3-task01/verifier_only/golden"
    judge = TASK_PATH / "steps/solve/tests/judge.py"
    agent_ws = RAW_ROOT / "workspace"
    output = agent_ws / "output"
    source = INPUT
    if not (private / "cuts.json").is_file():
        return {"status": "not_run_missing_private_material", "judge": "original"}
    if remaining <= 0:
        return {"status": "not_run_budget_exhausted", "judge": "original"}
    verifier_dir = RAW_ROOT / "verifier_private"
    verifier_dir.mkdir()
    shutil.copy2(private / "cuts.json", verifier_dir / "gt-cuts.json")
    shutil.copy2(judge, verifier_dir / "judge.py")
    reward = verifier_dir / "reward.json"
    begin = clock()
    try:
        p = subprocess.Popen([sys.executable, str(verifier_dir / "judge.py"),
                              "--source-mp4", str(source), "--output-mp4", str(output / "output.mp4"),
                              "--output-cuts", str(output / "cuts.json"),
                              "--gt-cuts", str(verifier_dir / "gt-cuts.json"),
                              "--reward-json", str(reward), "--reward-txt", str(verifier_dir / "reward.txt")],
                             cwd=verifier_dir, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                             text=True, start_new_session=True)
        try:
            stdout, stderr = p.communicate(timeout=remaining)
        except subprocess.TimeoutExpired:
            os.killpg(p.pid, signal.SIGTERM)
            try:
                stdout, stderr = p.communicate(timeout=5)
            except subprocess.TimeoutExpired:
                os.killpg(p.pid, signal.SIGKILL)
                stdout, stderr = p.communicate()
            return {"status": "timeout", "start": begin, "end": clock(),
                    "timeout_s": remaining, "returncode": p.returncode,
                    "stdout": stdout[-4000:], "stderr": stderr[-4000:],
                    "process_group_terminated": True}
        return {"status": "completed", "start": begin, "end": clock(), "returncode": p.returncode,
                "stdout": stdout[-4000:], "stderr": stderr[-4000:],
                "reward": json.loads(reward.read_text()) if reward.exists() else None,
                "judge_sha256": digest(verifier_dir / "judge.py"),
                "source_judge_sha256": digest(judge),
                "judge_identity_match": digest(verifier_dir / "judge.py") == digest(judge),
                "materials_sha256": digest(verifier_dir / "gt-cuts.json"),
                "private_material_scope": "independent host verifier only; not exposed to agent"}
    except subprocess.TimeoutExpired:
        return {"status": "timeout", "start": begin, "end": clock(), "timeout_s": remaining}


def verifier_after_agent(report, remaining=VERIFIER_BUDGET_S):
    """Only run the private judge after the Agent phase was actually invoked."""
    if any(p.get("phase") == "agent" for p in report.get("phases", [])):
        return run_verifier(report, remaining=remaining)
    return {"status": "not_started",
            "reason": "agent_not_started_after_pre_agent_failure",
            "judge": "original; not invoked"}


def emit_manifest(root: Path):
    files = {}
    for p in sorted(root.rglob("*")):
        if p.is_file() and p.name != "manifest.json":
            files[p.relative_to(root).as_posix()] = digest(p)
    write_json(root / "manifest.json", {"schema": "video-use-edit-pilot-01-manifest-v1",
                                        "files": files, "self_hash": "omitted"})


def elapsed_s():
    return (time.monotonic_ns() - PROCESS_START_NS) / 1e9


def index_rollouts(root: Path) -> dict:
    """Preserve every native JSONL and index only fields actually recorded."""
    entries = []
    for path in sorted(root.rglob("rollout-*.jsonl")):
        for line_no, line in enumerate(path.read_text(errors="replace").splitlines(), 1):
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                entries.append({"file": path.name, "line": line_no, "kind": "unparsed"})
                continue
            payload = event.get("payload") or {}
            kind = payload.get("type", event.get("type", "unknown"))
            record = {"file": path.name, "line": line_no, "kind": kind}
            if event.get("type") == "response_item":
                record["item_type"] = payload.get("type")
                for key in ("name", "call_id", "id", "role", "status"):
                    if key in payload:
                        record[key] = payload[key]
                if payload.get("type") == "function_call":
                    record["arguments"] = payload.get("arguments")
                if payload.get("type") == "function_call_output":
                    record["output"] = payload.get("output")
                if payload.get("type") == "message":
                    record["content"] = payload.get("content")
            if event.get("type") in ("token_usage_record", "event_msg"):
                for key in ("info", "usage", "model", "response"):
                    if key in payload:
                        record[key] = payload[key]
            entries.append(record)
    return {"source": "complete native rollout JSONL; line references are exact",
            "events": entries, "http_request_count": "unknown"}


def rollout_summary(root: Path) -> dict:
    models, usage, tools, returns, errors = set(), [], [], [], []
    call_ids = []
    for path in sorted(root.rglob("rollout-*.jsonl")):
        for line in path.read_text(errors="replace").splitlines():
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            payload = event.get("payload") or {}
            item = payload if isinstance(payload, dict) else {}
            for obj in (event, payload, item.get("response"), item.get("info"), item.get("usage")):
                if isinstance(obj, dict):
                    for k in ("model", "model_id", "response_model"):
                        if isinstance(obj.get(k), str):
                            models.add(obj[k])
            if event.get("type") in ("token_usage_record", "event_msg") and (
                    "token" in str(payload.get("type", "")).lower()
                    or "usage" in event.get("type", "")):
                usage.append(payload)
            if event.get("type") == "response_item":
                typ = payload.get("type")
                if typ == "function_call":
                    tools.append({"name": payload.get("name"), "call_id": payload.get("call_id"),
                                  "arguments": payload.get("arguments")})
                    if payload.get("call_id"):
                        call_ids.append(payload["call_id"])
                elif typ == "function_call_output":
                    returns.append({"call_id": payload.get("call_id"), "output": payload.get("output")})
                elif typ in ("error", "function_call_error"):
                    errors.append(payload)
    return {"request_ids": "unknown when absent from native rollout",
            "tool_call_count": len(tools), "tool_calls": tools,
            "tool_return_count": len(returns), "tool_returns": returns,
            "error_count": len(errors), "errors": errors,
            "usage_events": usage, "response_models": sorted(models),
            "http_attempts": "unknown; Codex CLI rollout does not expose reliable HTTP counts"}


def network_summary(rows):
    result = {"scope": "container network namespace; per-interface counters, shared bridge",
              "api_specific": False, "interfaces": {}, "intervals": []}
    previous = None
    for row in rows:
        raw = row.get("netns_proc_net_dev", {}).get("raw", "")
        counters = {}
        for line in raw.splitlines()[2:]:
            if ":" not in line:
                continue
            name, values = line.split(":", 1)
            nums = values.split()
            if len(nums) >= 16:
                counters[name.strip()] = {"rx_bytes": int(nums[0]), "tx_bytes": int(nums[8])}
        result["interfaces"][row["t_monotonic_ns"]] = counters
        if previous:
            dt = (row["t_monotonic_ns"] - previous[0]) / 1e9
            for name in counters.keys() & previous[1].keys():
                rx, tx = counters[name]["rx_bytes"] - previous[1][name]["rx_bytes"], counters[name]["tx_bytes"] - previous[1][name]["tx_bytes"]
                if dt > 0 and rx >= 0 and tx >= 0:
                    result["intervals"].append({"t_monotonic_ns": row["t_monotonic_ns"],
                        "interface": name, "duration_s": dt, "rx_Bps": rx / dt,
                        "tx_Bps": tx / dt, "rx_delta_bytes": rx, "tx_delta_bytes": tx})
        previous = (row["t_monotonic_ns"], counters)
    result["interval_count"] = len(result["intervals"])
    return result


def resource_metrics(rows):
    valid_cpu_s = valid_window_s = read_b = write_b = io_window_s = 0.0
    cpu_pairs = io_pairs = 0
    current = peak = None
    for row in rows:
        c = row.get("cgroup") or {}
        m, p = c.get("mem_current_bytes"), c.get("mem_peak_bytes")
        if m is not None: current = m if current is None else max(current, m)
        if p is not None: peak = p if peak is None else max(peak, p)
    for a, b in zip(rows, rows[1:]):
        ca, cb = a.get("cgroup") or {}, b.get("cgroup") or {}
        dt = (b.get("t_monotonic_ns", 0) - a.get("t_monotonic_ns", 0)) / 1e9
        if dt <= 0: continue
        x, y = ca.get("cpu_usage_usec"), cb.get("cpu_usage_usec")
        if x is not None and y is not None and y >= x:
            valid_cpu_s += (y - x) / 1e6; valid_window_s += dt; cpu_pairs += 1
        r0, r1 = ca.get("io_read_bytes"), cb.get("io_read_bytes")
        w0, w1 = ca.get("io_write_bytes"), cb.get("io_write_bytes")
        if None not in (r0, r1, w0, w1) and r1 >= r0 and w1 >= w0:
            read_b += r1 - r0; write_b += w1 - w0; io_window_s += dt; io_pairs += 1
    return {"cpu_core_seconds": valid_cpu_s, "cpu_valid_interval_s": valid_window_s,
            "cpu_average_cores": valid_cpu_s / valid_window_s if valid_window_s else None,
            "cpu_valid_pairs": cpu_pairs, "io_read_bytes": read_b if io_pairs else None,
            "io_write_bytes": write_b if io_pairs else None,
            "io_valid_interval_s": io_window_s,
            "io_read_Bps": read_b / io_window_s if io_window_s else None,
            "io_write_Bps": write_b / io_window_s if io_window_s else None,
            "io_valid_pairs": io_pairs, "max_sampled_memory_current_bytes": current,
            "max_kernel_memory_peak_bytes": peak,
            "missing_counters_remain_null": True}


def resource_rows(rows, container_id):
    """Adapt saved cgroup rows to the project's shared measurement schema."""
    normalized = []
    for row in rows:
        item = dict(row)
        cgroup = dict(item.get("cgroup") or {})
        if container_id:
            cgroup["container_id"] = container_id
        item["container"] = cgroup
        normalized.append(item)
    return normalized


def container_directory_boundaries(handle, runtime):
    paths = {"materials": "/workspace/materials", "agent_workspace": "/workspace/project",
             "output": "/workspace/output"}
    out = {}
    for role, path in paths.items():
        cmd = f"du -sb {shlex.quote(path)} 2>/dev/null || true"
        r = runtime.execute(handle, cmd, timeout_s=10, output_limit=2000)
        vals = []
        for line in r.get("output", "").splitlines():
            parts = line.split(None, 1)
            if parts and parts[0].isdigit():
                vals.append({"bytes": int(parts[0]), "path": parts[1] if len(parts)>1 else path})
        out[role] = {"path": path, "measurement": vals, "non_overlapping_boundary": True}
    return out


def write_resource_report(report):
    REPORT_ROOT.mkdir(parents=True, exist_ok=True)
    rows = report.get("sampler_rows", [])
    points = []
    for row in rows:
        c = row.get("cgroup") or {}
        points.append({"t": row.get("t_monotonic_ns"),
                       "cpu_s": (c.get("cpu_usage_usec") / 1e6
                                 if c.get("cpu_usage_usec") is not None else None),
                       "memory": c.get("mem_current_bytes"),
                       "io_read": c.get("io_read_bytes"),
                       "io_write": c.get("io_write_bytes")})
    interfaces = {}
    ns = report.get("net_summary", {})
    for iv in ns.get("intervals", []):
        interfaces.setdefault(iv["interface"], []).append(
            {"t": iv["t_monotonic_ns"], "rx": iv["rx_Bps"], "tx": iv["tx_Bps"]})
    panels = [
        ("CPU cumulative (core-seconds)", [([p["t"], p["cpu_s"]] for p in points)], ["CPU"]),
        ("Memory current (MiB); kernel peak separate", [([p["t"], p["memory"] / 1048576]
                                                            for p in points if p["memory"] is not None)], ["current"]),
        ("cgroup disk I/O cumulative (MiB)", [([p["t"], p["io_read"] / 1048576]
                                                for p in points if p["io_read"] is not None),
                                               ([p["t"], p["io_write"] / 1048576]
                                                for p in points if p["io_write"] is not None)], ["read", "write"]),
        ("container netns per-interface (KiB/s)",
         [([p["t"], p[direction] / 1024] for p in values)
          for values in interfaces.values() for direction in ("rx", "tx")],
         [f"{name} {direction.upper()}" for name in interfaces for direction in ("rx", "tx")]),
    ]
    colors = ("#1565c0", "#d84315", "#2e7d32", "#7b1fa2")
    width, height, panel_h = 1100, 880, 220
    svg = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
           '<rect width="100%" height="100%" fill="white"/>',
           '<style>text{font-family:sans-serif;fill:#263238}.title{font-size:18px;font-weight:bold}.label{font-size:12px}</style>']
    for idx, (title, series, labels) in enumerate(panels):
        top = idx * panel_h + 12
        svg.append(f'<text x="70" y="{top+16}" class="title">{title}</text>')
        svg.append(f'<path d="M70 {top+185} H1050 M70 {top+38} V{top+185}" stroke="#90a4ae" fill="none"/>')
        flattened = [list(s) for s in series]
        flat = [q for s in flattened for q in s if q[0] is not None and q[1] is not None]
        if not flat:
            svg.append(f'<text x="90" y="{top+110}" class="label">缺测：无有效样本</text>')
            continue
        x0, x1 = min(x for x, _ in flat), max(x for x, _ in flat)
        y0, y1 = min(y for _, y in flat), max(y for _, y in flat)
        if x1 == x0: x1 = x0 + 1
        if y1 == y0: y1 = y0 + 1
        for si, seq in enumerate(flattened):
            seq = [(x, y) for x, y in seq if x is not None and y is not None]
            if not seq: continue
            coords = " ".join(f"{70+(x-x0)/(x1-x0)*970:.1f},{top+185-(y-y0)/(y1-y0)*140:.1f}" for x, y in seq)
            svg.append(f'<polyline points="{coords}" fill="none" stroke="{colors[si%len(colors)]}" stroke-width="2"/>')
            svg.append(f'<text x="{820+si*80}" y="{top+17}" class="label" fill="{colors[si%len(colors)]}">{labels[si] if si<len(labels) else "series"}</text>')
    svg.append('</svg>')
    (REPORT_ROOT / "resource-curves.svg").write_text("\n".join(svg))
    verifier = report.get("verifier", {})
    reward = verifier.get("reward")
    metrics = report.get("resource_metrics", {})
    completeness = ("complete" if rows and report.get("phases")
                    and any(p.get("phase") == "agent" for p in report.get("phases", []))
                    and verifier.get("returncode") == 0
                    and verifier.get("reward") is not None
                    and report.get("removal_verification") == "removed"
                    and report.get("resource_metrics", {}).get("cpu_valid_pairs", 0) > 1
                    else "partial")
    agent = next((p for p in report.get("phases", []) if p.get("phase") == "agent"), {})
    asr = next((p for p in report.get("phases", []) if p.get("phase") == "official_elevenlabs_transcribe"), {})
    summary = ["# VIDEO-USE-EDIT-PILOT-01 执行报告", "",
               f"- run_id: `{report.get('run_id')}`；执行次数：一次。", 
               f"- 输入：{report.get('source', {}).get('bytes')} bytes，SHA-256 `{report.get('source', {}).get('sha256')}`。",
               f"- 测量完整性：{completeness}；0.5 秒目标采样，实际 {len(rows)} 行；缺测保持 null。",
               f"- CPU：{metrics.get('cpu_core_seconds')} core-s；有效区间平均 {metrics.get('cpu_average_cores')} core。",
               f"- 内存：sampled current 峰值 {metrics.get('max_sampled_memory_current_bytes')} B；kernel peak {metrics.get('max_kernel_memory_peak_bytes')} B，分列。",
               f"- 磁盘 I/O：read {metrics.get('io_read_bytes')} B / {metrics.get('io_read_Bps')} B/s；write {metrics.get('io_write_bytes')} B / {metrics.get('io_write_Bps')} B/s。",
               f"- 官方任务结果：verifier 进程状态 `{verifier.get('status', '未运行')}`，returncode `{verifier.get('returncode', 'unknown')}`；reward `{reward}`。",
               f"- Agent 终止原因：returncode `{agent.get('returncode', 'not_started')}`，timeout `{agent.get('timed_out', 'not_started')}`；{report.get('termination_reason', {}).get('message', '按执行流程结束或结果字段见 run-record.json')}。",
               f"- ASR：官方 Scribe 转写 returncode `{asr.get('returncode', 'unknown')}`；发送次数 `{asr.get('request_count', 'unknown')}`；不重试、不换供应商。",
               f"- 资源 scope：Agent 容器 cgroup CPU、memory.current/kernel peak、cgroup I/O；网络为共享容器 netns 的逐接口字节，不代表 API 专属流量。",
               f"- 清理/归档：容器 `{report.get('removal_verification', 'unknown')}`；run-record 与逐文件 bytes/SHA manifest 已保存。",
               "- 请求/工具/返回/错误/usage/响应模型以 raw 内完整 Codex rollout 与事件索引为准；可靠 HTTP 次数 unknown。",
               "- 网络接口和时间边界详见 raw `run-record.json`；曲线：`resource-curves.svg`。", ""]
    (REPORT_ROOT / "summary.md").write_text("\n".join(summary))


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        raise SystemExit(f"preflight/runner error: {type(exc).__name__}: {exc}")
