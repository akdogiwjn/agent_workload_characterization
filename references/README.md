# References

本目录保存 `agent_workload_characterization` 项目使用的外部参考资料，包括开源仓库、论文和部分方法说明。

2026-09-10 规划修订：本目录的 README 和 manifest 是本项目维护的参考说明；`repos/` 和 `papers/` 是第三方内容，本阶段不修改、不运行。任务计划和数据约定分别见 [development_tasks.md](../docs/development_tasks.md)、[data_management.md](../docs/data_management.md)、[trace_contract.md](../docs/trace_contract.md)。

这些内容主要用于：

* 理解主流 Agent Benchmark 和 Agent workload 的组织方式；
* 借鉴 Agent Trace、Tool Trace、OS Resource Trace 的采集方法；
* 参考 Tool-call 粒度资源归因、Trace Replay、CPU Characterization 等实现；
* 为 Coding、Office、Assistant、Video 等场景选择代表性 workload；
* 对照已有研究的方法、指标和实验设计。

本目录中的第三方仓库和论文主要作为本地参考资料，原则上不提交到本项目 Git 仓库。

---

## 1. 参考项目分类

### 1.1 系统级 Agent Workload Characterization

#### AgentCgroup

目录：

```text
repos/agentcgroup/
```

用途：

* 重点参考 Tool-call 粒度的系统资源分析方法；
* 参考 Tool Call 与 cgroup 的绑定方式；
* 参考 Tool → Process → Child Process 的资源归因；
* 参考 CPU / Memory resource timeline；
* 参考 SWE-bench Agent Trace collection；
* 参考 Trace Replay；
* 参考 Agent workload 的资源 burst 分析。

本项目主要借鉴：

```text
Agent
  ↓
Tool Call
  ↓
Process / cgroup
  ↓
CPU / Memory / IO
  ↓
Resource Characterization
```

借鉴的是边界与归因方法，不保证“一次调用对应一个独占 cgroup”。常驻服务、进程内工具、异步 job 和远端 API 需分别声明 scope；Tool 返回、job 完成和资源释放不是同一时间。参考 wrapper 的具体行为须测试，不直接作为本项目已验证实现。

第一阶段不计划直接照搬：

* sched_ext 调度器；
* memory controller；
* Agent-specific resource scheduler。

这些属于 AgentCgroup 后半部分的资源管理工作，本项目首先完成 workload characterization。

---

### 1.2 Coding Agent Benchmark

#### SWE-bench

目录：

```text
repos/SWE-bench/
```

用途：

* Coding Agent 主 Benchmark；
* 参考 task definition；
* 参考 repository issue → patch → verification 的完整任务流程；
* 参考 Docker evaluation；
* 参考 SWE-bench Verified；
* 与已经下载的 SWE-bench trajectories 配合分析。

本项目主要用于：

```text
Coding Agent
→ Search / Read / Edit
→ Test / Compile / Verify
→ CPU / Memory / IO Characterization
```

---

#### SWE-rebench-V2

目录：

```text
repos/SWE-rebench-V2/
```

用途：

* 了解 SWE-rebench 的任务扩展方式；
* 参考 AgentCgroup 所使用的 SWE-rebench 类 Coding workload；
* 参考更大规模、多语言 Coding task 的构建方式；
* 后续如果需要扩展 Coding workload，可以作为 SWE-bench 之外的补充来源。

注意：

SWE-rebench-V2 是当前参考版本，不代表与 AgentCgroup 论文实验时所使用的数据版本完全一致。

如果需要严格复现 AgentCgroup，需要以 AgentCgroup 仓库中的 reproduction 配置和 task list 为准。

---

### 1.3 Computer / Office Agent

#### OSWorld-V2

目录：

```text
repos/OSWorld-V2/
```

用途：

* Computer-use / GUI Agent 主参考；
* 分析 Browser、Desktop、Application 操作；
* 参考真实 GUI task；
* 参考 trajectory 组织方式；
* 用于补充个人助手 / Desktop Agent 场景。

重点关注：

```text
Agent
→ GUI Action
→ Browser / Desktop Application
→ Process / CPU / Memory
```

正式实验时必须固定 OSWorld release、task、asset 和代码版本。

---

#### DocOps

目录：

```text
repos/DocOps/
```

用途：

* Office / Document Agent 主 Benchmark；
* Word；
* Excel；
* PowerPoint；
* PDF；
* 参考 Harbor task；
* 参考 Skill；
* 参考 artifact verifier；
* 参考 Document Agent 的真实任务流程。

重点分析的底层软件可能包括：

```text
Python
LibreOffice
openpyxl
PDF tools
Chromium
filesystem
```

---

#### WorkArena

目录：

```text
repos/WorkArena/
```

用途：

* Enterprise Workflow 扩展场景；
* ServiceNow；
* Browser Agent；
* Knowledge Work；
* 多步骤企业任务。

当前定位：

不是第一阶段核心 Office Benchmark，而是 Enterprise / Browser Workflow 扩展负载。

---

### 1.4 Assistant / Tool Agent

#### ToolSandbox

目录：

```text
repos/ToolSandbox/
```

用途：

* Assistant / Tool-use Agent 主参考；
* Stateful Tool execution；
* Tool dependency；
* API interaction；
* Intermediate state；
* Tool correctness verification。

用于补充 Coding、Office、Video 之外的：

```text
General Assistant
API Agent
Personal Assistant
Tool Agent
```

重点不是 CPU-heavy workload，而是研究：

```text
LLM
↔ Tool
↔ State
↔ API
```

的典型 Agent 执行结构。

---

### 1.5 Video Agent

#### VideoWeaver

目录：

```text
repos/VideoWeaver/
```

用途：

* Video Generation Agent 主参考；
* Foundation Skills；
* Composition Skills；
* Agent Harness；
* ReAct execution；
* Long-video generation；
* Video Tool orchestration。

重点关注：

```text
Agent
→ Skill Selection
→ Video Tool
→ FFmpeg / Python / VLM / ASR
→ Resource Characterization
```

本项目不自己重新设计 Video Generation workload，优先使用公开 Benchmark 中定义的任务。

---

#### AgenticVBench

目录：

```text
repos/agentic-vbench/
```

用途：

* Video Editing Agent 主参考；
* Assembly；
* Repair；
* Sequencing；
* Repurpose；
* Harbor execution；
* Verifier。

主要用于构建：

```text
Video Editing
→ Inspect
→ Understand
→ Select
→ Edit
→ Render
→ Verify
```

这一类 Agent workload。

---

### 1.6 Agent Benchmark Runtime

#### Harbor

目录：

```text
repos/harbor/
```

用途：

* 参考统一 Agent Benchmark execution framework；
* 参考 task / environment / verifier / trajectory 的组织方式；
* DocOps、AgenticVBench 等项目与 Harbor 体系存在较强关联；
* 后续考虑是否统一 Coding / Office / Video workload 的执行接口时重点参考。

当前阶段：

优先参考架构，不急于把所有 Benchmark 强行迁移到 Harbor。

---

## 2. 论文参考

论文放在：

```text
papers/
```

---

### AgentCgroup

重点阅读：

* Tool-call-granularity resource characterization；
* OS resource burst；
* cgroup；
* Trace replay；
* Resource unpredictability。

主要对应本项目：

```text
collectors/cgroup/
collectors/process/
analyzers/resource/
replay/
```

---

### AgentSysBench

重点阅读：

* Agent workload 与 serving system 分离；
* 多类型 Agent workload；
* Unified Instrumentation；
* LLM / Tool / Sandbox / State / Resource；
* End-to-end system characterization。

主要用于指导整个项目的方法论。

本项目借鉴：

```text
Observed Performance = Φ(Agent Workload, Serving Environment)
```

因此实验必须记录完整软硬件环境。

---

### A CPU-Centric Perspective on Agentic AI

重点阅读：

* Agent CPU-side workload；
* Tool processing；
* CPU scalability；
* Core utilization；
* CPU bottleneck；
* CPU/GPU interaction。

主要对应：

```text
analyzers/cpu/
collectors/perf/
```

---

### Agentic AI Workload Characteristics

重点阅读：

* Agent execution phase；
* Tool behavior；
* Read / Explore；
* Execute / Write；
* LLM 与 Tool 的联合 workload characterization。

本项目计划借鉴其 phase 分析思想：

```text
Explore / Modify / Execute / Verify
允许回退、交错与重复
```

这些是分析标签候选，不是所有任务必经的单向流程。

---

## 3. 已有公开 Trace

已有数据不建议重复复制到 `references/`。

当前主要公开 Trace 来源包括：

```text
AgentX
Applied Compute
SWE-bench trajectories
TraceBench
OSWorld trajectories
SpreadsheetBench
```

已有数据暂时原地保留为只读来源，主要入口是：

```text
/home/lcq/agent_workload/benchmark/agent_benchmark_traces/
/home/lcq/agent_workload/benchmark/traces_generation/
```

新项目统一维护索引和派生数据，后续新增原始采集也写新项目：

```text
data/catalog/       # locator、版本、筛选、校验与血缘
data/raw/           # 后续新增原始数据，不要求迁入旧源
data/normalized/    # 新项目派生 IR
reports/            # 质量、宏观、资源、CPU、Replay、Scale
```

旧工程已有 adapter、sidecar 和报表，但有待审计的指标/身份问题，不因存在产物而视为已验收。旧失败归档、生成快照和未绑定 telemetry 分别登记，不自动恢复或合并。软链接只为访问便利，不提供只读保护；详情见 [数据管理](../docs/data_management.md)。

`references/` 始终只承载设计参考，不是本项目运行数据输出位置。

---

## 4. 各参考工作的角色

整个项目中不同参考工作的定位如下：

```text
AgentX / Applied Compute
        ↓
公开样本 / 生产派生模板的宏观 workload shape
        ↓
turn / token / context / latency


SWE-bench / OSWorld / DocOps /
ToolSandbox / VideoWeaver / AgenticVBench
        ↓
提供公开、可复现、可验证任务
        ↓
本地 Real Agent Trace


AgentCgroup
        ↓
Tool-call boundary
Process attribution
cgroup
Resource timeline
Trace Replay


AgentSysBench
        ↓
整体系统 Characterization 方法


CPU-Centric Agentic AI
        ↓
CPU-side 重要性 / scaling；本项目扩展 PMU / Hotspot 分析


Agentic AI Workload Characteristics
        ↓
Agent Phase / Tool Phase 分析


agent_vm_bench
        ↓
Replay / Sandbox / Concurrency / Scale
```

---

## 5. 本项目不应该做什么

参考这些项目不意味着直接复刻。

当前阶段不要：

1. 为了覆盖数量不断增加 Benchmark；
2. 直接复制第三方项目的大量代码；
3. 把 AgentCgroup 的 scheduler 当成本项目第一阶段目标；
4. 把 AgentX inference trace 当成 Tool CPU trace；
5. 把 Oracle / Replay trace 当成真实 Agent trace；
6. 未做 characterization 就提前设计优化方案；
7. 因为某篇论文得到了某个结论，就默认本项目也成立。

所有结论最终必须由本项目自己的数据验证。

---

## 6. 阅读优先级

如果本地 AI 需要理解整个项目，建议按以下顺序阅读。

### 第一优先级

```text
1. 本项目 methodology.md
2. docs/development_tasks.md
3. references/README.md
4. references/manifest.yaml
```

先完整阅读以上四份文档，再阅读 `docs/data_management.md` 与 `docs/trace_contract.md`。根据当前任务需要阅读 AgentCgroup paper/repository、AgentSysBench paper 等参考；不要求为每个小任务重新遍历全部第三方仓库。

### 第二优先级

根据场景阅读：

```text
Coding
→ SWE-bench / SWE-rebench

Office
→ DocOps / OSWorld

Assistant
→ ToolSandbox

Video
→ VideoWeaver / AgenticVBench
```

### 第三优先级

需要 CPU 深入分析时阅读：

```text
A CPU-Centric Perspective on Agentic AI
```

需要执行阶段分析时阅读：

```text
Agentic AI Workload Characteristics
```

需要统一 Benchmark Runtime 时阅读：

```text
Harbor
```

---

## 7. 使用原则

本地 AI 在参考 `references/` 时必须遵守：

* 本阶段第三方代码只读，不修改或运行；后续如需执行验证，须在具体任务范围与授权内安排；
* 如果直接复用代码，必须检查 License；
* 不允许仅凭参考论文结论代替本项目实验；
* 后续确需第三方补丁时，在明确授权的独立执行副本/补丁目录维护，不回写此处参考快照；
* 重要参考必须记录 commit / tag / release；
* 如果项目更新，不直接覆盖旧版本，应先确认是否影响现有实验；
* 正式实验必须记录实际使用版本，而不是只写项目名称。

---

## 8. 建议维护版本信息

每个参考仓库最终都应该记录：

```text
repository
URL
local path
commit SHA
tag / release
download date
purpose
```

建议统一维护在：

```text
manifest.yaml
```

只有 URL、真实 commit/release、资产版本等完整且可访问，才具备恢复相同参考环境的基础。当前 manifest 仅是部分占位登记，空 commit 不代表版本已冻结；补齐和核实属于 P0-00，不在本轮文档修订中假造版本号。
