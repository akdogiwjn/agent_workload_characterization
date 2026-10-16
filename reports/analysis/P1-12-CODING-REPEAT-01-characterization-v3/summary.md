# CODING-REPEAT-01 characterization v2

9 runs, 3 tasks × 3 repeats; collection `P1-12-CODING-REPEAT-01`.
Unselected raw dirs excluded: none.

## Identity association

| run | traj calls | valid linked | rejected | hash mismatch | dup IDs |
| --- | --- | --- | --- | --- | --- |
| bc1dca | 47 | 47 | 0 | 0 | 0 |
| 11bacd | 51 | 51 | 0 | 0 | 0 |
| ad0290 | 25 | 25 | 0 | 0 | 0 |
| d87dd3 | 34 | 34 | 0 | 0 | 0 |
| 004fd1 | 43 | 43 | 0 | 0 | 0 |
| 03d61c | 25 | 25 | 0 | 0 | 0 |
| 2bbb44 | 31 | 31 | 0 | 0 | 0 |
| 8adc15 | 48 | 48 | 0 | 0 | 0 |
| 441807 | 44 | 44 | 0 | 0 | 0 |
| **total** | **348** | **348** | **0** | **0** | **0** |

## Tool classification (per run)

Labels are FORM classifications (what the command text looks like), not verified purposes.
Python without pytest evidence = Interpreter/Execute.

| run | Read/Search | Interpreter/Exec | Test | Git-action | File-write | Submit-marker | Mixed | Partial | Unknown |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| bc1dca | 27 | 3 | 0 | 0 | 2 | 0 | 13 | 2 | 0 |
| 11bacd | 22 | 1 | 0 | 0 | 3 | 0 | 23 | 2 | 0 |
| ad0290 | 11 | 4 | 4 | 0 | 0 | 1 | 4 | 1 | 0 |
| d87dd3 | 18 | 2 | 0 | 0 | 0 | 0 | 12 | 2 | 0 |
| 004fd1 | 24 | 2 | 1 | 0 | 1 | 1 | 11 | 3 | 0 |
| 03d61c | 14 | 5 | 0 | 0 | 0 | 1 | 4 | 1 | 0 |
| 2bbb44 | 11 | 7 | 3 | 0 | 0 | 1 | 6 | 3 | 0 |
| 8adc15 | 39 | 2 | 1 | 0 | 0 | 0 | 2 | 4 | 0 |
| 441807 | 27 | 6 | 3 | 0 | 0 | 1 | 3 | 4 | 0 |

## Time structure (per run, seconds)

Observation window = first request/tool start to last end. NOT the attempt wall or agent scope wall.

| run | attempt wall | agent scope wall | obs window | only-req | only-tool | overlap | uncovered |
| --- | --- | --- | --- | --- | --- | --- | --- |
| bc1dca | 128.1 | 111.4 | 107.7 | 59.2 | 48.5 | 0.0 | 0.1 |
| 11bacd | 149.7 | 137.5 | 133.5 | 91.4 | 42.0 | 0.0 | 0.1 |
| ad0290 | 99.8 | 88.4 | 84.8 | 61.1 | 23.6 | 0.0 | 0.1 |
| d87dd3 | 176.5 | 162.7 | 158.8 | 71.8 | 86.9 | 0.0 | 0.1 |
| 004fd1 | 128.2 | 111.0 | 107.0 | 86.9 | 20.0 | 0.0 | 0.1 |
| 03d61c | 83.1 | 71.6 | 67.9 | 48.2 | 19.7 | 0.0 | 0.1 |
| 2bbb44 | 106.7 | 95.0 | 91.2 | 71.4 | 19.8 | 0.0 | 0.1 |
| 8adc15 | 93.9 | 81.8 | 78.3 | 63.5 | 14.7 | 0.0 | 0.1 |
| 441807 | 111.8 | 96.3 | 92.8 | 71.0 | 21.7 | 0.0 | 0.1 |

## Per-task aggregate (medians over n=3)

| task | attempt wall | agent scope wall | obs window | agent CPU | mem kernel peak (MiB) |
| --- | --- | --- | --- | --- | --- |
| astropy__astropy-13236 | 128.1 | 111.0 | 107.0 | 25.10 | 113.3 |
| astropy__astropy-13398 | 149.7 | 137.5 | 133.5 | 34.50 | 140.8 |
| django__django-16485 | 99.8 | 88.4 | 84.8 | 39.42 | 1341.0 |

## Key observations (descriptive)

- Request and tool call intervals appear largely sequential in this batch's records (overlap ≈ 0). This is a description of recorded interval ordering; it does not prove single-threadedness, absence of background processes, or tool-internal concurrency.
- Django runs show higher kernel-peak memory (~1.3 GiB) than astropy runs (~0.1-0.4 GiB). High memory.current sampling points co-occur with various activity categories; co-occurrence is not causation.
- Per-run CPU and call composition (computed from data):

| run | task | CPU (core-s) | Interp/Exec | Test | tool union (s) | term | resolved |
| --- | --- | --- | --- | --- | --- | --- | --- |
| bc1dca | astropy__astropy-13236 | 43.778057 | 3 | 0 | 48.5 | LimitsExceeded | True |
| 11bacd | astropy__astropy-13398 | 34.501083 | 1 | 0 | 42.0 | LimitsExceeded | False |
| ad0290 | django__django-16485 | 52.468421 | 4 | 4 | 23.6 | Submitted | True |
| d87dd3 | astropy__astropy-13398 | 90.562382 | 2 | 0 | 86.9 | LimitsExceeded | True |
| 004fd1 | astropy__astropy-13236 | 22.899077 | 2 | 1 | 20.0 | Submitted | True |
| 03d61c | django__django-16485 | 39.423826 | 5 | 0 | 19.7 | Submitted | True |
| 2bbb44 | django__django-16485 | 32.691907 | 7 | 3 | 19.8 | Submitted | True |
| 8adc15 | astropy__astropy-13398 | 14.783254 | 2 | 1 | 14.7 | LimitsExceeded | False |
| 441807 | astropy__astropy-13236 | 25.097775 | 6 | 3 | 21.7 | Submitted | True |
- astropy__astropy-13236: highest CPU run (43.78 core-s) has 3 Interpreter/Execute calls; lowest CPU run (22.90 core-s) has 2.
- astropy__astropy-13398: highest CPU run (90.56 core-s) has 2 Interpreter/Execute calls; lowest CPU run (14.78 core-s) has 2.
  The highest and lowest CPU runs have the SAME Interpreter/Execute count (2); call count alone does not explain the CPU difference in this batch.
- django__django-16485: highest CPU run (52.47 core-s) has 4 Interpreter/Execute calls; lowest CPU run (32.69 core-s) has 7.

## Limits

- three repeats per task are raw points, not independent tasks
- shared-container CPU/memory; no exclusive per-tool attribution
- request intervals are client-observed, not server inference time
- uncovered window time is not thinking/waiting time
- python invocations without pytest evidence are Interpreter/Execute, not Test
- label assignment rate is not purpose identification accuracy
- sequential interval co-occurrence does not prove single-threadedness
- model usage is not a bill; cost unknown

CPU-02 and Replay remain paused. No G2 or architecture claim.
