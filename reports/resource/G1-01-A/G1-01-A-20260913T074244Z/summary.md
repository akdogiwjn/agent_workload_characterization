# G1-01-A summary (G1-01-A-20260913T074244Z)

Generated: 2026-09-13T07:42:47.111566+00:00 (offline; sealed
inputs read-only; no containers, no model, no network).

## A1 historical tool timeline (RUN-01-C, read-only)

- tool calls: **26/26** identity-paired
  (tool_call_id + positional pairing (assistant actions <-> following tool messages)); missing results:
  0
- epoch->monotonic calibration: 26 anchors, residual max
  **0.00 ms**
- TRUE tool duration coverage: **0/26**
  (reason: no native tool start/end in the historical run)
- estimated/bound window coverage:
  26/
  26
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
