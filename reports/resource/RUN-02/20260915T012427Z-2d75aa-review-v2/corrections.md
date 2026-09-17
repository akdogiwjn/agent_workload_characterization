# Corrections from the original RUN-02 report

| 原说明 | 修正口径 | 证据 |
| --- | --- | --- |
| 本次没有 native Tool hook、true duration=0 | 本次 28 条工具记录均使用 native hook 起止边界；历史 receipt 估计不作 native duration | `mini_tool_events.jsonl`、raw manifest |
| Tool closed 可视为成功 | 28 closed 中保留 returncode；其中 1 个非零，closed 只表示事件闭合 | `mini_tool_events.jsonl`、`summary.json` |
| Agent 正常提交 | Agent 状态为 `LimitsExceeded`、`submitted=false`；candidate 来自工作树 diff 且通过 verifier | `metadata.json`、`mini_trajectory.json`、`candidate.patch` |
| 宿主 CPU/RSS 未采集或是退出精确值 | 宿主有 717 次快照、716 次可读；CPU 是可读区间增量；RSS last-readable 与 sampled-max 分开，退出末次为 process_exited | `host_process.jsonl` |
| 354904 bytes 未进入计账、未来再全树计账 | 本次 review 按实际全树核对 10 文件/647461 bytes；metadata 645154 是快照口径，差异不补造文件 | raw 全树、`metadata.json`、raw `manifest.json` |
| 容器 I/O 可用于正式比较 | formal I/O 保持 null；诊断计数仅作原始辅助值 | `samples.json`、原报告 |

本批只读生成，没有重新测量、没有修改 raw 或原报告，也没有添加独占 Tool CPU 或性能因果结论。
