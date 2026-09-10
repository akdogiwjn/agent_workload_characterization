# AI Agent Workload Characterization

面向 CPU / OS 的 Agent workload 研究与工程项目，不做 Agent 能力排行榜。

## 当前状态与边界

2026-09-10：完成方法与任务计划修订；尚未执行新项目开发、数据转换、采集或实验。旧工程已有代码和 trace，但不等于新项目的指标、Schema 或采集链路已验收。

本轮只维护项目文档。计划中的目录、接口、命令和测试均是未来交付要求，不表示已经实现，也不授权自动执行。下一项候选任务为 **P0-00 资产与语义审计**，待用户明确开始后执行。

## 阅读顺序

先完整阅读：

1. [methodology.md](methodology.md)
2. [docs/development_tasks.md](docs/development_tasks.md)
3. [references/README.md](references/README.md)
4. [references/manifest.yaml](references/manifest.yaml)

再阅读本次补充的共同约定：

- [数据管理与旧资产接入](docs/data_management.md)：旧原始数据原地保留，新项目统一登记、转换和分析。
- [Trace 语义与测量契约](docs/trace_contract.md)：ID、时间、缺失、证据、资源归因和统计口径。

`references/repos/` 与 `references/papers/` 仅作设计参考，本阶段不修改第三方内容；不直接复制任何参考项目的数据格式。

## 技术路线

```text
Public Trace ──→ 来源适配 ──→ 宏观分布与采样依据
                              ↕ 共享语义 IR
Real Agent Run → 原生埋点 ──→ 行为 / Job / Process / Resource Scope
                              ↓
                      CPU Characterization / Hotspot
                              ↓
                      Replay 保真验证 → Scale
```

公共 trace 和本地运行是互补的证据来源，不是同一条 trace 的自动转换；公开样本的分布不自动代表所有生产 workload。

## 开发顺序摘要

资产审计 → 最小 IR 与手算指标样例 → 少量任务资源归因闭环 → CPU 试点 → 扩展场景与样本 → Replay 保真与 Scale。

保留 P0～P4 作为工作类别，不再要求完成所有 P0 adapter 才验证 P1，也不要求收集约 50 个任务才开始 P2 试点。各 Gate 的具体证据见任务计划；所有 Gate 当前均未验收。
