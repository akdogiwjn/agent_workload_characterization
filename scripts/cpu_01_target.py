"""CPU-01 owned synthetic target: fixed integer loop with self-reported identity.

Protocol (stdout, one JSON object per line):
  1. {"event":"target_started","pid":...,"starttime_ticks":...,"iterations":N}
  2. {"event":"target_done","pid":...,"checksum":"<sha256>","cpu_seconds":<process_time>}

The fixed workload is the same closed-form-checkable integer loop family used
by G1-02 (3*n*(n-1)//2 mod 2**32 accumulated over n in [1..N]). CPU-01 only
needs a deterministic, short, CPU-bound owned process; this is NOT an Agent
workload and its hotspots are NOT Agent hotspots.
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
import time


def main() -> int:
    iterations = int(sys.argv[1]) if len(sys.argv) > 1 else 20000000
    pid = os.getpid()
    starttime = None
    try:
        stat = open(f"/proc/{pid}/stat", encoding="ascii", errors="replace").read()
        starttime = int(stat.rsplit(")", 1)[1].split()[19])
    except (OSError, IndexError, ValueError):
        starttime = None  # identity degraded, not fabricated
    print(json.dumps({"event": "target_started", "pid": pid,
                      "starttime_ticks": starttime, "iterations": iterations}),
          flush=True)
    acc = 0
    t0 = time.process_time()
    for n in range(1, iterations + 1):
        acc = (acc + 3 * n * (n - 1) // 2) & 0xFFFFFFFF
    cpu = time.process_time() - t0
    checksum = hashlib.sha256(str(acc).encode()).hexdigest()
    print(json.dumps({"event": "target_done", "pid": pid,
                      "checksum": checksum, "cpu_seconds": round(cpu, 6)}),
          flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
