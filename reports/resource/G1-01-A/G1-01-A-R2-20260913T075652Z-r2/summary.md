# G1-01-A 返修轮 summary (G1-01-A-R2-20260913T075652Z-r2)

Generated: 1 offline; sealed inputs read-only; no containers, no
model, no network. Supersedes G1-01-A-20260913T074244Z (preserved, not
overwritten). Review fixes: pairing ID cross-check + anchor count consistency,
host evidence fully persisted, mechanism deadlines + same-interval CPU
comparison + report writer path guard, restored wall-kill regression +
sampler stop-loop coverage.

## A1 (sealed RUN-01-C, read-only)

- tool calls: 26/26 identity-paired WITH ID cross-check
  (n_id_mismatch=0, n_duplicate_action_id=0)
- anchor streams: 26 ok status lines vs 26 assistant-with-actions,
  counts_match=true; 26 anchors; residual max 3.84 ms
  (semantics: observed anchor spread, NOT a proven calibration error bound)
- true duration coverage 0/26 (reason recorded); estimated windows 26/26
- container association shared_scope only; no per-tool exclusive CPU

## A2 tool-event hook (future runs)

Real installed mini + fake transport/executor, 5-test integration suite
(19.4 s): 3 open / 2 closed / 1 error (Submitted interrupt kept as error);
failing returncode recorded; no raw command/output; format-error branch
writes no tool events; wall-kill regression RESTORED (unconditional
request+tool-entry assertions).

## A3 host observation

host_process.jsonl is now a STRUCTURED document: identity (pid +
starttime_ticks + reuse semantics), units (clk_tck, page_size, tick/rss
semantics), coverage interval (first/last monotonic, n_snapshots,
final_read_status), per-snapshot records, and the full summary. Write
failure records host_archive_status + infra event (never silent).
Historical gap not back-filled.

## A4 mechanism checks (this batch's ACTUAL values)

- C1 dual-source CPU (same interval = child whole lifetime): self-report
  0.3497 s vs /proc 0.3500 s,
  diff 0.0003 s < 0.02 s poll granularity (tolerance
  declared before execution); deadline_exceeded=False
- C2 dual overlapping workers: span 0.293749 s;
  w1 CPU 0.2400 + w2 0.2700 =
  sum 0.5100 s > span (overlap as expected);
  deadline_exceeded=False
- O1-O3 overhead pairs (raw, no percentage claim):
  - O1: off 0.362049 s, on 0.363523 s, diff +1 ms, collector reads 36 @ 0.038 ms mean
  - O2: off 0.362041 s, on 0.353242 s, diff -9 ms, collector reads 35 @ 0.034 ms mean
  - O3: off 0.362029 s, on 0.353241 s, diff -9 ms, collector reads 35 @ 0.035 ms mean
- batch wall 2.828 s (limit 120 s); all deadlines enforced
  in-loop (kill + keep evidence), batch checked before each case
  (stopped_batch marker on breach)

## Fixes applied this round

- pair_tools: ID cross-check (id_mismatch/duplicate_action_id), orphaned
  results tracked; anchor_consistency() reports stream count mismatches
  (shorter prefix flagged, never silently absorbed)
- calibrate(): residual semantics renamed honest ("observed max spread,
  NOT a proven calibration error bound"); downstream field renamed
  anchor_residual_ns_max
- host evidence: structured persistence with identity/units/coverage/
  summary; write failure recorded (host_archive_status + infra event)
- mechanism script: hard per-case and per-pair deadlines checked inside
  the wait loops (kill + deadline_exceeded kept); batch deadline checked
  BEFORE each case; C1 comparison interval stated (both sources span the
  child's whole lifetime)
- report writer: batch id validated (no absolute/.. / separators /
  symlink escape); existing outputs refused (exclusive create)
- restored test_budget_kill_preserves_evidence as an independent method
  (it had been accidentally merged into the preceding test); integration
  suite is 5 tests again (3 original + 2 new)
- sampler: real background-thread stop coverage (reader count and sample
  count frozen after stop_background_sampling)
