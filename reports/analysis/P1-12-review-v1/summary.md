# P1-12 review-v1 (offline acceptance & descriptive analysis)

Batch `P1-12-49bfc714`; 9/9 planned attempts executed; archive recheck ALL MATCH.

## Task results

| task | resolved T/F/N | wall med (s) | agent CPU med (core-s) | verifier CPU med (core-s) | tools med |
| --- | --- | --- | --- | --- | --- |
| astropy__astropy-13236 | 3/0/0 | 147.3 | 20.57 | 7.41 (n=3) | 45 |
| astropy__astropy-13398 | 0/2/1 | 168.5 | 22.58 | 5.12 (n=2) | 53 |
| django__django-16485 | 3/0/0 | 138.4 | 10.46 | 3.24 (n=3) | 35 |

## Focused questions

1. **270 requests**: budget counter = sum of closed llm_request events = 270 (ok 261, errored 9); every attempt hit its 30 cap; success/retry split unknown; tool steps counted separately.
2. **astropy-13398 no_candidate**: 1 attempt(s) ended without a candidate patch; verifier never started (evaluation not_run, no verifier scope); NOT an evaluation failure; the other two attempts were evaluated and resolved false.
3. **Credentials**: in-memory only through the registered chain; no credential material found in the nine archived raw dirs; no absolute persistence guarantee claimed beyond this evidence.

## Allowed conclusions

- descriptive run-to-run variation within each fixed task under the registered configuration
- task-level resolved counts (3/3, 3/3, 0-of-3 with one not-evaluated) for exactly these three tasks
- NOT cross-task causal claims, NOT Coding-category representativeness, NOT per-tool CPU, NOT wait-time inference

Costs: unknown (user accepted no hard cap; not a bill).
CPU-02 and Replay remain paused; G2 not claimed.
