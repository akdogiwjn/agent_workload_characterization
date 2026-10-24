"""Bounded native ViMax media continuation entry (REPAIR-01 fixed version).

Reusable production entry derived from PILOT-03's generation_entry.py with
the following audited fixes (see ../FIXES.md):

1. seed_session ordering (PILOT-03 root cause): SessionIndex(ROOT) — whose
   CONSTRUCTOR initializes .vimax/sessions.json on a fresh workspace — must
   run BEFORE the duplicate-session check reads that file. PILOT-03 read
   sessions.json first, so every fresh workspace died with FileNotFoundError
   right after STARTUP-ACK, before any Agent/media work.
2. No HANDSHAKE_ONLY shortcut: a startup handshake is NOT a cold-start
   proof. This entry has exactly one path: gate -> seed -> agent -> render.
3. Earliest-stage evidence: every phase boundary and every failure (with
   full traceback) is persisted to ENTRY-PHASES.jsonl / ENTRY-FAILED.json
   from the first executable statement on; initialization failures never
   fabricate Agent events, COMPLETE or media artifacts.
4. Configuration: session id, source session, script hash and caps come
   from environment variables so future pilots do not copy-edit constants.

Unchanged from PILOT-03: startup gate protocol, plan copy + hash contract,
media-only tool policy, one-render lock, image send gate, FFmpeg audit,
caps verification, single native render pipeline invocation.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import os
import shutil
import signal
import sys
import threading
import time
import traceback
from pathlib import Path

ROOT = Path("/workspace")
WORK = ROOT / "attempt"
PLAN = Path("/planning")

SESSION_ID = os.environ.get("VIMAX_MEDIA_SESSION_ID", "media-continuation-01")
SOURCE_SESSION_ID = os.environ.get("VIMAX_MEDIA_SOURCE_SESSION", "planning-validation-03")
EXPECTED_SCRIPT_SHA = os.environ.get(
    "VIMAX_MEDIA_SOURCE_SCRIPT_SHA256",
    "447e4d88ccd76f9cb4a206f799993620a3c832238dd873c9ae9e905c2452b59a")
SOURCE_SCRIPT_SHOT_COUNT = int(os.environ.get("VIMAX_MEDIA_SHOT_COUNT", "8"))
TRANSITION_CAP = int(os.environ.get("VIMAX_BAILIAN_BUDGET_TRANSITIONS", "7"))
REQUIRED_CAPS = {
    "llm_calls": int(os.environ.get("VIMAX_BAILIAN_BUDGET_LLM_CALLS", "80")),
    "llm_attempts": int(os.environ.get("VIMAX_BAILIAN_BUDGET_LLM_ATTEMPTS", "80")),
    "image_generations": int(os.environ.get("VIMAX_BAILIAN_BUDGET_IMAGE_GENERATIONS", "40")),
    "video_creates": int(os.environ.get("VIMAX_BAILIAN_BUDGET_VIDEO_CREATES", "15")),
    "video_polls": int(os.environ.get("VIMAX_BAILIAN_BUDGET_VIDEO_POLLS", "1800")),
    "media_downloads": int(os.environ.get("VIMAX_BAILIAN_BUDGET_MEDIA_DOWNLOADS", "80")),
    "single_request_output_tokens": int(
        os.environ.get("VIMAX_BAILIAN_BUDGET_SINGLE_REQUEST_OUTPUT_TOKENS", "8192")),
}
_image_send_lock = threading.Lock()
_image_send_count = 0
_image_send_cap = REQUIRED_CAPS["image_generations"]

_phase_lock = threading.Lock()


def phase(name: str, **fields) -> None:
    """Durable phase marker from the earliest executable moment."""
    try:
        WORK.mkdir(parents=True, exist_ok=True)
        row = {"phase": name, "t_wall": time.time(),
               "t_monotonic_ns": time.monotonic_ns(), **fields}
        with _phase_lock, (WORK / "ENTRY-PHASES.jsonl").open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    except OSError:
        pass  # evidence path failure must not mask the primary error


def fail(kind: str, exc: BaseException) -> None:
    """Persist the failure marker with the full traceback; never fabricate
    COMPLETE / Agent events / media artifacts."""
    try:
        WORK.mkdir(parents=True, exist_ok=True)
        payload = {
            "state": "failed",
            "kind": kind,
            "error_type": type(exc).__name__,
            "message": str(exc)[:2000],
            "traceback": traceback.format_exc()[:20000],
            "t_wall": time.time(),
            "t_monotonic_ns": time.monotonic_ns(),
            "session_id": SESSION_ID,
            "complete_written": False,
            "agent_events_written": (WORK / "agent-events.jsonl").exists(),
        }
        tmp = WORK / "ENTRY-FAILED.json.tmp"
        tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                       encoding="utf-8")
        os.replace(tmp, WORK / "ENTRY-FAILED.json")
    except OSError:
        pass


class Tee:
    def __init__(self, *streams, timestamp_stream=None):
        self.streams = streams
        self.timestamp_stream = timestamp_stream
        self.pending = ""

    def write(self, value):
        for stream in self.streams:
            stream.write(value)
            stream.flush()
        if self.timestamp_stream is not None:
            self.pending += value
            while "\n" in self.pending:
                line, self.pending = self.pending.split("\n", 1)
                if not line.strip():
                    continue
                try:
                    event = json.loads(line)
                    envelope = {"t_wall": time.time(),
                                "t_monotonic_ns": time.monotonic_ns(),
                                "event": event}
                    self.timestamp_stream.write(
                        json.dumps(envelope, ensure_ascii=False) + "\n")
                    self.timestamp_stream.flush()
                except json.JSONDecodeError:
                    pass
        return len(value)

    def flush(self):
        for stream in self.streams:
            stream.flush()


def atomic_json(path: Path, payload: dict) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                   encoding="utf-8")
    os.replace(tmp, path)


def startup_gate() -> None:
    """Do not initialize the Agent/runtime until the host releases the gate."""
    if os.environ.get("VIMAX_STARTUP_GATE_REQUIRED") != "1":
        raise RuntimeError("host startup gate must be enabled")
    ready = WORK / "STARTUP-READY.json"
    release = WORK / "STARTUP-RELEASE.json"
    abort = WORK / "STARTUP-ABORT.json"
    ack = WORK / "STARTUP-ACK.json"
    atomic_json(ready, {"state": "ready_waiting_for_host", "t_wall": time.time(),
                        "t_monotonic_ns": time.monotonic_ns()})
    timeout = float(os.environ.get("VIMAX_STARTUP_HANDSHAKE_TIMEOUT_SECONDS", "45"))
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if abort.exists():
            raise RuntimeError("host aborted startup before release")
        if release.exists():
            atomic_json(ack, {"state": "released", "t_wall": time.time(),
                              "t_monotonic_ns": time.monotonic_ns()})
            return
        time.sleep(0.05)
    atomic_json(WORK / "STARTUP-FAILED.json",
                {"state": "release_timeout", "t_wall": time.time(),
                 "t_monotonic_ns": time.monotonic_ns()})
    raise TimeoutError("host did not release startup within the bounded handshake")


def load_plan() -> tuple[dict, Path]:
    sessions = json.loads((PLAN / ".vimax/sessions.json").read_text(encoding="utf-8"))
    source = sessions.get("sessions", {}).get(SOURCE_SESSION_ID)
    if not isinstance(source, dict) or source.get("planning_mode") != "script":
        raise RuntimeError("accepted planning session metadata is missing or not script mode")
    return source, PLAN / f".working_dir/{SOURCE_SESSION_ID}/script2video"


def seed_session() -> dict:
    from agent_runtime.session_index import SessionIndex

    phase("seed_session.start")
    source, src_dir = load_plan()
    source_script = (src_dir / "script.txt").read_bytes()
    if hashlib.sha256(source_script).hexdigest() != EXPECTED_SCRIPT_SHA:
        raise RuntimeError("frozen source script hash mismatch")
    # FIX (PILOT-03 root cause): construct SessionIndex FIRST — its
    # constructor initializes .vimax/sessions.json on a fresh workspace —
    # and only then check for a duplicate session id. The previous order
    # read the file before it existed and crashed every fresh workspace.
    index = SessionIndex(ROOT)
    existing = index.get(SESSION_ID)
    if existing is not None:
        raise RuntimeError("fresh generation session already exists; refusing resume")
    session = index.create(
        script=source_script.decode("utf-8"), planning_mode="script",
        user_requirement=str(source.get("user_requirement", "")),
        style=str(source.get("style", "")), session_id=SESSION_ID,
        project_name="ViMax media continuation",
    )
    phase("seed_session.created", session_id=SESSION_ID,
          working_dir=session.get("working_dir"))
    dst = Path(str(index.working_dir(SESSION_ID))) / "script2video"
    for name in ("script.txt", "characters.json", "storyboard.json", "camera_tree.json"):
        shutil.copyfile(src_dir / name, dst / name)
    for idx in range(SOURCE_SCRIPT_SHOT_COUNT):
        target = dst / "shots" / str(idx)
        target.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src_dir / "shots" / str(idx) / "shot_description.json",
                        target / "shot_description.json")
    required = [dst / name for name in
                ("script.txt", "characters.json", "storyboard.json", "camera_tree.json")]
    required += [dst / "shots" / str(idx) / "shot_description.json"
                 for idx in range(SOURCE_SCRIPT_SHOT_COUNT)]
    hashes = {p.relative_to(ROOT).as_posix():
              hashlib.sha256(p.read_bytes()).hexdigest() for p in required}
    if hashes.get(f"{session['working_dir']}/script2video/script.txt") != EXPECTED_SCRIPT_SHA:
        raise RuntimeError("new session script differs from the frozen source")
    if len(hashes) != 4 + SOURCE_SCRIPT_SHOT_COUNT:
        raise RuntimeError("new session plan copy is incomplete")
    summary = {"session_id": SESSION_ID, "planning_mode": session["planning_mode"],
               "source_session_id": SOURCE_SESSION_ID,
               "source_script_sha256": EXPECTED_SCRIPT_SHA,
               "copied_plan_files": hashes, "copied_file_count": len(hashes),
               "new_session": True, "media_artifacts_preexisting": False}
    atomic_json(WORK / "session-source-map.json", summary)
    phase("seed_session.done", copied_files=len(hashes))
    return session


def install_generation_policy(build_runtime):
    def build(*args, **kwargs):
        runtime = build_runtime(*args, **kwargs)
        registry = runtime.tool_registry
        allowed = {"vimax_render_video"}
        registry._specs = {k: v for k, v in registry._specs.items() if k in allowed}
        registry._aliases = {a: n for a, n in registry._aliases.items() if n in allowed}
        if set(registry._specs) != allowed:
            raise RuntimeError("media-only tool policy was not installed")
        if runtime.llm.ledger.path is None:
            raise RuntimeError("persistent request ledger is unavailable")
        ledger = runtime.llm.ledger
        for key, value in REQUIRED_CAPS.items():
            if ledger.caps().get(key) != value:
                raise RuntimeError(f"unexpected request cap for {key}")
        if int(os.environ.get("VIMAX_BAILIAN_BUDGET_TRANSITIONS", "-1")) != TRANSITION_CAP:
            raise RuntimeError(f"transition cap must be exactly {TRANSITION_CAP}")
        if abs(float(ledger._deadline or 0) - 5400.0) > 0.001:
            raise RuntimeError("shared deadline mismatch")

        lock = threading.Lock()
        observed = {"total_tokens": 0, "unknown": False}
        soft_limit = int(os.environ.get(
            "VIMAX_BAILIAN_BUDGET_OBSERVED_OUTPUT_TOKENS_TOTAL", "500000"))
        close = ledger.close
        guard = ledger.guard
        reserve = ledger.reserve_and_open
        open_event = ledger.open

        def close_observed(request_id, status="ok", **fields):
            opened = ledger._open.get(request_id, {})
            result = close(request_id, status, **fields)
            usage = fields.get("usage")
            total = usage.get("total_tokens") if isinstance(usage, dict) else None
            if isinstance(total, int) and total >= 0:
                with lock:
                    observed["total_tokens"] += total
            elif opened.get("op") == "llm_chat":
                with lock:
                    observed["unknown"] = True
            return result

        def check_observed():
            with lock:
                total, unknown = observed["total_tokens"], observed["unknown"]
            if unknown:
                from agent_runtime.request_ledger import BudgetExceeded
                raise BudgetExceeded("observed_total_tokens_unavailable", soft_limit,
                                     "a completed language response omitted total_tokens")
            if total >= soft_limit:
                from agent_runtime.request_ledger import BudgetExceeded
                raise BudgetExceeded("observed_total_tokens_soft", soft_limit,
                                     f"already_returned_total_tokens={total}")

        def guarded(key, n=1):
            check_observed()
            return guard(key, n)

        def reserved(kind, reservations, **fields):
            check_observed()
            return reserve(kind, reservations, **fields)

        def strict_open(kind, **fields):
            before = ledger.failure_state()["ledger_write_failures"]
            rid = open_event(kind, **fields)
            if ledger.failure_state()["ledger_write_failures"] != before:
                with ledger._lock:
                    ledger._open.pop(rid, None)
                from agent_runtime.request_ledger import LedgerWriteError
                raise LedgerWriteError("pre-send ledger open was not persisted")
            return rid

        ledger.close = close_observed
        ledger.guard = guarded
        ledger.reserve_and_open = reserved
        ledger.open = strict_open
        spec = registry._specs["vimax_render_video"]
        original_handler = spec.handler
        render_lock = threading.Lock()
        render_started = {"value": False}

        async def one_native_render(args, tool_runtime=None):
            with render_lock:
                if render_started["value"]:
                    from agent_runtime.models import ToolResult
                    return ToolResult("vimax_render_video", False,
                                      "This attempt already started its single render "
                                      "pipeline; no retry is allowed.",
                                      {"error_type": "attempt_render_already_consumed",
                                       "media_retry": False})
                render_started["value"] = True
            return await original_handler(args, tool_runtime)

        spec.handler = one_native_render
        (WORK / "tool-policy.json").write_text(json.dumps({
            "allowed_tools": sorted(allowed), "planning_tools_registered": False,
            "shell_registered": False, "media_tool": "vimax_render_video",
            "render_pipeline_invocations": 1,
            "render_retry_after_unknown_create": "blocked before pipeline invocation",
            "image_create_cap": REQUIRED_CAPS["image_generations"],
            "video_create_cap": REQUIRED_CAPS["video_creates"],
            "transition_cap": TRANSITION_CAP, "soft_total_tokens": soft_limit,
            "soft_total_tokens_basis": "returned usage.total_tokens only",
        }, indent=2) + "\n")
        phase("tool_policy.installed")
        return runtime
    return build


def install_image_send_gate() -> None:
    """Count and durably reserve every image POST, including 429 retries."""
    import tools.image_generator_bailian_api as image_module
    from agent_runtime.request_ledger import BudgetExceeded, LedgerWriteError, get_ledger
    original = image_module._post_json

    async def guarded_post(url, *, headers, payload, timeout):
        global _image_send_count
        ledger = get_ledger()
        with _image_send_lock:
            if _image_send_count >= _image_send_cap:
                raise BudgetExceeded("image_create_sends", _image_send_cap,
                                     f"already_reserved={_image_send_count}")
            _image_send_count += 1
            seq = _image_send_count
            before = ledger.failure_state()["ledger_write_failures"]
            rid = ledger.open("image_create_http_send", send_sequence=seq,
                              model=str(payload.get("model", "")),
                              url=str(url).split("?", 1)[0])
            after = ledger.failure_state()["ledger_write_failures"]
            if after != before:
                with ledger._lock:
                    ledger._open.pop(rid, None)
                raise LedgerWriteError("image send reservation could not be persisted")
        try:
            status, body = await original(url, headers=headers, payload=payload,
                                          timeout=timeout)
            ledger.close(rid, "returned", http_status=status)
            return status, body
        except BaseException as exc:
            ledger.error(rid, type(exc).__name__, right_censored=True)
            raise

    image_module._post_json = guarded_post


def install_ffmpeg_audit() -> None:
    """Record actual FFmpeg argv and return code without changing pipeline I/O."""
    import subprocess
    original = subprocess.Popen
    lock = threading.Lock()
    log_path = WORK / "ffmpeg-processes.jsonl"

    def is_ffmpeg(args):
        item = args[0] if isinstance(args, (list, tuple)) and args else args
        return Path(str(item)).name in {"ffmpeg", "ffmpeg-linux-x86_64-v7.0.0"}

    class AuditedPopen(original):
        def __init__(self, args, *pargs, **kwargs):
            self._vimax_ffmpeg = is_ffmpeg(args)
            self._vimax_args = args
            self._vimax_started = time.monotonic()
            super().__init__(args, *pargs, **kwargs)

        def _record(self):
            if not self._vimax_ffmpeg or getattr(self, "_vimax_recorded", False):
                return
            self._vimax_recorded = True
            row = {"command": self._vimax_args if isinstance(self._vimax_args, str)
                   else list(self._vimax_args),
                   "returncode": self.returncode,
                   "wall_s": round(time.monotonic() - self._vimax_started, 6)}
            with lock, log_path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")

        def wait(self, *args, **kwargs):
            rc = super().wait(*args, **kwargs)
            self._record()
            return rc

        def communicate(self, *args, **kwargs):
            result = super().communicate(*args, **kwargs)
            self._record()
            return result

    subprocess.Popen = AuditedPopen


def self_check() -> int:
    from agent_runtime.vimax_adapters import preflight_render_capability
    source, src_dir = load_plan()
    from utils.video_generation_capabilities import configured_video_generation_capabilities
    ok, reasons = preflight_render_capability(
        src_dir, video_capabilities=configured_video_generation_capabilities())
    if not ok:
        raise RuntimeError("source plan failed current media capability preflight: "
                           + "; ".join(reasons))
    import subprocess
    ffmpeg = subprocess.run(["ffmpeg", "-version"], capture_output=True, text=True, timeout=10)
    ffprobe = subprocess.run(["ffprobe", "-version"], capture_output=True, text=True, timeout=10)
    if ffmpeg.returncode or ffprobe.returncode:
        raise RuntimeError("container ffmpeg/ffprobe unavailable")
    encoders = subprocess.run(["ffmpeg", "-hide_banner", "-encoders"],
                              capture_output=True, text=True, timeout=10)
    if encoders.returncode or "libx264" not in encoders.stdout:
        raise RuntimeError("container FFmpeg libx264 encoder unavailable")
    from utils.image_selection import image_candidate_count_from_config
    if image_candidate_count_from_config({}) != 2:
        raise RuntimeError("frozen image candidate count differs from 2")
    return 0


async def run_attempt() -> int:
    """The single production path: gate -> seed -> policy -> native agent."""
    phase("entry.start", session_id=SESSION_ID)
    startup_gate()
    phase("startup_gate.released")
    os.environ["VIMAX_BAILIAN_EVENT_LOG"] = str(WORK / "model-events.jsonl")
    session = seed_session()
    install_image_send_gate()
    install_ffmpeg_audit()
    import agent_runtime
    agent_runtime.build_runtime = install_generation_policy(agent_runtime.build_runtime)
    import main_agent
    prompt = ("使用当前已固定的 ViMax session `" + SESSION_ID + "`，仅调用一次 "
              "`vimax_render_video` 继续已有规划并完成原生图片、过渡、主体视频和最终拼接流程。"
              "不要调用任何规划、shell或其他工具；不要重写或修改规划。工具成功返回后结束本轮，"
              "并如实报告工具结果。")
    event_path = WORK / "agent-events.jsonl"
    with event_path.open("a", encoding="utf-8", buffering=1) as event_file, \
         (WORK / "agent-events-timed.jsonl").open("a", encoding="utf-8", buffering=1) as timed_file:
        original = sys.stdout
        sys.stdout = Tee(original, event_file, timestamp_stream=timed_file)
        try:
            rc = await main_agent.amain(["--session", SESSION_ID, "--jsonl", "--once", prompt])
        finally:
            sys.stdout = original
    phase("agent.finished", returncode=rc)
    rows = []
    for line in event_path.read_text(encoding="utf-8").splitlines():
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            pass
    render_results = [r.get("tool_result", {}) for r in rows
                      if r.get("type") == "tool_result"
                      and (r.get("tool_result") or {}).get("name") == "vimax_render_video"]
    success = bool(render_results and render_results[-1].get("ok") is True)
    final_path = ((render_results[-1].get("metadata") or {}).get("final_video_path")
                  if success else None)
    from agent_runtime.request_ledger import get_ledger
    ledger = get_ledger()
    ledger.flush_state()
    complete = {"main_agent_returncode": rc,
                "render_tool_result_seen": bool(render_results),
                "render_tool_ok": success, "final_video_path": final_path,
                "session_id": SESSION_ID, "termination": "native_agent_done"}
    atomic_json(WORK / "COMPLETE", complete)
    phase("complete.written", render_ok=success, final_video_path=final_path)
    # Keep the cgroup alive until the host samples its final boundary.
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))
    while True:
        time.sleep(1)


async def main() -> int:
    WORK.mkdir(parents=True, exist_ok=True)
    if "--self-check" in sys.argv:
        try:
            rc = self_check()
            phase("self_check.done", returncode=rc)
            return rc
        except SystemExit:
            raise
        except BaseException as exc:  # noqa: BLE001 — evidence first
            fail("self_check", exc)
            raise
    try:
        await run_attempt()
        return 0
    except SystemExit:
        # the SIGTERM handshake exits 0 after COMPLETE; that is the designed
        # success path, NOT a failure — never write ENTRY-FAILED for it
        # (bug found by the REPAIR-01 cold-start acceptance)
        raise
    except BaseException as exc:  # noqa: BLE001 — evidence first, then re-raise
        fail("run_attempt", exc)
        raise


if __name__ == "__main__":
    try:
        raise SystemExit(asyncio.run(main()))
    except SystemExit:
        raise
    except BaseException as exc:  # noqa: BLE001 — last-resort evidence net
        fail("main", exc)
        raise SystemExit(1)
