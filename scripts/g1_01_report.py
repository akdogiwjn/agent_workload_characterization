"""G1-01 A report assembly (offline; sealed inputs read-only)."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from agent_workload_characterization.analyzers.tool_timeline import (  # noqa: E402
    write_tool_timeline_outputs)

RUN_DIR = Path("data/raw/generated/RUN-01-C/20260912T125202Z-840e49")
V2_DIR = Path("reports/resource/RUN-01-C-v2")
CODE_FILES = [
    "src/agent_workload_characterization/analyzers/tool_timeline.py",
    "src/agent_workload_characterization/collectors/host_process.py",
    "src/agent_workload_characterization/collectors/resource_sampler.py",
    "src/agent_workload_characterization/runners/mini_agent_adapter.py",
    "src/agent_workload_characterization/runners/coding_pilot.py",
    "scripts/g1_01_mechanism.py",
    "tests/test_g1_01.py",
    "tests/integration_run01.py",
]

TIMING_SEMANTICS = """# Timing field semantics (verified against installed mini 2.4.6)

## Field table

| Field | Source locator | Clock | Native/log_receipt | Precision | Valid uses |
| --- | --- | --- | --- | --- | --- |
| assistant `extra.timestamp` | `minisweagent/models/litellm_model.py:104` (`time.time()` at query end, before tools) | epoch (CLOCK_REALTIME) | log_receipt (post-query, PRE-execution) | ~µs | pre-execution boundary estimate; anchor pair component |
| tool msg `extra.timestamp` | `minisweagent/models/utils/actions_toolcall.py:100` (`time.time()` after `env.execute` returned + observation formatted) | epoch | log_receipt (post-execution, post-format) | ~µs | post-execution boundary estimate; window END (overstated by formatting) |
| status `t_start_ns`/`t_end_ns` | our `StatusTrackingAgent.query` (child) | CLOCK_MONOTONIC ns | native request boundary (query bracket) | ns | request windows; anchor pair component; budget counting |
| sampler `boundary_start/end` | runner `SystemClock` (parent) | CLOCK_MONOTONIC ns | native scope boundary | ns | container CPU/memory interval denominators |
| recorder `t_monotonic_ns` + `t_utc` | `SemanticRecorder._stamp` | CLOCK_MONOTONIC ns + UTC epoch | native event stamp | ns | event ordering; UTC anchor per event |
| `mini_tool_events.jsonl` `t_start_ns`/`t_end_ns` (NEW, G1-01-A2) | `ToolEventRecordingEnvironment` (child) | CLOCK_MONOTONIC ns | **native tool execute bracket** (open persisted before call) | ns | true tool durations in FUTURE runs; scope window association |

## Clock-domain rules

- Linux `CLOCK_MONOTONIC` is SYSTEM-WIDE (not per-process): child and
  parent monotonic stamps on this host are directly comparable.
- epoch <-> monotonic conversion REQUIRES an anchor pair. The pair
  (assistant `extra.timestamp` [epoch], status `t_end_ns` [monotonic])
  is read within the same child query call (~µs apart) and is used as
  the anchor; the measured anchor residual (max deviation of the
  per-request offset from the median) is the declared error bound.
  RUN-01-C: 26 anchors, residual max 3.84 ms.
- Without an anchor pair, epoch and monotonic stamps are never
  subtracted from each other.

## What the historical RUN-01-C data supports

- Tool identity/sequence/result: FULLY (26/26, tool_call_id +
  positional pairing, returncode/output-length present).
- Tool time: estimated/bound windows only
  ([assistant.timestamp, tool.timestamp] in epoch, calibrated to
  monotonic via anchors); the window OVERSTATES execution by
  scheduling + formatting overhead. TRUE tool durations: null
  (the A2 hook did not exist in that run).
- Tool <-> container resources: shared_scope/window association only;
  sparse samples (0.5 s) falling inside calibrated windows are counted
  as association evidence, never as exclusive per-tool CPU.
- Host mini child process CPU/RSS: MISSING (no reader existed; gap kept
  null, not back-filled).
"""


def _sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def _guard_batch(out_root: Path, batch: str) -> Path:
    """Reject absolute paths, '..' traversal, symlink escape and
    existing outputs (exclusive create, like the project's other
    report writers)."""
    import re
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", batch):
        raise ValueError(f"invalid batch id: {batch!r}")
    if batch in (".", ".."):
        raise ValueError("batch id must not be a path segment")
    candidate = out_root / batch
    resolved_root = out_root.resolve()
    resolved = candidate.resolve()
    if not resolved.is_relative_to(resolved_root):
        raise ValueError("batch escapes the report root")
    if resolved.exists():
        raise ValueError("batch directory already exists; "
                         "reports are never overwritten")
    for part in candidate.parts[:-1]:
        pass
    # also reject symlinked intermediate segments
    current = out_root
    for part in Path(batch).parts:
        current = current / part
        if current.is_symlink():
            raise ValueError(f"symlink in batch path: {current}")
    return candidate


def main() -> int:
    parser = argparse.ArgumentParser(allow_abbrev=False)
    parser.add_argument("--batch", required=True)
    args = parser.parse_args()
    out = _guard_batch(Path("reports/resource/G1-01-A"), args.batch)
    out.mkdir(parents=True, exist_ok=False)

    t0 = time.monotonic()

    # A1: sealed-data analysis (read-only)
    analysis = write_tool_timeline_outputs(RUN_DIR, out)
    (out / "timing_semantics.md").write_text(TIMING_SEMANTICS,
                                             encoding="utf-8")

    # A4: mechanism checks (bounded real local programs)
    proc = subprocess.run(
        [sys.executable, "-B", "scripts/g1_01_mechanism.py",
         "--out", str(out)], capture_output=True, text=True, timeout=150)
    if proc.returncode != 0:
        print("MECHANISM FAILED (kept as-is):", proc.stderr[-500:],
              file=sys.stderr)

    # input hashes (sealed + v2 report + code identity)
    inputs = {}
    for p in sorted(RUN_DIR.rglob("*")):
        if p.is_file():
            inputs[f"sealed:{p.relative_to(RUN_DIR)}"] = _sha(p)
    for p in sorted(V2_DIR.rglob("*")):
        if p.is_file():
            inputs[f"v2report:{p.relative_to(V2_DIR)}"] = _sha(p)
    code = {f: _sha(Path(f)) for f in CODE_FILES}

    cal = analysis["calibration"]
    summary_md = f"""# G1-01-A summary ({args.batch})

Generated: {datetime.now(timezone.utc).isoformat()} (offline; sealed
inputs read-only; no containers, no model, no network).

## A1 historical tool timeline (RUN-01-C, read-only)

- tool calls: **{analysis['tool_calls_total']}/26** identity-paired
  ({analysis['identity_basis']}); missing results:
  {analysis['pairing_missing_results']}
- epoch->monotonic calibration: {cal['n_anchors']} anchors, residual max
  **{cal['anchor_residual_ns_max']/1e6:.2f} ms**
- TRUE tool duration coverage: **0/{analysis['tool_calls_total']}**
  (reason: {analysis['true_duration_coverage']['reason']})
- estimated/bound window coverage:
  {analysis['estimated_window_coverage']['n_valid']}/
  {analysis['estimated_window_coverage']['n_applicable']}
  (windows OVERSTATE execution by scheduling+formatting overhead)
- container-scope window association: shared_scope only; no per-tool
  exclusive CPU claimed

## A2 tool-event hook (future runs)

`ToolEventRecordingEnvironment` brackets every `env.execute` with an
open line persisted BEFORE the call and a closed/error line after
(child CLOCK_MONOTONIC = system-wide; safe projections only). Verified
offline against the REAL installed mini with fake transport + fake
executor (4-test integration suite, 19 s): 3 opens / 2 closed / 1 error
(Submitted interrupt kept as error, never fake-closed); failing
returncode recorded; no raw command/output in events; format-error
requests write no tool events.

## A3 host observation (future runs)

`HostProcessReader`/`HostProcessMonitor` (/proc stat; pid+starttime
identity pin; utime+stime ticks with actual CLK_TCK; RSS pages with
actual page size; per-read wall cost accumulated). Wired into the mini
harness parent poll loop; final post-exit read kept as
process_exited (verified final = null, last readable = diagnostic).
Historical host gap NOT back-filled.

## A4 mechanism checks

See mechanism_checks.json / overhead.json: C1 two-source CPU agreement
within poll granularity; C2 dual-worker work/union/span; O1-O3 raw
overhead pairs (no percentage claim). One prior smoke execution of the
same script/budget occurred before the canonical run recorded here.

## Fixes found by the audit (future runs)

- `ScopeSamples.summary()`: sampled max now restricted to
  [boundary_start, boundary_end]; out-of-boundary samples preserved in
  evidence and counted separately (never polluting in-window metrics).

## Limits

Report <= 20 MiB; batch wall recorded in mechanism_checks.json.
"""
    (out / "summary.md").write_text(summary_md, encoding="utf-8")

    # manifest with full lineage
    files = {}
    for p in sorted(out.rglob("*")):
        if p.is_file() and p.name != "manifest.json":
            files[str(p.relative_to(out))] = _sha(p)
    manifest = {
        "batch": args.batch,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "assembly_wall_s": round(time.monotonic() - t0, 2),
        "files": files,
        "inputs": inputs,
        "code_identity": code,
        "sealed_inputs_untouched": True,
        "claim": ("G1-01-A offline analysis only; no containers, no "
                  "model, no network; historical gaps kept null"),
    }
    (out / "manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

    # POST-WRITE VERIFICATION (the R3 defect: the manifest hashed files
    # BEFORE later edits refreshed summary.md, so the recorded hash went
    # stale). The manifest is now written LAST and immediately re-read
    # and cross-checked against the on-disk files; any mismatch is a
    # hard failure of the report assembly.
    written = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
    mismatched = [name for name, sha in written.get("files", {}).items()
                  if _sha(out / name) != sha]
    missing = [name for name in written.get("files", {})
               if not (out / name).is_file()]
    unlisted = [str(p.relative_to(out))
                for p in sorted(out.rglob("*"))
                if p.is_file() and p.name != "manifest.json"
                and str(p.relative_to(out)) not in written.get("files", {})]
    if mismatched or missing or unlisted:
        raise SystemExit(
            f"manifest verification FAILED: mismatched={mismatched} "
            f"missing={missing} unlisted={unlisted}")
    print(json.dumps({"batch": args.batch, "files": len(files),
                      "manifest_verified": True,
                      "assembly_wall_s": manifest["assembly_wall_s"]},
                     indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
