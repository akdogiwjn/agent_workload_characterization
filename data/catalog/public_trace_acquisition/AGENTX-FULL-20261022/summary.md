# AgentX v1.0 Full：获取与分析完成

上游：`semianalysisai/cc-traces-weka-062126`；固定revision `23f152f6f0f9399a85901b89a6458def0ef16729`。

- 原始JSONL完整获取：1,847,151,435 bytes；LFS SHA-256 `29b6a19e751ff5230771519aab755f80a0f43a4ba9cf96b72d3a6a437ec99276`核验通过。
- README/stats已获取并核对上游Git blob身份；license为数据卡声明Apache-2.0。未下载上游图片，分析自行生成分布图。
- 全393会话、98,827请求的离线统计完成；来源stats的7项全部与实际重算相符。旧256k输入另行重算，7项亦一致。
- 与256k的68,266请求全部逐payload匹配；Full独有30,561请求，恰好均超过input+output 256,000阈值。两版共有393会话，不合并为独立会话总数。
- 不含原始业务工具参数/返回；1697个group的tool_use_count全部为空。没有本地资源测量。
- 仅下载公开数据和离线分析；未执行Agent、模型、轨迹命令或benchmark。历史数据/报告保留。

[分析报告](../../../../reports/analysis/AGENTX-FULL-MACRO-v1/summary.md) · [获取manifest](manifest.json) · [复现命令](commands.md)
