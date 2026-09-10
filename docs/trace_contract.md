# Trace 语义与测量契约

修订日期：2026-09-10。本文规定 P0-02 设计和验收所需语义；不是已实现的 JSON Schema。字段名可在评审中细化，含义不可静默改变。

## 1. 共享语义，不强制相同观测能力

Public Trace 与 Real Agent Run 共享 ID、事件、来源和指标语义，但保留不同 profile：

- `macro_template`：生产派生的 workload 模板，无真实执行时间轴也可合法。
- `semantic_trace`：有 Agent/LLM/Tool 行为证据，无系统测量也可合法。
- `resource_trace`：有本机进程或资源 scope 测量，未必能逐 Tool 独占归因。
- `replay_trace`：重放执行结果，关联原始 trace 与 replay spec。

Profile 是能力声明，不是单字段全部完整的保证；coverage 必须逐指标检查。逻辑 IR 与物理存储分离：小样可按 run 使用 JSON/JSONL，批量可分区 Parquet；不强制每个模板生成空进程表，也不提前固定十几张表。

## 2. 来源、身份与关联

必要概念：`source_id`、`snapshot_id`、`source_record_ref`、`run_id`、`task_id`、`attempt_id`、`agent_id`、`request_id`、`event_id`。只有实际存在的概念才分配身份；模板记录不冒充真实 execution run。

- ID 必须防止同任务跨模型、seed、attempt 冲突；重新 ingest 同一原始运行不得重复计数。
- `parent_id` 表达 span 包含关系，支持并行分支；跨分支依赖和 join 使用可选 typed links，不用多父节点替代全部树结构。
- `agent_id` 与 `parent_agent_id` 不得自指；主 Agent 与全部子 Agent 的统计范围分别声明。
- Tool 调用、后台 job/session、进程和 resource scope 分别标识。一个 job 可关联 submit/poll/wait 多次调用；一个常驻进程可服务多次调用。
- 进程身份至少包括 host/boot 或等价命名空间、PID namespace、PID、启动标识，不能只用可复用的 PID。
- 关联附 `association_status`、依据和方法。未绑定请求保留 batch/request ID、`run_id=null`；不得只按最近时间戳关联。

`trace_type` 保留 `production | benchmark_real | oracle | replay | synthetic`，增加 `production_derived | unknown`，避免把生产派生模板或未知来源强塞为原始生产实测。来源未知不能通过正式已分类 cohort 验收。`trace_type` 不替代 profile、逐指标证据和原始来源链。

## 3. 时间、延迟与并发

- 本地 duration 优先来自同一 clock domain 的 monotonic 时间；另存 UTC wall-clock anchor、时钟来源、精度和采集延迟信息。
- 纳秒整数用于归一化时间存储；转换单位不提升原始精度。没有时间戳的模板不得伪造真实时间轴。
- 跨 host/VM 时钟必须记录对齐方法与误差；未校准时不做精确跨时钟相减。
- 标记 `native_event`、`log_receipt`、`adjacent_event_estimate` 等时间来源。下游注入的日志时间不是自动精确的执行边界。
- 开始存在、结束缺失：保留 null、状态与右删失信息，不补成零时长；取消/超时/采集器退出不得静默丢弃未闭合事件。
- `run_elapsed` 要有可信运行边界；事件首尾得到的是 `observed_span`。请求开始时刻之差不能命名为完整 session duration。
- 区分客户端 request latency、proxy/upstream latency、TTFT、服务端推理时间；未测服务端就不能从 API 时延反推纯推理。
- LLM/Tool 的 duration 之和可能因并发超过 E2E。分别报告累计 work time、区间并集 busy time、overlap 与 uncovered time；没有依赖证据不编造 critical path。

时间分解只有在定义互斥阶段或采用明确的重叠处理后才能相加；不能简单以 E2E 减去全部请求/Tool duration 得出 Agent 开销。

## 4. 指标证据、缺失与覆盖

每项指标至少记录：值/单位、scope、来源字段或计算规则、证据类型、适用分母、缺失原因。可按同语义字段组附注，无需逐值重复庞大结构。

| 证据 | 含义 |
| --- | --- |
| `observed` | 原始来源直接记录的测量或事件；不自动意味着无误差 |
| `derived` | 从明确输入确定性计算，保留输入证据与公式 |
| `template_parameter` | 模板指定值或其确定性展开，非真实执行测量 |
| `estimated` | 近似推断或分摊，公开假设与限制 |
| `unavailable` | 当前来源不能提供；值为 null |

缺失原因区分 not_recorded、not_applicable、unreadable、unresolved、unsupported、censored 等。null 不补零，真实测得的零也不能被 `value or null` 丢弃。字段非空并不意味着可纳入所有聚合。

Coverage 报告分开列出 run aggregate、resolved request、unassigned request、tool/job、resource scope；提供 n_valid/n_applicable、来源与筛选。统计排除缺失值时同时报告排除数量。

## 5. 宏观指标口径

- `turn_count`、模型请求数、Tool 调用数、事件数不是同义词。turn 需声明源定义，无法映射时保留 source turn 或 null。
- token 总量、模型时间总量和请求数必须使用相同 main/all-agents 范围；重试计数策略显式化。运行级 token 汇总不能再次加上逐请求 token。
- AgentX 的 Tool count 若只观测子 Agent，必须标范围，不能冒充全 run；保留完整 prefix hash、block size、hash 适用范围，不能截断后推导可靠 cache reuse。
- Applied Compute / trie 的 N 个 tool-use turns 对应 N+1 次模板 completion。设初始输入 I₀、每轮输出 Oᵢ 和工具结果 Rᵢ，则模板逻辑上下文可按 Iᵢ₊₁ = Iᵢ + Oᵢ + Rᵢ 计算；全部输入为 ΣIᵢ（i=0…N）。这些是模板口径，不等同实际 tokenizer/chat 包装/截断后的服务端测量。
- 同一模板最后一次输出计入总输出，不再加入下一次不存在的模型输入。缺少必要长度时不得补出精确 context。
- API/Tool delay 不等于本地 CPU execution time；请求间 gap 也不自动等于 Tool latency。

模板依据：[trie workload format](../references/repos/trie/README.md)。具体输入展开还需在 P0-05 对照所固定版本的 client 实现。

## 6. 资源归因边界

Tool 调用返回、job 完成、scope 不再有活跃工作、资源完全释放是不同事件。Collector 应保留 run 级观测，以及可实现的 job/service/Tool 级观测。

| 执行模式 | 首选测量边界 | 允许的结论 |
| --- | --- | --- |
| 独立子进程及其后代 | 启动工作前进入专属 scope | scope 内资源直接归因，记录外部共享服务遗漏 |
| 常驻浏览器 / runtime / 进程内函数 | run 或 service scope，关联调用窗口 | scope 实测；per-call 只在证据充分时测量，否则共享/估计 |
| 异步本地 job | job scope，submit/poll/wait 链接 | job 生命周期资源；不因 submit 返回提前 cleanup |
| 远端 API / 媒体生成 | 本地 client scope ＋远端已提供遥测 | 本地资源与远端等待分别报告；远端 CPU 未测则未知 |

记录 `attribution_method`（exclusive_scope / shared_scope / window_estimate / unresolved）、scope 层级与生命周期。`tool_event_id` 可空，scope 到 Tool 的关系可多对多；不能复制共享 scope 的全部 CPU 给每个调用后再求和。

采集器原则上放在被测 workload scope 外并单独测开销。区分 Agent runtime、初始化/收尾、Tool、共享服务和未归因残差；不能只测工具后将其称为完整 Agent CPU。

cgroup 约束：domain controller 的内部节点/叶节点布局必须合法；进程迁移不搬迁既有内存记账，不能据此宣称 per-call 内存归因完整；PID 不再活跃也不等于 page cache 等记账立刻归零。依据：[Linux cgroup v2](https://cdn.kernel.org/doc/html/latest/admin-guide/cgroup-v2.html#memory-ownership)。具体支持能力需在目标机器 preflight 验证。

## 7. 资源指标与验收

- CPU 时间取累计计数器增量，平均使用核心数为 ΔCPU_seconds / Δwall_seconds；若报告百分比，声明按单核还是可用核数归一化。不将 CPU/wall 命名为算法“效率”。
- RSS、cgroup memory.current、memory.peak 含义不同，不能互换。多个进程 RSS 求和可能重复计共享页；并发或跨时段的各 scope 峰值之和不是 run 峰值。
- I/O 区分应用读写字节、实际 block I/O 和 network bytes；page cache 会使它们不同。
- 累计 counter、瞬时 gauge、采样峰值分开；记录 scope 重建/计数器 reset。父 scope 已包含子 scope 时不得再相加。
- 500 ms 与 100–200 ms 只是候选采样间隔。短进程/突发需边界计数器或生命周期证据；轮询漏检要量化，不以“采到 20 点”证明正确。

验收使用确定性 CPU、内存、I/O、短进程、并发、后台作业和常驻服务样例：对照独立测量，报告计数覆盖、scope 残差、短任务遗漏、时间误差与采集开销。每个指标的容差在试点后、正式比较前固定，不能看结果后放宽。

对可加的 CPU/I/O 计数检查 run 与互斥子 scope 的差值；内存峰值不可按同样方法相减。共享 scope 无法拆分时保留共享项，而非要求所有 Tool 都“完整归因”。

## 8. 统计与研究结论

- 先按来源/profile/场景/配置分层；缺失维度不同的样本不能直接做同一距离排名。
- Public Trace 只描述所发布且被筛选的样本。公开 Coding 数据不能直接证明本地 Office/Video 代表生产总体。
- Local Real Trace 提供关联证据；因果和架构需求结论需受控实验，不能仅靠时间重叠。
- 分开报告 task 数、attempt 数、run 数、调用数。重复三次同任务不是三个独立任务；置信区间/重采样按 task 等合理单位分层或聚类。
- 3 次重复、重点 5 次是初始预算建议，不是统计充分性保证。少样本 P95/P99 只作带样本量说明的描述，必要时不报告，不能据此外推尾部规律。
- phase 是可回退、交错、重复的注释；保留分类规则和置信/未知状态，不强制 Explore → Modify → Verify 单向流程。
- RQ1 必须定义传统 LLM 对照与测量边界；RQ3 控制任务/配置差异；RQ4 的 memory/compute 等分类结合 PMU、利用率、I/O 和受控 scaling，不凭单一 IPC。

## 9. Replay 契约

Replay 分开记录原 trace、spec 与执行结果，永远不能改标为 real。

- 捕获 cwd、argv/shell、stdin、输入/输出文件与修改、环境变量白名单、镜像/软件版本、缓存初态、网络/远端依赖、进程拓扑及依赖边。
- 区分固定 release time 的 open-loop、前驱完成后 think gap 的 dependency-driven、保留依赖且去除可选等待的 fast-as-possible。不得同时叠加 offset 和 wait 重复计时。
- 远端服务、交互式 shell 状态等无法复现时说明替代/省略；不能把不可执行 trace 变成虚构的等价负载。
- 扩并发前先验证输出/状态正确性、依赖顺序、工具/进程形态及 CPU/内存/I/O 分布；声明保真目标和事先固定的容差，记录失败项。
- scaling 结果只对通过对应保真目标的部分成立；不要求重放完全复现模型 reasoning，也不伪造 token。
