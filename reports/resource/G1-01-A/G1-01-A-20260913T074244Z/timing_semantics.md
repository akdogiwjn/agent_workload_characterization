# Timing field semantics (verified against installed mini 2.4.6)

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
