"""CPU-02 container-side eval supervisor: identity, barrier, exec.

Protocol (stdin/stdout JSONL, no network):
  1. print {"event":"supervisor_ready","pid":<container pid>,
            "starttime_ticks":<ticks>,"eval_file":...}
  2. BLOCK on stdin until the host sends {"cmd":"release"} — the target
     consumes no CPU while waiting, so the perf sampling window is defined
     purely by the host-side control protocol (perf starts with events
     disabled via -D -1 and is enabled only after an explicit 'enable'
     ACK); no marker busy-loop is used or needed;
  3. on release: print {"event":"release_ack"} and os.execvp the official
     eval script — same PID, so the attached perf keeps tracking the whole
     eval chain and its descendants;
  4. stdin EOF before release (host died): report and exit non-zero
     WITHOUT running eval.

The readiness barrier is the perf control ACK on the host side, not this
process's Popen success or any sleep.
"""
from __future__ import annotations

import json
import os
import sys


def main(eval_file: str) -> int:
    pid = os.getpid()
    starttime = None
    try:
        stat = open("/proc/self/stat", encoding="ascii", errors="replace").read()
        starttime = int(stat.rsplit(")", 1)[1].split()[19])
    except (OSError, IndexError, ValueError):
        starttime = None
    print(json.dumps({"event": "supervisor_ready", "pid": pid,
                      "starttime_ticks": starttime, "eval_file": eval_file}),
          flush=True)
    released = False
    noise_lines = []
    while not released:
        line = sys.stdin.readline()
        if not line:
            break  # EOF: host side gone
        stripped = line.strip()
        if not stripped:
            continue
        try:
            obj = json.loads(stripped)
        except ValueError:
            noise_lines.append(stripped[:100])
            continue
        if obj.get("cmd") == "release":
            released = True
    if not released:
        print(json.dumps({"event": "supervisor_exit",
                          "reason": "stdin_eof_before_release",
                          "observed_noise": noise_lines}), flush=True)
        return 3
    print(json.dumps({"event": "release_ack", "pid": pid}), flush=True)
    # Same PID exec: the attached perf target and its inheritance range
    # continue over the official eval script and its descendants.
    os.execvp("bash", ["bash", eval_file])
    return 0  # unreachable on success


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1] if len(sys.argv) > 1 else "/eval.sh"))
