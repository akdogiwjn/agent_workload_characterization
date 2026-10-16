# CODING-REPEAT-01 characterization

9 runs, 3 tasks × 3 repeats; collection `P1-12-CODING-REPEAT-01`.
Unselected raw dirs excluded: none.

## Method mapping (AgentCgroup reference → this project)

| Reference | Original | Adopted | Why / limits |
| --- | --- | --- | --- |
| tool_timing.py: merge_intervals, union_duration_seconds | merge overlapping datetime intervals; sum union duration | same algorithm with integer monotonic-ns intervals | only intervals with valid start/end; Submitted terminal events included |
| tool_timing.py: attribute_union_seconds | split union time among overlapping categories evenly | NOT adopted | even splitting would imply exclusive attribution unsupported by shared-container sampling |
| compute_active_time.py: compute_active_time_from_trace | active_time = last trace timestamp - first trace timestamp | adapted as the agent observation window (first request/tool start to last end); NOT called active time | uncovered time within the window is NOT thinking/waiting time; it is simply not covered by request or tool intervals |
| analyze_tool_time_ratio.py: categorize_bash_command | regex-based bash categorization (Test/Git/Package/File/Python/Text/Shell/Other) | adapted: frozen rules for the actual command corpus; compound commands classified Mixed when parts differ; navigation (cd) stripped | static text only; does not prove actual subprocess behavior or side effects |
| analyze_extended_insights.py: analyze_transient_bursts | peak/avg overprovisioning factor; spike duration at 80% of peak (1 sample = 1 s) | NOT adopted as-is; only peak-to-median memory ratio reported descriptively | no threshold claimed as validated; actual timestamps used, not sample-count-as-seconds |
| analyze_tool_time_ratio.py: thinking_time = exec_time - tool_time | subtraction to get thinking time | PROHIBITED by task; uncovered time is reported as uncovered only | explicitly banned |

Reference commit: 551ca16 (local git log)

## Per-run overview

| run | task | term | resolved | tools | reqs | tool union (s) | req union (s) | overlap (s) | uncovered (s) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| bc1dca | astropy__astropy-13236 | LimitsExceeded | True | 47 | 30 | 48.5 | 59.2 | 0.0 | 0.1 |
| 11bacd | astropy__astropy-13398 | LimitsExceeded | False | 51 | 30 | 42.0 | 91.4 | 0.0 | 0.1 |
| ad0290 | django__django-16485 | Submitted | True | 25 | 22 | 23.6 | 61.1 | 0.0 | 0.1 |
| d87dd3 | astropy__astropy-13398 | LimitsExceeded | True | 34 | 30 | 86.9 | 71.8 | 0.0 | 0.1 |
| 004fd1 | astropy__astropy-13236 | Submitted | True | 43 | 20 | 20.0 | 86.9 | 0.0 | 0.1 |
| 03d61c | django__django-16485 | Submitted | True | 25 | 15 | 19.7 | 48.2 | 0.0 | 0.1 |
| 2bbb44 | django__django-16485 | Submitted | True | 31 | 20 | 19.8 | 71.4 | 0.0 | 0.1 |
| 8adc15 | astropy__astropy-13398 | LimitsExceeded | False | 48 | 30 | 14.7 | 63.5 | 0.0 | 0.1 |
| 441807 | astropy__astropy-13236 | Submitted | True | 44 | 29 | 21.7 | 71.0 | 0.0 | 0.1 |

## Tool composition (per run)

| run | Read/Search | Edit | Test/Exec | Git/Patch | Submit | Mixed | Other | Unknown | coverage |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| bc1dca | 33 | 1 | 5 | 0 | 0 | 7 | 0 | 1 | 98% |
| 11bacd | 31 | 1 | 5 | 0 | 0 | 13 | 0 | 1 | 98% |
| ad0290 | 11 | 0 | 6 | 0 | 1 | 7 | 0 | 0 | 100% |
| d87dd3 | 24 | 0 | 6 | 0 | 0 | 4 | 0 | 0 | 100% |
| 004fd1 | 30 | 0 | 6 | 1 | 1 | 5 | 0 | 0 | 100% |
| 03d61c | 14 | 0 | 7 | 1 | 1 | 2 | 0 | 0 | 100% |
| 2bbb44 | 15 | 0 | 12 | 1 | 1 | 2 | 0 | 0 | 100% |
| 8adc15 | 40 | 0 | 2 | 0 | 0 | 5 | 0 | 1 | 98% |
| 441807 | 29 | 0 | 8 | 0 | 1 | 6 | 0 | 0 | 100% |

## Time structure (per run, seconds)

Window = first request/tool start to last end. Decomposition is mutually exclusive and conserves the window.

| run | window | only-request | only-tool | overlap | uncovered | residual |
| --- | --- | --- | --- | --- | --- | --- |
| bc1dca | 107.7 | 59.2 | 48.5 | 0.0 | 0.1 | 0.000000 |
| 11bacd | 133.5 | 91.4 | 42.0 | 0.0 | 0.1 | 0.000000 |
| ad0290 | 84.8 | 61.1 | 23.6 | 0.0 | 0.1 | 0.000000 |
| d87dd3 | 158.8 | 71.8 | 86.9 | 0.0 | 0.1 | 0.000000 |
| 004fd1 | 107.0 | 86.9 | 20.0 | 0.0 | 0.1 | 0.000000 |
| 03d61c | 67.9 | 48.2 | 19.7 | 0.0 | 0.1 | 0.000000 |
| 2bbb44 | 91.2 | 71.4 | 19.8 | 0.0 | 0.1 | 0.000000 |
| 8adc15 | 78.3 | 63.5 | 14.7 | 0.0 | 0.1 | 0.000000 |
| 441807 | 92.8 | 71.0 | 21.7 | 0.0 | 0.1 | 0.000000 |

## Per-task aggregate (medians over n=3)

| task | wall (s) | agent CPU (core-s) | mem kernel peak (MiB) | tool union (s) | req union (s) |
| --- | --- | --- | --- | --- | --- |
| astropy__astropy-13236 | 128.1 | 25.10 | 113.3 | 21.7 | 71.0 |
| astropy__astropy-13398 | 149.7 | 34.50 | 140.8 | 42.0 | 71.8 |
| django__django-16485 | 99.8 | 39.42 | 1341.0 | 19.8 | 61.1 |

## Key observations (descriptive, n=3 per task)

- **Django memory**: kernel peak across the three runs: ad0290=1385.4 MiB, 03d61c=1341.0 MiB, 2bbb44=1330.8 MiB.
- **Astropy-13398 CPU contrast** (three runs):
  - 11bacd: resolved=False, term=LimitsExceeded, tools=51 (Read/Search=31, Test=5, Git/Patch=0), CPU=34.501083, wall=137.49537943
  - d87dd3: resolved=True, term=LimitsExceeded, tools=34 (Read/Search=24, Test=6, Git/Patch=0), CPU=90.562382, wall=162.688540457
  - 8adc15: resolved=False, term=LimitsExceeded, tools=48 (Read/Search=40, Test=2, Git/Patch=0), CPU=14.783254, wall=81.77025921
- **Request/tool alternation**: every run shows sequential request-then-tool patterns; overlap between request intervals and tool intervals is small (see per-run table), consistent with a single-threaded agent loop. This is a description of interval co-occurrence, not a concurrency claim.

## Corrections to the previous review (P1-12-CODING-REPEAT-01-review-v1)

- Astropy-13398 wall raw point middle value: the old summary.md states 162.69 s; the actual value from metadata.json budget_usage.elapsed_total_s is 149.73 s (median). The old report's number was hardcoded and incorrect.
- Memory IQR 136136704 bytes = 129.83 MiB, not 136.1 MiB as stated in the old report. Unit conversion error.
- All numbers in this report are computed from input files at run time; no conclusion values are hardcoded.

## Limits

- three repeats per task are raw points, not independent tasks
- container CPU/memory are shared-scope evidence; no exclusive per-tool attribution
- request intervals are client-observed, not server inference time
- uncovered window time is not thinking/waiting time
- static command classification does not prove actual subprocess behavior
- model usage is not a bill; cost unknown
- no causal or frequency-ranking claims

CPU-02 and Replay remain paused. No G2 or architecture claim.
