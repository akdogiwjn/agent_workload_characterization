"""Small private stdin/stdout worker for G1-02 A fixtures and B proposal."""
from __future__ import annotations

import hashlib
import json
import os
import sys
import time
import threading

_OUTPUT_LOCK = threading.Lock()
_IDENTITY = {}


def emit(event, **fields):
    for key, value in _IDENTITY.items():
        fields.setdefault(key, value)
    fields.setdefault("t_monotonic_ns", time.monotonic_ns())
    with _OUTPUT_LOCK:
        sys.stdout.write(json.dumps({"event": event, **fields}) + "\n")
        sys.stdout.flush()


def work(iterations):
    value = 0
    for i in range(iterations):
        value = (value + i * 3) & 0xFFFFFFFF
    return hashlib.sha256(str(value).encode()).hexdigest()


def main(run_id="fixture"):
    with open('/proc/self/stat') as fh:
        stat = fh.read().rsplit(')', 1)[1].split()
    _IDENTITY.update(run_id=run_id, service_id=run_id + ':service',
                     pid=os.getpid(), starttime_ticks=int(stat[19]))
    pending = {}
    for line in sys.stdin:
        try:
            msg = json.loads(line)
        except ValueError:
            emit("error", category="protocol")
            continue
        op = msg.get("op")
        ident = msg.get("id")
        if op == "hello":
            emit("ready", pid=os.getpid(), start_monotonic_ns=time.monotonic_ns())
        elif op == "sync":
            emit("request_started", id=ident, kind="sync")
            cpu0 = time.process_time()
            digest = work(int(msg.get("iterations", 1000)))
            emit("request_finished", id=ident, kind="sync", digest=digest,
                 cpu_seconds=time.process_time() - cpu0)
        elif op == "window_start":
            emit("baseline_ready", id=ident)
        elif op == "window_release":
            emit("work_started", id=ident)
            cpu0 = time.process_time()
            digest = work(int(msg.get("iterations", 1000)))
            emit("work_done", id=ident, digest=digest,
                 cpu_seconds=time.process_time() - cpu0)
        elif op == "window_ack":
            emit("window_acknowledged", id=ident)
        elif op == "submit":
            pending[ident] = {"state": "submitted", "cancelable": bool(msg.get("cancelable"))}
            emit("job_submitted", id=ident)
        elif op == "release":
            job = pending.get(ident)
            if not job:
                emit("error", category="unknown_job", id=ident)
                continue
            job["state"] = "started"
            emit("job_started", id=ident)
            job["proceed"] = threading.Event()
            job["cancel"] = threading.Event()
            def background(job=job, ident=ident):
                while not job["cancel"].is_set() and not job["proceed"].is_set():
                    time.sleep(0.01)
                if job["cancel"].is_set():
                    job["state"] = "cancelled"
                    emit("job_finished", id=ident, state="cancelled")
                    return
                cpu0 = time.process_time()
                digest = work(job["iterations"])
                job["state"] = "completed"
                emit("job_finished", id=ident, state="completed", digest=digest,
                     cpu_seconds=time.process_time() - cpu0)
            job["thread"] = threading.Thread(target=background, daemon=True)
            job["thread"].start()
        elif op == "proceed":
            job = pending.get(ident)
            if not job or job.get("state") != "started" or job.get("cancelable"):
                emit("error", category="invalid_complete", id=ident)
                continue
            job["iterations"] = int(msg.get("iterations", 1000))
            emit("proceed_ack", id=ident)
            job["proceed"].set()
        elif op == "poll":
            job = pending.get(ident)
            emit("poll_result", id=ident, state=(job or {}).get("state", "unknown"))
        elif op == "wait":
            job = pending.get(ident)
            emit("wait_result", id=ident, state=(job or {}).get("state", "unknown"))
        elif op == "cancel":
            job = pending.get(ident)
            if job and job.get("state") == "started":
                job["cancel"].set()
                job["thread"].join(timeout=15)
                if job["thread"].is_alive():
                    emit("error", category="cancel_timeout", id=ident)
            else:
                emit("error", category="invalid_cancel", id=ident)
        elif op == "shutdown":
            for job in pending.values():
                if job.get("thread"):
                    job["cancel"].set(); job["thread"].join(timeout=15)
            emit("closed", pending=list(pending))
            return
        else:
            emit("error", category="unknown_operation")


def self_test():
    """Container command mode: run the fixed protocol without a network."""
    emit("ready", pid=os.getpid(), start_monotonic_ns=time.monotonic_ns())
    for ident in ("sync-1", "sync-2"):
        emit("request_started", id=ident, kind="sync")
        emit("request_finished", id=ident, kind="sync", digest=work(1000))
    emit("job_submitted", id="job-1")
    emit("job_started", id="job-1")
    emit("poll_result", id="job-1", state="started")
    emit("job_finished", id="job-1", state="completed", digest=work(1000))
    emit("wait_result", id="job-1", state="completed")
    emit("job_submitted", id="job-2")
    emit("job_started", id="job-2")
    emit("job_finished", id="job-2", state="cancelled")
    emit("wait_result", id="job-2", state="cancelled")
    emit("closed", pending=[])


if __name__ == "__main__":
    self_test() if "--self-test" in sys.argv[1:] else main()
