# AI Agent Workload Characterization

面向 CPU / OS 的 Agent workload 研究与工程项目，不做 Agent 能力排行榜。

## 当前状态与边界

日常先看 **[项目总览与固定收尾清单](docs/project_status.md)**；材料查询用 [文档索引](docs/README.md)。历史任务书在索引中折叠，不需要逐份重读。

当前：G1 登记小闭环与 CPU-01 宿主合成进程 perf 可测性已验收。下一步为 [CPU-02 A 离线准备](docs/cpu_02_handoff.md)，[提示词](docs/cpu_02_execution_prompt.md)供实施模型使用：只准备真实 Verifier 段的一次采样，不重跑 Agent；真实执行另批。
G0 有既有通过记录；G1 通过不代表多任务代表性、独占 Tool CPU 或函数热点已经完成，G2 未通过。具体边界以集中评审 §0 为准。
RUN-02-R2 已完成一次真实 Django 联合观测，原始 raw、原报告、批准/marker 与 review-v2 均保留。
历史运行、失败记录和测试数量按各自交付解释，测试数量不等于任务数或独立实验数。

最短入口：[文档索引](docs/README.md) · [当前集中评审](docs/g1_consolidated_review.md) ·
[CLOSEOUT-01 交付](docs/repository_closeout_delivery.md) ·
[RUN-02-R2 review-v2](reports/resource/RUN-02/20260915T012427Z-2d75aa-review-v2/)。

## 源码运行与测试

要求 Python >=3.11；依赖版本以 `pyproject.toml` 为准。从项目根目录运行，以下仅帮助、版本及合成 IR 校验：

```bash
PYTHONPATH=src python3 -B -m agent_workload_characterization --help
PYTHONPATH=src python3 -B -m agent_workload_characterization --version
PYTHONPATH=src python3 -B -m agent_workload_characterization validate tests/fixtures/ir/template_n2.json
```

无参数显示帮助。注意：旧 CLI 帮助尾部“不会写文件”的概括已经过时，应按具体命令区分：

| 命令/入口 | 副作用与前置 |
| --- | --- |
| `inspect-source`、`check-*-samples` | 只读登记来源，依赖本地 catalog/数据，不启动实验 |
| `analyze-macro-pilot` | 默认只读；指定 `--output-dir` 会写派生报告 |
| `prepare-pilot` | 默认可做宿主/Docker 探针；离线需 `--skip-preflight`；指定输出目录会写报告，不作为日常查看入口 |
| `plan-coding-pilot` | 历史 RUN-01 离线计划，不授权运行 |
| `runners.*_entry --execute`、smoke 等 | 可能操作 Docker/模型/文件；历史命令不可直接复用，须当前任务批准 |

ingest 仍为 Python API，没有全量转换 CLI。按任务选择测试，不为文档整理默认运行全历史 discover。G1-02 已改为短 fixture，正式工作量仅在另批 B 中运行；测试层级和证据边界见总览。

实际代码位于 `src/agent_workload_characterization/`。`pyproject.toml` 声明安装后命令 `awc`；本轮仅核对源码帮助入口，未安装、打包或重验全部命令。

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

保留 P0～P4 作为工作类别，不再要求完成所有 P0 adapter 才验证 P1，也不要求收集约 50 个任务才开始 P2 试点。各 Gate 的具体证据见任务计划；G0 已有通过记录，G1 仍 PARTIAL，后续 Gate 未验收。
