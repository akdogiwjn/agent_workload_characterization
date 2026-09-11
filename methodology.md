# AI Agent Workload Characterization 详细实施方案

初版修订日期：2026-09-10；进度更新：2026-09-11。已完成 P0-00-r2～P0-05、P0-10 VideoWeaver 小样、P0-08/09 最小宏观/coverage（当前依据 reports/macro/macro-pilot-v6 与 175 项隔离测试，当前 IR 0.2）；P0-07 PARTIAL，模型/harness 已选、任务记录与 mini 2.4.6 静态核实完成；G0 READY_FOR_REVIEW 未通过，未执行采集/实验。下一批见 [首次运行准备包](docs/first_run_preparation_handoff.md)，当前只准备任务书。已有旧工程产物不等于新项目指标或采集链路验收通过。

配套文档：[开发任务与 Gate](docs/development_tasks.md)、[数据管理](docs/data_management.md)、[Trace 语义与测量契约](docs/trace_contract.md)。本文给出研究方法；具体开发顺序以任务计划的依赖和 Gate 为准，第 8～19 节的阶段是研究模块而非强制串行排期。

## 1. 项目定位

### 1.1 总体目标

本项目不是单纯做一个“Agent Benchmark 排行榜”，也不是单独研究某一个 Agent 框架，而是建立一套：

**面向 CPU / OS 的 AI Agent Workload Characterization 方法、代表性负载集和分析工具链。**

最终需要回答：

1. 当前主流 AI Agent 有哪些典型使用场景？
2. 不同场景采用什么 Agent 架构、软件栈和工具栈？
3. Agent 与传统单次 LLM workload 相比，在执行形态上有什么不同？
4. Agent 的时间到底花在 LLM、Agent 本体、Tool、Sandbox、I/O 的哪部分？
5. Coding、Office、Assistant、Video 等场景分别会调用哪些核心 Tool？
6. 这些 Tool 对 CPU、内存、存储、网络产生什么系统负载？
7. CPU 消耗集中在哪些程序、库和热点函数？
8. Agent workload 对 CPU 架构有什么诉求，例如单核性能、多核、Cache、Memory BW、SIMD、I/O、调度等？
9. 多 Agent 并发时是否会产生资源突发、竞争、尾延迟和 Sandbox 扩展问题？
10. 能否通过软件、Runtime、资源调度或 CPU 架构优化提高 Agent workload 的执行效率？

项目研究主线为：

```text
Public Trace ──→ 来源适配 ──→ 宏观行为、覆盖与采样依据
                              ↕ 共享语义 IR
Real Agent Run → 原生埋点 ──→ Tool / Job / Process / Resource Scope
                              ↓
                      CPU Characterization / Hotspot
                              ↓
                      受控验证 / 软件优化
                              ↓
                      Replay 保真 → Runtime / Scale
```

这不是将公共 trace 自动转换为同一 workload 的真实运行。两路数据的来源、筛选和观测能力不同；公共数据补充行为分布，本地执行补充系统观测。统一的是语义和血缘，不是伪造两者相同的统计总体。

以后新增 Benchmark、Agent 框架或者 Trace 时，都必须说明对应的研究问题和证据缺口，不为了覆盖数量无限增加工作量。

### 1.2 本地已有资产与数据边界

已有公共数据、生成结果、sidecar 和宏观分析代码分别位于旧项目的 `benchmark/agent_benchmark_traces/`、`benchmark/traces_generation/`、`benchmark/benchmark_analysis/` 等目录。完整入口和处理规则见 [数据管理](docs/data_management.md)。

原始数据原地保留、逻辑只读；新项目统一登记、转换和分析。新开发不在旧目录继续展开，不修改原始日志，不搬迁或恢复归档，不修改 `references/repos/`、`references/papers/`。旧 adapter 的身份、时间和聚合错误应通过新项目测试与派生数据修正，不能把旧报表直接当正确基线。

---

# 2. 最终交付物

整个项目最终至少形成 5 类成果。

## 2.1 Agent 场景与软件栈全景图

输出：

`docs/agent_landscape.md`

内容至少包括：

* Agent 典型场景；
* Agent 基本架构；
* Agent Runtime；
* Agent Harness；
* Tool 系统；
* Sandbox；
* Model API；
* Memory / State；
* 主流开源社区；
* 对应 Benchmark；
* 是否有公开 Trace；
* 是否适合本地复现；
* 是否适合 CPU workload 分析。

重点不是罗列项目，而是回答：

> 不同 Agent 最终落到系统层到底运行了什么软件。

---

## 2.2 Agent Benchmark / Workload Catalog

输出：

`workload_catalog/{coding,office,assistant,video}.yaml`

以及：

`docs/benchmark_selection.md`

先冻结试点范围与选样规则，正式代表性集合在资源/CPU 试点后评审。Catalog 不等于证明了生产代表性。

建议固定为四大类。

| 大类                      | 主要 Benchmark                     | 主要目的                                                  |
| ----------------------- | -------------------------------- | ----------------------------------------------------- |
| Coding Agent            | SWE-bench Verified / SWE-rebench | Coding、Shell、Test、Compile                             |
| Computer / Office Agent | OSWorld 2.0 + DocOps             | Browser、GUI、Document、Python                           |
| Assistant / Tool Agent  | ToolSandbox，可补其他 API benchmark   | API、状态管理、tool dependency                              |
| Video Agent             | VideoWeaver + AgenticVBench      | Video generation / editing / FFmpeg / multimodal tool |

WorkArena++ 可以保留，但定位为：

**Enterprise Workflow 扩展负载。**

不是第一阶段必须全量跑的主 Benchmark。

已阅读的本地 DocOps 参考快照包含 210 个 Word、Excel、PowerPoint、PDF 操作任务，并带有 artifact-level deterministic verifier 和 Harbor 执行结构，很适合作为 Office Agent 本地可执行负载。

VideoWeaver 作为生成型 Video Agent 的 Tool orchestration 候选；任务类别、数量和 asset 对应关系需以选定版本清单核实，不把尚未核对的“16 类、285 个 case”作为实验事实。本地替代模型/远端服务配置需标为 adapted 或 surrogate，并说明与参考配置差异。

已阅读的 AgenticVBench 参考材料描述 100 个真实视频后期制作任务，包含 Assembly、Repair、Sequencing、Repurpose，并采用 sandboxed Harbor execution，适合 Video Editing Agent。

OSWorld 2.0 用于 Computer-use / GUI 类负载。复现实验时必须固定官方 release，不允许把不同版本 task、asset、code 混用；本地已阅读文档提及 `osworld-v2-2026.08.08`，具体实验选用版本仍需登记实际 commit/release 和 asset，不将该记录当作实时“最新版本”声明。

---

## 2.3 统一 Agent Trace 数据集与分析工具

输出：

```text
schemas/
adapters/
data/catalog/
data/normalized/
analyzers/macro/
reports/quality/
reports/macro/
```

统一处理：

* AgentX；
* Applied Compute；
* SWE-bench trajectories；
* OSWorld trajectories；
* 本地生成 Coding Trace；
* 本地生成 Office Trace；
* 本地生成 Video Trace；
* 以后新增的其他 Trace。

---

## 2.4 Agent Tool / CPU Characterization 报告

输出：

`reports/cpu/cpu_characterization.md`

主要回答：

* 哪些 Tool 最常调用；
* 哪些 Tool wall time 最大；
* 哪些 Tool CPU time 最大；
* 哪些 Tool memory peak 最大；
* Tool 的资源使用是否存在 burst；
* 不同 Agent 场景有什么系统行为区别；
* CPU 是 compute-bound、memory-bound、latency-bound 还是 I/O-bound；
* CPU hotspot 在哪里；
* 软件优化点在哪里；
* CPU 架构诉求是什么。

---

## 2.5 Agent Runtime / Sandbox 并发实验报告

优先审计并复用现有：

`agent_vm_bench`

重点研究：

```text
Sandbox startup
Ready time
Idle footprint
Concurrent density
CPU contention
Memory contention
Page cache
Disk I/O
NUMA
Tail latency
Runtime scalability
```

已有 `bench_core` 与历史 `vm_monitor` 是 Runtime / Replay 层的复用候选；先审计其所在版本、backend、监测范围与接口，不假定新 bench_core 与旧监测链路可以无缝连接。接入前需通过单实例验证与 Replay 保真 Gate，不在本阶段重构旧工程。

---

# 3. 整体方法需要借鉴哪些工作

不是复现某一篇论文，而是不同工作借鉴不同部分。

## 3.1 AgentSysBench：借鉴整体系统分析框架

AgentSysBench 是本项目整体方法最重要的参考之一。

它的核心思想是：

**不能把 Agent workload 和 Serving System 混在一起。**

它把 workload 与 serving environment 分开考虑，并对 LLM、Tool、Sandbox、State、Resource、Data Movement 做统一 instrumentation。研究覆盖十类代表性 Agent application，而不是只测模型请求。

本项目借鉴：

```text
Agent Application
       ↓
LLM
Tool
Environment
State
Sandbox
       ↓
Unified Instrumentation
       ↓
Latency
Resource
Data movement
State footprint
```

特别需要借鉴它的思想：

```text
Observed Performance = Φ(Workload, Serving System)
```

也就是说：

同一个 Coding Agent 在不同系统上可能表现成：

```text
LLM bound
CPU bound
Sandbox bound
Memory bound
Network bound
```

所以任何 CPU 结论都必须记录：

* Hardware；
* OS；
* CPU；
* Memory；
* Agent；
* Model；
* Tool；
* Container；
* Runtime；
* Benchmark；
* Software Version。

不能把环境导致的瓶颈错误归因给 Agent workload。

---

# 4. AgentCgroup：重点借鉴系统层方法

AgentCgroup 是本项目 Tool / OS characterization 部分最重要的参考。

但不要把目标变成“复现 AgentCgroup”。

AgentCgroup 研究的是：

```text
Coding Agent
    ↓
Tool Call
    ↓
OS Resource
    ↓
cgroup
    ↓
Resource Management
```

它在 SWE-rebench Coding Agent 上分析 tool-call-level OS resource dynamics，并发现 Tool execution 与资源 burst 强相关，因此进一步使用与 Tool Call 对齐的 hierarchical cgroup 做资源管理。

本项目主要借鉴其前半部分：

```text
Agent Execution
      ↓
Tool Call Boundary
      ↓
Process / Child Process
      ↓
cgroup
      ↓
CPU / Memory / IO Timeline
      ↓
Resource Characterization
```

---

## 4.1 借鉴一：Tool Call 是系统分析的重要边界

不要只测整个 Agent：

```text
Agent task:
duration = 180s
avg CPU = 25%
peak RSS = 4GB
```

这种信息过于粗。

需要变成：

```text
Agent
│
├─ LLM
│
├─ Tool #1
│   └─ pytest
│
├─ LLM
│
├─ Tool #2
│   └─ git grep
│
├─ LLM
│
└─ Tool #3
    └─ python
```

分别得到：

```text
Tool
Wall Time
CPU Time
CPU %
Peak RSS
Read/Write
Page Fault
Process Count
Exit Code
```

因此统一 Collector 应按来源能力表达下列信息；无法测量的部分保留 null 和原因，不强制每个 Tool 都有 PID/cgroup：

```text
tool_start
tool_end
tool_id
tool_type
command
pid
child_pids
cgroup_id
```

Tool 是语义边界，不总是资源所有权边界。调用返回、后台 job 完成和资源生命周期结束必须分开；submit/poll/wait 可关联同一个 job，常驻浏览器/进程内函数可能只能测 service/run scope。远端 API 只能直接说明本地 client 资源和已观测延迟。

独立子进程可使用专属 scope；共享资源保留共享项，时间窗口分摊须标估计。不能给每次调用复制整个共享 scope 的资源再求和，也不能因调用返回而清理仍有后台工作的 scope。run 级观测同时覆盖初始化、Agent runtime、工具、服务、收尾与未归因开销。具体契约见 [资源归因边界](docs/trace_contract.md#6-资源归因边界)。

---

## 4.2 借鉴二：Agent Trace 与 OS Trace 时间对齐

必须同时保存：

```text
Semantic Timeline
```

和：

```text
System Timeline
```

最终能够形成：

```text
LLM  | pytest        | LLM | grep | LLM
-----+---------------+-----+------+----
     ↑
     CPU burst
     RSS burst
     processes ↑
```

后续所有 CPU / Memory 结论都尽量能定位回：

> 哪个 Agent Step、哪个 Tool Call、哪个命令导致。

---

## 4.3 借鉴三：分析时间序列，不只看平均值

AgentCgroup 的实验显示 Agent Tool 可能具有很强的资源突发性，因此：

```text
avg CPU
avg RSS
```

只能作为摘要指标。

必须同时保存：

```text
CPU timeline
Memory timeline
IO timeline
Process timeline
Tool timeline
```

建议 Sampling Interval：

```text
基础监控：
500 ms

重点 CPU-heavy Case：
100~200 ms
```

上述间隔只是试点候选，不是正确性保证。短进程与短 burst 需结合边界累计计数器/生命周期事件，并测量轮询遗漏；正式比较前固定误差容差。不要一开始所有任务都使用极高频率 eBPF/perf，避免 instrumentation overhead 影响 workload；Collector 自身开销需独立记录。

---

## 4.4 借鉴四：Trace Replay

AgentCgroup 提供 trace collection / replay 思路。

本项目也采用：

```text
真实 Agent + Benchmark
        ↓
Generate Trace
        ↓
抽取 Tool Sequence
        ↓
Replay
        ↓
Docker / E2B / VM
```

但是必须区分：

### Real Agent Run

用于：

* Agent 行为；
* LLM；
* 实际记录的 reasoning/action 信息（不反推隐藏思考）；
* 真实 Tool sequence；
* 真实 dependency。

### Replay

用于：

* 系统重复实验；
* 并发与资源限制；
* Sandbox / CPU / 不同 Runtime。

Replay **不能冒充真实 Agent Trace**。重放前要捕获环境、输入/文件修改、依赖、缓存和状态；远端服务或交互式状态不可复现时说明限制。先验证输出/状态、执行结构和资源保真，再扩并发，而不是只抽出 shell command 即宣称等价。

---

# 5. CPU-Centric Perspective：借鉴 CPU 分析方法

`A CPU-Centric Perspective on Agentic AI` 的价值主要在于提醒：

> Agent 并不是单纯 GPU inference workload，Tool / orchestration 等 CPU-side processing 可能成为非常重要的系统成本。

该工作对多个 Agent workload 做 CPU-centric characterization，并报告部分测试中 Tool processing 可以占端到端时延的很高比例。这里的具体数字只能作为研究参考，不能直接推广到本项目场景。

本项目重点借鉴：

```text
Agent
 ↓
Tool
 ↓
CPU workload
 ↓
microarchitecture
```

增加：

* cycles；
* instructions；
* IPC；
* LLC miss；
* Cache MPKI；
* Branch miss；
* Context switch；
* Page fault；
* CPU utilization；
* runnable tasks；
* CPU scaling；
* energy（有条件时）。

---

# 6. Agentic AI Workload Characteristics：借鉴执行阶段分析

该工作发现 Agent Tool 使用具有明显时间结构，例如 Agent 执行过程中可能从早期 read/explore 转向后期 execute/write。

因此本项目不要只统计：

```text
grep 20次
pytest 5次
```

还应该分析：

```text
Agent Phase

0%---------30%---------70%---------100%

Explore     Modify       Execute/Verify
```

以下是分析标签候选，不是预设所有任务必经的单向阶段；phase 可以回退、交错、重复，需保存规则和未知/置信状态：

```text
Explore
Read
Search

Modify
Write
Edit

Execute
Test
Compile
Render
Verify
```

观察：

* Tool 是否具有阶段性；
* CPU burst 集中在哪个阶段；
* memory peak 出现在哪个阶段；
* 后期 Verification 是否成为主要 CPU 开销。

---

# 7. AgentX / Applied Compute：借鉴宏观真实负载分布

这两类数据主要用于：

> 描述所发布、经筛选或变换的样本中的 Agent workload shape；不是无条件的生产总体分布。

不要用它们直接做本地 CPU hotspot。

AgentX 是 trace-derived agentic inference workload，重点保留 multi-turn、context growth、prefix reuse、tool delay、subagent 等 workload shape，用来研究 inference serving，而不是本地 Tool CPU。

Applied Compute 已公开 production-derived：

```text
agentic coding
code QA
office work
```

workload 模板，保留 multi-turn、Tool delay 等参数。模板统计与原始执行测量要分开：N 个 tool-use turns 对应 N+1 次模板 completion；初始 prompt 不等于总输入或最大 context，不可构造真实执行时间戳。

所以：

```text
Public Trace
      ↓
Source-conditioned Distribution
      ↓
Representative Case Selection
```

而不是：

```text
Public Trace
      ↓
直接推出 CPU 需求
```

---

# 8. 第一阶段：建立 Agent Workload 全景图

## 8.1 目的

回答：

> Agent 到底有哪些主要 workload，系统里真正运行的东西是什么？

---

## 8.2 工作内容

每一个 Agent 场景记录：

```text
Scenario
Agent Framework
Agent Harness
Model
Memory / State
Tool
Environment
Sandbox
Runtime
Benchmark
Public Trace
Local Reproducibility
```

重点场景：

```text
Coding
Office / Document
Computer Use / Browser
Assistant / API
Video Generation
Video Editing
Enterprise Workflow
Research / Retrieval
```

第一版最终收敛到四类核心 workload：

```text
Coding
Office / Computer
Assistant
Video
```

---

## 8.3 输出

```text
docs/agent_landscape.md
reports/quality/benchmark_matrix.csv
```

---

## 8.4 验收标准

每个核心场景至少明确：

* 一个主要 Benchmark；
* 一个可运行 Agent；
* 核心 Tool；
* 可否获得公开 trace；
* 是否可以本地生成 trace；
* 系统层主要软件。

完成后停止无限增加 Benchmark。

---

# 9. 第二阶段：建立统一 Trace IR

这是整个工程优先级最高的基础工作之一。

## 9.1 目标

不同数据源统一语义、身份与血缘，不强制具备相同字段或观测能力。支持宏观模板、语义事件、资源测量与 replay profile；逻辑 IR 不等于单一物理文件格式。先做最小样例和手算指标测试，再决定分区 Parquet 或逐 run 文件视图。

例如：

```text
run
│
├─ metadata
│
└─ events
```

---

## 9.2 Metadata

至少保存：

```text
source_id / snapshot_id / source_record_ref
schema_version / adapter_version / profile / trace_type
run_id / attempt_id / task_id
scenario
benchmark
benchmark_version

agent
agent_version
harness
harness_version

model
model_provider

machine
cpu
memory
kernel

container
runtime

start_time
end_time
execution_status / evaluation_status / archive_status
success / score
metric provenance / scope / coverage
```

ID 必须区分多模型、多次 attempt，并防止同一原始 run 重复 ingest；模板和未绑定 telemetry 不虚构 execution run。来源、时间、缺失、关联规则以 [Trace 契约](docs/trace_contract.md) 为准。

---

## 9.3 Event

建议统一：

```json
{
  "event_id": "<stable-event-id>",
  "parent_id": null,
  "type": "tool",
  "clock_domain": null,
  "start_ns": null,
  "end_ns": null
}
```

公共字段示例只表达语义，不是最终 Schema。未知时间为 null，不补零。parent_id 表达包含树，并行分支可共存；依赖/join 用可选 typed links。job/process/resource scope 独立标识并关联，多对多共享关系不能塞入一个必填 tool_event_id。

### LLM Event

```text
model
input_tokens
output_tokens
cached_tokens
context_length
ttft
api_latency
```

### Tool Event

```text
tool_name
tool_category
command
arguments
start/end
exit_code
pid
cgroup
```

### System Event

```text
cpu_time
cycles
instructions
rss
io
page_fault
network
```

---

# 10. 第三阶段：Public Trace 宏观分析

## 10.1 输入

第一批：

```text
AgentX
Applied Compute
SWE-bench trajectories
OSWorld trajectories
其他已有公开 Trace
```

---

## 10.2 分析指标

### Session

```text
duration
turn count
success
```

### LLM

```text
model calls
input tokens
output tokens
TTFT
API latency
```

### Context

```text
initial context
context growth
max context
prefix/cache reuse
```

### Tool

```text
tool calls
tool/category distribution
tool latency
```

### Temporal

```text
LLM accumulated work / union busy time
Tool/job wall time / overlap
Agent/runtime measured time
Uncovered time
```

### Tail

按来源/配置/证据分层输出适用的分位数，并报告有效 task/run 数、缺失和筛选。少量样本可以不报告 P95/P99；计算出经验分位数不等于尾部结论可靠。候选指标：

```text
P50
P90
P95
P99
```

---

## 10.3 最重要的输出

不是只做统计表。

要形成每种 Agent 的：

**Workload Fingerprint。**

例如：

```text
Coding Agent

Long session            High
Turns                   High
Context growth          High
Tool frequency          High
Tool latency variance   High
```

---

## 10.4 用宏观 Trace 选择本地 Case

本地不能只挑“容易跑的”。

仅在来源和指标可比时，按对应公开样本的来源内分布选择候选：

```text
Short
Median
Long-tail
```

或者：

```text
Low tool
Medium tool
High tool
```

这样可以解释为什么选这些 case，但不能据此证明跨场景生产代表性。无相应公开数据的场景，按功能/执行机制覆盖选择 pilot 并明确限制。选择时按 source/profile/config 与可用维度分层，缺失值不当低负载；宏观 turns-heavy 不等于 CPU-heavy，系统代表性还需资源试点验证。

---

# 11. 第四阶段：本地 Benchmark 真实 Agent Trace

目标：

> 获得公开 Trace 无法提供的 Tool + Process + OS 信息。

先做一个真实 Runner 小闭环，并以确定性样例覆盖独立子进程、常驻服务和异步执行；其他场景随后各做少量 smoke。已有日志先用于语义审计，不能补造未采集的 OS 真值。

下表是小闭环和 CPU 试点之后的扩展预算，不是进入 CPU 分析的门槛：

| Workload          | Case 数 |
| ----------------- | -----: |
| Coding            |  15–20 |
| Office / Computer |  15–20 |
| Assistant         |  10–15 |
| Video GEN         |   5–10 |
| Video EDIT        |   5–10 |

总量约：

```text
50–75 distinct tasks（不含重复 runs）
```

不是为了测试 Agent 能力排名。任务数量不代表统计充分性；记录全部新采 attempts、重试和失败，成功子集单独标记，不能把失败样本悄悄从研究总体删除。

---

# 12. 第五阶段：实现统一 Instrumentation

建议按照四级 instrumentation。

## Level 0：Agent Semantic Trace

记录：

```text
LLM
reasoning/action
Tool Call
Tool Result
```

## Level 1：Process

记录：

```text
PID
PPID
process tree
command
start/end
exit
```

## Level 2：OS Resource

记录：

```text
CPU
RSS
Memory
IO
Network
Page Fault
Context Switch
```

## Level 3：CPU Performance

针对选出的重点 Tool：

```text
cycles
instructions
IPC
cache
branch
perf record
flamegraph
```

---

# 13. 第六阶段：Tool Classification

不要直接比较：

```text
bash
browser
python
```

因为 Tool Name 太粗。

例如 Bash 里面可能是：

```text
grep
pytest
gcc
ffmpeg
python
```

资源行为完全不同。

因此统一成：

```text
Read / Explore
Search / Retrieval
Write / Edit
Execute
Test
Compile
Browser / GUI
Document Processing
Media Processing
API / Network
Verification
Other
```

同时保存：

```text
Tool Interface
```

和：

```text
Operation Category
```

例如：

```text
tool = bash
command = pytest
category = Test

tool = bash
command = ffmpeg
category = Media Processing
```

这是借鉴 AgentCgroup 后进一步增强的地方。

---

# 14. 第七阶段：Agent Tool Resource Characterization

对可测 Tool/job/service scope 计算；未实现独占归因时不强行生成 per-call 真值：

```text
Invocation count
Wall time
CPU time
Average cores used (CPU seconds / wall seconds)
Peak RSS / cgroup memory peak（分开）
Average memory（注明 scope 与口径）
Read bytes
Write bytes
Page faults
Context switches
Process fan-out
```

还要计算：

```text
Peak / Average
```

描述可观测的 burst，同时注明采样间隔与短突发遗漏。

CPU/I/O 采用同 scope 累计计数器增量，记录 reset；父子 scope 不重复相加。RSS 与 cgroup memory.current 不可互换，各进程或 scope 的峰值不能相加称 run 峰值。CPU/wall 是平均占用核心数，不是算法效率。完整要求见 [资源指标与验收](docs/trace_contract.md#7-资源指标与验收)。

---

## 14.1 最终分析维度

### 按 Scenario

```text
Coding
Office
Assistant
Video
```

### 按 Tool Category

```text
Test
Compile
Browser
Document
Media
```

### 按 Software

```text
pytest
Python
Chromium
LibreOffice
FFmpeg
```

不能只有按 Agent 场景统计。

---

# 15. 第八阶段：CPU Microarchitecture Analysis

先从上一阶段筛出：

```text
Top CPU Tool
Top Wall-time Tool
Top Memory Tool
Top Invocation Tool
```

再深入。

不要对所有 Agent Trace 全量跑重型 perf。

---

## 15.1 perf stat

建议基础事件：

```text
task-clock
cycles
instructions
branches
branch-misses
cache-references
cache-misses
context-switches
page-faults
```

保存 PMU 型号、事件语义、time_enabled/time_running、multiplexing、权限与不可用原因；未支持不填 0。通用 cache-misses 不能直接解释为 LLC misses，IPC 必须来自同 scope/同区间。

平台支持时进一步增加：

```text
LLC load
LLC miss
L1D
TLB
frontend/backend stall
memory bandwidth
```

---

## 15.2 派生指标

计算：

```text
IPC
=
instructions / cycles
```

```text
Branch MPKI
```

```text
LLC MPKI
```

```text
CPU core-seconds
```

以及：

```text
CPU scaling efficiency
```

低 IPC 不直接证明 memory-bound。核心/线程扩展性、affinity、数据规模、cache 初态等需通过 P2-08 的受控实验验证；CPU 高占比、长 API 延迟或相关性不能单独推出 CPU 架构诉求。

---

# 16. 第九阶段：Hotspot 分析

只对重点 Tool 做：

```text
perf record -g
```

然后：

```text
FlameGraph
```

定位：

```text
Agent
 ↓
Tool
 ↓
Process
 ↓
Binary
 ↓
Library
 ↓
Function
```

记录符号版本、unwind 方法、采样丢失和 unknown 比例。热点样本占比不能冒充精确 CPU 时间；展示过滤不能静默改变分母。

最终 hotspot 表至少包含：

| Tool | Binary | Library | Function | CPU% | 原因 | 优化方向 |
| ---- | ------ | ------- | -------- | ---: | -- | ---- |

例如不能只写：

> Python CPU 高。

应该定位到：

```text
pytest
 ↓
python
 ↓
import/parser/GC/regex/serialization
```

类似 Video：

```text
FFmpeg
 ↓
libavcodec
 ↓
specific codec/filter
 ↓
hot function
```

---

# 17. 第十阶段：归纳 CPU 诉求

最终不能只写：

```text
Coding CPU较高
Video CPU很高
```

而应归纳成 workload type。

例如：

### Coding

可能呈现：

```text
bursty
process fan-out
test/compile dominant
cache/memory sensitive
```

### Browser

可能呈现：

```text
latency sensitive
burst CPU
many process
syscall/context switch
```

### Document

可能呈现：

```text
Python processing
render/conversion
moderate CPU
memory + filesystem
```

### Video

可能呈现：

```text
sustained CPU
multi-thread
SIMD
memory bandwidth
large sequential IO
```

这些必须由实验数据确认，不能提前把它们写成结论。

最终 CPU 诉求可以归纳到：

```text
Single-core performance
Multi-core scalability
SIMD
Cache capacity
Memory bandwidth
Memory capacity
Context-switch efficiency
Storage IO
Network latency
NUMA
```

---

# 18. 第十一阶段：Software Optimization

优化必须来源于测量结果：

```text
Characterization
      ↓
Bottleneck
      ↓
Hotspot
      ↓
Optimization
      ↓
A/B Test
```

不能先提出优化再找数据证明。

例如可能包括：

```text
减少进程启动
避免重复 Tool
cache tool result
减少文件重复扫描
优化 Python serialization
减少 context copying
减少 sandbox init
并行 Tool
调整 thread 数
NUMA binding
page cache reuse
```

每个优化必须有：

```text
Before
After
CPU
Wall time
Memory
Correctness
```

---

# 19. 第十二阶段：接入 agent_vm_bench 做 Replay / Scale

这一阶段研究的已经不是：

> Agent 会怎么思考？

而是：

> 这种 workload 并发运行后系统会怎么样？

流程：

```text
Real Agent
    ↓
Trace
    ↓
Representative Tool Sequence
    ↓
Replay Workload
    ↓
agent_vm_bench
    ↓
Docker / E2B / Firecracker
```

进入 Scale 前必须通过 Replay 保真 Gate：环境/输入/依赖与输出正确，资源和时序偏差满足预先声明的用途与容差。固定 release 的 open-loop、前驱完成后的 think-gap 与去除等待的模式分开，不能重复叠加 offset 与 wait。

分析：

```text
1 Agent
4 Agents
8 Agents
16 Agents
...
```

观察：

```text
CPU saturation
Memory pressure
Page cache
Disk
NUMA
Tail latency
OOM
Sandbox startup
Ready time
```

---

# 20. Real Trace 和 Replay 必须严格区分

所有数据增加：

```text
trace_type
```

取值为：

```text
production
production_derived
benchmark_real
oracle
replay
synthetic
unknown
```

报告中不能把：

```text
oracle trace
replay trace
```

描述成：

```text
真实 Agent trace
```

生产派生模板使用 production_derived，未知来源保持 unknown 待审计。trace_type 不是唯一证据标签；还需 profile、逐指标 observed/derived/template_parameter/estimated/unavailable，以及原始来源链。修正 adapter 或重新存储不改变原始来源身份。

这是后续数据可信度非常关键的一点。

---

# 21. 实验变量控制

所有正式实验必须记录：

```text
Benchmark Version
Task ID

Agent
Agent Version

Harness
Harness Version

Model
Model Version
Temperature

Tool Version

Docker Image
Runtime

CPU Model
Core Count
NUMA

Kernel

Memory

CPU Governor
CPU Affinity
```

正式对比尽量固定 Model。

推荐：

```text
External Model API
        ↓
Local Agent
        ↓
Local Tool / Sandbox
```

这样本地 CPU 重点是：

```text
Agent runtime
Tool
OS
Sandbox
```

而模型侧单独记录：

```text
token
TTFT
API latency
```

不要把远程模型 GPU latency 错算成本地 CPU workload。

---

# 22. 重复实验

Agent 有 nondeterminism。

正式代表 Case 的初始预算建议：

```text
3 runs
```

核心重点 Case：

```text
5 runs
```

同时保存：

```text
success
trajectory difference
tool sequence difference
resource variation
```

3/5 runs 是预算起点，不保证统计精度。正式比较前确定重复策略、筛选、随机化/区组与容差；分开 task 数与 run 数，按 task 等合理单位做聚类/分层统计，不能把一次任务的多次调用当作独立任务。

这样还能分析：

> 同一个 task，不同 Agent run 的 Tool sequence 和资源需求差异有多大。

这也与 AgentCgroup 所强调的 Agent resource unpredictability 问题形成对应。

---

# 23. 推荐代码仓库结构与数据管理

正式项目根为 `agent_workload_characterization/`，不是旧 `agent_workload/`。方法论放根目录，工程规划在 docs，研究输入与派生输出分开。

```text
agent_workload_characterization/
├── methodology.md
├── docs/
├── references/             # 只读第三方参考
├── workload_catalog/
├── data/
│   ├── catalog/            # 登记旧源位置、快照、筛选、血缘
│   ├── raw/                # 后续新增采集，旧源原地只读
│   └── normalized/         # 新生成 IR，按版本隔离
├── adapters/
├── collectors/
├── runners/
├── analyzers/
├── replay/
├── scripts/
├── tests/
└── reports/
```

旧数据暂不物理搬迁。可选软链接只是定位便利，不提供只读保证；writer 需要检查真实路径防止回写来源。失败归档、成功子集与未绑定遥测分别登记。未来确需物理归档时先复制校验、再切换索引，删除旧副本另行确认。

详细目录与规则见 [数据管理](docs/data_management.md) 和 [任务计划](docs/development_tasks.md)。

---

# 24. 实施优先级与 Gate

P0～P4 是工作类别，不是全阶段严格串行的门槛。实际顺序：

1. P0-00：审计旧资产、筛选/血缘、指标问题和代码复用。
2. 最小 P0：IR、手算 gold fixtures、AgentX/Applied/一种已有本地 trace、macro + coverage，通过 G0。
3. P1 小闭环：确定性执行机制样例与一个真实 Runner，检查归因、开销和误差，通过 G1。
4. P2 试点：尽早验证 PMU/hotspot/受控 CPU 实验可行性，并反馈修正采集设计。
5. 扩展 P0/P1 的来源、四类场景与任务重复，形成正式 Characterization；CPU 结论通过 G2。
6. P3：Replay spec 与单实例保真 G3-R，再接 runtime 和 scale。
7. P4：只有明确瓶颈、证据和授权后才考虑重型 eBPF、预测或调度。

无需先完成所有公共 adapter，也无需先有四场景和约 50 个任务，才能做资源归因或 CPU 试点。P1 的“归因通过”允许明确的 service/run 测量与未知项，不能要求所有场景虚构 Tool 独占 CPU。

所有 Gate 当前未验收；本次只修订计划，不触发开发或运行。

---

# 25. 整个项目最关键的六个 Research Questions

以后所有实验必须至少服务其中一个问题。

## RQ1

**Agent workload 与传统 LLM workload 有什么不同？**

关注：

```text
multi-turn
context growth
tool interleave
state
long lifetime
```

若做性能对比，必须定义传统 LLM 对照、模型/token 与测量边界控制；只有公开形态数据时限定为描述性比较，不把来源差异当 Agent 架构的因果效应。

---

## RQ2

**Agent 时间到底花在哪里？**

拆成：

```text
LLM
Agent
Tool
Environment
Sandbox
```

这些时间可能重叠。区分累计工作量、区间并集、E2E 与未覆盖时间；未经互斥定义不能把各项简单相加为端到端分解。

---

## RQ3

**真正造成 CPU / Memory / IO 压力的是什么？**

比较：

```text
Agent type
vs.
Tool type
```

尤其验证：

> 系统资源行为是否主要由底层 Tool 决定，而不只是由“Coding/Office/Video”这个场景名称决定。

这是待验证假设；比较需控制任务、模型、harness 和环境，并处理同任务多次运行/调用的相关性。

---

## RQ4

**不同 Tool 的 CPU workload 特征是什么？**

回答：

```text
compute-bound?
memory-bound?
single-thread?
multi-thread?
latency-bound?
IO-bound?
```

---

## RQ5

**主要热点和软件优化机会在哪里？**

做到：

```text
Tool
→ Binary
→ Library
→ Function
```

---

## RQ6

**多个 Agent 并发时系统会发生什么？**

分析：

```text
resource burst
contention
tail latency
memory pressure
sandbox scalability
```

---

# 26. 方法论上的三个原则

## 原则一：先 Characterization，再 Optimization

借鉴 AgentCgroup 和 AgentSysBench。

先证明：

```text
What happens?
Why?
Where?
```

之后再研究：

```text
How to optimize?
```

---

## 原则二：Public Trace 和 Local Trace 各有用途

```text
Public Trace
→ 宏观分布

Local Real Trace
→ 系统关联观测；因果结论另需受控实验

Replay Trace
→ 可重复系统实验
```

不能混用。

---

## 原则三：Benchmark 是负载来源，不是最终研究目标

SWE-bench、DocOps、OSWorld、VideoWeaver 等的作用是：

> 提供真实、公开、可复现、可验证的任务。

项目最终研究对象仍然是：

> **执行这些任务时产生的 Agent workload。**

---

# 27. 第一版建议实际执行顺序

当前不新增 benchmark、不搬迁旧 trace、不自动启动后续任务或实验。P0-00-r2、P0-01～05、P0-10 小样与 P0-08/09 最小分析已验收。下一批按 [首次运行准备包 PREP-01](docs/first_run_preparation_handoff.md) 合并安全配置/输入准备、离线测试、只读能力预检与审批清单；本次仅准备任务书，未实施。此批允许 G0 前有限只读预检与自有准备代码，不含实际采集或第三方执行，不自动通过任何 Gate。P0-06 暂缓，不阻塞 G0；不全量重新 ingest。各 Gate 状态仍以任务计划为准。

待用户明确开始后，按 [开发任务计划](docs/development_tasks.md) 的任务依赖推进：

```text
审计旧资产
→ 验证最小语义与指标
→ 验证一个资源闭环
→ CPU 试点与反馈
→ 扩展来源/场景/重复
→ 正式 Characterization
→ Replay 保真
→ Runtime / Scale
```

早期机制覆盖比任务数量重要：专属子进程、常驻/进程内服务、异步 job、远端不可观测边界都要在采集设计中有位置。首个真实 Runner 可优先 Coding；既有 Office/Video 等资产用于适配和缺口审计，不代表已有 OS 测量。

质量报告与分析同时开发，不作为最后补件。正式筛选/容差在比较前固定；遇到费用、提权、旧数据恢复/删除或范围扩张需另行确认。

---

# 28. 最终项目与已有工作的关系

可以简单概括为：

```text
AgentX
Applied Compute
SWE trajectories
        │
        │  借鉴：
        │  公开且经筛选/变换的 Agent workload shape
        ▼
Macro Characterization
        │  采样参考（非 trace 转换；无匹配来源时按覆盖目标选择）
        ▼
Representative Workload
        │
        │  Benchmark来源：
        │  SWE / OSWorld / DocOps /
        │  ToolSandbox /
        │  VideoWeaver / AgenticVBench
        ▼
Real Agent Execution
        │
        │
        │  借鉴 AgentCgroup：
        │  Tool-call boundary
        │  Process attribution
        │  cgroup
        │  Resource timeline
        ▼
OS Characterization
        │
        │
        │  借鉴 CPU-Centric：
        │  CPU侧重要性
        │  scaling
        │  microarchitecture
        ▼
CPU Characterization
        │
        ▼
perf / hotspot
        │
        ▼
CPU Requirement
Software Optimization
        │
        │
        │  借鉴 AgentSysBench：
        │  performance = Φ(workload, serving system)
        │  unified instrumentation
        ▼
Runtime / Scale
        │
        ▼
agent_vm_bench
Docker / E2B / Firecracker
```

最核心的定位可以浓缩成一句话：

> **AgentSysBench 用来借鉴整个系统级 workload characterization 框架；AgentCgroup 用来借鉴 Tool-call 粒度的 OS 资源归因与 Replay；AgentX / Applied Compute 用来描述公开样本和生产派生模板的宏观分布；SWE-bench、OSWorld、DocOps、ToolSandbox、VideoWeaver、AgenticVBench 用来提供公开可复现任务；CPU-Centric Agentic AI 用来指导 CPU 深入分析；现有 agent_vm_bench 则负责最终 Runtime、Sandbox 和并发扩展实验。**

这就是后续整个 Agent workload 项目的统一技术路线。

---

# 29. 本地 AI 执行时必须遵守

1. 不擅自增加新的 Benchmark，除非现有四类场景确实存在覆盖缺口。
2. 不把 Benchmark success rate 当成本项目主要指标。
3. 不把 AgentX 等 inference trace 当成 Tool CPU trace。
4. 不把 replay/oracle trace 描述为真实 Agent trace。
5. 所有正式实验固定并记录软件、模型、Benchmark 和环境版本。
6. CPU 结论必须有实际 perf/resource 数据支撑。
7. 不根据单条 Trace 得出某一类 Agent 的普遍结论。
8. 先明确并验证可实现的资源归因 scope，再做函数 hotspot；共享/进程内工具不强造 exclusive Tool 归因。
9. 不在 characterization 尚未完成前提前设计复杂 scheduler。
10. 新增任何实验必须说明它服务于 RQ1～RQ6 中的哪一个问题。
11. Benchmark 的价值是提供“公开、代表、可复现、可验证的任务”，而不是为了扩大 Benchmark 数量。
12. 旧原始数据原地只读；新代码、IR 和报告收敛到新项目，不覆盖第三方参考或历史产物。
13. 区分来源、attempt、三类状态、模板与实测；保存失败、缺失和未绑定证据，不以样本量替代计量验收。
14. 文档中的计划、目录和命令不是已完成状态，也不构成运行/付费/迁移授权。
15. 最终分析单位从粗到细应能按实际观测能力关联：

```text
Scenario
→ Agent Run
→ Phase
→ Tool Call / Job / Service
→ Resource Scope / Process
→ Binary
→ Library
→ Function
→ CPU / OS Behavior
```

目标是让关键样本的这条链有可核验的身份、时间和归因证据，并诚实列出无法观测的边界；不是仅凭字段齐全或一条 trace 就宣布全部研究目标完成。
