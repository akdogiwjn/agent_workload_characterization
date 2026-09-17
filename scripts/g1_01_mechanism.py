"""G1-01 A4: deterministic local mini-program measurement checks.

Run explicitly (bounded budgets, declared BEFORE execution):

    PYTHONPATH=src python3 scripts/g1_01_mechanism.py \
        --out reports/resource/G1-01-A/<batch>

Case list and budgets (fixed in advance; stop at limit, keep failures):
- C1 single worker, FIXED workload (fixed iteration count, not fixed
  seconds; busy <= 2 s): /proc CPU delta vs the child's OWN
  time.process_time() — two INDEPENDENT sources for the same quantity;
- C2 dual overlapping workers (2 workers, fixed workload each):
  work/union/span wall math; per-worker CPU from separate readers
  (never summed into an exclusive total);
- O1..O3 overhead pairs (pre-fixed 3 pairs): fixed-workload child with
  the host monitor ON vs OFF; raw wall/CPU per run + paired difference.
  NOT a stable-percentage claim.

Limits per case: wall <= 10 s, busy <= 2 s, workers <= 2, per-worker
memory <= 64 MiB, temp files <= 8 MiB (none used). Whole batch
wall <= 120 s. Report <= 20 MiB. Only processes created by this script
are read (pid+starttime pinned); no unrelated scanning.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from agent_workload_characterization.collectors.host_process import (  # noqa: E402
    HostProcessMonitor, read_starttime)

WORKER_CODE = r'''
import json, sys, time
# process_time() read at MODULE ENTRY (after interpreter startup):
# the self-report therefore covers the code segment from module entry
# through the loop end. It EXCLUDES interpreter-startup CPU before the
# module ran and any exit-time work after the loop — it is a CODE
# SEGMENT CPU increment, not a whole-lifetime measurement. See
# comparison_semantics in the mechanism report.
w0 = time.perf_counter()
t0 = time.process_time()
iterations = int(sys.argv[1])
acc = 0
for i in range(iterations):
    acc += i % 7
cpu = time.process_time() - t0
wall = time.perf_counter() - w0
print(json.dumps({"iterations": iterations, "cpu_s_self": cpu,
                  "wall_s_self": wall}))
'''

# fixed workload: chosen so busy stays well under 2 s on this host
ITERATIONS_SINGLE = 3_000_000
ITERATIONS_WORKER = 2_000_000
OVERHEAD_PAIRS = 3


def _spawn_worker(iterations: int) -> subprocess.Popen:
    return subprocess.Popen(
        [sys.executable, "-c", WORKER_CODE, str(iterations)],
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)


def _monitor_run(iterations: int, *, monitor_on: bool,
                 deadline_s: float = 10.0) -> dict:
    """One run: fixed workload; optionally poll the child's /proc.

    ``deadline_s`` is a HARD wall on the wait loop (checked BEFORE each
    wait, not after): a hung child is killed and the failure recorded —
    the run result carries ``deadline_exceeded`` instead of blocking the
    batch. The CPU comparison is a DIAGNOSTIC cross-check of two
    DIFFERENT overlapping windows (child code-segment self-report vs
    parent /proc first-to-last-readable delta); see comparison_semantics
    in the emitted JSON for the exact boundary statement."""
    proc = _spawn_worker(iterations)
    startt = read_starttime(proc.pid)
    mon = HostProcessMonitor(proc.pid, expected_starttime=startt,
                             interval_s=0.02)
    t0 = time.monotonic_ns()
    deadline = time.monotonic() + deadline_s
    exceeded = False
    if monitor_on:
        while proc.poll() is None:
            if time.monotonic() > deadline:
                exceeded = True
                proc.kill()
                break
            mon.poll_once()
            time.sleep(0.01)
    else:
        while proc.poll() is None:
            if time.monotonic() > deadline:
                exceeded = True
                proc.kill()
                break
            time.sleep(0.01)
    wall_ns = time.monotonic_ns() - t0
    out, _ = proc.communicate(timeout=10)
    self_cpu = None
    for line in out.splitlines():
        line = line.strip()
        if line.startswith("{"):
            try:
                self_cpu = json.loads(line).get("cpu_s_self")
            except ValueError:
                pass
    if not monitor_on:
        mon.poll_once()  # identity sanity read
    return {"wall_ns": wall_ns, "child_cpu_s_self": self_cpu,
            "deadline_exceeded": exceeded,
            "child_rc": proc.returncode,
            "monitor": mon.summary() if monitor_on else None}


def _write_results(out: Path, results: dict) -> None:
    (out / "mechanism_checks.json").write_text(
        json.dumps(results, indent=2) + "\n", encoding="utf-8")
    pairs = results.get("cases", [{}])[-1].get("pairs") \
        if results.get("cases") else None
    overhead = {
        "note": ("raw measurements only; see mechanism_checks.json "
                 "cases[-1] for the pairs"),
        "pairs": pairs or [],
    }
    (out / "overhead.json").write_text(
        json.dumps(overhead, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(allow_abbrev=False)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    t_batch0 = time.monotonic()
    batch_deadline = t_batch0 + 120.0
    results: dict = {"batch_started_utc": time.strftime(
        "%Y-%m-%dT%H:%M:%SZ", time.gmtime())}

    def _batch_time_left() -> float:
        return batch_deadline - time.monotonic()

    # C1: single worker, two independent CPU sources; the batch
    # deadline is checked BEFORE the case and a breach records a
    # stopped_batch marker instead of silently continuing
    if _batch_time_left() <= 0:
        results["stopped_batch"] = "deadline_before_C1"
        _write_results(args.out, results)
        return 1
    c1 = _monitor_run(ITERATIONS_SINGLE, monitor_on=True,
                      deadline_s=min(10.0, _batch_time_left()))
    c1_case = {
        "case": "C1_single_worker_fixed_workload",
        "deadline_exceeded": c1["deadline_exceeded"],
        "child_rc": c1["child_rc"],
        "comparison_semantics": (
            "DIAGNOSTIC CROSS-CHECK of two DIFFERENT measurement windows. "
            "Source A (child self-report): code-segment CPU increment — "
            "process_time from module entry through loop end; EXCLUDES "
            "interpreter startup before the module and exit-time work "
            "after the loop. Source B (parent /proc): first-to-last "
            "READABLE snapshot tick delta — starts strictly AFTER spawn "
            "returns (may miss startup CPU) and ends at the last poll "
            "(may miss or include exit depending on timing). The windows "
            "overlap but neither contains the other; the numeric "
            "difference reflects window difference + polling "
            "granularity + scheduler noise. Agreement is a units/"
            "plausibility consistency check ONLY — it is NOT a "
            "same-interval verification and the difference does NOT "
            "bound any window's skew"),
        "wall_ns": c1["wall_ns"],
        "iterations": ITERATIONS_SINGLE,
        "child_cpu_s_self": c1["child_cpu_s_self"],
        "proc_cpu_s": c1["monitor"]["cpu_seconds"] if c1["monitor"] else None,
        "n_readable_snapshots": (c1["monitor"]["n_readable"]
                                 if c1["monitor"] else 0),
        "final_read_status": (c1["monitor"]["final_read_status"]
                              if c1["monitor"] else None),
        "independent_sources": ("child time.process_time() vs parent "
                                "/proc utime+stine tick delta"),
        "tolerance": ("declared before execution: the two CPU sources "
                      "measure DIFFERENT overlapping windows (see "
                      "comparison_semantics); no numeric bound on the "
                      "difference is claimed as a verification pass. The "
                      "recorded diff is raw diagnostic data; exact "
                      "counts/hashes exact"),
    }
    if c1_case["child_cpu_s_self"] is not None \
            and c1_case["proc_cpu_s"] is not None:
        c1_case["cpu_abs_diff_s"] = abs(c1_case["child_cpu_s_self"]
                                        - c1_case["proc_cpu_s"])
        c1_case["poll_granularity_s"] = 0.02

    # C2: dual overlapping workers
    w1 = _spawn_worker(ITERATIONS_WORKER)
    w2 = _spawn_worker(ITERATIONS_WORKER)
    st1, st2 = read_starttime(w1.pid), read_starttime(w2.pid)
    m1 = HostProcessMonitor(w1.pid, expected_starttime=st1, interval_s=0.02)
    m2 = HostProcessMonitor(w2.pid, expected_starttime=st2, interval_s=0.02)
    t0 = time.monotonic_ns()
    deadline = time.monotonic() + 10.0
    exceeded = False
    while w1.poll() is None or w2.poll() is None:
        if time.monotonic() > deadline:
            exceeded = True
            w1.kill()
            w2.kill()
            break
        if w1.poll() is None:
            m1.poll_once()
        if w2.poll() is None:
            m2.poll_once()
        time.sleep(0.01)
    span_ns = time.monotonic_ns() - t0
    o1, _ = w1.communicate(timeout=10)
    o2, _ = w2.communicate(timeout=10)
    s1, s2 = m1.summary(), m2.summary()
    c2_case = {
        "case": "C2_dual_overlapping_workers",
        "deadline_exceeded": exceeded,
        "iterations_per_worker": ITERATIONS_WORKER,
        "span_s": span_ns / 1e9,
        "worker1_cpu_s": s1["cpu_seconds"],
        "worker2_cpu_s": s2["cpu_seconds"],
        "cpu_sum_s": (s1["cpu_seconds"] + s2["cpu_seconds"]
                      if s1["cpu_seconds"] is not None
                      and s2["cpu_seconds"] is not None else None),
        "semantics": ("span = wall from first spawn to last exit; "
                      "cpu_sum = per-worker exclusive CPU (separate "
                      "processes: summable as WORK, never as wall or as "
                      "a shared-scope total)"),
    }

    # O1..O3: overhead pairs (fixed in advance)
    pairs = []
    for i in range(OVERHEAD_PAIRS):
        if _batch_time_left() <= 0:
            results["stopped_batch"] = f"deadline_before_pair_{i+1}"
            break
        dl = min(10.0, _batch_time_left() / 2)
        off = _monitor_run(ITERATIONS_SINGLE, monitor_on=False,
                           deadline_s=dl)
        on = _monitor_run(ITERATIONS_SINGLE, monitor_on=True,
                          deadline_s=dl)
        pairs.append({
            "pair": i + 1,
            "off": {"wall_ns": off["wall_ns"],
                    "child_cpu_s_self": off["child_cpu_s_self"],
                    "deadline_exceeded": off["deadline_exceeded"]},
            "on": {"wall_ns": on["wall_ns"],
                   "child_cpu_s_self": on["child_cpu_s_self"],
                   "deadline_exceeded": on["deadline_exceeded"]},
            "wall_diff_ns": on["wall_ns"] - off["wall_ns"],
            "collector": (on["monitor"]["collector"]
                          if on["monitor"] else None),
        })
    overhead_case = {
        "case": "O1_O3_overhead_pairs",
        "pairs_fixed_in_advance": OVERHEAD_PAIRS,
        "measurement": ("fixed workload, monitor ON vs OFF; raw values "
                        "reported; paired differences are data, NOT a "
                        "stable percentage claim"),
        "pairs": pairs,
    }

    batch_wall = time.monotonic() - t_batch0
    results["cases"] = [c1_case, c2_case, overhead_case]
    results["batch_wall_s"] = round(batch_wall, 3)
    results["limits"] = {"per_case_wall_s": 10, "busy_s": 2,
                         "workers": 2, "worker_mem_mib": 64,
                         "temp_files_mib": 8, "batch_wall_s": 120,
                         "report_mib": 20}
    results["within_limits"] = {
        "batch_wall": batch_wall <= 120,
    }
    _write_results(args.out, results)
    print(json.dumps({"batch_wall_s": results["batch_wall_s"],
                      "c1_diff_s": c1_case.get("cpu_abs_diff_s"),
                      "c2_span_s": c2_case["span_s"],
                      "pairs": len(pairs)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
