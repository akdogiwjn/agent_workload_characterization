# PILOT-03 post-run 离线分析说明

正式入口在已完成 Agent、verifier、容器清理、run-record 与 manifest 后，于报告函数因递归调用抛出 `RecursionError`，入口 shell returncode 为 1。raw 的 86 项文件清单、bytes 和 SHA-256 已独立核验；不修改 frozen source 或 raw。本目录中的 summary、CSV 和曲线根据已保存证据生成，未重跑任务、API 或 verifier。

本次提交物与官方评分：judge 完整执行（RC 0），reward 0；输出规格与可解析性通过，cut_ranges 检查未通过。HTTP 传输次数和费用 unknown。
