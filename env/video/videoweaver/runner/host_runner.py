#!/usr/bin/env python3
"""VIDEO-WEAVER fixed production entry (host-side lifecycle) — v2.

One executable path for offline acceptance and live production:

- offline:  network=none, gateway forwards to the local fake upstream (synthetic
            credential + synthetic media). Same production code (pipeline, Codex,
            skills, FFmpeg, budget, monitoring, export, cleanup).
- live:     real routing (gateway upstream = dashscope workspace domain), real
            CODEX_HOME provider config, runtime-injected upstream credential held
            ONLY by the gateway. This round validates the live branch with a
            synthetic credential provider and a fake upstream transport (no fake
            config / no fake mounts / no add-host); it never calls the real API.

Budget is enforced pre-send by the in-container gateway ledger (persistent JSON),
not by post-hoc rollout counting. Every run uses a unique new root directory
(never reset). Full per-point resource samples, netns, directory boundaries and
exec stdout/stderr are persisted.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import signal
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
from agent_workload_characterization.collectors.execution_measurement import (  # noqa: E402
    directory_footprint_snapshot, read_resource_stream, validate_resource_stream,
    assess_resource_quality, sample_content_digest)
from agent_workload_characterization.collectors.resource_sampler import (  # noqa: E402
    CounterSnapshot)

DOCKER = ["docker", "--host", "unix:///var/run/docker.sock"]
IMAGE = "videoweaver-task-bailian:arm64-v2"
IMAGE_ID = "sha256:933363d720001f71a74bd261c14a3480595942ec4612857797f3ca1814dbb6eb"

DEFAULT_CONFIG = {
    "task_id": "VIDEO-WEAVER-RUN",
    "image": IMAGE,
    "image_id": IMAGE_ID,
    "case_dir": "env/video/videoweaver/case/dataset",
    "merge_inputs_dir": "",
    "gateway_script": "env/video/videoweaver/gateway/gateway.py",
    "fake_script": "env/video/videoweaver/fake/fake_responses.py",   # offline only
    "codex_config": "env/video/videoweaver/runner/production-codex-config.toml",
    "merge_skill_fix": "env/video/videoweaver/source/skills/merge-video/SKILL.md",
    "target_task": "photographer_urban_timelapses",
    "case_id": "case-photographer-urban-01",
    "exp_id": "videoweaver-run",
    "sample_interval_s": 0.5,
    "netns_period_s": 2.0,
    "work_seconds": 900,
    "closeout_seconds": 120,
    "cpuset_cpus": None,          # host-specific; do NOT hardcode
    "pids_limit": 4096,
    "memory": "4g",
    "gateway_port": 8899,
    "gateway_upstream_llm": "http://127.0.0.1:8666",  # offline root; path added by gateway
    "gateway_upstream_media": "http://127.0.0.1:8666",                    # offline
    "gateway_llm_base": "http://127.0.0.1:8899/compatible-mode/v1",
    "gateway_video_base": "http://127.0.0.1:8899",
    "upstream_api_key": "synthetic-offline-key",
    "budget": {
        "max_llm_calls": 40,
        "max_image_creates": 20,
        "max_video_creates": 20,
        "max_video_polls": 400,
        "max_media_downloads": 40,
        "deadline_seconds": 900,
        "observed_output_tokens_soft": 500000,
    },
}


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def atomic_write(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def run(argv, timeout=30):
    try:
        return subprocess.run(argv, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired as e:
        return subprocess.CompletedProcess(argv, 124, e.stdout or "", "TIMEOUT")


def load_config(path: str | None, mode: str) -> dict:
    cfg = json.loads(json.dumps(DEFAULT_CONFIG))
    if path:
        cfg.update(json.loads(Path(path).read_text()))
    for key in ("case_dir", "gateway_script", "fake_script", "codex_config", "merge_skill_fix"):
        cfg[key] = str(REPO / cfg[key])
    if cfg.get("merge_inputs_dir"):
        cfg["merge_inputs_dir"] = str(REPO / cfg["merge_inputs_dir"])
    cfg["video_poll_interval_s"] = os.environ.get("VW_VIDEO_POLL_INTERVAL", "10" if mode == "live" else "1")
    if mode == "live":
        # real routing structure: LLM -> dashscope compatible-mode (verified),
        # media -> the workspace domain. No fake elements are part of the live
        # config. The acceptance harness may inject a fake upstream transport
        # via env only.
        cfg["network"] = os.environ.get("VW_LIVE_NETWORK", "bridge")
        ws = os.environ.get("BAILIAN_WORKSPACE_ID", "synthetic-ws")
        cfg["gateway_upstream_llm"] = (os.environ.get("VW_GATEWAY_UPSTREAM_LLM")
                                       or "https://dashscope.aliyuncs.com")
        cfg["gateway_upstream_media"] = (os.environ.get("VW_GATEWAY_UPSTREAM_MEDIA")
                                         or f"https://{ws}.cn-beijing.maas.aliyuncs.com")
        cfg["use_fake_upstream"] = os.environ.get("VW_LIVE_FAKE_TRANSPORT", "0") == "1"
        cfg["credentials_required"] = True
    else:
        cfg["network"] = "none"
        cfg["use_fake_upstream"] = True
        cfg["gateway_upstream_llm"] = "http://127.0.0.1:8666"
        cfg["gateway_upstream_media"] = "http://127.0.0.1:8666"
        cfg["credentials_required"] = False
    return cfg


CREDENTIAL_FILE = Path("/home/lcq/.config/agent-workload-characterization/bailian.env")


def read_credentials() -> dict:
    """Load runtime credentials for the gateway ONLY. Values are never echoed,
    persisted, hashed or placed in task config/archives."""
    if not CREDENTIAL_FILE.exists():
        return {}
    values = {}
    for line in CREDENTIAL_FILE.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        k = k.strip()
        if k.startswith("export "):
            k = k[len("export "):].strip()
        v = v.strip()
        if len(v) >= 2 and v[:1] in ('"', "'") and v[-1:] == v[:1]:
            v = v[1:-1]
        values[k] = v
    return values


def new_run_root(out: str | Path) -> Path:
    """Create a unique new run root; refuse if it exists. Never reset anything."""
    root = Path(out).resolve()
    root_ok = True
    for guard in (REPO, REPO / "data", Path.home()):
        if root == guard or root in guard.parents:
            root_ok = False
            break
    if not root_ok:
        raise ValueError(f"run root too broad/unsafe: {root}")
    try:
        root.mkdir(parents=True, exist_ok=False)
    except FileExistsError:
        raise ValueError(f"run output dir already exists (refusing, files unchanged): {root}")
    for sub in ("logs", "samples", "ledger", "workspace", "rollout", "closeout"):
        (root / sub).mkdir(parents=True)
    return root


def container_verify(image_id: str) -> str:
    """Inspect the fixed image; compare id/platform; return actual ID or raise."""
    res = run([*DOCKER, "inspect", IMAGE, "--format", "{{.Id}} {{.Os}}/{{.Architecture}}"])
    if res.returncode != 0:
        raise RuntimeError(f"image inspect failed: {res.stderr or res.stdout}")
    cid, plat = (res.stdout.strip().split() + ["", ""])[:2]
    if cid != image_id:
        raise RuntimeError(f"image id mismatch: expected {image_id}, got {cid}")
    if plat not in ("linux/arm64",):
        raise RuntimeError(f"image platform unexpected: {plat}")
    return cid


def start_container(cfg: dict, root: Path, task_token: str) -> tuple[str, str]:
    name = "videoweaver-run-" + uuid.uuid4().hex[:8]
    argv = [*DOCKER, "run", "-d", "--name", name, "--network", cfg["network"],
            "--label", f"videoweaver.run={name}"]
    if cfg.get("cpuset_cpus"):
        argv += ["--cpuset-cpus", cfg["cpuset_cpus"]]
    if cfg.get("pids_limit"):
        argv += ["--pids-limit", str(cfg["pids_limit"])]
    if cfg.get("memory"):
        argv += ["--memory", cfg["memory"]]
    if cfg.get("add_host"):
        argv += ["--add-host", cfg["add_host"]]
    env = {
        "VW_TASK_TOKEN": task_token,
        "DASHSCOPE_API_KEY": task_token,          # skills/summary use local token
        "VW_IMAGE_BASE_URL": cfg["gateway_llm_base"],
        "VW_VIDEO_BASE_URL": cfg["gateway_video_base"],
        "VW_VISION_BASE_URL": cfg["gateway_llm_base"],
        "VW_LLM_BASE_URL": cfg["gateway_llm_base"],
        "VW_PYTHON": "/opt/videoweaver-venv/bin/python",
        "VW_OUTPUT_DIR": "/opt/videoweaver/generate_materials",
        "VW_CASE_TXT": f"/opt/videoweaver/case/dataset/{cfg['target_task']}/{cfg['case_id']}/task.txt",
        "VW_GATEWAY_PORT": str(cfg["gateway_port"]),
        "VW_GATEWAY_UPSTREAM_LLM": cfg["gateway_upstream_llm"],
        "VW_GATEWAY_UPSTREAM_MEDIA": cfg["gateway_upstream_media"],
        "VW_LEDGER_PATH": "/run/ledger/ledger.json",
        "VW_BUDGET_JSON": json.dumps(cfg["budget"]),
        "VW_RUN_START_EPOCH": str(time.time()),
        "VW_FAKE_OUTPUT_DIR": "/opt/videoweaver/generate_materials",
        "VW_FAKE_STATE_PATH": "/run/logs/fake-state.json",
        "VW_FAKE_MAX_RESPONSES": str(cfg["budget"].get("max_llm_calls", 40)),
        "VW_VIDEO_POLL_INTERVAL": str(cfg.get("video_poll_interval_s", "1")),
    }
    for k, v in env.items():
        argv += ["-e", f"{k}={v}"]
    argv += [
        "-v", f"{cfg['case_dir']}:/opt/videoweaver/case/dataset:ro",
        "-v", f"{cfg['gateway_script']}:/opt/vw-run/gateway.py:ro",
        "-v", f"{cfg['codex_config']}:/opt/codex-home/config.toml:ro",
        # production mount fix: merged skills SKILL.md forbids runtime pip
        # install and pins the fixed venv python (mirror image skills dir)
        "-v", f"{cfg['merge_skill_fix']}:/opt/videoweaver/skills/merge-video/SKILL.md:ro",
        "-v", f"{root / 'workspace'}:/opt/videoweaver/generate_materials",
        "-v", f"{root / 'ledger'}:/run/ledger",
        "-v", f"{root / 'rollout'}:/opt/rollout",
        "-v", f"{root / 'closeout'}:/opt/vw-closeout",
        "-v", f"{root / 'logs'}:/run/logs",
    ]
    if cfg.get("use_fake_upstream"):
        argv += ["-v", f"{cfg['fake_script']}:/opt/vw-run/fake_responses.py:ro"]
    if cfg.get("merge_inputs_dir"):
        argv += ["-v", f"{cfg['merge_inputs_dir']}:/opt/videoweaver/merge_inputs"]
    argv += ["--entrypoint", "sh", cfg["image"], "-c", "sleep 3600"]
    res = run(argv, timeout=60)
    if res.returncode != 0:
        raise RuntimeError(f"container start failed: {res.stderr or res.stdout}")
    cid = res.stdout.strip().splitlines()[-1]
    return cid, name


def build_entry_script(cfg: dict) -> str:
    # gateway + fake are started by the host via separate docker exec so the
    # upstream credential lives only in the gateway process env; this entry
    # only runs the real production pipeline and archives the outputs.
    return f"""set -x
mkdir -p /run/ledger /run/logs /opt/rollout /opt/vw-closeout
sleep 2
/opt/videoweaver-venv/bin/python \\
  /opt/videoweaver/AutomaticSkillOptimization/inference_CodeX/pipeline.py \\
  --dataset /opt/videoweaver/case/dataset \\
  --target_task {cfg['target_task']} \\
  --no_composition_skills true \\
  --test_sample 1 \\
  --max_concurrency 1 \\
  --max_retries 1 \\
  --task_max_retries 1 \\
  --retry_delay 0 \\
  --timeout_seconds {cfg['work_seconds']} \\
  --exp_id {cfg['exp_id']} \\
  --skip_copy false \\
  --dry_run false \\
  --random_seed 42
RC=$?
cp -r /opt/codex-home/sessions/. /opt/rollout/ 2>/dev/null || true
EXP=/opt/videoweaver/{cfg['exp_id']}
if [ -d "$EXP" ]; then cp -r "$EXP" /opt/vw-closeout/ 2>/dev/null || true; fi
if [ -f /opt/videoweaver/merge_inputs/final.mp4 ]; then
  mkdir -p /opt/vw-closeout/merge-agent-output
  cp /opt/videoweaver/merge_inputs/final.mp4 /opt/vw-closeout/merge-agent-output/final.mp4 2>/dev/null || true
fi
echo "ENTRY_RC=$RC"
exit $RC
"""


class ExecCapture:
    """Persist docker exec stdout/stderr to disk as they stream."""

    def __init__(self, argv, stdout_path: Path, stderr_path: Path, timeout: float):
        self.argv = argv
        self.timeout = timeout
        self.stdout_f = stdout_path.open("wb")
        self.stderr_f = stderr_path.open("wb")
        self.proc = None
        self._stop = threading.Event()
        self.threads = []

    def _pump(self, stream, fh, tag):
        try:
            for chunk in iter(lambda: stream.read(4096), b""):
                fh.write(chunk)
                fh.flush()
        except Exception:
            pass

    def run(self) -> tuple[int, int]:
        self.proc = subprocess.Popen(self.argv, stdout=subprocess.PIPE,
                                     stderr=subprocess.PIPE, start_new_session=True)
        t1 = threading.Thread(target=self._pump, args=(self.proc.stdout, self.stdout_f, "o"), daemon=True)
        t2 = threading.Thread(target=self._pump, args=(self.proc.stderr, self.stderr_f, "e"), daemon=True)
        self.threads = [t1, t2]
        t1.start(); t2.start()
        try:
            rc = self.proc.wait(timeout=self.timeout)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(os.getpgid(self.proc.pid), signal.SIGTERM)
            except Exception:
                pass
            try:
                self.proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                try:
                    os.killpg(os.getpgid(self.proc.pid), signal.SIGKILL)
                except Exception:
                    pass
                self.proc.wait(timeout=10)
            rc = 124
        for t in self.threads:
            t.join(timeout=10)
        self.stdout_f.close(); self.stderr_f.close()
        return rc


def run_entry_in_container(cid: str, cfg: dict, root: Path) -> tuple[int, int, int]:
    script = build_entry_script(cfg)
    cap = ExecCapture(
        [*DOCKER, "exec", cid, "sh", "-c", script],
        root / "logs" / "exec-stdout.log",
        root / "logs" / "exec-stderr.log",
        cfg["work_seconds"] + cfg["closeout_seconds"] + 60,
    )
    rc = cap.run()
    entry_rc = rc
    return rc, entry_rc, cap.proc.pid if cap.proc else 0


def collect_resources(cfg: dict, root: Path, cid: str, name: str) -> dict:
    res = {}
    # directory occupancy before/after handled by caller
    # netns: read container /proc/net/dev via docker exec periodically
    return res


def dir_bytes(path: Path) -> dict:
    if not path.exists():
        return {"bytes": 0, "files": 0}
    total = 0; n = 0
    for p in path.rglob("*"):
        if p.is_file():
            try:
                total += p.stat().st_size; n += 1
            except OSError:
                pass
    return {"bytes": total, "files": n}


def container_logs(cid: str, tail: int = 2000) -> str:
    res = run([*DOCKER, "logs", "--tail", str(tail), cid], timeout=30)
    return (res.stdout or "") + (res.stderr or "")


def judge(cfg: dict, root: Path, report: dict) -> dict:
    """Unified result rules for offline and live. pipeline_rc==0 is NOT
    success by itself."""
    checks = []
    errors = report.get("errors", [])

    def add(name, ok, detail=""):
        checks.append({"check": name, "passed": ok, "detail": detail})

    # 1. entry completed without infra exception
    add("no_run_exception", not errors, "; ".join(errors) or "ok")
    # 2. ledger present and no unexplained gap
    ledger_p = root / "ledger" / "ledger.json"
    ledger = {}
    if ledger_p.exists():
        try:
            ledger = json.loads(ledger_p.read_text())
        except Exception as e:
            add("ledger_parse", False, str(e))
    add("ledger_present", bool(ledger), "missing" if not ledger else "ok")
    counters = ledger.get("counters", {})
    add("ledger_not_exhausted",
        ledger.get("exhausted") is False,
        str(ledger.get("status", "")))
    add("ledger_llm_sent", counters.get("llm_calls", 0) >= 1,
        f"llm_calls={counters.get('llm_calls')}")
    jm = cfg.get("judge_media", {"image_creates": 8, "video_creates": 8, "media_downloads": 16})
    add("ledger_image_creates", counters.get("image_creates", 0) == jm["image_creates"],
        f"image={counters.get('image_creates')} (expected {jm['image_creates']})")
    add("ledger_video_creates", counters.get("video_creates", 0) == jm["video_creates"],
        f"video={counters.get('video_creates')} (expected {jm['video_creates']})")
    add("ledger_downloads", counters.get("media_downloads", 0) >= jm["media_downloads"],
        f"downloads={counters.get('media_downloads')} (expected >= {jm['media_downloads']})")
    # blocked records must be explained or the chain has a gap
    blocked = [e for e in ledger.get("events", []) if e.get("kind") == "blocked"]
    add("no_unexplained_blocked", not blocked,
        json.dumps(blocked[:3], ensure_ascii=False) if blocked else "ok")
    # 3. final.mp4 present and spec-conformant
    final = None
    for p in (root / "closeout").rglob("final.mp4"):
        final = p
        break
    add("final_present", final is not None, "missing" if not final else str(final))
    if final is not None:
        res = run(["ffprobe", "-v", "error", "-show_entries",
                   "format=duration,size", "-show_entries",
                   "stream=codec_name,codec_type,width,height,avg_frame_rate",
                   str(final)], timeout=30)
        ok = res.returncode == 0
        probe = res.stdout if ok else (res.stderr or "")
        streams = []
        duration = None
        for line in probe.splitlines():
            k, _, v = line.partition("=")
            if k == "codec_name": streams.append({"codec": v})
            if k == "codec_type": streams[-1]["type"] = v
            if k in ("width", "height", "avg_frame_rate") and streams:
                streams[-1][k] = v
            if k == "duration": duration = float(v) if v else None
        vstreams = [s for s in streams if s.get("type") == "video"]
        astreams = [s for s in streams if s.get("type") == "audio"]
        add("final_ffprobe", ok, probe[:300])
        add("final_h264_720p30",
            ok and any(s.get("codec") == "h264" for s in vstreams)
            and any(s.get("width") == "1280" and s.get("height") == "720"
                    and s.get("avg_frame_rate") in ("30/1", "30000/1001")
                    for s in vstreams),
            f"vstreams={vstreams[:2]}")
        add("final_no_audio", len(astreams) == 0, f"audio={len(astreams)}")
        add("final_duration_40", duration is not None and abs((duration or 0) - 40.0) < 0.5,
            f"duration={duration}")
    # 4. eight clips (generation tasks only; merge-only tasks expect none)
    clips = sorted(p.name for p in (root / "closeout").rglob("shot*.mp4"))
    if jm["video_creates"] == 0:
        add("eight_clips", True, "merge-only task (no shot clips expected)")
    else:
        add("eight_clips", len(clips) == 8, ",".join(clips))
    # 5. logs + samples present AND measurement quality actually consumed
    add("exec_stdout_saved", (root / "logs" / "exec-stdout.log").exists())
    add("exec_stderr_saved", (root / "logs" / "exec-stderr.log").exists())
    add("docker_logs_saved", (root / "logs" / "docker-logs.txt").exists())
    add("resource_summary_saved", (root / "samples" / "summary.json").exists())
    # measurement quality: per-metric + timeline + boundaries must all pass;
    # a quality computation error must not be ignored
    mq = report.get("measurement_quality") or {}
    qa_err = [e for e in report.get("errors", []) if "quality" in e]
    add("quality_computed", not qa_err, "; ".join(qa_err) or "ok")
    for key in ("cpu", "memory", "io_read", "io_write"):
        m = mq.get(key)
        if m is None:
            add(f"mq_{key}", False, "quality missing for " + key)
        else:
            add(f"mq_{key}", m.get("passed") is True,
                f"{m.get('status')}: {m.get('reason') or ''} sampled={m.get('sampled')} missing={m.get('missing')}")
    tl = mq.get("timeline")
    add("mq_timeline", bool(tl) and tl.get("passed") is True, str(tl))
    bd = mq.get("boundaries")
    add("mq_boundaries", bool(bd) and bd.get("passed") is True, str(bd))
    # streaming sink state and file parse
    ss = report.get("stream_state")
    if ss is None:
        add("stream_ok", False, "stream_state missing")
    else:
        add("stream_ok", not ss.get("error"), str(ss))
    try:
        parsed = read_resource_stream(root / "samples" / "resource-stream.jsonl")
        add("stream_parse", parsed.get("status") == "ok",
            f"{parsed.get('status')} rows={len(parsed.get('rows', []))} "
            f"truncated={parsed.get('truncated_tail')} parse_errors={parsed.get('parse_errors')}")
    except Exception as e:  # noqa: BLE001
        add("stream_parse", False, f"parse error: {type(e).__name__}: {e}")
    # ---- resource stream contract validation (from the actual file) ----
    def _mk_boundary(d):
        if not d:
            return None
        return CounterSnapshot(scope=d.get("scope"), scope_kind=d.get("scope_kind"),
                              t_monotonic_ns=d.get("t_monotonic_ns"),
                              cpu_usage_usec=d.get("cpu_usage_usec"),
                              mem_current_bytes=d.get("mem_current_bytes"),
                              mem_peak_bytes=d.get("mem_peak_bytes"),
                              io_read_bytes=d.get("io_read_bytes"),
                              io_write_bytes=d.get("io_write_bytes"),
                              read_status=d.get("read_status") or {})
    try:
        v = validate_resource_stream(root / "samples" / "resource-stream.jsonl")
        bf = root / "samples" / "boundaries.json"
        bounds = json.loads(bf.read_text()) if bf.exists() else {}
        re_q = assess_resource_quality(
            stream_rows=v["valid_rows"],
            boundary_start=_mk_boundary(bounds.get("boundary_start")),
            boundary_end=_mk_boundary(bounds.get("boundary_end")),
            expected_scope="videoweaver",
            expected_scope_kind="agent_container",
            interval_target_s=report.get("sample_interval_s", 0.5))
        boundary_ok = (re_q.get("boundaries", {}).get("passed") is True
                       and re_q.get("cpu", {}).get("passed") is True)
        add("stream_validated",
            v["status"] == "ok" and (v["valid_count"] >= 1 or boundary_ok),
            f"status={v['status']} valid={v['valid_count']} invalid={len(v['invalid'])} "
            f"boundary_only_ok={boundary_ok}")
        add("stream_metrics_valid", not v["invalid"],
            f"{len(v['invalid'])} invalid rows: {[x['reason'] for x in v['invalid'][:3]]}")
        add("stream_schema_scope",
            set(v["scopes_seen"]) == {"videoweaver"} or not v["valid_rows"],
            f"scopes={v['scopes_seen']} schemas={v['schemas_seen']}")
        ss = report.get("stream_state") or {}
        summary = report.get("resource_samples") or {}
        declared = ss.get("rows_written")
        memory_n = summary.get("n_samples")
        add("stream_rows_consistent",
            v["valid_count"] == declared
            and (memory_n is None or v["valid_count"] == memory_n),
            f"file={v['valid_count']} stream_state={declared} memory_summary={memory_n}")
        mism = []
        rep_q = report.get("measurement_quality") or {}
        for k in ("cpu", "memory", "io_read", "io_write", "timeline", "boundaries"):
            a = re_q.get(k, {}).get("passed")
            b = rep_q.get(k, {}).get("passed")
            if a is not b:
                mism.append(f"{k}: file={a} report={b}")
        bm_a = re_q.get("boundaries", {}).get("metrics_valid")
        bm_b = rep_q.get("boundaries", {}).get("metrics_valid")
        if bm_a is not None and bm_b is not None and bm_a is not bm_b:
            mism.append(f"boundaries.metrics_valid: file={bm_a} report={bm_b}")
        add("quality_recomputed", not mism, "; ".join(mism) or "ok")
        # scope identity must reach final acceptance
        si = re_q.get("scope_identity") or {}
        add("scope_identity_ok",
            not si.get("conflict") and not si.get("missing"),
            f"conflict={si.get('conflict')} missing={si.get('missing')} "
            f"samples_scope={si.get('samples_scope')} boundaries_scope={si.get('boundaries_scope')}")
        # numeric consistency: recompute verifiable values from file+boundaries
        bsx = _mk_boundary(bounds.get("boundary_start"))
        bex = _mk_boundary(bounds.get("boundary_end"))
        rs = report.get("resource_samples") or {}
        num_mismatch = []
        def _num_eq(a, b):
            if a is None or b is None:
                return None
            return abs(a - b) <= 1e-6 + 1e-6 * abs(b)
        if rs.get("n_samples") is not None and v["valid_count"] != rs["n_samples"]:
            num_mismatch.append(f"n_samples file={v['valid_count']} report={rs.get('n_samples')}")
        if bsx and bex and bsx.cpu_usage_usec is not None and bex.cpu_usage_usec is not None:
            core = (bex.cpu_usage_usec - bsx.cpu_usage_usec) / 1e6
            if rs.get("cpu_core_seconds") is not None and _num_eq(core, rs["cpu_core_seconds"]) is False:
                num_mismatch.append(f"cpu_core_seconds file={core:.6g} report={rs.get('cpu_core_seconds')}")
        mems = [r.get("mem_current_bytes") for r in v["valid_rows"]
                if r.get("mem_current_bytes") is not None]
        if mems:
            mmax = max(mems)
            if rs.get("memory_sampled_max_bytes") is not None and mmax != rs["memory_sampled_max_bytes"]:
                num_mismatch.append(f"mem_sampled_max file={mmax} report={rs.get('memory_sampled_max_bytes')}")
        if bex is not None and bex.mem_peak_bytes is not None and rs.get("memory_kernel_peak_bytes") is not None \
                and bex.mem_peak_bytes != rs["memory_kernel_peak_bytes"]:
            num_mismatch.append("mem_kernel_peak mismatch")
        if bsx and bex:
            wall = (bex.t_monotonic_ns - bsx.t_monotonic_ns) / 1e9
            if rs.get("wall_s") is not None and _num_eq(wall, rs["wall_s"]) is False:
                num_mismatch.append(f"wall_s file={wall:.6g} report={rs.get('wall_s')}")
        ssm = report.get("sample_metrics_summary") or {}
        if ssm.get("mem_sum") is not None and mems:
            if sum(mems) != ssm["mem_sum"]:
                num_mismatch.append(f"mem_sum file={sum(mems)} saved={ssm['mem_sum']}")
        add("numeric_consistent", not num_mismatch, "; ".join(num_mismatch) or "ok")
        # full-sample content digest from the actual stream vs saved summary
        cs = report.get("sample_content_summary") or {}
        if cs.get("digest"):
            fd = sample_content_digest(v["valid_rows"])
            add("content_digest_consistent",
                fd["digest"] == cs["digest"] and fd["n_samples"] == cs.get("n_samples"),
                f"file={fd['digest'][:12]} saved={str(cs.get('digest'))[:12]} n={fd['n_samples']}")
        elif report.get("sample_interval_s") is not None:
            add("content_digest_consistent", False,
                "new-contract run (sample_interval_s present) is missing the "
                "required sample content summary")
        else:
            add("content_digest_consistent", True,
                "no saved content digest (legacy run; unknown)")
        # stream counter conservation
        ssc = report.get("stream_state") or {}
        recv = ssc.get("rows_received")
        writ = ssc.get("rows_written")
        buff = ssc.get("rows_buffered")
        lost = ssc.get("lost_undelivered")
        _num_ok = lambda x: isinstance(x, int) and not isinstance(x, bool) and x >= 0
        _present = None not in (recv, writ, buff, lost)
        allnum = _present and all(_num_ok(x) for x in (recv, writ, buff, lost))
        add("stream_counters_valid", allnum,
            f"recv={recv} writ={writ} buff={buff} lost={lost} present={_present}")
        if None not in (recv, writ, buff, lost) and allnum:
            add("stream_counters_conserved", recv == writ + buff + lost,
                f"recv={recv} writ+buff+lost={writ}+{buff}+{lost}={writ + buff + lost}")
        else:
            add("stream_counters_conserved", False,
                "missing/non-numeric counter field (cannot verify; not zeroed)")
        add("stream_flush_state", (buff or 0) == 0,
            f"buffered={buff} (must be 0 at closeout)")
        add("stream_no_loss", (lost or 0) == 0, f"lost={lost}")
        add("stream_written_rows", writ is not None and writ == v["valid_count"],
            f"writ={writ} file_rows={v['valid_count']}")
        # continuous sampling coverage
        cov = re_q.get("coverage") or {}
        add("coverage_ok", cov.get("passed") is True,
            f"{cov.get('status')}: {cov.get('reason') or ''}")
    except Exception as e:  # noqa: BLE001
        add("stream_validated", False, f"validate error: {type(e).__name__}: {e}")
        add("quality_recomputed", False, f"recompute error: {type(e).__name__}: {e}")
        add("scope_identity_ok", False, "scope identity unavailable (recompute error)")
        add("numeric_consistent", False, f"numeric recompute error: {type(e).__name__}: {e}")
        add("content_digest_consistent", False, "digest unavailable (recompute error)")
        add("coverage_ok", False, "coverage unavailable (recompute error)")
    add("cleanup_verified", report.get("cleanup", {}).get("removed") is True,
        json.dumps(report.get("cleanup", {})))
    all_ok = all(c["passed"] for c in checks)
    return {"passed": all_ok, "checks": checks}


def main() -> None:
    ap = argparse.ArgumentParser(description="VideoWeaver fixed production entry")
    ap.add_argument("--config", default=None)
    ap.add_argument("--mode", choices=["offline", "live"], default="offline")
    ap.add_argument("--out", required=True, help="unique new run root")
    ap.add_argument("--live-inject-fake-upstream", action="store_true",
                    help="acceptance-only: live branch routes to local fake transport")
    args = ap.parse_args()

    cfg = load_config(args.config, args.mode)
    root = new_run_root(args.out)
    report = {"task_id": cfg["task_id"], "mode": args.mode, "image": cfg["image"],
              "image_id": cfg["image_id"], "run_root": str(root),
              "started_utc": now(), "timeline_start_mono": time.monotonic(),
              "stages": {}, "stages_rel_s": {}, "cleanup": {}, "errors": [],
              "source_identity": {}}
    def rel():
        return round(time.monotonic() - report["timeline_start_mono"], 3)
    task_token = "vw-task-" + uuid.uuid4().hex[:20]

    # upstream credential: offline synthetic; live read at runtime for the
    # gateway ONLY (never echoed/persisted/hashed/archived)
    upstream_key = cfg["upstream_api_key"]
    if args.mode == "live":
        creds = read_credentials()
        if not creds.get("DASHSCOPE_API_KEY") or not creds.get("BAILIAN_WORKSPACE_ID"):
            raise SystemExit("live mode requires runtime credentials "
                             "(DASHSCOPE_API_KEY + BAILIAN_WORKSPACE_ID)")
        upstream_key = creds["DASHSCOPE_API_KEY"]
        ws = creds["BAILIAN_WORKSPACE_ID"]
        if not cfg.get("use_fake_upstream"):
            cfg["gateway_upstream_media"] = f"https://{ws}.cn-beijing.maas.aliyuncs.com"
        report["credentials"] = {"present": True, "kind": "runtime_gateway_only"}

    # source identity (gateway + fake + config) hashes
    for key in ("gateway_script", "fake_script", "codex_config", "merge_skill_fix"):
        p = Path(cfg[key])
        report["source_identity"][key] = {"path": str(p), "sha256": sha(p)}

    cid = None
    name = None
    sampler = None
    sampler_thread = None
    sampler_stop = threading.Event()
    netns_thread = None
    try:
        actual_id = container_verify(cfg["image_id"])
        report["stages"]["image_verified"] = actual_id
        cid, name = start_container(cfg, root, task_token)
        report["stages"]["container_started"] = cid
        report["container"] = {"id": cid, "name": name}

        # start local services: fake upstream (offline) and the gateway.
        # The upstream credential is passed ONLY to the gateway process env.
        if cfg.get("use_fake_upstream"):
            run([*DOCKER, "exec", "-d", cid, "sh", "-c",
                 "python /opt/vw-run/fake_responses.py > /run/logs/fake-server.out 2>&1"],
                timeout=30)
        gw = run([*DOCKER, "exec", "-d", "-e", f"VW_UPSTREAM_API_KEY={upstream_key}",
                  cid, "sh", "-c",
                  "python /opt/vw-run/gateway.py --ledger /run/ledger/ledger.json "
                  "> /run/logs/gateway.log 2>&1"], timeout=30)
        report["stages"]["gateway_started"] = gw.returncode == 0
        time.sleep(2)
        del upstream_key

        # directory occupancy BEFORE (workspace is empty by construction)
        report["dir_before"] = directory_footprint_snapshot([
            {"role": "workspace", "path": str(root / "workspace")},
            {"role": "ledger", "path": str(root / "ledger")},
            {"role": "rollout", "path": str(root / "rollout")},
            {"role": "closeout", "path": str(root / "closeout")},
        ], timeout_s=5.0)

        # resource sampling
        sampler_ok = False
        try:
            sampler = ResourceSampler(interval_s=cfg["sample_interval_s"])
            reader = CgroupV1FileReader("videoweaver", "agent_container", cid)
            sampler.register("videoweaver", "agent_container", reader)
            sampler.start("videoweaver")
            sampler.enable_stream("videoweaver", root / "samples" / "resource-stream.jsonl")
            try:
                bs = sampler.samples("videoweaver").boundary_start
                atomic_write(root / "samples" / "boundaries.json",
                             {"schema": "resource-boundaries-v1",
                              "boundary_start": bs.to_dict() if bs else None,
                              "utc_start": now()})
            except Exception as e:  # noqa: BLE001
                report["errors"].append(f"boundary_start_persist: {e}")
            sampler_ok = True

            def _sample():
                while not sampler_stop.is_set():
                    sampler.sample_once()
                    sampler_stop.wait(cfg["sample_interval_s"])
            sampler_thread = threading.Thread(target=_sample, daemon=True)
            sampler_thread.start()
        except Exception as e:  # noqa: BLE001
            report["errors"].append(f"sampler init: {type(e).__name__}: {e}")
        report["stages"]["sampler_ready"] = sampler_ok

        # netns sampling (container /proc/net/dev via docker exec)
        def _netns():
            out = []
            net_stream = (root / "samples" / "netns-stream.jsonl").open("a", encoding="utf-8")
            try:
                while not sampler_stop.is_set():
                    t0 = time.monotonic_ns()
                    r = run([*DOCKER, "exec", cid, "sh", "-c", "cat /proc/net/dev 2>/dev/null"],
                            timeout=10)
                    t1 = time.monotonic_ns()
                    row = {"schema": "netns-stream-v1",
                           "t_monotonic_ns": t0,
                           "read_end_monotonic_ns": t1,
                           "read_wall_ns": t1 - t0,
                           "read_status": "ok" if r.returncode == 0 else f"rc_{r.returncode}",
                           "scope": "container_netns_interfaces",
                           "rc": r.returncode, "out": r.stdout, "utc": now()}
                    net_stream.write(json.dumps(row, ensure_ascii=False) + "\n")
                    net_stream.flush()
                    out.append(row)
                    sampler_stop.wait(cfg["netns_period_s"])
            finally:
                net_stream.close()
            if out:
                atomic_write(root / "samples" / "netns.jsonl",
                             {"records": out})
        netns_thread = threading.Thread(target=_netns, daemon=True)
        netns_thread.start()

        # run the real production entry via docker exec (logs streamed to disk)
        report["stages"]["entry_start"] = now()
        report["stages_rel_s"]["entry_start"] = rel()
        rc, entry_rc, _ = run_entry_in_container(cid, cfg, root)
        report["stages"]["entry_end"] = now()
        report["stages_rel_s"]["entry_end"] = rel()
        report["pipeline_rc"] = rc
        report["entry_rc"] = entry_rc
        report["stages"]["exec_logs_saved"] = (root / "logs" / "exec-stdout.log").exists()

        # capture docker logs before removal
        report["stages"]["docker_logs_captured"] = True
        (root / "logs" / "docker-logs.txt").write_text(container_logs(cid)[:500000])
    except Exception as e:  # noqa: BLE001
        report["errors"].append(f"run error: {type(e).__name__}: {e}")
        report["stages"]["exception"] = now()
        report["stages_rel_s"]["exception"] = rel()
        if cid:
            try:
                (root / "logs" / "docker-logs.txt").write_text(container_logs(cid)[:500000])
                report["stages"]["docker_logs_captured"] = True
            except Exception:  # noqa: BLE001
                report["errors"].append("docker logs capture failed")
    finally:
        # stop sampling thread cleanly (event + finite join)
        sampler_stop.set()
        if sampler_thread:
            sampler_thread.join(timeout=10)
        if netns_thread:
            netns_thread.join(timeout=10)
        if sampler is not None:
            try:
                sampler.stop("videoweaver")
                try:
                    be = sampler.samples("videoweaver").boundary_end
                    bf = root / "samples" / "boundaries.json"
                    if bf.exists():
                        bd = json.loads(bf.read_text())
                        bd["boundary_end"] = be.to_dict() if be else None
                        bd["utc_end"] = now()
                        atomic_write(bf, bd)
                except Exception as e:  # noqa: BLE001
                    report["errors"].append(f"boundary_end_persist: {e}")
            except Exception as e:  # noqa: BLE001
                report["errors"].append(f"sampler stop: {e}")
            try:
                sampler.close_streams()
            except Exception as e:  # noqa: BLE001
                report["errors"].append(f"stream close: {e}")
            try:
                samples = sampler.samples("videoweaver")
                report["resource_samples"] = samples.summary()
                # content summary of periodic samples (new-run numeric evidence)
                try:
                    _mems = [sn.mem_current_bytes for sn in samples.samples
                             if sn.mem_current_bytes is not None]
                    report["sample_metrics_summary"] = {
                        "schema": "sample-metrics-summary-v1",
                        "mem_sum": sum(_mems) if _mems else None,
                        "mem_count": len(_mems),
                    }
                except Exception as e:  # noqa: BLE001
                    report["errors"].append(f"sample_metrics_summary: {e}")
                try:
                    report["sample_content_summary"] = sample_content_digest(samples.samples)
                except Exception as e:  # noqa: BLE001
                    report["errors"].append(f"sample_content_summary: {e}")
                report["sample_interval_s"] = cfg.get("sample_interval_s", 0.5)
                # per-point JSONL
                atomic_write(root / "samples" / "summary.json", samples.summary())
                ev = getattr(samples, "evidence", None)
                if callable(ev):
                    atomic_write(root / "samples" / "resources.jsonl", ev())
                # measurement quality + streaming sink state (production consumption)
                try:
                    from agent_workload_characterization.collectors.execution_measurement import (
                        assess_resource_quality)
                    report["measurement_quality"] = assess_resource_quality(samples)
                except Exception as e:  # noqa: BLE001
                    report["errors"].append(f"quality assess: {e}")
                report["stream_state"] = sampler.stream_state("videoweaver")
            except Exception as e:  # noqa: BLE001
                report["errors"].append(f"samples read: {e}")
        # container removal + ownership check
        if cid:
            stop = run([*DOCKER, "stop", "-t", "5", cid], timeout=30)
            rm = run([*DOCKER, "rm", cid], timeout=30)
            insp = run([*DOCKER, "inspect", cid], timeout=30)
            # distinguish 'not found' from daemon/perm failure
            missing = "No such" in (insp.stderr or "") or "No such" in (insp.stdout or "")
            report["cleanup"] = {
                "stop_rc": stop.returncode, "rm_rc": rm.returncode,
                "removed": insp.returncode != 0,
                "removed_basis": ("container_absent" if (insp.returncode != 0 and missing)
                                  else "verified_absent" if insp.returncode != 0
                                  else "still_present"),
            }
        report["dir_after"] = directory_footprint_snapshot([
            {"role": "workspace", "path": str(root / "workspace")},
            {"role": "ledger", "path": str(root / "ledger")},
            {"role": "rollout", "path": str(root / "rollout")},
            {"role": "closeout", "path": str(root / "closeout")},
        ], timeout_s=5.0)
        report["ended_utc"] = now()
        atomic_write(root / "run-report.json", report)
        judgement = judge(cfg, root, report)
        report["judgement"] = judgement
        atomic_write(root / "run-report.json", report)
        ok = judgement["passed"]
        print(json.dumps({"status": "PASS" if ok else "FAIL", "ok": ok,
                          "report": str(root / "run-report.json"),
                          "failed_checks": [c for c in judgement["checks"] if not c["passed"]]},
                         ensure_ascii=False))
        sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
