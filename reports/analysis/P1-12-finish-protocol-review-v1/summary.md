# P1-12 finish-protocol review-v1

Read-only. Batch `P1-12-20260928T023250Z-33ffbd62`.

## The protocol chain (as frozen in this batch)

1. **Prompt evidence**: every run's FIRST user message contains the exact submit instruction — `Step 3: Submit (EXACT command required) You MUST use this EXACT command to submit: ```bash echo COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT && cat patch.txt``` (verified in trajectory messages[1] of all nine runs; mini.yaml:18,41,147 of the pinned venv). This is **actual-sent-record evidence** (the trajectory stores the exact messages sent to the model), not just a template.
2. **Expected end action**: echo the marker as the FIRST output line with returncode 0; mini's native `DockerEnvironment._check_finished` (minisweagent/environments/docker.py:140-149) then raises `Submitted`, the run loop appends an exit message and breaks with `exit_status='Submitted'`.
3. **THE DEFECT**: this batch used the project's `AttachedDockerEnvironment` (`src/agent_workload_characterization/runners/mini_agent_adapter.py:441-482`). Its `execute()` (line 462-477) **never calls `_check_finished`**, and its `_check_finished` (line 479-482) checks only `exception_info` — **the marker→Submitted check is missing entirely**. (The offline `FakeScriptedEnvironment`, line 520-528, DOES have the check, which is why offline tests never caught it.)
4. **No swallowing of a working signal**: the signal never fired in production; there is no error-rewriting path to blame — the recognition step is simply absent.

## Submit events in the nine runs

| run | task | resolved | submits | after 1st submit | exit |
| --- | --- | --- | --- | --- | --- |
| 20d5ed | astropy__astropy-13236 | True | 0 | - | LimitsExceeded |
| 28a197 | astropy__astropy-13398 | None | 0 | - | LimitsExceeded |
| 743095 | django__django-16485 | True | 1 | 0 | LimitsExceeded |
| 201a12 | astropy__astropy-13398 | False | 0 | - | LimitsExceeded |
| 53761e | astropy__astropy-13236 | True | 0 | - | LimitsExceeded |
| eb2d90 | django__django-16485 | True | 2 | 7 | LimitsExceeded |
| 12c3df | django__django-16485 | True | 1 | 4 | LimitsExceeded |
| 5ed403 | astropy__astropy-13398 | False | 0 | - | LimitsExceeded |
| 1a3046 | astropy__astropy-13236 | True | 0 | - | LimitsExceeded |

## The six resolved runs

| run | last command (sanitized head) | classification |
| --- | --- | --- |
| 20d5ed | cd /testbed && git show 5f1c8e68cf --stat | head -30 | never submitted — was still verifying/testing when the cap hit |
| 743095 | cd /testbed && echo COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT && cat patch | SUBMITTED but signal NOT recognized — kept running until the request cap |
| 53761e | cd /testbed && git diff --stat | never submitted — was still verifying/testing when the cap hit |
| eb2d90 | echo COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT && cat patch.txt | SUBMITTED but signal NOT recognized — kept running until the request cap |
| 12c3df | true | SUBMITTED but signal NOT recognized — kept running until the request cap |
| 1a3046 | cd /testbed && git stash && python -m pytest astropy/table/tests/test_ | never submitted — was still verifying/testing when the cap hit |

## Conclusion: **A — a definite wiring defect is present**

The prompt correctly instructs the finish action and the agent **executed it successfully** (returncode 0, marker as first output line) in `743095` (once, after the 30th request) and `eb2d90` (twice: after ~20 requests, then again later). The `AttachedDockerEnvironment` never recognizes the marker, so the runs continued and ended `LimitsExceeded`. The other four resolved runs and all three unresolved runs never issued the marker; whether they would have finished given more budget is **unknown** — budget truncation and the missing signal are independent facts, both true.

### Minimal fix (NOT implemented this round)

`src/agent_workload_characterization/runners/mini_agent_adapter.py`:
1. `AttachedDockerEnvironment._check_finished` (line 479): add the same first-line marker + returncode-0 check as mini's native `docker.py:140-149`, raising `Submitted`.
2. `AttachedDockerEnvironment.execute` (line 462): call `self._check_finished(output)` before returning.
3. Add an offline regression that drives the REAL `AttachedDockerEnvironment` (with a fake docker exec) through a submit command and asserts `Submitted` is raised.

This defect also explains part of the previous review's picture: 'budget truncation' was the *proximate* cause on every run, but on 2 of 6 resolved runs the *underlying* cause was an unrecognized submission. The termination-review's counts and LimitsExceeded finding stand unchanged.

### Correction to a previous-round wording

Termination-review-v1 said errors carry 'usage (billed)'. Usage presence proves a usage RECORD was returned; actual billing is **unknown** without invoice evidence. The FormatError classification (sent, answered, parse failed) is unchanged.

## Next step: fix the implementation, then re-baseline

The single recommended action is the minimal fix above (a new user approval to modify code + offline tests). A budget comparison before fixing the signal would conflate two variables; after the fix, a fresh batch would measure both protocol-completion rates and budget effects cleanly. No evidence gap remains for this review's questions.
