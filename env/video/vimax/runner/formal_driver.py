#!/usr/bin/env python3
"""In-container driver for the FORMAL ViMax eight-shot attempt.

Runs the REAL native agent entry (main_agent.py --jsonl --stdin-repl) with
REAL Bailian routes and the pre-authorized single-shot task text. The driver
itself never calls any model API: it feeds the task once, streams every
native JSONL event to disk, waits for the turn's terminal `done`, then
performs the completion HANDSHAKE (write COMPLETE, wait for SIGTERM from
`docker stop`) so the host runner can take the final resource boundary
while the container still exists.
"""
from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path

RUNNER = Path("/opt/validation")
sys.path.insert(0, "/opt/vimax/src")
sys.path.insert(0, str(RUNNER))

WORK = Path(os.environ.get("ATTEMPT_WORK", "/workspace/attempt"))
TASK_TEXT_PATH = Path(os.environ.get("ATTEMPT_TASK_TEXT"))
EVENTS = WORK / "agent-events.jsonl"
WORK_WINDOW_S = float(os.environ.get("ATTEMPT_WORK_WINDOW_S", "5400"))

T0 = time.monotonic()
record: dict = {"phases": {}, "events": 0, "t_start_wall": time.time()}


def persist() -> None:
    WORK.mkdir(parents=True, exist_ok=True)
    (WORK / "driver-record.json").write_text(
        json.dumps(record, indent=1, ensure_ascii=False) + "\n")


def main() -> int:
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))
    WORK.mkdir(parents=True, exist_ok=True)
    task_text = TASK_TEXT_PATH.read_text(encoding="utf-8")

    # ---- network preflight: DNS/TLS reachability ONLY (no paid request) --
    import socket
    import ssl
    preflight = {}
    for host in sorted({
            os.environ["VIMAX_IMAGE_BASE_URL"].split("//", 1)[1]
            .split("/")[0].split(":")[0],
            os.environ["VIMAX_LLM_BASE_URL"].split("//", 1)[1]
            .split("/")[0].split(":")[0],
            os.environ["VIMAX_VIDEO_BASE_URL"].split("//", 1)[1]
            .split("/")[0].split(":")[0]}):
        try:
            ctx = ssl.create_default_context()
            with socket.create_connection((host, 443), timeout=10) as sock:
                with ctx.wrap_socket(sock, server_hostname=host) as tls:
                    preflight[host] = {
                        "tcp_tls": "ok",
                        "tls_version": tls.version()}
        except Exception as exc:  # noqa: BLE001
            preflight[host] = {"tcp_tls": f"error: {type(exc).__name__}: "
                                          f"{exc}"[:200]}
    record["network_preflight"] = preflight
    persist()
    bad = [h for h, v in preflight.items() if v["tcp_tls"] != "ok"]
    if bad:
        record["error"] = f"network preflight failed for {bad}; refusing " \
                          "to start the attempt"
        persist()
        (WORK / "COMPLETE").write_text(json.dumps(
            {"status": "preflight_failed", "hosts": bad}) + "\n")
        signal.pause()
        return 7

    # ---- run the native agent entry ---------------------------------------
    argv = [sys.executable, "/opt/vimax/src/main_agent.py", "--jsonl",
            "--stdin-repl", "--new-session",
            "--new-session-name", "formal-eight-shot-01"]
    record["agent_argv"] = argv
    persist()
    t_agent = time.monotonic()
    agent_cwd = WORK / "agent-cwd"
    agent_cwd.mkdir(parents=True, exist_ok=True)  # BEFORE Popen (fix)
    proc = subprocess.Popen(argv, stdin=subprocess.PIPE,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            text=True, cwd=str(agent_cwd))
    events: list[dict] = []
    reader_done = threading.Event()

    def reader() -> None:
        for raw in proc.stdout:
            raw = raw.strip()
            if not raw:
                continue
            try:
                ev = json.loads(raw)
            except json.JSONDecodeError:
                continue
            events.append(ev)
            with open(EVENTS, "a", encoding="utf-8") as fh:
                fh.write(json.dumps(ev, ensure_ascii=False) + "\n")
        reader_done.set()

    threading.Thread(target=reader, daemon=True).start()

    def wait_for(pred, timeout):
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            if any(pred(e) for e in events):
                return True
            if proc.poll() is not None:
                return False
            time.sleep(1.0)
        return False

    mark = 0
    proc.stdin.write(task_text + "\n")
    proc.stdin.flush()
    mark = len(events)
    got_done = wait_for(lambda e: e.get("type") == "done", WORK_WINDOW_S)
    record["phases"]["agent_turn"] = {
        "wall_s": round(time.monotonic() - t_agent, 3),
        "done_seen": got_done,
        "events": len(events)}
    try:
        proc.stdin.close()
    except Exception:  # noqa: BLE001
        pass
    try:
        proc.wait(timeout=300)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(timeout=15)
        record["phases"]["agent_turn"]["killed_after_timeout"] = True
    reader_done.wait(15)
    record["agent_returncode"] = proc.returncode
    record["event_types"] = sorted({e.get("type", "?") for e in events})
    record["tool_results"] = [
        {"name": (e.get("tool_result") or {}).get("name"),
         "ok": (e.get("tool_result") or {}).get("ok")}
        for e in events if e.get("type") == "tool_result"]
    persist()

    # ledger state (write failures / unclosed requests are never invisible)
    ledger_path = os.environ.get("VIMAX_BAILIAN_EVENT_LOG")
    if ledger_path and Path(ledger_path + ".state").exists():
        record["ledger_state"] = json.loads(
            Path(ledger_path + ".state").read_text())

    # ---- completion handshake ---------------------------------------------
    (WORK / "COMPLETE").write_text(json.dumps({
        "status": "agent_finished",
        "returncode": proc.returncode,
        "done_seen": got_done,
        "wall_s": round(time.monotonic() - T0, 3)}) + "\n")
    print(json.dumps({"done_seen": got_done,
                      "returncode": proc.returncode,
                      "events": len(events)}, ensure_ascii=False), flush=True)
    try:
        signal.pause()  # wait for SIGTERM from docker stop; not agent work
    except (KeyboardInterrupt, SystemExit):
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
