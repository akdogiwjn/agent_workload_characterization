# AI Agent Workload Characterization

面向 CPU / OS 的 Agent workload 研究与工程项目，不做 Agent 能力排行榜。

## 当前状态与边界

已完成 P0-00-r2～P0-05、P0-10、P0-08/09（IR 0.2，v6 报告）；PREP-01 离线准备包已通过集中验收（231 项测试，[交付](docs/first_run_preparation_delivery.md)、[审批清单](docs/first_run_approval.md)）。P0-07/G0 未完成，真实运行未授权。各阶段交付详见对应 delivery 文档。

ENV-01 独立安装与离线适配已验收（23 项 SDK 集成测试，硬超时 started→kill 证据闭合）。下一批：[SMOKE-01 单次真实工具协议连通性执行文档](docs/model_smoke_handoff.md)。当前仅准备文档，待明确批准后最多发送一次请求；不执行工具、不拉镜像、不运行 benchmark。

## 源码运行与测试

要求 Python >=3.11；完整功能/测试需要 `pydantic>=2.13,<3` 与 `PyYAML>=6.0,<7`（本机已有 2.13.4 / 6.0.3）。从项目根目录运行：

```bash
PYTHONPATH=src python3 -B -m agent_workload_characterization --help
PYTHONPATH=src python3 -B -m agent_workload_characterization --version
PYTHONPATH=src python3 -B -m agent_workload_characterization validate tests/fixtures/ir/template_n2.json
PYTHONPATH=src python3 -B -m agent_workload_characterization inspect-source agentx_256k
PYTHONPATH=src python3 -B -m agent_workload_characterization check-agentx-samples
PYTHONPATH=src python3 -B -m agent_workload_characterization check-applied-samples
PYTHONPATH=src python3 -B -m unittest discover -s tests -v
```

无参数时显示帮助；未知选项或未实现命令返回非零。`validate` 只读 IR 0.2 JSON，`inspect-source` 检查 locator，`check-agentx-samples` 只读核对两条已登记记录并输出摘要；CLI 不写文件。ingest 仍为 Python API，没有全量转换 CLI。完整单元测试不要求旧 trace 存在，真实 sample 命令则需要 catalog 对应文件。

实际代码位于 `src/agent_workload_characterization/`。`pyproject.toml` 声明安装后命令 `awc`，本轮未执行安装或打包；已验证上述源码入口及 console entry point 的目标函数。

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
