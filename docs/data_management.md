# 数据管理与旧资产接入

修订日期：2026-09-10。本文是规划，不代表已建立 catalog、计算校验和、搬迁数据或修改权限。

## 1. 管理原则

统一管理不等于立即统一物理存储。

- 已有公共 trace、真实运行原始日志与历史归档保留原路径，作为逻辑只读输入。
- 新项目维护数据源索引、适配器、统一 IR、质量检查和新分析报告。
- 不继续把旧目录作为主开发现场；不回写原始日志以修正解析错误。
- 旧分析代码、sidecar 和报表保留为历史资产；先审计，再选择性复用自有代码，不整目录复制。
- 不重复下载已有数据，不恢复、删除或合并失败归档，除非另行明确授权。
- `references/` 保存设计参考，不是正式运行数据目录。

## 2. 已知旧资产位置

以下是入口清单，不是完成的逐文件 inventory；日期、版本、规模、覆盖率仍由 P0-00 审计。

| 路径（相对 `/home/lcq/agent_workload/benchmark/`） | 内容与角色 | 新项目处理 |
| --- | --- | --- |
| `agent_benchmark_traces/` | 公共 trace，亦包含部分 `gen_*` 本地生成快照；不能按父目录推断来源 | 按子数据源登记，并检查与生成目录的重复 |
| `traces_generation/` | DocOps、AgenticVBench、VideoWeaver、WorkArena 等生成脚本、原始产物和 sidecar | 原始日志只读；生成代码、sidecar、报告分别标识 |
| `benchmark_analysis/` | 已有多源 adapter、统一表、宏观分析与可视化 | 可复用候选，不是已验证的新项目基线 |
| `telemetry/`、`telemetry_proxy/` | 模型观测数据和采集实现 | 区分已绑定请求与未绑定历史样本；不得靠时间邻近强行关联 |
| `trace_cleanup_archive/20260908T060905Z/` | 未成功运行的可恢复归档、筛选清单、旧 sidecar | 登记为独立历史集合；不自动恢复，不与当前集合重复计数 |

入口参考：[旧分析说明](../../agent_workload/benchmark/benchmark_analysis/README.md)、[遥测汇总](../../agent_workload/benchmark/traces_generation/TELEMETRY_SUMMARY.md)、[归档说明](../../agent_workload/benchmark/trace_cleanup_archive/20260908T060905Z/README.md)。历史文档可能先后描述不同快照；其中数字不作为本项目当前统计真值。

## 3. 新项目目标目录

以下目录仅为计划，按任务需要创建，不要求一次搭空架子。

```text
agent_workload_characterization/
├── methodology.md
├── docs/
├── references/                  # 外部参考，非数据入口
├── workload_catalog/            # 任务选择与 workload 配置
├── data/
│   ├── catalog/                 # 来源、位置、快照、筛选、覆盖与血缘
│   ├── raw/
│   │   ├── generated/           # 后续新采原始日志，按 run 保存
│   │   ├── public/              # 后续确需新增的公共数据
│   │   └── replay/              # 重放执行原始日志，独立于 real
│   └── normalized/              # 派生 IR，按输入与转换版本隔离
└── reports/                     # quality / macro / resource / cpu / replay / scale
```

统一使用 `data/normalized/` 与 `reports/`，不另建含义相同的 `traces/normalized/` 或 `results/`。大型数据通常不进代码版本库；元数据也应先做隐私检查再提交。

## 4. Catalog 最小登记内容

每个来源快照至少计划登记：

| 内容 | 要求 |
| --- | --- |
| 身份与位置 | `source_id`、`snapshot_id`、来源角色、实际 locator、访问状态；路径不是唯一身份 |
| 来源 | 上游 URL/数据集版本、采集或下载时间（未知则 null）、license、引用 |
| 文件证据 | 原始相对路径或归档成员、大小、内容校验和、清单版本；未完成哈希必须显式注明 |
| 运行配置 | benchmark/task/asset 版本，模型、harness、工具、镜像、补丁；未知不补猜 |
| 筛选与状态 | 纳入/排除规则、原因、全集与子集关系，execution/evaluation/archive 分别记录 |
| 观测覆盖 | 指标、scope、证据类型、有效数量/适用分母、关联状态 |
| 血缘与转换 | 原始 locator → record → run/event；adapter 版本、配置、IR 版本、输出批次 |
| 复现差异 | 原配置 / adapted / surrogate / unknown；替代模型、远端服务、任务或 verifier 差异 |

对压缩包优先登记“包校验和＋成员路径”，无需为审计全量解包。来源在旧目录继续变化时，应登记新 snapshot，不能静默覆盖旧快照描述。

## 5. 原始数据、派生数据与身份

原始日志和模型响应不改写。sidecar、normalized 表及报表均是派生产物；旧 sidecar 的 `Observed` 标签也需核实，不能直接视为精确测量。

- `task_id` 表示任务；多模型、多 seed、多 attempt 是不同 run。
- 相同原始运行的拷贝、重新打包或重新 ingest，不得变成新的运行样本。
- 缺少原生 run ID 时，按已审计的来源命名空间与稳定原始记录键生成身份，并保存生成规则；信息不足时保留疑似重复/关联未决，不能擅自合并。
- snapshot、转换版本与 run 身份分离：原始数据移动或 adapter 修正不应自行制造额外 run。
- 未绑定模型请求保留 batch/request 身份与 `run_id=null`，只能参与其证据允许的分析。

## 6. 失败、重试与筛选偏差

分别统计全部已知 attempts、原始数据可访问 attempts、可解析 trace、成功运行、满足资源测量质量的运行。原始全集不可恢复时，不能把已知集合称为完整总体。

成功子集可以单独研究，但标题和结论必须注明“成功条件下”；失败、重试、基础设施异常、遥测缺失分别报告。job 级汇总不是额外 trial；有 token 不代表执行完成；verifier 失败不自动代表 trace 无效；归档失败不自动代表执行失败。

归档清单仅用于解释样本变化。以历史失败样本开展分析、恢复原文件或重新运行是后续独立决定，不在本次文档修订范围。

## 7. 路径与写入保护

优先通过 catalog locator 访问旧数据；可选软链接只为方便，不替代 catalog，也不提供只读保护。本轮不创建软链接。

后续 writer 必须解析真实路径，拒绝输出到任一已登记原始来源及其子路径（包括软链接指向的旧目录），拒绝输入输出重叠。覆盖已有派生批次必须显式选择；默认产生新版本。

后续新采集直接写新项目 `data/raw/generated/<collection_id>/<run_id>/`，并发任务独立目录。日志流可在运行中追加；封存后保留完整性记录，转换器只读。采集器不得为了“统一格式”删除原生日志。

不提交密钥、认证 header 或未经检查的 prompt/文件内容。原始敏感日志按访问权限保存；对外副本脱敏，保留脱敏规则与血缘。Replay 导入命令和路径必须人工审查，不能把 trace 当可信脚本自动执行。

## 8. 可选的未来物理归档

当需要独立备份、迁移或发布时，再决定是否复制旧数据。顺序为：冻结来源清单 → 估算空间和许可 → 明确批准 → 复制到新批次 → 校验文件/成员与元数据完整性 → 切换 locator → 保留回退入口。

删除旧副本是单独的破坏性决定，不包含在“归档”或“统一接入”的默认授权中。
