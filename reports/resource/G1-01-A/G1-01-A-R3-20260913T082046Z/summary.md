# G1-01-A R3 summary (G1-01-A-R3-20260913T082046Z)

Supersedes G1-01-A-R2 (preserved). Third-round review fixes: C1
re-declared as a DIAGNOSTIC cross-check of DIFFERENT windows (child
self-report spans its whole lifetime incl. interpreter startup; /proc
delta spans first-to-last readable snapshot — agreement bounds window
skew + noise, it is NOT a same-interval verification); single-scope
stop now freezes that scope in the running sampling loop (other active
scopes keep sampling; regression with the thread left running);
anchor-stream count mismatch now DISABLES calibration and all derived
monotonic windows (mid-stream gap regression covered).

## A4 actual values (this batch)

- C1: self 0.3462 s vs /proc 0.3500 s, diff 0.0038 s (diagnostic cross-check)
- C2: span 0.2637 s; w1 0.2300 + w2 0.2400 = 0.4700 s
- O1: off 0.362 s, on 0.394 s, diff +32 ms
- O2: off 0.362 s, on 0.414 s, diff +52 ms
- O3: off 0.362 s, on 0.384 s, diff +22 ms
- batch wall 2.92 s; sealed RUN-01-C: 26/26 anchors, residual 3.84 ms, gate enabled
- tests: 418 default (project + external cwd), mini integration 5, swebench 5
