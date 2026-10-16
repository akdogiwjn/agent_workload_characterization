# v2 → v3 corrections

## Problem 1: Test classification treated keywords as execution evidence
- v2 `_TEST_EVIDENCE` searched the full part text for pytest/unittest/tox keywords.
- `grep pytest README.md`, `echo pytest`, and `python -c 'print("pytest")'` were all misclassified as Test.
- v3: `_TEST_INVOCATION` matches only when a test runner is the command HEAD (pytest/python -m pytest/python -m unittest/tox/python tests/runtests.py).
- Keyword occurrences in arguments or script bodies no longer trigger Test.

## Problem 2: identity gate lacked open/event_id/t_start validation
- v2 accepted: missing open, duplicate open, mismatched event_id, mismatched t_start_ns between open and terminal.
- v2 hash/length checks were conditional ("if field present"); missing fields could bypass.
- v3: all checks mandatory — exactly one open + one terminal, event_id present and equal on both, t_start_ns equal on both, command_view sha256+length required and matching, timestamps are valid non-bool integers with end >= start.

## Problem 3: hardcoded CPU-call relationship
- v2 summary.md stated: 'The run with highest CPU also has the most Interpreter/Execute calls.'
- Actual astropy-13398 data: mid-CPU run had 1, high-CPU run had 2, low-CPU run had 2 — the high and low CPU runs had the SAME count.
- v3: this observation is withdrawn; per-run comparison table is computed from data with ties explicitly reported.

## Preserved from v2
- Shell-aware splitting, memory independent of CPU, observation window naming.
- 348/348 calls passed identity association (v3 re-verified with stricter gates).
- Django higher kernel-peak memory; request/tool sequential ordering.
