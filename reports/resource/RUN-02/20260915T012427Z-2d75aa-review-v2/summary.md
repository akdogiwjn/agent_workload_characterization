# RUN-02-R2 review-v2

这是对已封存 `20260915T012427Z-2d75aa` 的只读派生修正，不是新运行。
本报告 supersedes 原报告中受 RUN-01 模板影响的解释，不覆盖原件。

- pipeline：execution/evaluation/archive/cleanup `ok`，report `complete`，`resolved=true`
- Agent：`LimitsExceeded`，`submitted=false`；candidate 来自容器工作树 `git diff`，不能解释为主动提交完成
- 模型请求：30（27 成功、3 失败）；steps=26；这些计数不等价
- 工具：28 次，native hook 28 open/28 closed/0 error，其中 1 次 returncode 非零；closed 不等于成功
- 时间：工具 duration 取 `mini_tool_events.jsonl` 原生起止边界；不使用历史 receipt 估计替代，也不伪造 RUN-01 风格的零 native duration
- 宿主：717 次快照、716 次可读；CPU 4.19 s 是首末可读区间增量；RSS last-readable 与 sampled-max 分开
- 容器：Agent 51.007123 core-s、143.651636264 s；Verifier 3.64963 core-s、12.264456124 s；正式 I/O 为 null
- 归档：实际 raw 全树 10 文件、647461 bytes；metadata 快照 645154 bytes 作为不同口径保留，不能再写成“未来才覆盖全树”

Tool 与资源仍是 shared-scope，不提供独占 Tool CPU；不做 RUN-01/RUN-02 性能因果比较。
