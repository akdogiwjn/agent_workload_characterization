# P1-12 termination review-v1

Batch `P1-12-20260928T023250Z-33ffbd62`; 9 runs; read-only.

## Termination table

| run | task | closed | ok | err (FormatError) | mini exit | resolved |
| --- | --- | --- | --- | --- | --- | --- |
| 20d5ed | astropy__astropy-13236 | 30 | 30 | 0  | LimitsExceeded | True |
| 28a197 | astropy__astropy-13398 | 30 | 30 | 0  | LimitsExceeded | None |
| 743095 | django__django-16485 | 30 | 29 | 1 ['mini-30'] | LimitsExceeded | True |
| 201a12 | astropy__astropy-13398 | 30 | 30 | 0  | LimitsExceeded | False |
| 53761e | astropy__astropy-13236 | 30 | 30 | 0  | LimitsExceeded | True |
| eb2d90 | django__django-16485 | 30 | 25 | 5 ['mini-19', 'mini-21', 'mini-25', 'mini-28', 'mini-30'] | LimitsExceeded | True |
| 12c3df | django__django-16485 | 30 | 27 | 3 ['mini-24', 'mini-26', 'mini-29'] | LimitsExceeded | True |
| 5ed403 | astropy__astropy-13398 | 30 | 30 | 0  | LimitsExceeded | False |
| 1a3046 | astropy__astropy-13236 | 30 | 30 | 0  | LimitsExceeded | True |

## Why 30 requests everywhere

mini-SWE-agent's `step_limit` gates **n_calls (the model request count)**, mapped 1:1 from the frozen budget (`max_model_requests=30`, `mini_agent_adapter.py:326,402-404`). The limit trips when `n_calls >= 30` AFTER the 30th request, so **all 30 closed events per run are real, completed round-trips** (each carries its own child-side t_start/t_end and usage). No run reached a 31st attempt, so no event can be a pure local budget rejection; the counter position is **after completion** (status line written in `StatusTrackingAgent.query`, `mini_agent_adapter.py:546-583`).

## The 9 errored requests

All 9 are `ok=false` **with full usage and timing** — the `StatusTrackingAgent` FormatError path: the call was sent, billed and answered, but the reply failed mini's output-format parse. They are NOT budget rejections, NOT network failures. They occur only in the three django runs ({'-13236': [], '-13398': [], '-16485': ['mini-30', 'mini-19', 'mini-21', 'mini-25', 'mini-28', 'mini-30', 'mini-24', 'mini-26', 'mini-29']}); astropy runs have zero.

## Termination mechanism

9/9 runs ended with mini `exit_status=LimitsExceeded` — **every run was budget-truncated at the request cap, including the six resolved=true runs and the no_candidate run**. No run ended via the agent's protocol finish. Task resolution and termination are independent: the six resolved runs produced a valid patch before the cap; the no_candidate run (astropy-13398 r0) produced none.

## Corrections to review-v1

- review-v1 said 'every attempt hit its 30-request cap' — CONFIRMED and now evidenced at the mechanism level: mini exit_status=LimitsExceeded on 9/9 runs (step_limit=30 trips after the 30th request). No correction needed, but the stronger evidence is recorded here.

## Step vs request counting

mini has no separate step counter: `step_limit` gates n_calls. The runner's `max_steps=30` (BudgetTracker) counts completed steps (`n_steps=29` on runs whose 30th request hit FormatError — the step aborts before incrementing). The two budgets coexist; the request cap is the binding one.

## Next-step recommendation: **C** (budget truncation confirmed)

The 30-request cap truncated all nine runs; whether a higher cap changes outcomes is unknown. If the study question needs completed-agent behavior, the minimal next batch is a pre-registered uniform budget comparison (e.g. one task x higher request cap x same seeds) — a NEW user approval; this review does not change any budget or code.

Costs remain unknown; no network/model/Docker was accessed; historical files unchanged.
