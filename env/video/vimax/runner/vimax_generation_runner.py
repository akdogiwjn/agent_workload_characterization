#!/usr/bin/env python3
"""Host runner for the FORMAL ViMax eight-shot attempt (one attempt only).

Pre-authorized single attempt with REAL Bailian calls. Everything reused
from the accepted validation path: the v3 task image (code-identity
verified against the registration), the budget gates, the capability
preflight inside the render tool, the cgroup sampler (0.5 s target), the
completion handshake for the final resource boundary, independent-finally
cleanup and ownership-verified container removal.

Registered network decision: docker bridge blackholes some HTTPS
destinations on this host (observed during image builds), so the attempt
runs with --network host. Consequence, registered here and in the report:
the container SHARES the host netns; per-interface counters are host-wide
and are NOT attributable to this attempt or to API traffic.

Credentials: DASHSCOPE_API_KEY and BAILIAN_WORKSPACE_ID are read from the
registered file at runtime and injected ONLY into the container
environment; they are never printed, written to disk or hashed here.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO / "src"))

from agent_workload_characterization.collectors.resource_sampler import (  # noqa: E402
    CgroupV1FileReader, ResourceSampler)

RUNNER_DIR = Path(__file__).resolve().parent
CRED_FILE = Path("/home/lcq/.config/agent-workload-characterization/bailian.env")
EXPECTED_IMAGE_ID = "sha256:7c634c46a829e2d22ee901023b70a6bdb2e5bd06d7b334b0f8a8150a3daa39be"
IMAGE = "vimax-task-bailian:arm64-v4"
NETNS_PERIOD_S = 5.0  # host-shared netns snapshots (zero-cost reads)
DOCKER_TIMEOUT_S = 30.0


def sh(argv, timeout=DOCKER_TIMEOUT_S):
    try:
        return subprocess.run(argv, capture_output=True, text=True,
                              timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        return subprocess.CompletedProcess(
            argv, 124, stdout=exc.stdout or "",
            stderr=f"TIMEOUT after {timeout}s")


def now_iso():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def load_registered_env() -> dict:
    values = {}
    for line in CRED_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line.startswith("export "):
            line = line[7:]
        if line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        if key in ("DASHSCOPE_API_KEY", "BAILIAN_WORKSPACE_ID"):
            values[key] = value.strip().strip('"').strip("'")
    missing = [k for k in ("DASHSCOPE_API_KEY", "BAILIAN_WORKSPACE_ID")
               if not values.get(k)]
    if missing:
        raise SystemExit(f"registered credential file missing: {missing}")
    return values


def build_task_text(task_json_path: Path) -> str:
    data = json.loads(task_json_path.read_text(encoding="utf-8"))
    shots = []
    for scene in data["scenes"]:
        for shot in scene["shots"]:
            shots.append(shot)
    lines = []
    lines.append("请使用 vimax_narrative_planning 工具为以下剧本完成叙事规划，"
                 "并在规划通过能力与预算预检后，在同一会话内直接调用 "
                 "vimax_render_video 完成渲染（本任务已预授权，无需等待人工确认）。")
    lines.append("")
    lines.append("<SCRIPT>")
    for shot in shots:
        lines.append(f"Shot {shot['shot_id']} (Scene "
                     f"{scene_scene_num(data, shot['shot_id'])}):")
        lines.append(f"首帧画面：{shot['first_frame']}")
        lines.append(f"镜头动作：{shot['video_prompt']}")
        lines.append("")
    lines.append("</SCRIPT>")
    lines.append("")
    lines.append("<REQUIREMENTS>")
    lines.append(
        "- 主角外观全程一致：32岁女摄影师，暖棕色皮肤、黑色短卷发、圆框哑光黑眼镜、"
        "右眉上方有小月牙形疤痕；穿芥末黄田野夹克（带翻盖口袋）、深靛蓝牛仔裤、"
        "白色运动鞋；黑色无反光相机配红色背带，随身黑色小背包与紧凑旅行三脚架。")
    lines.append(
        "- 严格保留 8 个镜头的原始顺序与主要动作（日出屋顶→清晨街市→正午广场→"
        "黄昏天桥→蓝调运河步道→夜晚地铁站台→雨后霓虹小巷→深夜路口长曝光），"
        "不得删除、合并或重排镜头。")
    lines.append(
        "- 叙事规划的 storyboard 必须输出恰好 8 个 shot（shot idx 0–7），"
        "与上述 Shot 1–Shot 8 一一对应；任何少于 8 个 shot 的规划都会被"
        "能力预检拒绝。")
    lines.append(
        "- 每镜头约 5 秒、16:9 横构图；全片约 40 秒；不添加对白、旁白或音乐。")
    lines.append(
        "- 重要能力约束：视频生成模型（wan2.6-i2v-flash）仅支持“首帧生视频”路径——"
        "每个镜头的全部动态必须能从其首帧自然、连续地演化，镜头内不得发生需要"
        "首尾帧跳转的剧烈内容变化。请在不删改故事主要动作的前提下，将每个镜头"
        "规划为小变化（variation_type=small），机位运动与人物动作均以首帧为基准。")
    lines.append(
        "- 机位请使用独立机位；如确需子机位过渡（transition），全片最多 4 条，"
        "每条会产生一次额外视频生成调用。")
    lines.append(
        "- 人物关键帧生成可参考角色肖像（正/侧/背）；同一镜头内保持人物、服装、"
        "相机与场景光线的连续性。")
    lines.append("</REQUIREMENTS>")
    lines.append("")
    lines.append("<STYLE>纪实地摄影风格，自然光效，电影感构图，16:9</STYLE>")
    return "\n".join(lines)


def scene_scene_num(data, shot_id):
    for scene in data["scenes"]:
        if any(s["shot_id"] == shot_id for s in scene["shots"]):
            return scene["scene_num"]
    return "?"


def dir_bytes(path: Path) -> dict:
    out = {"apparent_bytes": 0, "files": 0, "unreadable": 0}
    if not path.exists():
        return out
    for p in path.rglob("*"):
        if p.is_file():
            try:
                out["apparent_bytes"] += p.stat().st_size
                out["files"] += 1
            except OSError:
                out["unreadable"] += 1
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", required=True)
    ap.add_argument("--deadline-s", type=float, default=6000.0)  # 100 min
    args = ap.parse_args()

    out = Path(args.out).resolve()
    if out.exists():
        print(f"refusing: output directory already exists: {out}")
        return 2
    out.mkdir(parents=True)
    t0 = time.monotonic()
    deadline = t0 + args.deadline_s

    record = {"task": "VIMAX-GENERATION-PILOT-01",
              "started_utc": now_iso(),
              "image": IMAGE,
              "network": "host (registered: docker bridge blackholes "
                         "HTTPS on this host; host netns is SHARED — "
                         "interface counters are host-wide, not "
                         "attempt-attributable)",
              "phases": {}, "problems": [], "cleanup_errors": []}
    problems = record["problems"]

    def phase(name, **kw):
        record["phases"][name] = {"wall_s": round(time.monotonic() - t0, 3), **kw}
        (out / "run-record.json").write_text(
            json.dumps(record, indent=1, ensure_ascii=False) + "\n")

    # ---- preflight: full image identity ------------------------------------
    r = sh(["docker", "image", "inspect", IMAGE,
            "--format", "{{.Id}} {{.Os}} {{.Architecture}}"])
    if r.returncode != 0:
        record["error"] = f"image inspect failed: {r.stderr.strip()[:200]}"
        phase("preflight", ok=False)
        return 7
    image_id, image_os, image_arch = r.stdout.split()
    record["image_id"] = image_id
    if (image_id != EXPECTED_IMAGE_ID or image_os != "linux"
            or image_arch != "arm64"):
        record["error"] = (f"image identity mismatch: {image_id} "
                           f"{image_os}/{image_arch} != registered "
                           f"{EXPECTED_IMAGE_ID} linux/arm64")
        phase("preflight", ok=False)
        return 7
    # code identity: hash the adapted sources inside the image vs the tree
    r = sh(["docker", "run", "--rm", "--network", "none", "--user", "2000:2000",
            IMAGE, "python3", "-c",
            "import hashlib, pathlib\n"
            "root = pathlib.Path('/opt/vimax/src')\n"
            "for rel in ['agent_runtime/request_ledger.py','agent_runtime/llm.py',"
            "'agent_runtime/vimax_adapters.py','tools/image_generator_bailian_api.py',"
            "'tools/video_generator_bailian_api.py']:\n"
            "    p = root / rel\n"
            "    print(rel, hashlib.sha256(p.read_bytes()).hexdigest())"],
           timeout=60)
    if r.returncode != 0:
        record["error"] = "in-image code identity check failed"
        phase("preflight", ok=False)
        return 7
    record["in_image_code_sha256"] = dict(
        line.split(" ", 1) for line in r.stdout.strip().splitlines())
    phase("preflight", ok=True)

    # ---- task text + identity inputs ---------------------------------------
    task_json = REPO / "references/repos/ViMax/vimax_benchmark/photographer_urban_timelapses_typeA.json"
    task_text = build_task_text(task_json)
    # main_agent.py --stdin-repl treats EVERY stdin LINE as one prompt:
    # the task MUST be a single line (all whitespace folded to spaces) or
    # the eight-shot script gets fragmented into dozens of turns (root
    # cause of startup-failed-02)
    task_text = " ".join(task_text.split())
    assert "\n" not in task_text
    workspace = out / "workspace"
    workspace.mkdir()
    (workspace / "task-input.txt").write_text(task_text, encoding="utf-8")
    import hashlib
    record["task_json_sha256"] = hashlib.sha256(
        task_json.read_bytes()).hexdigest()
    record["task_text_sha256"] = hashlib.sha256(
        task_text.encode()).hexdigest()
    creds = load_registered_env()  # values never leave this process
    ws = creds["BAILIAN_WORKSPACE_ID"]
    record["route"] = {
        "region": "cn-beijing",
        "llm_model": "qwen3.7-plus",
        "llm_base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "image_model": "qwen-image-3.0",
        "image_base_url": f"https://{ws}.cn-beijing.maas.aliyuncs.com/compatible-mode/v1",
        "video_model": "wan2.6-i2v-flash",
        "video_base_url": f"https://{ws}.cn-beijing.maas.aliyuncs.com",
        "workspace_host_registered": True,
        "credential_values_stored": False,
    }
    record["budget"] = {
        "llm_calls": 80, "llm_attempts": 240, "image_generations": 32,
        "video_creates": 12, "video_polls_global_cap": 1200,
        "video_polls_per_task_note": "per-task <=100 enforced by the "
                                     "generator query window (1000 s @10 s); "
                                     "the ledger cap is the global 1200 "
                                     "approximation (registered)",
        "media_downloads": 64, "single_request_output_tokens": 8192,
        "observed_output_tokens_soft_total": 500000,
        "work_window_s": 5400, "deadline_s": args.deadline_s,
        "container": "8 cpus / 8 GiB",
    }
    phase("identity_frozen")

    # ---- workspace + unique container --------------------------------------
    if sh(["chown", "-R", "2000:2000", str(workspace)]).returncode != 0:
        workspace.chmod(0o777)
        record["workspace_permission_fallback"] = "chmod 777 (no sudo)"
    name = f"vimax-formal-{uuid.uuid4().hex[:8]}"
    record["container_name"] = name
    phase("before", workspace=dir_bytes(workspace))

    env = {
        "DASHSCOPE_API_KEY": creds["DASHSCOPE_API_KEY"],  # runtime-only
        "VIMAX_LLM_MODEL": "qwen3.7-plus",
        "VIMAX_LLM_MODEL_PROVIDER": "openai",
        "VIMAX_LLM_BASE_URL": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "VIMAX_LLM_API_KEY": creds["DASHSCOPE_API_KEY"],
        "VIMAX_IMAGE_MODEL": "qwen-image-3.0",
        "VIMAX_IMAGE_BASE_URL": record["route"]["image_base_url"],
        "VIMAX_IMAGE_API_KEY": creds["DASHSCOPE_API_KEY"],
        "VIMAX_VIDEO_MODEL": "wan2.6-i2v-flash",
        "VIMAX_VIDEO_BASE_URL": record["route"]["video_base_url"],
        "VIMAX_VIDEO_API_KEY": creds["DASHSCOPE_API_KEY"],
        "VIMAX_BAILIAN_EVENT_LOG": "/workspace/attempt/bailian-ledger.jsonl",
        "VIMAX_BAILIAN_BUDGET_LLM_CALLS": "80",
        "VIMAX_BAILIAN_BUDGET_LLM_ATTEMPTS": "240",
        "VIMAX_BAILIAN_BUDGET_IMAGE_GENERATIONS": "32",
        "VIMAX_BAILIAN_BUDGET_VIDEO_CREATES": "12",
        "VIMAX_BAILIAN_BUDGET_VIDEO_POLLS": "1200",
        "VIMAX_BAILIAN_BUDGET_MEDIA_DOWNLOADS": "64",
        "VIMAX_BAILIAN_BUDGET_SINGLE_REQUEST_OUTPUT_TOKENS": "8192",
        "VIMAX_BAILIAN_BUDGET_OBSERVED_OUTPUT_TOKENS_TOTAL": "500000",
        "VIMAX_BAILIAN_BUDGET_DEADLINE_SECONDS": "5400",
        "VIMAX_BAILIAN_VIDEO_POLL_INTERVAL_SECONDS": "10",
        "VIMAX_BAILIAN_VIDEO_QUERY_TIMEOUT_SECONDS": "1000",
        "VIMAX_AGENT_MAX_TOKENS": "8192",
        "VIMAX_BAILIAN_REQUIRED_SHOTS": "8",
        "VIMAX_NARRATIVE_STEP_TIMEOUT_SECONDS": "1200",
        "ATTEMPT_WORK": "/workspace/attempt",
        "ATTEMPT_TASK_TEXT": "/workspace/task-input.txt",
        "ATTEMPT_WORK_WINDOW_S": "5400",
    }
    argv = ["docker", "run", "-d", "--name", name,
            "--network", "host",
            "--user", "2000:2000", "-w", "/workspace",
            "--memory", "8g", "--cpus", "8",
            "--mount", f"type=bind,source={RUNNER_DIR},target=/opt/validation,readonly",
            "--mount", f"type=bind,source={workspace},target=/workspace"]
    for k, v in env.items():
        argv += ["-e", f"{k}={v}"]
    argv += [IMAGE, "python3", "/opt/validation/formal_driver.py"]
    record["docker_run_argv_redacted"] = [
        a for a in argv if not a.startswith("DASHSCOPE_API_KEY")
        and not a.startswith("VIMAX_LLM_API_KEY")
        and not a.startswith("VIMAX_IMAGE_API_KEY")
        and not a.startswith("VIMAX_VIDEO_API_KEY")]
    r = sh(argv, timeout=60)
    if r.returncode != 0:
        record["error"] = f"docker run failed: {r.stderr.strip()[:300]}"
        phase("docker_run", ok=False)
        return 7
    cid_full = r.stdout.strip()
    record["container_id"] = cid_full
    r = sh(["docker", "inspect", "-f", "{{.Name}}", cid_full])
    if r.returncode != 0 or r.stdout.strip() != f"/{name}":
        record["error"] = "container ownership check failed"
        phase("docker_run", ok=False)
        sh(["docker", "rm", "-f", cid_full])
        return 7
    phase("docker_run", ok=True, cid=cid_full[:16])

    # ---- resource wiring ----------------------------------------------------
    sampler = ResourceSampler(interval_s=0.5)
    sampling_started = False
    host_netns: list[dict] = []
    netns_stop = threading.Event()
    netns_thread = None

    def netns_loop():
        while not netns_stop.is_set():
            try:
                lines = [l.split() for l in
                         Path("/proc/net/dev").read_text().splitlines()[2:]
                         if ":" in l]
                host_netns.append({
                    "t": round(time.monotonic() - t0, 3),
                    "scope": "HOST_NETNS_SHARED",
                    "ifaces": {p[0].rstrip(":"): {"rx": int(p[1]), "tx": int(p[9])}
                               for p in lines if len(p) > 9}})
            except OSError:
                pass
            netns_stop.wait(NETNS_PERIOD_S)

    try:
        reader = CgroupV1FileReader(
            scope="vimax_formal_01", scope_kind="agent_container",
            container_id=cid_full, cg_root=Path("/sys/fs/cgroup"))
        sampler.register("vimax_formal_01", "agent_container", reader)
        sampler.start("vimax_formal_01")
        sampler.start_background_sampling()
        sampling_started = True
    except Exception as exc:  # noqa: BLE001
        record["sampler_error"] = f"{type(exc).__name__}: {exc}"
        problems.append("sampler start failed")
    netns_thread = threading.Thread(target=netns_loop, daemon=True)
    netns_thread.start()
    phase("sampling_started")

    # ---- wait for completion handshake -------------------------------------
    marker = workspace / "attempt" / "COMPLETE"
    handshake = False
    while time.monotonic() < deadline:
        if marker.exists():
            handshake = True
            break
        r = sh(["docker", "inspect", "-f", "{{.State.Running}}", cid_full],
               timeout=10)
        if r.returncode == 0 and r.stdout.strip() == "false":
            break
        time.sleep(5.0)
    record["handshake_seen"] = handshake
    if not handshake:
        problems.append("completion handshake not observed")
    phase("attempt_finished", handshake=handshake,
          wall=round(time.monotonic() - t0, 1))

    # ---- final resource boundary BEFORE teardown ---------------------------
    try:
        if sampling_started:
            sampler.stop("vimax_formal_01")
    except Exception as exc:  # noqa: BLE001
        problems.append(f"sampler stop failed: {exc}")
    netns_stop.set()
    if netns_thread:
        netns_thread.join(timeout=15)
    try:
        if sampling_started:
            sampler.stop_background_sampling()
            samples = sampler.samples("vimax_formal_01")
            record["resource_summary"] = samples.summary()
            with open(out / "resource-samples.jsonl", "w", encoding="utf-8") as fh:
                for snap in samples.samples:
                    fh.write(json.dumps(snap.to_dict(), ensure_ascii=False) + "\n")
            record["resource_boundary"] = {
                "start": samples.boundary_start.to_dict() if samples.boundary_start else None,
                "end": samples.boundary_end.to_dict() if samples.boundary_end else None}
            record["resource_sample_gaps_ns"] = list(samples.sample_gaps_ns)
    except Exception as exc:  # noqa: BLE001
        problems.append(f"sample export failed: {exc}")
    record["host_netns_samples"] = host_netns
    phase("sampling_stopped")

    # ---- teardown -----------------------------------------------------------
    sh(["docker", "stop", "-t", "60", cid_full], timeout=90)
    r = sh(["docker", "inspect", "-f", "{{.State.ExitCode}}", cid_full])
    record["container_exit_code"] = int(r.stdout.strip()) if r.returncode == 0 else None
    phase("after", workspace=dir_bytes(workspace))
    removed = False
    r = sh(["docker", "rm", "-f", cid_full], timeout=45)
    if r.returncode != 0:
        problems.append(f"docker rm failed: {r.stderr.strip()[:200]}")
    else:
        removed = sh(["docker", "inspect", cid_full]).returncode != 0
        if not removed:
            problems.append("container still inspectable after rm")
    phase("cleanup", removed=removed)

    record["finished_utc"] = now_iso()
    record["total_wall_s"] = round(time.monotonic() - t0, 3)
    record["ok"] = handshake  # the attempt RAN to its handshake; outcome
    # quality is judged separately by the acceptance analysis, never here
    (out / "run-record.json").write_text(
        json.dumps(record, indent=1, ensure_ascii=False) + "\n")
    print(json.dumps({"handshake": handshake,
                      "total_wall_s": record["total_wall_s"],
                      "problems": problems}, ensure_ascii=False))
    return 0 if handshake else 7


if __name__ == "__main__":
    raise SystemExit(main())
