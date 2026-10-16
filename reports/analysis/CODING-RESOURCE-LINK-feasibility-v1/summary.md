# CODING-RESOURCE-LINK-feasibility-v1：现有 Coding 数据的行为—资源关联可行性核查

生成日期：2026-10-07。离线只读检查，未联网、未运行 Agent/verifier/Docker/perf、未修改历史 raw 与既有报告；不改变 G2/G3-R、CPU-02、Replay 状态。

## 结论（直接给出）

**判定：有增量，并已完成一项最小分析；其余候选判定为不可行或低价值并关闭。** 现有 CODING-REPEAT-01 数据在"区间类型级"的行为—资源关联上还有一项 v3 未回答的问题且字段完全可用；在"调用级"归因上，现有共享 scope 及采样分辨率不足以支持可靠独占归因。唯一下一步建议为代表性 SWE-bench 子集行为分析（未授权、未启动）。

## 可行性核查结果（九个 run）

**时间关系**：工具事件（mini_tool_events.jsonl 的 t_start_ns/t_end_ns）、请求事件（mini_status.jsonl 的 t_start_ns/t_end_ns）与资源采样（samples.json 逐点 t_monotonic_ns）使用同一宿主 monotonic 时钟，可直接对齐，无需猜测偏移。采样目标间隔 0.5s，起止为 scope boundary（含 boundary_start/end 计数器），缺测以 sample_gaps_ns 记录。

**资源语义**：cpu_usage_usec 为 cgroup cpuacct 累计计数器（相邻差分即区间 core-s，与 characterization-v3 同口径）；mem_current_bytes 为瞬时值、mem_peak_bytes 为内核累计峰值；Agent/verifier 为独立 cgroup scope。九个 run 负差分 0、计数器重置 0（v3 已核）、越界样本 0。

**事件覆盖**：348/348 工具调用通过 v3 严格身份门禁配对；共享容器内的后台活动无法排除，可出现在任意事件类别中。

**分辨率硬限制**：348 个工具调用中 263 个（75.6%）时长短于 0.5s 采样间隔（中位数字段存在上中位数实现问题，本修订排除引用）。现有共享 scope 和采样分辨率不足以支持可靠的逐调用独占归因。增加同类实验次数不会自动提高测量粒度；事件边界快照、更高采样率或进程级观测可另行评估，但都不自动保证独占归因。

## 本轮完成的唯一最小分析：纯区间 CPU 分解

方法（预先固定）：将每个 agent 容器 CPU 采样区间按事件覆盖分类——完全被请求区间覆盖且无工具（only_req）、完全被工具覆盖且无请求（only_tool）、无任何事件（uncovered）、其余（mixed，单列、不做任何按时间比例分摊）。分类容差 1e-9；不做单调用归因、不用 wall−CPU。每 run 总 CPU 与 characterization-v3 逐位一致（9/9，如 bc1dca 43.778057 core-s）。

**新发现：九个 run 的 only_req CPU 全部精确为 0.000000 core-s**（每 run 82–154 个纯请求采样区间，每个区间的计数器差分均为 0 usec）。该结果限于目标容器 cgroup、完整归类的采样区间与计数器精度，不覆盖宿主 Agent/API 进程，也不证明进程完全阻塞。其余 CPU 分布：only_tool 占各 run 总量的 29.1%–91.2%（per-task 中位数：astropy-13236 11.77、astropy-13398 15.64、django-16485 32.96 core-s），mixed（事件边界跨界区间）6.26–18.72 core-s，uncovered 仅 0.13–0.21 core-s（基本为收尾段）。

允许的解释：本批九个 run 的目标容器 CPU 可按事件覆盖窗口描述；only_req 窗口的观测增量为零，only_tool 是工具事件窗口内的共享容器 CPU，不是独占工具消耗。mixed 是其他覆盖组合，本批主要为事件边界跨界。后台活动可贡献于任意类别；宿主编排/API 进程不属于目标容器 scope。该结果不证明阻塞机制，也不能推广到整个 Agent 或其他任务。

## 关闭的候选（判定与理由）

- 高值集中度统计：v3 已有 top 区间共现；集中度数字依赖阈值选择，增量小，有多试多选风险——不做。
- 同任务跨 run 高值区间活动组合对比：v3 activity_correlations 显示高值区间通常仅重叠 1 个调用，类别粒度不足以支撑组合对比——不做。
- 单调用级归因：受 75.6% < 0.5s 的分辨率限制——现有证据不足以可靠归因，需另行评估测量能力（方向 B），本轮关闭。

## 唯一下一步建议（仅建议，未授权、未启动）

**代表性 SWE-bench 子集行为分析**（离线、数据已在本地）。理由：CODING-REPEAT-01 的行为—资源关联已到数据边界——区间类型级本轮已回答，调用级需新测量能力而非更多样本；SWE-bench 子集（按 task/harness 多样性选样，不按成功率）以零新授权扩展 Coding 行为覆盖（RQ1/工具形态）；公开 Computer/Office 测量准备依赖用户对执行授权与资产的决策，不由本轮单方面启动。停止条件：子集分析完成登记即停，不自动扩全量、不开发超出子集需要的适配。

## 边界

未修改任何历史 raw、批准、marker、catalog 或既有报告；分析脚本 `scripts/coding_resource_link_feasibility.py` 与定向反例测试 `tests/test_coding_resource_link_feasibility.py`（4 项合成用例全部通过）为本轮新增；3×3 试点不推广为 Coding 类别规律；本报告不构成执行授权。

## 可追溯入口

- [decision.json](decision.json)（候选、判定与唯一下一步）· [per_run_decomposition.json](per_run_decomposition.json)（逐 run 数值）· [manifest.json](manifest.json)
- 输入依据：CODING-REPEAT-01 批次 summary/manifest 与九个 raw run（路径取自 characterization-v3 manifest）；已有结论引用 [characterization-v3](../P1-12-CODING-REPEAT-01-characterization-v3/summary.md) 与 [review-v1](../P1-12-CODING-REPEAT-01-review-v1/summary.md)


## 2026-10-08 复核修订

落实 2026-10-07 独立核验发现的文案问题：原 manifest 输入/输出哈希匹配；独立整数区间并集算法复算九个 run，各分类 CPU 与产物一致，分类总和等于末首计数器差，无负差分、倒序或零长度采样区间。修正零 CPU 的机制外推、后台活动范围及纯请求区间数范围（82–154）。本轮修改报告和登记，不重跑实验。

分析代码和 `per_run_decomposition.json` 未改。`tool_duration_s.median` 对偶数样本取上中位数，d87dd3、8adc15、441807 三条记录因此排除引用；独立正确中位数约为 0.221883、0.195104、0.237954 秒。此辅助字段错误不影响 CPU 分解及 263/348 短调用计数。以后复用脚本须修该字段，本轮不是代码全部功能验收。
