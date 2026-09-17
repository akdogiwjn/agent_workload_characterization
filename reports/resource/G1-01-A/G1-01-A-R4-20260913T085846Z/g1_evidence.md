# G1 逐项证据（G1-01-A 第三轮返修；不宣布 G1 通过）

对照 `docs/development_tasks.md` G1 六条。本批为 A 第三轮返修（评审三
项意见修复）；B（无模型容器验证）继续待批。

| # | G1 标准 | 状态 | 证据与边界 |
| --- | --- | --- | --- |
| 1 | 目标 scope 的语义、process、资源可关联，独占/共享/未知明确 | **partial** | 26/26 身份（ID 交叉核对 0 异常）；锚点流数量门控（一致才校准，**中间缺行禁用校准与派生 monotonic 窗口**——回归覆盖）；实测 C run：26/26 锚点、残差 3.84 ms（观测散布语义）；host scope 落盘完整；独占 per-tool CPU 0/26。 |
| 2 | 短进程、后台作业、常驻服务、异常退出、时钟/采集延迟有测试 | **partial** | fixtures 23 项（含**单 scope 停止冻结**：后台线程保持运行、已停 scope 读取/样本/边界冻结、活跃 scope 继续采样；**中间缺行禁用校准**）；后台超返回；时钟规则；硬 deadline。常驻服务：B 提案。 |
| 3 | CPU/I/O 计数核对、memory 口径、重叠/残差和遗漏报告通过评审 | **partial** | C1 改为**不同窗口的诊断对照**（comparison_semantics 如实声明：自报覆盖子进程全生命周期含解释器启动，/proc 为首末可读快照差——同意差不能证明同区间计量）；本轮实际差 3.8 ms；单位独立期望；重叠 C2；I/O 正式 null。**评审待做。** |
| 4 | 至少一种真实 Runner 小样与确定性测试闭环，原始日志和三类状态保留 | **evidenced** | RUN-01-C（封存+supplement）；真实 mini 离线集成 5 项（原 3 + 新 2）；fixtures 23 项；默认 418 项无退步。 |
| 5 | Collector 开销已量化；正式比较前固定计量容差与降级边界 | **partial** | O1–O3 本轮原始值 +31/+51/+21 ms（噪声级；~0.04 ms/读）；容差语义更正（不同窗口一致性检查，非同区间验证通过）；B 后评审固定正式容差。 |
| 6 | 可找出 CPU/Wall/Memory 的候选 scope；精确 Tool 归因并非必需 | **partial** | 候选 scope 四类（container 封存实测、host_mini_child 落盘、host_runner_process 未单独测）；工具窗口 26/26 estimated（门控启用时）。B 后补容器实测。 |

**结论**：六条中 1 条 evidenced、5 条 partial。B 执行并评审后方可讨论
G1 决议；本文件不构成 G1 通过声明。
