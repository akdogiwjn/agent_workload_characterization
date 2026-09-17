# G1 逐项证据（G1-01-A 范围；不宣布 G1 通过）

对照 `docs/development_tasks.md` G1 六条。本批为 A（离线分析+机制验证）；
B（无模型容器验证）待批准。逐项标注 evidenced / partial / missing 及
支持的 scope。

| # | G1 标准 | 状态 | 证据与边界 |
| --- | --- | --- | --- |
| 1 | 目标 scope 的语义、process、资源可关联，独占/共享/未知明确 | **partial** | 语义：tool_timeline.jsonl 26/26 身份+顺序+结果（tool_call_id+位置配对）；scope 关联：shared_scope/window（校准残差 3.84 ms）；host scope：A3 新增 HostProcessReader（未来运行），历史为 missing 且未回填。独占 per-tool CPU：明示不存在（0/26 true duration）。B 后容器窗口关联待验。 |
| 2 | 短进程、后台作业、常驻服务、异常退出、时钟/采集延迟有测试 | **partial** | 短进程/PID 复用/计数 reset/读取失败：fixtures（test_g1_01，fake /proc）；后台超出调用返回：fixtures（不伪闭合）；时钟：锚点校准+残差、跨域不相减规则、系统级 monotonic 论证（timing_semantics.md）；采集延迟：collector 读耗时实测（~0.035 ms/读）。常驻服务：本批未覆盖（B 提案含停止链复查）。 |
| 3 | CPU/I/O 计数核对、memory 口径、重叠/残差和遗漏报告通过评审 | **partial** | CPU 双源核对：C1（/proc vs 子进程自报，差 12 ms < 20 ms 轮询粒度）；单位：CLK_TCK/页大小独立期望（fixtures）；重叠：C2 work/union/span + 共享计数不复制；memory 口径：current/sampled-max/内核 peak 分离（RUN-01 沿用）；I/O：正式 null+降级原因（v2 口径）；采样窗口：出界样本可检测且已修 summary 过滤。**评审待做（本文件即送审材料）。** |
| 4 | 至少一种真实 Runner 小样与确定性测试闭环，原始日志和三类状态保留 | **evidenced（既有+本批补强）** | RUN-01-C 真实 attempt（resolved=true，三状态独立，8 文件封存+supplement）；本批补真实 mini 离线 hook 集成 4 项（含工具事件边界/错误/格式错误分支）。确定性 fixtures：test_g1_01 15 项 + 既有 395 项无退步（410 总）。 |
| 5 | Collector 开销已量化；正式比较前固定计量容差与降级边界 | **partial** | 开销：O1-O3 原始配对数据（差 ±噪声级；读耗时 ~0.035 ms×~35 次≈1.2 ms/运行；无百分比声明）；容差：C1 声明式（轮询粒度+调度噪声）；计数/哈希精确一致。**B 后需评审固定正式容差。** |
| 6 | 可找出 CPU/Wall/Memory 的候选 scope；精确 Tool 归因并非必需 | **partial** | 候选 scope：agent_container（6.412 core-s）/verifier_container（3.423 core-s）/host_mini_child（未来；A3 已接）/host_runner_process（collector 含内，未单独测）；Wall：估计工具窗口 26/26（overstate 声明）。Memory：scope 峰值已分口径。B 容器验证后可补 hook+容器窗口实测。 |

**结论**：G1 六条中 1 条 evidenced、5 条 partial，无 missing 项归零。
B（无模型容器验证：真实 hook 窗口+容器计数器+宿主采集+停止后边界）
执行并评审后方可讨论 G1 决议。本文件不构成 G1 通过声明。
