# v1 → v2 corrections

## Classification
- v1 split on `&&`/`;` without quote awareness → v2 uses shlex-based top-level splitting; quoted semicolons inside python `-c` strings are no longer split points.
- v1 put all `python` invocations into Test/Execute → v2 separates: `Test` only with pytest/unittest/runtests evidence; other python = `Interpreter/Execute`.
- v1 counted Mixed-with-Unknown as classified (≥98% coverage) → v2 separates `form-identified`, `partial` (has unknown parts), and `unknown`.
- v1's 'Test/Exec' table header abbreviated to 'Test', inflating test-count evidence → v2 uses full form labels.
- v1's 'high CPU run has 6 tests, low CPU run has 2 tests' observation relied on the v1 classification → v2 recasts as Interpreter/Execute count difference (descriptive).

## Identity association
- v1 used dict overwriting for duplicate tool_call_ids → v2 detects and rejects duplicates.
- v1 did not validate command hash/length → v2 recomputes SHA-256 and length, rejects mismatches.
- v1 took the last terminal event on ambiguity → v2 rejects multi-terminal records.

## Time structure
- v1 called the observation window just 'window' → v2 names it `observation_window_s` and separately reports `attempt_wall_s` and `agent_scope_wall_s`.
- v1 inferred 'single-threaded agent loop' from overlap≈0 → v2 states only 'largely sequential in this batch's records' with explicit non-claims.
- v1's 'uncovered <0.2s' implied minimal unobserved overhead → v2 notes this is within the observation window only, not the full attempt.

## Resources
- v1 built the memory trajectory inside the CPU differencing loop → v2 extracts memory points independently of CPU validity.
- v1 reported peak-to-median ratio (from method mapping) without computing it → v2 removes the claim; only per-task kernel-peak stats are reported.

## v1 numeric errors (retained for reference)
- Astropy-13398 wall raw point middle value: v1 summary.md stated 162.69 s; actual metadata value is 149.73 s (hardcoded error in v1).
- Memory IQR 136136704 bytes = 129.83 MiB, not 136.1 MiB (unit conversion error in v1).

## Preserved conclusions
- Request/tool sequential ordering (now with weaker wording).
- Django higher kernel-peak memory than astropy (unchanged).
- Submitted is a normal terminal; LimitsExceeded is a budget stop (unchanged).
- All numbers in v2 are computed from input at run time; no hardcoded conclusions.
