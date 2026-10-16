# CODING-REPEAT-01 offline resource analysis

限定范围验收：9 个由 batch/summary.json 显式登记的真实 run，输入 manifest 全部匹配；不含旧 P1-12、FINISH-01/02。

## Per-task descriptive resources

| task | resolved T/F/unknown | attempt wall median (s) | agent CPU median (core-s) | agent kernel peak median (MiB) | verifier CPU median (core-s) | requests median | tools median |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| astropy__astropy-13236 | 3/0/0 | 128.1 | 25.10 | 113.3 | 7.59 | 29 | 44 |
| astropy__astropy-13398 | 1/2/0 | 149.7 | 34.50 | 140.8 | 4.55 | 30 | 48 |
| django__django-16485 | 3/0/0 | 99.8 | 39.42 | 1341.0 | 3.55 | 20 | 25 |

CPU is cgroup counter-boundary core-seconds; agent and verifier are separate scopes. Memory kernel peak is not sampled maximum or process RSS.

## Observations

- The fixed-task repeats show descriptive spread in wall, CPU, memory, request counts and tool counts; the three points are not independent tasks.
- Astropy-13398 的三次 Agent 终止均为 `LimitsExceeded`；其中 `resolved=true` 1 次、`resolved=false` 2 次。任务结果与 Agent 终止类型是两个独立维度。
- 三任务中按绝对 IQR，Astropy-13398 的波动最大：attempt wall IQR **41.28 s**（原始点 93.95/162.69/176.51 s）、Agent CPU IQR **37.89 core-s**（14.78/34.50/90.56），内核峰值内存 IQR **136.1 MiB**（126.0/140.8/385.7 MiB，显示值为 MiB）。这只是三个登记重复的描述，不是显著性或因果结论。
- `Submitted` 是正常 Agent 终止信号；`LimitsExceeded` 是预算限制结果，不是工具故障。
- Tool counts are counts, not rates. The archived evidence has no denominator that supports a frequency ranking.
- Host observations are reported separately and do not establish container-wide or Agent-wide waiting time; wall minus CPU is not used.

## Limits

No causal explanation, stable population claim, per-tool CPU, bill, or Coding-category representativeness is supported. Stored requests show no network failure; this does not prove network conditions were constant.
CPU-02 and Replay remain paused; this report does not change G2 or project-wide status.
