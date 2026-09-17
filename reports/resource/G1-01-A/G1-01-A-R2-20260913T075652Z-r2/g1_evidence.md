# G1 逐项证据（G1-01-A 返修轮；不宣布 G1 通过）

对照 `docs/development_tasks.md` G1 六条。本批为 A 返修（离线分析+机制
验证，评审四组意见修复后）；B（无模型容器验证）继续待批。

| # | G1 标准 | 状态 | 证据与边界 |
| --- | --- | --- | --- |
| 1 | 目标 scope 的语义、process、资源可关联，独占/共享/未知明确 | **partial** | 语义：tool_timeline 26/26 身份（tool_call_id + 位置配对 **含 ID 交叉核对**——mismatch/duplicate/orphan 报告不静默接受；实测 0 异常）；锚点流数量一致性检查（26/26 ok 行 vs assistant 数，counts_match=true）；scope 关联：shared_scope/window（锚点残差 3.84 ms，语义=观测散布**非**校准误差上界）；host scope：A3 新增（身份/单位/覆盖区间/摘要完整落盘）；独占 per-tool CPU：明示 0/26。 |
| 2 | 短进程、后台作业、常驻服务、异常退出、时钟/采集延迟有测试 | **partial** | 短进程/PID 复用/reset/读取失败：fixtures（fake /proc，20 项）；后台超返回：fixtures；时钟：锚点校准+残差语义、跨域不相减、系统级 monotonic；采集延迟：collector 读耗时实测。机制脚本硬 deadline（等待循环内检查、超限 kill+留证、批前检查 stopped_batch）。常驻服务：B 提案含。 |
| 3 | CPU/I/O 计数核对、memory 口径、重叠/残差和遗漏报告通过评审 | **partial** | CPU 双源核对：C1（同区间=子进程整个生命周期，两源声明；差 9.2 ms < 20 ms 轮询粒度）；单位：CLK_TCK/页大小独立期望；重叠：C2 + 共享计数不复制；memory：三口径分离；I/O：正式 null+降级。**评审待做。** |
| 4 | 至少一种真实 Runner 小样与确定性测试闭环，原始日志和三类状态保留 | **evidenced** | RUN-01-C 真实 attempt（resolved=true，封存+supplement）；真实 mini 离线集成 **5 项**（原 3 项含 wall-kill 已恢复 + 新增 hook 边界/格式错误分支）；fixtures 20 项；默认 415 项无退步。 |
| 5 | Collector 开销已量化；正式比较前固定计量容差与降级边界 | **partial** | 开销：O1–O3 原始配对（本轮实际：−28/+42/−28 ms，噪声级；读耗时 ~0.044 ms×~38 读≈1.7 ms/运行；无百分比声明）；容差：C1 声明式；B 后评审固定正式容差。 |
| 6 | 可找出 CPU/Wall/Memory 的候选 scope；精确 Tool 归因并非必需 | **partial** | 候选 scope：agent/verifier container（封存）、host_mini_child（A3 落盘）、host_runner_process（未单独测）；工具窗口 26/26 estimated。B 后补容器实测。 |

**结论**：六条中 1 条 evidenced、5 条 partial。B 执行并评审后方可讨论
G1 决议；本文件不构成 G1 通过声明。
