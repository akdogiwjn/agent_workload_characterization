# G1-01-A R4 summary (G1-01-A-R4-20260913T085846Z)

Supersedes R3 (preserved). Fourth-round closeout (no containers, no
model, no network; sealed inputs read-only):

1. **stop() race closed**: stop() now acquires the scope's read gate
   and WAITS for any in-flight sampling read before taking the final
   boundary. Deterministic regression: a gated reader holds a read in
   flight; stop() provably blocks (checked at 150 ms), completes only
   after the read is released, and the final boundary comes from the
   last-read generation. Cross-scope variant: stopping scope A while
   scope B's read is in flight neither blocks nor freezes B.
2. **C1 wording corrected** (no re-run needed): the child self-report
   is a CODE-SEGMENT CPU increment (module entry -> loop end; excludes
   interpreter startup and exit-time work); the /proc delta is
   first-to-last readable snapshot. The windows overlap but neither
   contains the other; the difference does NOT bound any window's
   skew. All "whole lifetime"/"same interval"/"bounds skew" wording
   removed from the script.
3. **Manifest integrity**: root cause of R3's stale summary.md hash
   found — the manifest dict never carried the files map. The writer
   now (a) always includes files, (b) post-write re-reads and
   cross-checks every hash (hard failure on mismatch/missing/
   unlisted). The first batch's container_validation_approval.md
   (lost to a replace() move during R3 assembly) was restored verbatim
   from the R2 copy after SHA-256 verification against the first
   batch's manifest (5ceee00cefcae855...).

## A4 actual values (this batch)

- C1 (diagnostic cross-check, different windows): self
  0.3514 s vs /proc 0.3500 s,
  diff 0.0014 s — raw data, no verification claim
- C2: span 0.2635 s; w1 0.2400 +
  w2 0.2500 = 0.4900 s
- O1: off 0.372 s, on 0.374 s, diff +2 ms
- O2: off 0.372 s, on 0.363 s, diff -9 ms
- O3: off 0.373 s, on 0.363 s, diff -9 ms
- batch wall 2.86 s; sealed RUN-01-C: 26/26 anchors, gate enabled
- tests: 420 default (project + external cwd), mini integration 5, swebench 5
