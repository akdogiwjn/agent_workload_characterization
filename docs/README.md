# 文档索引

这是文档导航入口。日常状态只看 **[项目总览与固定收尾清单](project_status.md)**；Gate 裁定只看 [G1 集中评审 §0](g1_consolidated_review.md)。G1登记小闭环、CPU-01可测性已验收；当前任务为CPU-02 A离线准备，G2未通过。

历史文档原位保留并在本页折叠。文件仍存在不表示任务仍在进行；delivery 是交付声明，不自动等于验收通过，旧 prompt 不提供当前授权。

## 最短阅读路径

- 日常查看：[`project_status.md`](project_status.md) 即可；不必浏览所有历史交付。
- 新实施者：按当前任务书完整阅读必读四文档及语义/数据契约；本导航不替代任务要求。
- 执行者：先读 [`development_tasks.md`](development_tasks.md) 和当前任务
  [`cpu_02_handoff.md`](cpu_02_handoff.md)；旧 RUN-02/R1/R2
  handoff/prompt 仅是各自历史授权文本。
- 评审者：[`g1_consolidated_review.md`](g1_consolidated_review.md) →
  [`repository_closeout_delivery.md`](repository_closeout_delivery.md) →
  RUN-02-R2 的 [原始报告](../reports/resource/RUN-02/20260915T012427Z-2d75aa/)
  和 [review-v2](../reports/resource/RUN-02/20260915T012427Z-2d75aa-review-v2/)。

## 当前状态时间线

1. G0 有既有通过记录；G1 现为 `PASSED（登记小闭环范围）`，不是全部研究目标完成。
2. RUN-01-C 是历史真实 attempt；RUN-02 原批和 R1 在启动阶段失败；READY-01 是只读准备证据。
3. RUN-02-R2 已完成一次真实联合观测并保留 raw、原报告、批准和 marker；review-v2 只修正文义口径。
4. CLOSEOUT-01、G1-02及CPU-01已验收。下一步CPU-02 A，不启动真实perf或容器。测试数量不等于任务数、模型请求数或独立实验数。

## 长期规范

- [`methodology.md`](../methodology.md)：研究目标、路线、方法和 Gate 原则。
- [`data_management.md`](data_management.md)：来源、raw/derived、血缘、保护和失败样本规则。
- [`trace_contract.md`](trace_contract.md)：ID、时间、缺失、证据、资源归因和统计语义。
- [`ir_v0_1.md`](ir_v0_1.md)、[`ir_v0_2.md`](ir_v0_2.md)：IR 版本约定。
- [`adapter_framework.md`](adapter_framework.md)：adapter 接口与边界。
- [`benchmark_selection.md`](benchmark_selection.md)：benchmark 选择与版本限制。
- [`macro_coverage.md`](macro_coverage.md)：宏观指标与 coverage 口径。

## 当前任务、评审与交付

- [`cpu_02_handoff.md`](cpu_02_handoff.md)、[A 提示词](cpu_02_execution_prompt.md)、[A 交付](cpu_02_delivery.md)：真实 Verifier 执行段的目标映射与热点离线准备已交付（`A_OFFLINE_VERIFIED`），B 另批。
- CPU-01已完成：[`cpu_01_handoff.md`](cpu_01_handoff.md)、[历史提示词](cpu_01_execution_prompt.md)、[交付与评审](cpu_01_delivery.md)；不重跑。
- G1-02 已完成：[`g1_02_handoff.md`](g1_02_handoff.md)、[历史提示词](g1_02_execution_prompt.md)、[交付](g1_02_delivery.md)；完整历史身份见 [`g1_02_identity.json`](../workload_catalog/g1_02_identity.json)，不重复执行。
- [`project_status.md`](project_status.md)：日常状态、代码地图、固定收尾表和本次仓库审查记录。
- [`g1_consolidated_review.md`](g1_consolidated_review.md)：当前六条 G1 集中评审。
- [`development_tasks.md`](development_tasks.md)：完整 P0–P4 目标、依赖与 Gate；长期任务库，不是要求当前全部实施。

## 历史阶段交付

<details>
<summary>需要追溯时展开：历史交付与旧任务书</summary>

下列文档是历史交付或实施记录，原文和哈希不因本索引改变：

- CLOSEOUT-01：[`repository_closeout_handoff.md`](repository_closeout_handoff.md)、[提示词](repository_closeout_execution_prompt.md)、[交付](repository_closeout_delivery.md)。已验收，不是当前整理任务的新批准。

- P0：[`p0_01_delivery.md`](p0_01_delivery.md)、[`p0_02_delivery.md`](p0_02_delivery.md)、[`p0_03_delivery.md`](p0_03_delivery.md)、[`p0_04_delivery.md`](p0_04_delivery.md)、[`p0_05_delivery.md`](p0_05_delivery.md)、[`p0_07_08_09_delivery.md`](p0_07_08_09_delivery.md)、[`p0_10_delivery.md`](p0_10_delivery.md)。
- 资源/运行准备：[`first_run_preparation_delivery.md`](first_run_preparation_delivery.md)、[`first_run_approval.md`](first_run_approval.md)、[`pilot_taskdata_delivery.md`](pilot_taskdata_delivery.md)、[`pilot_harness_model_delivery.md`](pilot_harness_model_delivery.md)、[`environment_adaptation_delivery.md`](environment_adaptation_delivery.md)、[`mini_2_4_6_static_delivery.md`](mini_2_4_6_static_delivery.md)。
- 模型/协议：[`model_smoke_delivery.md`](model_smoke_delivery.md)、[`coding_pilot_delivery.md`](coding_pilot_delivery.md)。
- G1-01：[`g1_01_delivery.md`](g1_01_delivery.md)、[`g1_01_b_delivery.md`](g1_01_b_delivery.md)、[`run_02_delivery.md`](run_02_delivery.md)、[`run_02_r1_delivery.md`](run_02_r1_delivery.md)、[`run_02_r2_delivery.md`](run_02_r2_delivery.md)、[`run_02_launch_readiness_delivery.md`](run_02_launch_readiness_delivery.md)。
- 方法/来源交付：[`agentx_adapter.md`](agentx_adapter.md)、[`applied_compute_adapter.md`](applied_compute_adapter.md)、[`videoweaver_adapter.md`](videoweaver_adapter.md)、[`legacy_asset_audit.md`](legacy_asset_audit.md)。

## 历史任务书、提示词与执行文本

这些文件描述当时的范围和批准门槛，不提供当前授权：

- [`p0_05_luna_handoff.md`](p0_05_luna_handoff.md)、[`p0_07_08_09_handoff.md`](p0_07_08_09_handoff.md)、[`p0_07_g0_handoff.md`](p0_07_g0_handoff.md)、[`p0_10_handoff.md`](p0_10_handoff.md)。
- [`first_run_preparation_handoff.md`](first_run_preparation_handoff.md)、[`pilot_harness_model_handoff.md`](pilot_harness_model_handoff.md)、[`environment_adaptation_handoff.md`](environment_adaptation_handoff.md)、[`model_smoke_handoff.md`](model_smoke_handoff.md)、[`coding_pilot_handoff.md`](coding_pilot_handoff.md)。
- [`g1_01_handoff.md`](g1_01_handoff.md)、[`g1_01_execution_prompt.md`](g1_01_execution_prompt.md)、[`g1_01_b_handoff.md`](g1_01_b_handoff.md)、[`g1_01_b_execution_prompt.md`](g1_01_b_execution_prompt.md)。
- [`run_02_handoff.md`](run_02_handoff.md)、[`run_02_execution_prompt.md`](run_02_execution_prompt.md)、[`run_02_r1_handoff.md`](run_02_r1_handoff.md)、[`run_02_r1_execution_prompt.md`](run_02_r1_execution_prompt.md)、[`run_02_r2_handoff.md`](run_02_r2_handoff.md)、[`run_02_r2_execution_prompt.md`](run_02_r2_execution_prompt.md)、[`run_02_launch_readiness_handoff.md`](run_02_launch_readiness_handoff.md)、[`run_02_launch_readiness_prompt.md`](run_02_launch_readiness_prompt.md)。

</details>

## 全文档目录（查找用，非必读清单）

<details>
<summary>展开全部 73 个文件名</summary>

下面列出当前目录全部 Markdown 文件，避免索引遗漏：

```text
README.md
adapter_framework.md
agent_landscape.md
agentx_adapter.md
applied_compute_adapter.md
benchmark_selection.md
coding_pilot_delivery.md
coding_pilot_handoff.md
cpu_01_delivery.md
cpu_01_execution_prompt.md
cpu_01_handoff.md
cpu_02_delivery.md
cpu_02_execution_prompt.md
cpu_02_handoff.md
data_management.md
development_tasks.md
environment_adaptation_delivery.md
environment_adaptation_handoff.md
first_run_approval.md
first_run_preparation_delivery.md
first_run_preparation_handoff.md
g1_01_b_delivery.md
g1_01_b_execution_prompt.md
g1_01_b_handoff.md
g1_01_delivery.md
g1_01_execution_prompt.md
g1_01_handoff.md
g1_02_delivery.md
g1_02_handoff.md
g1_02_execution_prompt.md
g1_consolidated_review.md
ir_v0_1.md
ir_v0_2.md
legacy_asset_audit.md
macro_coverage.md
mini_2_4_6_static_delivery.md
mini_2_4_6_static_handoff.md
model_smoke_delivery.md
model_smoke_handoff.md
p0_01_delivery.md
p0_02_delivery.md
p0_03_delivery.md
p0_04_delivery.md
p0_05_delivery.md
p0_05_luna_handoff.md
p0_07_08_09_delivery.md
p0_07_08_09_handoff.md
p0_07_g0_delivery.md
p0_07_g0_handoff.md
p0_10_delivery.md
p0_10_handoff.md
pilot_execution_spec.md
pilot_harness_model_compatibility.md
pilot_harness_model_delivery.md
pilot_harness_model_handoff.md
pilot_taskdata_delivery.md
project_status.md
repository_closeout_execution_prompt.md
repository_closeout_handoff.md
repository_closeout_delivery.md
run_02_delivery.md
run_02_execution_prompt.md
run_02_handoff.md
run_02_launch_readiness_delivery.md
run_02_launch_readiness_handoff.md
run_02_launch_readiness_prompt.md
run_02_r1_delivery.md
run_02_r1_execution_prompt.md
run_02_r1_handoff.md
run_02_r2_delivery.md
run_02_r2_execution_prompt.md
run_02_r2_handoff.md
trace_contract.md
videoweaver_adapter.md
```

</details>

## 目录与产物地图

```text
src/agent_workload_characterization/  源码：adapters、runners、collectors、analyzers
tests/                                单元、合成和封网 mini 集成测试
scripts/                              自有脚本
schemas/                              当前存在的 schema/契约资产（若有）
workload_catalog/                     workload 配置与身份
data/catalog/                         来源 catalog
data/raw/                             外部 public 与封存 generated raw，逻辑只读
data/normalized/                      规划/派生归一化数据，按实际批次判断
reports/preparation/                  READY 只读准备证据
reports/resource/                     运行 raw 关联报告、批准、marker 与派生报告
reports/macro/、reports/quality/      宏观/质量派生报告
references/                           第三方参考，不是运行数据
.venvs/                               本地软件环境，不是仓库证据
```

权威数据按批次定位：RUN-01-C 在 `data/raw/generated/RUN-01-C/` 与其 resource 报告；
G1 A/B 在 `reports/resource/G1-01-A/`、`reports/resource/G1-01-B/`；RUN-02-R2 的 raw、
原报告和 [review-v2](../reports/resource/RUN-02/20260915T012427Z-2d75aa-review-v2/)；
失败/准备证据在 `reports/resource/RUN-02/` 与 `reports/preparation/READY-01/`。不枚举大规模 trace。

## 导航维护与未来迁移建议

本次采用原位逻辑归档，不移动、删除历史文档或证据。以后只更新一份当前任务书、提示词、交付和固定问题表，不为零碎返修增加文件。物理迁移须先检查历史引用与身份绑定，不能把旧提示词改成新授权。

文档分工：项目总览维护当前状态；本页只做导航；任务计划维护编号与长期要求；集中评审维护 Gate 裁定；原始 raw、历史批准/marker、报告按批次保留。代码或配置 hash 变化后的运行仍须按任务重新核验身份。
