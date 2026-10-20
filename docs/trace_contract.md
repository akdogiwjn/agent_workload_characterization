# Trace 语义与测量契约

当前目标以[current_scope.md](current_scope.md)为准；日常只需按需阅读本契约§11，前文保留详细语义和历史版本，不扩大当前必交范围。

修订日期：2026-10-11。本文规定共享语义与实测验收清单；不是全字段已实现的 JSON Schema。§10 明确当前实现、未支持能力与后续实测要求。字段含义不可静默改变。

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
- 若另行做原RQ1传统LLM性能对照，必须定义对照与测量边界；因果比较控制任务/配置。原RQ4的memory/compute分类需PMU、利用率、I/O与受控scaling，不凭单一IPC；这些扩展不再是2026-10-16收窄目标的必交。

## 9. Replay 契约

Replay 分开记录原 trace、spec 与执行结果，永远不能改标为 real。

- 捕获 cwd、argv/shell、stdin、输入/输出文件与修改、环境变量白名单、镜像/软件版本、缓存初态、网络/远端依赖、进程拓扑及依赖边。
- 区分固定 release time 的 open-loop、前驱完成后 think gap 的 dependency-driven、保留依赖且去除可选等待的 fast-as-possible。不得同时叠加 offset 和 wait 重复计时。
- 远端服务、交互式 shell 状态等无法复现时说明替代/省略；不能把不可执行 trace 变成虚构的等价负载。
- 扩并发前先验证输出/状态正确性、依赖顺序、工具/进程形态及 CPU/内存/I/O 分布；声明保真目标和事先固定的容差，记录失败项。
- scaling 结果只对通过对应保真目标的部分成立；不要求重放完全复现模型 reasoning，也不伪造 token。

## 10. 后续真实执行的必备记录（REAL-RUN-MEASUREMENT-01）

**先决定问题、scope 和必需能力，再批准执行；不能执行完才发现缺少研究所需字段。** 此清单用于后续所有本地实测（Coding、Office，以及未来 Computer/Video），不追溯填补旧 trace。新类别复用现有 recorder/reader，但必须在真实入口接入并验证，不因填写此表就视为实现。

| 记录组 | 每次必须保存/检查什么 | 当前实现与范围 |
| --- | --- | --- |
| 身份与配置 | task/输入/代码/harness/镜像完整身份，模型路由和实际响应标识，预算/采样/重试/资源限制，独立批准与 attempt | 复用既有执行门禁；新采集模块进入 DocOps 单次与批次 identity，Coding 全源文件身份包含该模块。旧冻结值不改，旧批准不适用于新代码 |
| 环境 | 架构、CPU 可得字段、kernel、boot ID、Python 路径/版本、宿主包名/版本，governor/SMT/NUMA 的观测或缺失原因；容器环境引用镜像/preflight/freeze | `environment.json` 自动保存本次宿主观察，不读密钥/environ/无关进程，不运行外部探针。CPU0 governor 不代表所有核；包版本观察不是完整可重建 lock；filesystem/cache/perf 未测则明确 unknown |
| 生命周期 | 初始化/setup、Agent、verifier、清理、删除核验、归档起止；同宿主 monotonic + UTC 锚点；容器 ID/cgroup 与宿主 PID/starttime/CLK_TCK/page size | Coding 保留双容器 scope；DocOps 保留共享容器阶段，并新增 setup/Agent/verifier 资源边界。采样窗口不是 attempt wall |
| 模型调用 | 每个实际开始的逻辑请求 ID、起止/错误终态、模型、返回 usage（含真实零值）、上下文规模的已观测口径；预算拒绝不得算请求 | DocOps 在真实 `LLM.call` 外记录 span；Coding 保存 child query 的真实时间，API 异常也留终态。DocOps 保存返回模型/request ID；Coding 响应模型逐调用尚未接入。上下文字符数不是 token。逻辑调用包含内部 retry，实际传输尝试未装 hook，保持 unknown；usage/cost 不是账单 |
| 工具调用 | 独立 event ID、工具/命令身份、参数摘要/长度、调用与结果起止/错误/删失，末次返回；bootstrap 与自主动作分开；finish/invalid 与工具结果分开 | DocOps `agent/events.jsonl` 直接记录实际官方循环及参数/结果 UTF-8 bytes+SHA，工具用 `request_event_id` 表示因果链接（不是 span 包含）；bootstrap 无 request ID。Coding native hook 保留 tool-call ID/命令 hash/长度及真实边界，不靠位置补配 |
| 资源 | scope 起止累计 CPU 差分、memory.current 采样与内核 peak、宿主进程 CPU/RSS，I/O 的 controller/source/读数状态；保留原始时间序列与边界 | Coding 复用既有 scope evidence；DocOps 增加起止采样、阶段和工具前后共享 cgroup 计数器。宿主 reader 补 user/system ticks、faults、threads、context switches、进程 io（权限不足留原因）。宿主 Agent 与 collector 同进程时不能称独立 Agent 成本 |
| 采集质量与开销 | 目标间隔、实际 gap、时间异常、counter 回退、缺读、边界、调用起止覆盖与期望数量对照，读数耗时 | `measurement.json` 保存调用覆盖；DocOps 另存采样质量/读状态。Coding samples 保留 gap/边界/读状态；两链新增 read wall cost（不是采集器 CPU 或全部记录开销）。数量、退出码 0、reward=1 均不能替代测量完整性检查 |
| 结果与封存 | 测量完整性、任务结果、Agent 终止、infra、清理/归档分别判定；输出文件清单 bytes/SHA 回读 | 新环境/measurement/events 纳入既有 manifest；工具返回 `ok=false` 不自动等于 infra。预算/取消/未闭合事件保留，不补零，不删失败路径 |

### 10.1 本轮确实补齐的内容

实现位于 `collectors/execution_measurement.py`（小型本地快照、请求包装与覆盖检查），继续使用 `SemanticRecorder`，没有第二套执行框架。DocOps 实际执行路径强制走测量 Agent；批摘要直接消费该事件文件，不再按响应是否为裸 JSON 重建动作数。最后一次工具结果在返回时写入，不依赖下一次模型请求的 history。

DocOps 工具前后 cgroup 值只能产生 **共享 scope 调用窗口差分**：包含可能同时发生的后台工作，不能累加重叠窗口或称单工具独占资源。前后读数与记录有开销；时间尺度很短时不得把微小差分过度解释。CPU/内存边界缺失或 counter reset 时停止对应推导，不以首尾可读点冒充完整生命周期。

新 span 是客户端包装的观测边界，可能包含事件写入、结果解析和工具末端计数器读取；没有开销校准时不称纯工具 CPU 执行时间。传输层 TTFT、服务端推理时间与逻辑 API 延迟是不同指标。

`measurement.json.call_timing_status` 只评价请求/工具配对和起止覆盖，不是全指标 PASS。另审 usage 缺失、resource scopes/采样状态、环境缺口、cleanup 和 manifest。Coding 用 trajectory **提议** tool-call 数作独立对照；若有提议但未派发，登记 coverage gap，而不是捏造执行。事件/实际工具返回与任务 termination 分列（例如 Submitted 异常是协议正常终止，不是工具基础设施故障）。

Coding 另存 `mini_request_starts.jsonl`，在原生预算检查放行并实际进入 `model.query` 后登记开始；被硬杀时仍可见已开始、终态缺失，覆盖报告不会把它当作零请求。正常结束的预算拒绝没有 start 记录。`runtime_completed_request_count` 与开始数分列，不从缺少 usage 推断未发请求。

### 10.2 执行前与归档后各做一次明确核对

DocOps 当前生产环境使用项目 `DocOpsDockerEnvironment`：保留 Harbor 的日志权限处理与 compose 项目/文件绑定，`stop(delete=True)` 仅执行 `down --volumes --remove-orphans`，保留可复用镜像。失败必须传回调用方并单列，仍执行本批容器删除核验；删除确认不能抹掉 stop 失败。清理超时继续服从总 deadline。两个入口 identity 绑定项目适配层与实际安装的 Harbor Docker 实现。此策略仅经离线真实接线测试；历史清理/身份不改，真实镜像保留尚未验证。

1. 执行前：声明要回答哪些 RQ、每个必需指标的来源与 scope；在入口真实链路的离线测试中核对末次返回/finish/异常；真实预检只在另行授权后验证 controller/环境。若研究目标需要当前尚无的能力，先补该能力或缩小目标，不能标为“测量就绪”。
2. 归档后：核对独立 runtime/trajectory 数与 span 数、时钟域/时间顺序/删失；检查 CPU reset、缺读、边界与采样 gaps；核验新输出 bytes/SHA；分别列 complete/partial/unavailable。缺失必需指标时仍保存实验结果，但不验收为“测量完整”，不得用于对应结论。
3. **默认自动记录不等于自动授权执行。** 本轮只离线实现；既有真实数据不会凭新代码得到新字段。下次需要独立 identity/新批准，不能复用已消费 namespace。

### 10.3 有意不自动开启的能力

PMU（cycles/instructions/cache/TLB/branches 等）、函数热点、逐进程树/独占工具归因、网络传输字节、远端 CPU/内存、完整应用/文件系统 I/O、受控缓存、精确传输 retry/TTFT 都不是本轮已实现能力。相应位置保留 unavailable/unknown 及原因，绝不把空值或 cgroup blkio 的真实零写成“没有文件操作”。需要这些研究指标时，应一次性列入新实验设计和权限范围；CPU-02/perf/Replay 不因此恢复。

## 11. 当前目标的连续采样与图表要求（2026-10-16）

本节是当前交付要求；本轮代码变更不改变任何历史合同、冻结身份或raw。热点/PMU/微架构/优化、单工具独占归因不再必交；本轮离线接线仍须经过逐链真实运行验收。

| 项目 | 后续过程观测与展示要求 | 当前已有/缺口 |
| --- | --- | --- |
| 采样与范围 | 单run内周期采样，当前主链目标0.5s；保存真实monotonic时间、scope/PID或container身份、读状态、gap/reset。明确任务与宿主整机不是一个scope | 已有cgroup/进程采样；无整机统一采集。不同长度任务不以固定点数验收，不为多采点强制补跑 |
| CPU | 累计CPU差分/真实Δt转平均core；若百分比，100%=1core或明确其他归一化；另报总core-s | 已有CPU累计计数和部分HTML时序图；不是服务器端模型CPU |
| 内存 | current/RSS时间序列及有效样本峰值，内核peak单列；不同scope不相加 | 已有采样，Coding/DocOps有曲线；Assistant最新样本待展示接入 |
| 磁盘I/O | 分读/写累计B与有效相邻差分B/s，明确cgroup块设备服务字节或proc read_bytes/write_bytes；rchar/wchar另列 | cgroup采样输出增加区间速率与gap；host进程报告增加CPU及proc I/O速率。不是完整文件系统I/O；缺读和计数回退保持gap |
| 磁盘占用（必统计） | 显式任务工作区/提交目录、可见输出目录及可识别缓存的前后表观大小、增长、角色/scope、扫描耗时与状态；重叠排除且不跟随符号链接 | Coding容器`/testbed`与Office容器`/root/submission`已接入有时限的边界扫描；Assistant任务状态为内存态并标not_applicable，宿主run输出另测；共享cache仍unsupported。仅离线fake验证，依赖容器`python3`尚未真实核验；后测量后还会写归档文件，不称最终归档大小 |
| 网络通信 | 累计接口rx/tx及有效相邻B/s，明确netns/接口范围；区分共享netns与HTTP应用正文 | 三链采集进程所在netns的`/proc/net/dev`，按接口独立保存共享计数与速率；不是PID/API专属流量。三条模型客户端的请求/流式响应正文bytes尚未实现，TLS/协议开销不支持；仅离线fake验证。禁网容器不代表宿主API流量为零 |
| 时长与行为 | attempt wall、实际阶段、请求/工具起止与计数、具体软件集合；bootstrap、自主动作、错误、终止和评估分列 | 三类已有不同范围的事件/资源边界，旧缺边界不倒填 |
| 总览与重复 | 一次任务时间对齐的CPU/内存/I/O/网络四面板，分别标单位与阶段；缺失断线或显示unavailable。重复run保留独立曲线，另报原始点/median/IQR | 本轮未更新HTML；历史数据无网络和目录边界曲线。新采字段经真实运行验收后再统一展示，不伪造历史曲线 |

除四项资源及工具统计外，报告还包含以下支撑记录。新增要求不是“全部已经实现”的声明；字段不可得则明确unavailable，历史未采不倒填。

| 支撑记录 | 记录范围与口径 | 当前已有/限制 |
| --- | --- | --- |
| 模型调用与用量 | 逻辑请求数、客户端耗时、输入/输出/cache token、错误及有证据的重试 | 三类已有不同范围的请求与usage；真实HTTP传输次数、完整TTFT与账单不能由现有计数推定 |
| 阶段时间与结果 | 启动/setup/Agent/评估/清理边界；评分、终止、超时、工具错误、infra与可观测OOM分列 | 已有生命周期和独立结果记录；OOM未保存时unknown，不把工具错误当infra或未解决当测量无效 |
| 进程/线程活动 | 可得线程/进程数、user/system CPU、上下文切换、minor/major faults；明确scope | HostProcessReader已有相关进程字段；不是整机/进程树全量采集，线程数不代表使用核心数 |
| 环境和限制 | CPU/内存/OS/kernel/软件/模型身份、CPU及内存配额、采样scope | 已有环境快照及冻结配置；按运行时记录判断覆盖，不能用当前机器配置倒填历史 |
| 采样质量与开销 | 有效点数、真实间隔、gap/缺读/reset、时间窗与实际可得读数开销 | 已有部分质量检查与read wall cost；后者不是采集器全部CPU成本 |

磁盘占用按用户补充已列入上方必统计项目；禁止因此默认全盘扫描、清缓存、删除数据或安装新监测器。采集开销须记录，共享缓存与任务独占数据分开。

GPU使用暂不统计，不列为当前缺口或验收要求；支撑记录也不引入函数热点、PMU、逐工具独占归因或微架构分类要求。

历史字段盘点见[LOCAL-MEASUREMENT-COVERAGE-v2](../reports/analysis/LOCAL-MEASUREMENT-COVERAGE-v2/summary.md)：三个已登记批次各9个run；有效CPU/I/O速率按逐run端点状态和scope身份离线推导，历史网络字节和任务目录起止占用不存在，必须新采。本轮修复后的共享采集链仅经离线fake验证，尚未真实运行验收。下一步分别对Coding、Office、Assistant各做一次单次验证；验收采样、scope、清理和归档后，再决定是否扩大为新口径重复批次。此处不授予执行权限，不改历史批准/身份；CPU-02和Replay继续暂停。
