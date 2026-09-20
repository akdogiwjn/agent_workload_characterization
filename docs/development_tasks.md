# AI Agent Workload Characterization 开发任务计划

<!-- PROJECT_STATE:START -->
当前状态由 [2026-09-20 状态真源](../project_state.json)统一登记；这是进度记录，不是执行授权。

- G1：登记小闭环通过；G2 / G3-R 未通过。
- CPU-02：初次 B 准备失败，修复后 R1 映射失败；后续 perf 权限受限。路线暂停，无有效容器热点样本，新 retry 未授权。
- P2-01 小样分析与 P3-01 v3 现有 trace 审计已交付；不授权 Replay。
- 当前：P1-12 小规模独立任务 × 重复的离线选样与预算设计；不启动容器、模型或新实验。
<!-- PROJECT_STATE:END -->

## 1. 目的、范围与共同约定

目标不是 Agent 能力排行榜，而是将公开宏观行为与本地系统观测连接到 CPU Characterization、Hotspot、Replay / Scale。

必读：[方法论](../methodology.md)、[参考说明](../references/README.md)、[参考清单](../references/manifest.yaml)。
所有任务同时遵守：[数据管理](data_management.md)、[Trace 语义与测量契约](trace_contract.md)。

历史 P0 阶段记录：初版规划未开发，后续完成 P0-00-r2、P0-01～05、P0-10 小样及 P0-08/09 最小集，当时未启动 benchmark。此句不描述现在：后来 RUN-01-C 与 RUN-02-R2 已完成真实 Coding attempt，见顶部集中评审。未全量转换或搬迁旧 trace，不因已有运行自动获准下一次执行。

旧工程已有 adapter、sidecar、宏观分析和真实运行产物；需审计后选择性复用。不能以“已有报表”判定 P0 已完成，也不能假定新项目必须从零重写。

## 2. 项目结构与数据位置

项目根为 `/home/lcq/agent_workload_characterization`，方法论保留根目录 `methodology.md`。

目标结构按任务逐步建立。下图按职责列出代码模块；P0-01 已选择 `src/agent_workload_characterization/` 包布局，后续 adapters、collectors、runners、analyzers、replay 等 Python 子包置于其中，不在根目录另建同名 Python 包。schemas/data/docs/reports 保持项目级目录：

```text
agent_workload_characterization/
├── README.md
├── methodology.md
├── docs/
│   ├── development_tasks.md
│   ├── data_management.md
│   ├── trace_contract.md
│   └── benchmark_selection.md
├── references/                # repos / papers 只读参考
├── schemas/
├── workload_catalog/          # coding / office / assistant / video
├── data/
│   ├── catalog/
│   ├── raw/                   # 新增 public / generated / replay 数据
│   └── normalized/
├── adapters/                  # common / agentx / applied_compute / swebench / local
├── collectors/                # semantic / process / cgroup / resource / perf
├── runners/                   # coding / office / assistant / video
├── analyzers/                 # macro / phase / tool / resource / cpu / hotspot
├── replay/
├── reports/                   # quality / macro / resource / cpu / replay / scale
├── scripts/
├── tests/
└── pyproject.toml
```

旧原始数据通过 catalog locator 原地读取。新产物只写新项目；不建立可回写旧源的输出路径。目标目录不等于要求立即搭建全部空目录。

## 3. 阶段与实际依赖

保留原 P0～P4 和已有任务编号以便追踪；P 编号是工作类别，不是整阶段串行锁。

| 类别 | 范围 | 进入条件 |
| --- | --- | --- |
| P0 | 资产审计、IR、来源适配、宏观分析与质量 | 审计先行；最小语义闭环优先 |
| P1 | 本地语义与资源归因 | G0 通过；不等待全部公共 adapter |
| P2 | CPU / Hotspot / 受控实验 | 对拟分析 scope 的 G1 通过；不等待四场景或 50 个任务 |
| P3 | Replay / Runtime / Scale | 来源 trace 质量满足用途；保真 Gate 先于 scale |
| P4 | eBPF 深化、预测、调度等优化 | 有测量证据和独立实施授权 |

```text
P0-00 资产审计
  → P0-01/02/03 + P0-04/05/10 小样 + P0-07/08/09 最小集
  → G0 语义 Gate
  → P1-00/01/02/03/04/05/06 + 一个本地 Runner + P1-11/13 小样
  → G1 资源归因 Gate
  ├→ P2 CPU 试点 → 修正测量设计 → 扩展 P1 场景/样本
  └→ 其余 P0 adapters / 宏观分析扩展
       → 正式 characterization
       → P3 Replay 保真 Gate → Runtime / Scale
```

共同要求：每个任务说明 RQ、输入快照、可复用资产、输出和验收。阻塞某种精确归因时，可保留 service/run 级测量继续研究，但不得把降级结果标成 exclusive Tool 测量。

## 4. P0：资产、语义与宏观分析

### P0-00：旧资产与指标语义审计（r2 已完成）

依赖：用户明确开始开发/审计工作；首先只读，不运行旧 pipeline 或付费请求。服务 RQ1～RQ6 的证据基础。

范围：

- 按 [数据管理清单](data_management.md)登记公共/生成/归档数据、旧分析代码、sidecar 与 telemetry。
- 区分原始日志、生成快照、重复副本、派生表、报表；不按目录名推断 production/real/oracle。
- 对每源登记版本、可访问性、筛选、attempt/run 身份、profile、逐指标 coverage、许可。
- 对自有代码逐模块决定复用/修正/替换/暂缓；不复制第三方格式或修改参考仓库。
- 对旧 runtime/VM 工程审计真实接口，不能假定 bench_core 与旧 vm_monitor 可无缝连接。
- 不将文档中的旧数量写成当前精确总数；未审计项标 pending。

已在文档审阅中发现、尚未修复的项目：

| 位置（相对旧 benchmark_analysis/src/agent_trace_analysis/） | 待解决问题 | 必备回归样例 |
| --- | --- | --- |
| adapters/agentx.py | 请求开始跨度不等于 run 时长；turn/request 混用；主/子 Agent 聚合 scope 不一致 | 单请求、嵌套/并发子 Agent、未知结束 |
| adapters/agentx.py | prefix hash 截断；模型行 parent_agent 自指风险；未知 latency 补零 | 完整 hash、父子引用、null 与实测零 |
| adapters/applied_compute.py | N turns 漏最终请求；初始 prompt 冒充累计输入和最大 context | N=0、N=2 手算模板、长度缺失 |
| adapters/spreadsheetbench.py | task 文件名生成 trace_id，跨模型/attempt 冲突 | 同任务两个模型、两个 attempt |
| adapters/osworld.py | action 时间跨度被当作端到端时长 | 单动作与缺结束边界 |
| metrics/representative.py | 缺失维度混排；Heavy/Light 按 turns 排序，不能称 CPU heavy/light | 不同 coverage、不同来源规模 |
| 旧 sidecar/gen_sidecar.py | wa_ts 是下游日志时间；工具/job 关联与未闭合事件需审计 | 延迟日志、submit/poll/wait、取消 |

这些是静态审查证据，不是本轮跑出的测试结果；正式任务需记录所审代码版本并建立 fixtures。

输出计划：`docs/legacy_asset_audit.md`、`data/catalog/` 中来源快照、`reports/quality/asset_inventory.*`、复用决策和待修复清单。

验收：每个来源有真实 locator 与证据；原始与派生、success 子集与全部已知 attempts 可区分；不执行迁移、删除或重采。

### P0-01：最小项目骨架与自有代码复用边界

状态：**DONE**，见 [交付记录](p0_01_delivery.md)。该任务交付时标准库 CLI/测试和 src 包布局已实现，10 项测试通过，无运行时第三方依赖；后续 P0-02 按需要新增 Pydantic。未安装/打包分发。此状态不代表 G0 通过。

依赖 P0-00。只建立下一步需要的包、CLI、测试与配置；参考旧工程实际技术栈再决定依赖，不同时引入两套等价数据框架。

输出：最小 `pyproject.toml`、`.gitignore`、包入口、测试框架及 README 使用说明。现有 README 不覆盖丢失。

验收：至少一个有断言的测试通过、包可导入、CLI 帮助可用。仅“pytest 能启动”或无测试退出不算完成。不引入重型 eBPF 依赖。

### P0-02：最小 Trace IR 与指标契约

状态：**DONE**，见 [交付记录](p0_02_delivery.md)及 [IR v0.1 约定](ir_v0_1.md)。四 profile、公共模型、Schema、只读验证与手算契约已实现；全套 42 项测试通过。跨批次身份幂等、真实小样 adapter 和资源测量仍待后续任务，不代表 G0 通过。

依赖 P0-00，可与 P0-01 设计交错。以 [Trace 契约](trace_contract.md) 为准，不直接照搬旧七表或任一参考项目格式。

最小覆盖：

- macro_template、semantic_trace、resource_trace、replay_trace 的能力差异；
- provenance、单位、clock domain、null/零、未闭合事件、来源引用；
- task/attempt/run、agent/request/event、job/session/process/resource scope；
- 包含树与可选依赖链接；共享 scope、多调用关联和未绑定请求；
- execution/evaluation/archive 独立状态；
- Schema 与 adapter 版本，批量分区存储与逐 run 调试视图的映射。

输出计划：`schemas/`、公共模型和版本迁移约定；物理文件数在评审后决定。

验收：合法样例通过，缺身份/自指/冲突 ID/非法时间关系等反例失败；源能力不足时合法保留 null。未知端点不能用 0 补齐；模板无 timestamp 不应被强制制造时间轴。

### P0-03：公共 Adapter 框架

状态：**DONE（单 JSONL 文件框架）**，见 [交付记录](p0_03_delivery.md)及 [接口/限制](adapter_framework.md)。全套 68 项测试通过；来源检查、稳定身份、逐行拒绝、不可覆盖批次与同输入幂等已实现。目录/ZIP、跨来源去重与跨版本视图选择未实现；没有全量转换，也不代表 G0 通过。

依赖 P0-01/02。提供 discover/inspect、normalize、validate 的等价接口，具体 Python 接口按旧模块复用方案定。

要求：读取 catalog locator；流式读取；保留 source record ref；输出新批次；检查真实路径防回写旧源；同输入同配置转换可重复；异常隔离且有 reject 清单，不静默丢行。

验收：小样 round-trip/血缘可追溯；重复 ingest 不新增 run；故意将输出指向旧目录或其软链接时拒绝；输入输出重叠时失败。

### P0-04：AgentX Adapter 与回归

状态：**DONE（小样范围）**，见 [交付记录](p0_04_delivery.md)。全套 87 项测试通过，真实 AX-7/AX-SUB 的请求/token/prefix/round-trip 检查通过；IR 0.2 的标签/未知精度补齐及显式迁移已测试。没有全量 ingest 或 G0 验收。

依赖 P0-02/03。已有数据原地读取，不重新下载。

先完成小样再批量。核对 request/subagent 语义、时间单位、完整 hash/prefix 元数据；分别声明 main/all-agents 聚合；不虚构 Tool payload、完整 Tool 总数、turn 定义或 run 边界。

验收：P0-00 列出的 AgentX fixtures 逐指标匹配手算结果；模型计数/token/time 范围一致；并发总 work time 与 wall span 分开；缺失 latency 不能得到伪造零耗时。

### P0-05：Applied Compute Adapter 与回归 ✅ DONE（2026-09-10）

状态：**已完成 P0-05 小样范围验收**。实现 Applied Compute v1 normalize、严格校验、Metric IR、合成 30 项回归、真实 AC-N2 小样检查和交付文档。无全量 ingest、无 API 请求、无第三方代码执行。

依赖 P0-02/03。三个 JSONL 分别以独立 source_id（applied_agentic_coding/applied_code_qa/applied_office_work）登记。

按固定版本 trie 文档及 client 实现核对：N 个 tool-use turns → N+1 次模板 completion；初始、逐请求、最大上下文及总输入分别计算；模板值/展开不能标为执行实测，不能生成虚假的 wall-clock。

验收：N=0、N=2、缺长度、向量长度不一致等样例；无效输入显式报告。报告保留 production-derived 身份和 macro_template profile。

### P0-06：SWE-bench Trajectory Adapter

依赖 P0-02/03；不阻塞 G0/P1 试点。复用候选含 OpenHands/SWE-agent 解析，按实际格式版本处理。

保留 LLM/Tool/result、shell、edit/test、可用 token/timestamp 和 outcome；分类规则与 parser 分离；未知时间/token 保留 null。

验收：固定来源键和版本的两类格式样例及失败/缺失反例；血缘和状态检查通过。全量前可选各约 10 条作人工抽查，不用随机抽样替代确定性测试。

### P0-07：Workload Catalog 与采样设计（PARTIAL）

历史候选阶段为 **PARTIAL**；“首选模型/harness/verifier 待确定”已由后续配置核实和 RUN-01/RUN-02 交付取代，不再是当前阻塞。首个 Coding 试点已固定并运行；正式多场景代表性集合仍未完成。[旧收尾任务书](p0_07_g0_handoff.md)仅作历史定位，当前不重复执行。

初版依赖 P0-00，随宏观/试点结果更新。四类为覆盖目标，不是四类必须同时完成的开工门槛。

输出：`workload_catalog/{coding,office,assistant,video}.yaml`、`docs/benchmark_selection.md`；场景/软件栈概览写 `docs/agent_landscape.md`，来源与可执行性矩阵写 `reports/quality/benchmark_matrix.csv`。

每项记录 task/asset/code 版本、执行配置与适配差异、可测边界、选择理由、预算、纳入排除规则。将来源内宏观分层与本地任务选择分开；无对应公共分布时标 coverage-driven pilot。

验收：每种计划场景有候选与限制，首个试点已明确；不宣称“公开生产总体代表性”，不擅自增加 benchmark。

### P0-08：Macro Analyzer（DONE，最小小样范围）

状态：**DONE（最小小样范围）**；v6 功能及测试隔离收尾已验收，175 项隔离测试和显式真实小样/联合分析命令通过。当前报告为 `reports/macro/macro-pilot-v6/`；不代表全量分析或 G0 通过。

依赖最小已验收 adapters + P0-09 的 coverage 规则；与 P0-09 同批推进，不先生成漂亮报表再补质量。

指标：turn/request/Tool、token/context、可测 latency、观测跨度/真实 duration、子 Agent、phase、分布及 missingness。所有指标输出 definition/scope/unit/evidence/n_valid。

先来源内统计，再在语义可比的层内比较；模型时间求和、区间并集、overlap 分开；不能混合 template_parameter 与 observed 得到无标记总分布。小样 P99 可以不报告。

验收：gold fixtures 的均值、分位数、重叠时间、缺失与零、层级聚合结果可手算；不把 turns-heavy 命名为 CPU-heavy。

输出：`reports/macro/` 的逐来源/场景分层摘要、图表和局限说明。

### P0-09：Trace Quality 与 Coverage（DONE，最小小样范围）

状态：**DONE（最小小样范围）**；v6 sidecar 核对、macro/coverage 对齐及测试隔离已验收；完整质量体系和其他来源仍待扩展。当时 G0 未通过，当前已有通过记录，见顶部摘要。

依赖 P0-02；第一版即进入 G0，后续增量覆盖。

输出：`reports/quality/trace_coverage.csv`、ID/关联/时间/筛选检查与 rejected records。coverage 包含 source snapshot、profile、metric、scope、evidence、n_valid/n_applicable、missing reason。

示例能力仅作待验证假设：

| 来源 | 可能支持 | 不能默认支持 |
| --- | --- | --- |
| AgentX | 请求 token、部分时间、子 Agent 结构 | 完整 Tool payload、本地 CPU、完整 session 边界 |
| Applied Compute | 模板 turns、长度、模拟 delay | 真实起止 timestamp、实测工具 CPU |
| 本地 sidecar | 已绑定请求、运行状态、部分 Tool | 历史未绑定请求的 run 归属、精确执行边界 |
| OS/process collector | 指定 host/scope 的资源 | 远端服务 CPU、所有共享资源的逐调用独占分配 |

验收：字段非空与可用于研究的覆盖分开；成功/失败/未知/不可读数量可解释；新旧数量差异有筛选/去重依据。

### P0-10：既有本地 Trace/Sidecar 接入（VideoWeaver 小样已完成）

当前安排：**VideoWeaver 单来源小样阶段已完成**。详见 [P0-10 交付](p0_10_delivery.md)。P0-06 可暂缓，不阻塞此任务。

依赖 P0-00/02/03。先选一种已有本地来源形成小样，再扩展四套来源。

原生日志为依据，sidecar 为派生输入候选；保留旧转换血缘，避免把聚合 token 和逐请求 token 重复相加。WorkArena oracle、真实模型运行、Video adapted/surrogate 配置分别标识。

验收：多 attempt、多状态、resolved/unresolved 请求、日志接收时间、submit/wait 和缺失 telemetry 均诚实表达。不得为了通过 Gate 发起重采或付费请求。

### G0：最小语义 Gate（已有通过记录；以下保留原验收清单）

- [ ] P0-00 审计与复用边界清楚，旧数据只读策略可检查。
- [ ] 最小 Schema 覆盖三种输入：AgentX 小样、Applied 模板、一种已有本地 trace。
- [ ] 手算 fixtures 验证身份、N+1、context、时间/并发、缺失和聚合范围。
- [ ] 最小宏观与 coverage 同时输出；所有已知误导性指标被修正或停用。
- [ ] 首个资源试点的任务、配置、可测边界和预算确定。

G0 通过即可进入 P1 小闭环；不要求全量转换、所有 SWE/OSWorld adapter 完成或最终 Schema 永久冻结。

## 5. P1：本地语义与资源归因

### P1-00：采集可行性与授权边界（新增）

依赖 G0。历史记录：PREP-01 曾获准在 G0 前做本机只读能力发现与自有离线准备代码；该准备不代表 P1-00 全项完成。完整 P1-00 计划检查 cgroup v2 delegation、namespace/容器布局、计数器、时钟、进程可见性、PMU/perf 权限以及 collector 自身开销；本段不构成当前下一步授权。

输出 capability report 和降级方案；只读 preflight 不得自动修改系统全局配置或清理他人 cgroup。需要提权、付费 API、新基础设施或大规模任务时另行明确授权。

### P1-01：Semantic Recorder

依赖 P1-00 与 P0-02。记录 run/LLM/Tool 起止及结果、取消/异常；区分调用与后台 job、service，关联 submit/poll/wait。

同机 monotonic + UTC anchor；保留未闭合事件。demo 使用确定性假 LLM/Tool 明确标 synthetic，只用于测试。

验收：串行/并发/超时/异常/异步样例，ID 可传播到 proxy 与 child process；不同 clock domain 不直接相减。

### P1-02：Process Collector

依赖 P1-00/01。优先 /proc、启动 wrapper 和已知进程树；不一开始依赖 eBPF。

保存 host/boot、PID namespace、PID/PPID/start identity、exe/cmd、生命周期和采集方法。长进程轮询可用；短进程和 reparent/daemonize 必须通过样例揭示遗漏。

验收：多级子进程、瞬时退出、PID 重用、后台 job；独立计数基准对照。未观测到进程不能等同没有 CPU。

### P1-03：cgroup / Resource Scope Collector

依赖 P1-00/01/02。借鉴 AgentCgroup 边界思想，不默认每个 Tool 都有专属 cgroup。

专属子进程在开始工作前进入 scope；异步任务 scope 延续到 job 生命周期结束；常驻服务保留 service/run scope；远端仅测本地 client。scope 与调用通过关系关联。

目标布局示意：run 作为聚合节点，runtime/service/job/tool 为适用的叶 scope，监测器在被测层级外；具体 controller 布局遵守目标内核约束。

采集 cpu.stat、memory.current/peak、io.stat 及可用 memory.events/stat；记录不支持项。退出码 137 不能单独证明 OOM。

验收：子进程继承、常驻共享、异步后台、scope 创建失败/进程迁移失败均可解释；不迁移常驻进程后宣称旧内存随之转移。

Cleanup 必须限定本次创建且身份可确认的 scope；不因 Tool 返回杀死存活 job。记录残留/失败并有可恢复处理，不强制递归删除共享目录。

### P1-04：Resource Sampler

依赖 P1-03。时间序列以 run_id、resource_scope_id、host/clock、timestamp 为键；tool_event_id 可空，不能强行单值归因。

500 ms 与 100–200 ms 为试点候选；结合边界累计计数器测短任务。记录 counter/gauge/peak 类型、reset 与采样实际间隔。

验收：不仅检查样本数量，还检查 CPU/I/O 增量、短突发遗漏、内存口径、采集开销；数值误差与容差写入报告。

### P1-05：Timeline Alignment 与核对

依赖 P1-01～04。将 semantic/job/process/scope 关联，保留时钟对齐误差和归因方法。

输出调用 wall、job wall、累计 CPU、采样/内核 memory peak、I/O、overlap、uncovered 与可加计数残差。父 scope 与子 scope 不重复累加；共享 scope 不复制到每个 Tool。

验收：确定性串行、并行、后台和共享服务样例能核对；memory peaks 不错误相加；不能从时间重合直接推断因果。

### P1-06：Tool / Phase Classifier

保留 raw tool/interface、operation category、software、规则版本和 unknown/confidence。

类别覆盖 Read/Search/Write/Edit/Execute/Test/Compile/Browser/Document/Media/API/Verification/Repository/Other；依据 command/exe/arguments，不能只凭 bash/python 名称分类。

phase 可重复、回退和交错；复合命令允许 multi-label 或 mixed。验收人工标注样例与混淆/未知统计，不把 Explore→Modify→Verify 当固定执行流程。

### P1-07：Coding Runner

优先 SWE-bench Verified；必要时对照 SWE-rebench/AgentCgroup 的固定任务版本。先一条闭环，再约三条 smoke；不直接跑全量。

保留原生日志、metadata、模型/工具事件、process/scope/resource、verifier 与输出 artifact；初始化/收尾计入明确范围。模型/API 参数与镜像固定并记录。

验收按 G1，而非只看任务成功率；task 失败但测量完整可作为有效失败样本。

### P1-08：Office / Computer Runner

先复用 DocOps 经验；可选 XLSX/PDF/Document 小样。常驻服务覆盖不足时引入 OSWorld 或已有浏览器任务，WorkArena oracle 只作为 oracle 测试。

明确 Python/LibreOffice/Chromium/PDF renderer 的 scope；共享服务不冒充单 Tool 独占。记录 GUI/资产版本与适配差异。

### P1-09：Assistant Runner

以 ToolSandbox 为候选，核对进程内工具、状态操作与远端 API 边界。测 local CPU、service scope、网络等待及状态操作；不以 CPU-heavy 为纳入条件。

不能为获取 per-call cgroup 任意把进程内函数改造成子进程而仍声称测的是原 workload。若做该改造，另列配置与研究问题。

### P1-10：Video Runner

GEN：VideoWeaver；EDIT：AgenticVBench。分别约 2～3 条 smoke 是预算建议，不是首个 G1 的前置条件。

追踪本地 ffmpeg/python/opencv 与远端 job submit/poll/complete；区分远端媒体生成等待和本地计算。替代模型/服务、任务、asset、harness、verifier 差异需登记。

原始 session 在环境销毁前的导出与权限要预检；归档状态不能覆盖 execution/evaluation。

### P1-11：Smoke 与资源归因 Gate

先按执行机制覆盖：独立子进程、常驻/进程内服务、异步作业；远端不可观测声明。确定性测试加一个可行真实 Runner 足以进入 G1 评审。

四场景逐步各做少量 smoke，分别记录已覆盖机制和未验证边界；不要求它们同时到齐才开始 CPU 试点。

### P1-12：扩大 Characterization 与重复实验

依赖对应场景的 smoke 和 G1；先由 P2 试点反馈修正测量。

#### 当前小批次设计（2026-09-20，离线，未授权运行）

长期 50～75 task 数量仍仅为后续规模建议。当前先做 Coding 小试点，不恢复 CPU-02，不以 perf/Replay 可用作为普通容器资源观测的前置。Office/Computer 保留第二阶段候选，尚未证明其 runner、初态与产物验证可用，不与 Coding 一起承诺执行。

本地 `data/raw/public/**/record.json` 盘点只有 `django__django-16485` 一个 SWE-bench 记录（固定 revision `78f471bf655a3137b2e8a75af1501690ec009ec3`）。两个历史 attempt 不增加 task 数，也不自动算作新试点的受控重复。公开 trace 小样不等价于可直接执行的 benchmark task。

最小选样提案：同一固定数据集内 3 个不同 Coding task，每个 3 次重复，共 9 个计划 attempt。至少需再取得 2 个不同 task 的完整记录；目前不命名不存在的本地候选、不下载。选择前登记规则：本平台镜像/官方评估可用性、许可和安全范围优先；再依据题目/补丁或公开元数据中的测试、搜索、编辑工作类型覆盖选样，不使用待测 CPU 或运行成败事后挑选。若仅选 Django，应明确项目内覆盖，不能外推整个 Coding 类别。

执行前冻结 task清单、排除理由、随机种子/区组顺序（每轮每task一次）、模型/环境、正确性判据和失败处置。原任务历史数据仅作参照；重复3次不等于允许失败后自动重试。遇基础设施/清理/安全失败停止批次，剩余计划样本未运行，不能偷偷补齐；任务 resolved=false 与基础设施失败分别记录。

| 预算项 | 初步上限推算，不是授权 |
| --- | --- |
| attempt | 3 task × 3 repeat = 9；自动 retry=0 |
| 模型请求 | 每attempt不超过30，总不超过270 |
| 输出 token | 每请求4096上限，理论总上限1,105,920；不是预计用量 |
| wall | 参照既有配置每attempt30分钟，9次为270分钟；批前预检、归档和清理总预算必须在真实入口中另行闭合，不能据此直接运行 |
| 容器 | 顺序执行；沿用原试点资源提案4CPU/8GiB，但不同task须验证足够且不擅改 |
| 成本 | 输入token与当前计价未确定，金额上限待用户批准；成本未闭合不得 READY |

当前 ready=false：缺新增记录、镜像身份/可用性确认、逐task评估条件、货币预算和独立新批身份。下一安全动作是审批“指定revision的有限候选元数据/记录获取范围”，不是直接请求9次运行。获取和执行分别审批；不拉镜像、不安装、不联网，直到用户明确授权相应步骤。

离线交付已落实：选样单位、排除原则、预算推算、失败规则与统计口径（见 methodology 的 Evidence → Allowed Claim）。后续收齐记录后复用现有 runner/hook/analyzer；不复制 RUN-02 入口或新建通用执行框架。完成选样不等于完整 P1-12 或 G2 验收。

建议预算：Coding 15～20、Office 15～20、Assistant 10～15、Video GEN 5～10、EDIT 5～10，合计 **50～75 个不同 task**；不是 Gate 或统计充分性承诺。

来源内 short/median/tail、Tool mix 与资源试点共同选样；无可比公开来源的场景按覆盖目的解释。普通任务先按 3 runs、重点 5 runs 估算预算，正式数量由变异/精度/成本决定。

保留全部新采 attempts 及三类状态；预先写筛选规则、随机化/区组策略、任务级统计单位和重试预算。重复运行不增加独立 task 数。

### P1-13：Tool / Run Resource Analyzer

输出 scope 与归因方式分层的调用数、wall/job time、CPU core-seconds、平均使用核心数、memory、I/O、进程 fan-out 与未归因残差。

聚合按 source/config/scenario/benchmark/task/run/category/software；CPU/wall 不称算法效率，Top Memory 与 Top CPU 独立排名。

输出 `reports/resource/` 的摘要、timeline、coverage 与限制。共享 service 和 Agent runtime 不得从 E2E 报告消失。

### G1：资源归因小闭环 Gate（登记范围 PASSED）

当前集中判定：[G1 集中评审 §0](g1_consolidated_review.md)：RUN-02-R2 与 G1-01/G1-02 共同满足下列小闭环要求。勾选只适用于登记 scope 与机制，不是全平台支持。I/O null、shared CPU、宿主非完整后代树等边界继续保留；正式 perf 比较必须重新登记其测量条件，新实验另批。

- [x] 目标 scope 的语义、process、资源可关联，独占/共享/未知明确。
- [x] 短进程、后台作业、常驻服务、异常退出、时钟/采集延迟有测试。
- [x] CPU/I/O 计数核对、memory 口径、重叠/残差和遗漏报告通过评审。
- [x] 至少一种真实 Runner 小样与确定性测试闭环，原始日志和三类状态保留。
- [x] Collector 开销已量化；登记比较固定诊断容差与降级边界，不外推为稳定百分比。
- [x] 可找出 CPU/Wall/Memory 的候选 scope；精确 Tool 归因并非所有场景的必需条件。

G1 通过后立即可做 P2 试点；全场景与 50～75 task 目标属于后续覆盖扩展。

## 6. P2：CPU Characterization 与 Hotspot

### P2-01：Representative Case Selector

依赖 G1 和 P1-13。分别选择 Top CPU、Wall、Memory、调用频率及 wait-heavy 对照；按来源/配置/coverage 分层，不把缺失值当低负载。

状态：**离线派生及集中验收材料已完成，限定范围待评审确认**。输入为封存的 RUN-01-C-v2 与 RUN-02-R2 review-v2；输出 [候选清单](../reports/cpu/selected_cases.yaml) 与 [P2-01 review-v1](../reports/analysis/P2-01-review-v1/summary.md)，包含输入/输出哈希、候选角色、精确字段、有效性和限制。wait-heavy 仅为低 host CPU 的假设代理，没有直接 wait 计数；共享 scope 不解释为独占 Tool CPU。此输出不授权 P2-02 perf。

验收：逐项核对来源哈希和字段；缺失值不排序为低负载；候选选择可追溯到 source/run/scope；不得将候选清单解释成新运行或 RUN-01/RUN-02 因果比较。

### P2-02：perf stat Collector

对可测 scope 采 task-clock、cycles、instructions、branch、cache、context-switch、fault；核对进程后代、线程、cgroup 与 host 支持情况。

记录 PMU 型号、事件编码、权限、time_enabled/time_running、multiplexing 与 not_supported；通用 cache-misses 不直接改名 LLC misses。IPC 必须同 scope/同区间。

验收：可支持机器上的已知负载对照；受限平台明确 partial/unavailable，不以填零强行通过。

### P2-03：Microarchitecture Analyzer

结合 PMU、CPU utilization、I/O、调度、进程拓扑和受控实验，输出 compute-heavy、cache/memory-sensitive、branch-heavy、scheduler-heavy、wait-heavy 或 mixed 候选。

低 IPC 不足以证明 memory-bound。证据不足输出候选与待验证假设，不自动产生架构结论。

### P2-04：perf record / FlameGraph

只对候选 scope 采样。保留 perf.data、解析结果、符号版本、unwind 方法、采样丢失与 unknown 比例；报告采样开销。

工具/服务 → 进程 → binary/library/function 的链条有身份依据；共享服务热点只能标其真实归因精度。

### P2-05：Hotspot Parser

输出 `reports/cpu/hotspots.csv`；包含 run/scope、tool 关联方法、binary/library/function、样本比例与分母。

unknown/kernel/loader 可在展示时分组，但不能从分母或原始数据中静默删除；采样占比不冒充精确 CPU 时间。

### P2-06：CPU Requirement Report

将数据、task/run 数、环境、误差、适用范围与假设连同结论输出。

报告区分“观测现象”“可能解释”“受控验证结论”。核心数、SIMD、cache、带宽等诉求需 P2-08 或等价实验支撑；未验证时不生成确定性建议。

### P2-07：Optimization A/B Harness

可选，明确热点和授权后执行；不是 characterization 完成的强制条件。

固定任务/环境/模型或合格 replay，控制顺序与 cache；比较 correctness、wall、CPU、memory 和失败率，按 task 配对/分层，报告重复与不确定性。

### P2-08：受控 CPU Scaling / 对照实验（新增）

依赖 P2 试点。根据 RQ 选择核心/线程数、affinity、数据规模、缓存状态或资源限制等最小矩阵，不要求一次测试所有硬件因素。

RQ1 如需性能比较，定义单次/非 Agent LLM 对照、相同测量范围与 token/模型控制；只有公开形态数据时限制为描述性比较。
RQ3 控制 task/config 差异后讨论 Tool 与场景解释力；RQ4 不从不同机器/不同模型的混杂结果推导 CPU 因果需求。

验收：预注册变量与比较单位，记录干扰项、基线、重复策略及正确性；结论不过度外推。

### G2：CPU 结论 Gate（未验收）

- [ ] 代表样本选择和计量 scope 可追溯，指标不可用项明确。
- [ ] 主要热点可解释且保留 unknown/采样损失。
- [ ] 架构/扩展性结论有受控证据，否则明确为候选假设。
- [ ] task/run 数、重复、筛选、变异和结论适用范围完整。
- [ ] 不要求为“完成任务”而强行提出优化。

## 7. P3：Replay / Runtime / Scale

### P3-01：Replay Spec 与可重放性清单

依赖 G1 后质量足够的源 trace；设计可与 P2 交错，scale 不能跳过保真验证。

当前状态（2026-09-20）：**P3-01 限定离线审计已完成并关闭；v3 修正了关联身份与全局事件完整性核验**。已从 RUN-02-R2 trajectory 的 `function.arguments.command` 逐项重算并核验 hook hash/length、R2 marker/catalog/代码身份、顺序、配对、时长和返回码；不执行导入命令。交付为 [P3-01 v3 inventory](../reports/replay/P3-01-audit-v3/inventory.json)、[summary](../reports/replay/P3-01-audit-v3/summary.md)、[corrections](../reports/replay/P3-01-audit-v3/corrections.md) 和 manifest，详见 [项目总览 §2.2](project_status.md#22-p3-01-离线审计已完成-v3-纠正限定范围)。CPU-02 保持暂停；本项不以 G2 通过为前提，也不替代 G3-R；P3-02 仍需另行批准。

除 source trace/trace_type=replay 外，记录 cwd、argv/shell、stdin、文件初态与编辑、环境白名单、image/software、cache、远端依赖、进程/依赖拓扑和输出验证。

区分 command、文件/状态操作、远端占位及不可重放步骤；不伪造 reasoning/token，不自动执行导入命令。

### P3-02：Replay Executor 与保真验证

先本地/Docker，再考虑其他 backend。支持显式模式：open-loop release、dependency-driven think gap、保持依赖的 fast-as-possible。

禁止 offset+wait 双重等待；调度延迟和排队规则显式化。恢复初态、输出路径隔离，命令执行前审查安全边界。

输出 `reports/replay/fidelity.md`：correctness、依赖、工具/进程形态、wall/CPU/memory/I/O 对比、容差与未复现项。容差在正式比较前固定。

### G3-R：Replay 保真 Gate（未验收）

- [ ] 目标与非目标明确，原始 trace/spec/执行结果三者独立且有血缘。
- [ ] 初态、依赖、输出/状态验证通过。
- [ ] 资源与时序偏差已测，符合所声称的保真目标。
- [ ] 远端替代、不可重放状态及共享资源限制不被掩盖。
- [ ] 安全审查与单实例资源预算通过。

### P3-03：接入 agent_vm_bench

依赖 P0-00 runtime 审计及 G3-R。选择性复用 bench_core/env_provider 和已验证的监测能力；不假定旧 vm_monitor 接口天然兼容。

保留独立配置与版本，通过适配器接入，不在本阶段顺手改造整个旧工程。先单实例验证源/重放身份和监测分母。

### P3-04：Concurrency Matrix

依赖 P3-03 的单实例验证。按资源预算选择 1/2/4/8/16，而不是机械跑满；注明 open/closed-loop、arrival、warmup、计时范围、重复和失败处理。

记录吞吐、延迟、CPU、memory、I/O、page cache、NUMA、startup/ready、失败与 OOM。没有足够观测不能宣称稳定 P99。

### P3-05：Resource Contention Analyzer

结合 CPU/run queue、memory pressure、cache、I/O、NUMA 与控制实验解释扩展瓶颈。区分 workload、runtime、collector 和远端服务的影响。

相同 workload/spec/初态的 backend 对比才具有解释力，不能混合不同模型轨迹当系统 A/B。

### P3-06：Scale Report

输出 `reports/scale/runtime_characterization.md`，说明已通过哪些保真目标、什么资源先受限、runtime 如何改变开销与尾延迟、结论适用范围。

## 8. P4：可选高级工作

- P4-01 eBPF Process / Syscall Trace：现有观测确有无法接受的遗漏时再评估；不得未经授权修改内核/全局策略。
- P4-02 Resource Prediction：以已验证标签、task/source 隔离的训练测试划分为基础。
- P4-03 Agent-aware Scheduling：RQ6 已发现资源调度问题后再提出独立计划，不直接照搬 AgentCgroup scheduler。

## 9. 测试、完成证据与状态管理

所有命令在实现后才可执行。后续 CLI 可采用 `python -m adapters.<name>`、`python -m analyzers.<name>` 等形式，具体参数以实现后的 --help 为准；失败返回非零。

测试层级：

1. Unit：ID、schema、null/零、N+1/context、scope、时间重叠、分位数、状态分类、分类规则。
2. Collector integration：CPU/memory/I/O、短进程、并发、后台、常驻服务、clock skew/日志缓冲、取消及 cleanup。
3. E2E：逐步保留四场景小样；有成本的真实运行与无付费回归测试分开。
4. Replay：初态/依赖/输出/资源保真；不只断言“命令退出 0”。

任务状态用 NOT_STARTED / IN_PROGRESS / PARTIAL / BLOCKED / DONE。Gate 不因写了文档或产生文件就勾选。

每次完成记录：

```text
Task / RQ:
Status:
Input snapshot / reused asset:
Files changed:
Implementation or documentation:
Tests and commands actually executed:
Results / artifact references:
Coverage / known limitations:
Gate evidence / next dependency:
```

本地 Agent 每次按一个边界明确的任务推进；遇到新的权限、费用、迁移、破坏性 cleanup 或范围扩张需先确认。文档中的“可以参考运行”不是第三方代码执行授权。

## 10. 里程碑与当前下一步

本次重新定义里程碑，取代旧版“先全量 P0，再四场景，再 CPU”的串行排期：

| 里程碑 | 交付与 Gate | 当前状态 |
| --- | --- | --- |
| M0 资产审计 | P0-00 清单、来源/筛选、复用与缺口 | **DONE（2026-09-10，r2 审计返修通过；不代表 G0 通过）** |
| M1 最小语义闭环 | 三种来源小样、指标 fixtures、coverage，G0 | 既有 G0 通过记录；历史小样和限制仍按原交付保存 |
| M2 资源归因闭环 | 一个真实 Runner＋机制覆盖测试，G1 | DONE（登记小闭环范围；扩展机制与平台另验） |
| M3 CPU 试点 | PMU/hotspot/受控实验可行性，反馈测量设计 | PARTIAL：CPU-01 合成可测性完成；P2-01 小样分析已交付；CPU-02 暂停，G2 未通过 |
| M4 多场景正式 Characterization | 扩展任务与重复，宏观/资源/CPU 分层报告，G2 | NOT_STARTED |
| M5 Replay / Scale | G3-R、runtime 接入、并发报告 | P3-01 限定离线审计已关闭；executor、保真实验与 scale 未开始 |

P0-00-r2、P0-01～05、P0-10 小样和 P0-08/09 最小集已验收。模型=DeepSeek-V4-Flash，harness=mini-SWE-agent 2.4.6，任务=django__django-16485；任务记录获取与 wheel 静态核实已完成，不再重复询问这些选择。

PREP-01 已通过集中验收（2026-09-11，231 项项目外 cwd 测试、两条泄漏反例和报告哈希复核通过）；完成安全输入/配置准备、离线测试、只读预检和审批清单，不代表真实运行兼容性或 G0/G1 通过。

ENV-01、SMOKE 与 RUN-01 的后续进度以上方最新记录为准，不重复安装/连通性验证。历史下一批记录为 [RUN-02](run_02_handoff.md)；当前已由 RUN-02-R2 证据和 CLOSEOUT-01 收尾取代，不构成新的执行授权；G1-01 B1 不重复执行。

后续按里程碑集中推进：准备包 → 用户确认后的单任务真实闭环 → 资源归因 G1 → CPU/Hotspot 试点 → 多场景扩展 → Replay/Scale。P0-06、全量转换、四场景齐备不阻塞首个小闭环。验收一次集中列出关键问题，运行前依赖与非关键待办分开，不为历史措辞或未启用路径单独开返修轮。
