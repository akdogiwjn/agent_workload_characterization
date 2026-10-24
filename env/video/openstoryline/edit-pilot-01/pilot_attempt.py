"""OPENSTORYLINE-EDIT-PILOT-01 formal attempt orchestration.

One container (bridge network for the API), cgroup sampling at 0.5 s,
container-netns /proc/net/dev sampling at 2 s via docker exec, the REAL
openstoryline_task_entry (LangChain Agent + MCP + adapted English ASR),
wall budgets enforced by a parent-process deadline, cuts.json exported from
the Agent's ACTUAL rendered keep-ranges, container removed, images kept.
"""
import json, os, subprocess, sys, threading, time
from pathlib import Path

ROOT = Path("/home/lcq/agent_workload_characterization")
W = ROOT / "env/video/openstoryline/edit-pilot-01"
RUN = W / "workspace" / "attempt-run"
RUN.mkdir(parents=True, exist_ok=True)

IMAGE = "openstoryline-task:arm64-asr-adapted-v3"
ATTEMPT_WALL_S = 2700.0
AGENT_PHASE_S = 1800.0

def now(): return time.monotonic_ns()

def sh(cmd, timeout=60):
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)

# ---- ATTEMPT_STARTED (fresh monotonic origin) ----
attempt_started = {
    "namespace": "OPENSTORYLINE-EDIT-PILOT-01",
    "started_at_local": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
    "started_monotonic_ns": now(),
    "identity_sha256": json.loads((W / "frozen-identity.json").read_text())["identity_sha256"],
}
(RUN / "ATTEMPT_STARTED.json").write_text(json.dumps(attempt_started, indent=1) + "\n")

# ---- container ----
cname = "awc-os-edit-pilot-01"
sh(["docker", "rm", "-f", cname])
run_argv = ["docker", "run", "-d", "--name", cname,
            "--network", "bridge", "--cpus", "4", "--memory", "8g",
            "-v", f"{RUN}:/workspace/output",
            "-v", f"{ROOT}/data/workloads/video/editing/avb-disfluency-interview-3-v1/input:/workspace/input:ro",
            "-v", f"{ROOT}/env/video/openstoryline/OPENSTORYLINE-ENV-01/models:/root/.cache/modelscope:ro",
            "-e", f"DASHSCOPE_API_KEY={Path('/tmp/opencode/oskey').read_text().strip()}",
            IMAGE, "sleep", "3600"]
proc = sh(run_argv)
assert proc.returncode == 0, proc.stderr
cid = proc.stdout.strip()
print("container:", cid[:12])

events = []
def ev(name, **kw):
    events.append({"event": name, "t_monotonic_ns": now(), **kw})
    print(f"[{time.strftime('%H:%M:%S')}] {name}")

# ---- cgroup sampling (host reads container cgroup, 0.5 s) ----
sys.path.insert(0, str(ROOT / "src"))
from agent_workload_characterization.collectors.resource_sampler import (
    CounterSnapshot, CgroupV1FileReader)

class Handle:
    container_id = cid
    spec = type("S", (), {"scope": "os_edit_pilot_01"})()
    cgroup_version = None
    cgroup_dir = None

# resolve cgroup
cg_root = Path("/sys/fs/cgroup")
for cand in (cg_root / "cpu,cpuacct" / "docker" / cid,
             cg_root / "system.slice" / f"docker-{cid}.scope",
             cg_root / "docker" / cid):
    if cand.is_dir():
        Handle.cgroup_dir = cand
        Handle.cgroup_version = "v1"
        break

cgroup_rows = []
net_rows = []
stop = threading.Event()

def cgroup_loop():
    while not stop.is_set():
        t = time.monotonic_ns()
        if Handle.cgroup_dir is not None:
            r = CgroupV1FileReader("os_edit_pilot_01", "task_container", cid)
            cgroup_rows.append(r.read(t).to_dict())
        else:
            cgroup_rows.append({"t_monotonic_ns": t, "read_status": {"cgroup": "unresolved"}})
        stop.wait(0.5)

def netns_loop():
    while not stop.is_set():
        t = time.monotonic_ns()
        p = sh(["docker", "exec", cname, "cat", "/proc/net/dev"], timeout=10)
        interfaces = {}
        if p.returncode == 0:
            try:
                lines = p.stdout.splitlines()[2:]
                for line in lines:
                    name, _, counters = line.partition(":")
                    vals = counters.split()
                    if len(vals) >= 9:
                        interfaces[name.strip()] = {
                            "rx_bytes": int(vals[0]), "tx_bytes": int(vals[8])}
            except (ValueError, IndexError):
                pass
        net_rows.append({"t_monotonic_ns": t, "interfaces": interfaces,
                         "read_status": "observed" if interfaces else
                         ("container_gone" if p.returncode != 0 else "no_interfaces")})
        stop.wait(2.0)

threads = [threading.Thread(target=cgroup_loop, daemon=True),
           threading.Thread(target=netns_loop, daemon=True)]

# ---- directory footprints ----
def footprint():
    dirs = {"input": ROOT / "data/workloads/video/editing/avb-disfluency-interview-3-v1/input",
            "workspace": RUN}
    out = {}
    for tag, d in dirs.items():
        total = 0
        for p in d.rglob("*"):
            if p.is_file():
                try: total += p.stat().st_size
                except OSError: pass
        out[tag] = total
    return out

fp_before = footprint()

try:
    ev("container_started", container=cid[:12])
    for th in threads: th.start()
    ev("samplers_started")

    # ---- stage inputs + request ----
    instr = (ROOT / "references/repos/agentic-vbench/tasks/agentic_vbench_repair/"
             "exp-disfluency-interview-3-task01/steps/solve/instruction.md").read_text()
    req = {"instruction": instr, "output_dir": "/workspace/output",
           "recursion_limit": 32}
    (RUN / "request.json").write_text(json.dumps(req, indent=1))
    cp = sh(["docker", "cp", str(RUN / "request.json"), f"{cname}:/workspace/request.json"])
    assert cp.returncode == 0, cp.stderr
    # entry needs /workspace/input to contain source.mp4 — mounted ro above
    ev("request_staged")

    # ---- run the REAL entry with deadlines ----
    t_agent_start = time.monotonic()
    ev("agent_phase_started")
    entry = subprocess.run(
        ["docker", "exec", "-w", "/opt/openstoryline", cname,
         "bash", "-lc",
         "PYTHONPATH=/opt/openstoryline/src:/opt/openstoryline python3 "
         "/opt/openstoryline/openstoryline_task_entry.py --request /workspace/request.json"],
        capture_output=True, text=True, timeout=AGENT_PHASE_S + 120,
        cwd=None)
    agent_rc = entry.returncode
    ev("agent_phase_finished", rc=agent_rc,
       elapsed_s=round(time.monotonic() - t_agent_start, 1))
    (RUN / "entry-stdout.log").write_text(entry.stdout[-20000:])
    (RUN / "entry-stderr.log").write_text(entry.stderr[-20000:])

    # ---- export cuts.json from the Agent's ACTUAL keep ranges ----
    cuts_export = {"status": "not_attempted"}
    try:
        # find speech_rough_cut artifacts in the session store
        cache = RUN / ".server_cache"
        sessions = sorted(cache.glob("*/")) if cache.exists() else []
        keep_ranges = []
        for sess in sessions:
            for art_dir in sorted(sess.glob("*/")):
                # clips carry source_ref {start,end} against the ORIGINAL source
                for meta in sorted(art_dir.rglob("*.json")) + sorted(art_dir.glob("meta.json")):
                    pass
                # simpler: look for the rough-cut clips by filename pattern
        # robust approach: use ffprobe on rendered output + the ASR/timeline
        # artifacts; but the authoritative keep-ranges are the
        # speech_rough_cut clips' source_ref. Scan session artifacts:
        import glob as _glob
        for clips_dir in _glob.glob(str(cache / "*/*/*/"), recursive=False):
            pass
        # Fallback handled below via the timeline artifact JSON
        tl_files = sorted(cache.rglob("*.json")) if cache.exists() else []
        keep = []
        for f in tl_files:
            try:
                d = json.loads(f.read_text())
            except Exception:
                continue
            # speech_rough_cut node output artifact: {"clips": [...], "rough_cut_jsons": [...]}
            if isinstance(d, dict) and isinstance(d.get("clips"), list) and d["clips"]:
                if all("source_ref" in c for c in d["clips"]):
                    keep = [(c["source_ref"]["start"], c["source_ref"]["end"])
                            for c in d["clips"]]
                    break
        if keep:
            keep.sort()
            total_ms = 37000  # measured decoded duration
            cuts, prev = [], 0
            for s, e in keep:
                if s > prev:
                    cuts.append({"start_ms": prev, "end_ms": s, "reason": "rough-cut removal"})
                prev = max(prev, e)
            if prev < total_ms:
                cuts.append({"start_ms": prev, "end_ms": total_ms, "reason": "rough-cut removal"})
            cuts_doc = {"cuts": cuts}
            (RUN / "cuts.json").write_text(json.dumps(cuts_doc, indent=1))
            cuts_export = {"status": "exported", "keep_ranges": keep,
                           "n_cuts": len(cuts), "total_keep_ms": sum(e - s for s, e in keep)}
        else:
            cuts_export = {"status": "no_keep_ranges_found"}
    except Exception as exc:
        cuts_export = {"status": "error", "error": f"{type(exc).__name__}: {exc}"}
    ev("cuts_json_exported", **cuts_export)
    (RUN / "cuts-export.json").write_text(json.dumps(cuts_export, indent=1))

    # ---- locate the rendered output ----
    render_path = None
    for p in sorted(RUN.rglob("*.mp4")):
        if "speech_rough_cut_" not in p.name and p.stat().st_size > 10000:
            render_path = p
    if render_path:
        probe = sh(["ffprobe", "-v", "error", "-show_entries",
                    "format=duration,size:stream=codec_name,codec_type,width,height,avg_frame_rate",
                    "-of", "json", str(render_path)], timeout=60)
        (RUN / "render-probe.json").write_text(probe.stdout)
        ev("render_located", path=str(render_path.relative_to(RUN)),
           **json.loads(probe.stdout).get("format", {}))
    else:
        ev("render_not_found")

finally:
    stop.set()
    for th in threads: th.join(timeout=10)
    ev("samplers_stopped",
       cgroup_samples=len(cgroup_rows), net_samples=len(net_rows))
    fp_after = footprint()
    # export artifacts BEFORE container removal
    sh(["docker", "exec", cname, "bash", "-c",
        "cd /workspace/output && tar cf /tmp/artifacts.tar . 2>/dev/null"], timeout=120)
    sh(["docker", "cp", f"{cname}:/tmp/artifacts.tar", str(RUN / "container-artifacts.tar")],
       timeout=120)
    sh(["docker", "exec", cname, "bash", "-c",
        "cat /proc/1/status | grep -E 'Name|VmRSS' > /tmp/p1status.txt; "
        "ls /root/.cache 2>/dev/null > /tmp/cachelist.txt"], timeout=30)
    sh(["docker", "cp", f"{cname}:/tmp/p1status.txt", str(RUN / "p1status.txt")], timeout=30)
    # remove container
    sh(["docker", "rm", "-f", cname], timeout=60)
    verify = sh(["docker", "ps", "-a", "--filter", f"id={cid}", "--format", "{{.ID}}"], timeout=30)
    removed = verify.returncode == 0 and not verify.stdout.strip()
    ev("container_removed", removed=removed)
    img = sh(["docker", "inspect", IMAGE, "--format", "{{.Id}}"], timeout=30)
    ev("image_retained", image_id=img.stdout.strip()[:40] if img.returncode == 0 else None)

    # ---- persist everything ----
    (RUN / "events.json").write_text(json.dumps(events, indent=1))
    (RUN / "cgroup-samples.json").write_text(json.dumps(cgroup_rows))
    (RUN / "netns-samples.json").write_text(json.dumps(net_rows))
    (RUN / "footprints.json").write_text(json.dumps(
        {"before": fp_before, "after": fp_after}))
    print("cgroup samples:", len(cgroup_rows), "| net samples:", len(net_rows))
    print("container removed:", removed)

print("ATTEMPT COMPLETE — rc:", agent_rc)
