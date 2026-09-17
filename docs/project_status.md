# 项目总览与收尾清单

更新：2026-09-16。日常只读本页；查材料用 [文档索引](README.md)，实施时仍须遵守任务书的必读材料。这里不提供新的运行授权。

## 1. 现在做到哪里

已经打通公共 trace 小样分析和一个 Coding 任务的真实运行、工具时间线、容器与宿主资源观测。尚未完成 CPU 微架构/函数热点、正式多场景 Characterization、Replay/Scale。

| 阶段 | 当前能力 | 状态与依据 |
| --- | --- | --- |
| 资产 / IR / 宏观 | 旧源登记、AgentX / Applied / VideoWeaver 小样、macro + coverage | 最小范围已验收；不是全量转换，见 [任务计划](development_tasks.md) |
| 真实 Coding | RUN-01-C 与 RUN-02-R2；同一 Django task 的两个真实 attempt | 已有封存证据，不是两个不同 benchmark；见 [集中裁定](g1_consolidated_review.md#0-本次裁定及下一步边界当前有效) |
| G1 资源观测 | native arm64/cgroup v1；容器 CPU/Wall/memory、工具时间、mini 宿主区间观测及机制补证 | `PASSED（登记小闭环范围）`，见集中裁定 §0 |
| G1-02 补证 | 常驻服务/异步生命周期、固定6对采集开销比较 | B 单次完成并验收；不重跑，不外推稳定开销百分比 |
| CPU / Hotspot | CPU-01 已验收；CPU-02 真实 Verifier 段的容器映射与 record 接线 | CPU-02 A 评审五组反例（屏障协议、符号链、终态、端点、收尾）已一次修复重验（31 项定向回归）；B 未授权，见 [CPU-02 交付 §8](cpu_02_delivery.md)。容器 PMU 归因与 G2 仍未完成 |
| 多场景 / Replay / Scale | 依用途与 Gate 逐步扩展 | 后续计划，不在当前收尾中启动 |

不使用任务完成百分比：已有小样工具链与最终研究目标的工作量不同，测试数也不是 benchmark 数。

## 2. 当前只保留一个实施方向

CPU-01 B 已验收（宿主合成目标 10 项计数有效、354 samples；98 行中 83 行裸地址，0 个 `[unknown]` 不等于符号完整）。CPU-02 A 首轮交付后，原评审注入离线替身发现五组生产接线缺口（就绪屏障协议错误、符号链二进制损坏、失败仍 complete、Docker 端点未固定、日志收尾竞态），已一次修复并以 31 项定向＋4 项官方 parser venv 集成回归重验，见 [CPU-02 交付 §8](cpu_02_delivery.md)。A 未运行真实 Docker/perf，不重跑 Agent 或 READY/smoke/G1-02。

下一步顺序：原评审复核 CPU-02 A 修复 → 用户批准最终 B 清单及工具权限 → 单次真实 Verifier 采样（一次 eval＋一次 record，300s 预算）。当前 `A_REVIEW_FIXES_APPLIED / B_NOT_AUTHORIZED`。CPU-01/CPU-02 结果不构成真实 Agent 热点或容器 PMU 归因，G2 未通过。

`reports/cpu/CPU-01/` 为一次性封存证据，不重复执行；`reports/cpu/CPU-02/` 尚不存在（A 未创建批准/attempt）。[G1-02 交付](g1_02_delivery.md) 为已完成历史阶段，当前 Gate 决议以集中评审为准。

## 3. 代码与证据地图

Python 自有代码实际位于 `src/agent_workload_characterization/`；根目录不另建 adapters/runners 等同名框架。

| 位置 | 用途 | 维护边界 |
| --- | --- | --- |
| `adapters/`、`ir.py`、`metric_contracts.py`、`migrations.py` | 公共来源、语义与版本转换 | 维持已验收小样范围，新增来源另立明确任务 |
| `analyzers/` | macro/coverage、资源与工具派生报告 | 原始输入只读，派生批次独立，不覆盖旧报告 |
| `collectors/` | host/process、资源采样、语义记录、能力检查 | G1-02 最小复用；不要借整理重构计量实现 |
| `runners/container_runtime.py`、`tool_event_env.py` 等 | 共享执行、工具 hook、安全写入与清理 | 修改必须跑受影响生产路径的离线回归 |
| `runners/*entry.py`、`smoke*`、`canary.py` | 各历史批次的薄入口及共享依赖 | 历史入口保留，不因“旧”而删除；不是当前执行指令 |
| `scripts/g1_02_controller.py`、`g1_02_worker.py` | 当前补证协议与自有 worker | 一个生产编排路径；测试只替换运行环境，不预填 PASS |
| `tests/test_*.py`、`tests/integration_*.py` | 单元/本地进程/SDK 集成等不同层级 | 按任务选择，不默认 discover 全历史套件 |
| `data/catalog/`、`workload_catalog/` | 来源与 workload 配置 | 注册值须实际驱动执行；身份 hash 不等于配置已生效 |
| `data/raw/generated/`、`reports/` | 封存运行、历史批准/失败、派生证据 | 本轮只读、原位保留，不能作为缓存清理 |
| `references/`、`.venvs/` | 外部参考与本地环境 | 不修改第三方、不删除环境、不自动执行 |

关键证据入口：[RUN-01 派生 v2](../reports/resource/RUN-01-C-v2/)、[RUN-02 原报告](../reports/resource/RUN-02/20260915T012427Z-2d75aa/)、[RUN-02 review-v2](../reports/resource/RUN-02/20260915T012427Z-2d75aa-review-v2/)、[G1 集中裁定](g1_consolidated_review.md)。失败 attempt、READY 检查与合成用例不计为新的真实任务样本。

## 4. G1-02 固定收尾表（A 离线已关闭）

历史 A 收尾：G102-1～4 已关闭，具体代码/测试映射见 [交付 §2](g1_02_delivery.md#2-四组关闭证据)。后续 B 已完成并验收，当前 G1 决议见 §1；以下保留历史问题，不再是待办。

<details>
<summary>历史审查发现与原验收要求（不再作为当前待办）</summary>

这是原任务 A1–A3/最低回归的落实清单，不新增研究目标。本轮只审查和登记，不修改执行代码。以下均为 2026-09-15 代码快照观察，后续实现变化后以证据逐项关闭。

| ID | 当前发现及代码定位 | 一次关闭所需证据 |
| --- | --- | --- |
| G102-1 协议 / hook | [入口](../src/agent_workload_characterization/runners/g1_02_entry.py) 的 hook 包围整段实验，而非两个 sync 请求；[controller](../scripts/g1_02_controller.py) 的 service 分支未接资源 sampler。原始事件返回已补上，不需重做。 | 同一服务两个同步请求各有共享 hook 事件；service 有实际资源边界；校验 PID/start identity、ID、顺序及终态。错 ID/缺终态必须失败；失败保留已收集证据。 |
| G102-2 比较条件 | 宿主 monitor 仅批前后 poll；没有每条件 CPU/RSS；checksum 仅检查非空；生产 controller 默认常量未由 catalog 驱动。CPU missing/reset 和读耗时检查已有部分实现。 | ON/OFF 每区间宿主记录、实际采样区别；工作量/顺序/门槛由冻结配置驱动，checksum 对照已登记预期；缺边界/reset/缺样本/门槛不满足为 inconclusive。冻结诊断容差依据，不保证 B 一定充分。 |
| G102-3 预算 / 所有权 | stop/verify 仍复用同一个 cleanup_timeout；无 cleanup_pending 消费；预检在 batch deadline 外，各命令得到新 60s。 | 预检、操作、工作、清理使用同一绝对 deadline，每步重新取剩余；落实 15s 操作/8s 工作区间；启动响应丢失仍能按本批身份清理；资源收尾独立于采样/归档错误，超时/未确认不得 PASS。 |
| G102-4 入口 / 输出 | 固定 Docker env 仅用于预检，runtime 未沿用；20 MiB 仅结束后检查；build_plan 身份仅包含 entry/controller/worker，未覆盖共享 runtime/hook/collector；CLI 无任务书要求的第二确认旗标。 | 同一受限本地环境贯穿预检和执行；完整有效依赖身份及门禁；运行中阈值停止、最小失败证据；固定根、独占写入及哈希闭环反例。以上均在 A 用 fake/mock 跑实际入口，不访问 Docker。 |

每项自检记录必须含：实际函数 → 生产调用者 → 离线反例测试名 → 产物字段 → 通过/未通过。不要用“函数存在”“导入 hook”“返回码为零”或测试总数替代验收。

当前 `tests/test_g1_02.py` 仍有调用旧 `run_synthetic_batch()` 的测试，与生产 controller 路径并存；空输出测试修改 `default_exec`，但生产已走 interactive 接口。修复时反例应注入实际传输，不应因缺少接口而偶然 FAIL。缩小 A fixture 的迭代数并断言配置传播；不要用正式 20M × 12 工作量证明接线，遵守任务书 A 的进程/CPU/命令预算。

</details>

## 5. 仓库整理决定

- 文档采取原位逻辑归档：历史 handoff/prompt/delivery 折叠在索引中，不移动、不删除、不覆盖。这避免破坏历史引用及登记哈希。
- 日常状态只维护本页；Gate 决议只维护集中评审；长期方法与完整任务编号仍分别在 methodology / development_tasks。
- 同一任务继续更新既有 handoff/prompt/delivery，不为小修补增加一套新文档。新实验有新身份时才建新批次。
- 后续代码维护项：CLI 帮助中的“no files are written / no analysis pipeline”已经过时；部分命令会写输出或做本机探针。本轮以根 README 的命令分级消除使用歧义，不改被冻结代码身份。
- `references/manifest.yaml` 仍含空 commit 占位；它不是运行镜像/软件身份的权威来源。需要扩展来源时补审计，不为当前 G1 另开修文轮。
- 未跟踪文件包含大量真实开发成果，不等于垃圾；不运行 git clean/reset、批量删除缓存或自动提交。

## 6. 本轮审查与完成边界

范围：必读四文档、数据/语义契约、现有索引与 Gate、全部自有 Python 文件的 AST 静态检查、当前 G1-02 执行链重点审查、文档本地链接、保护文件前后哈希。不是对所有模块逐分支功能验收或生产安全认证。

实际检查：

- 整理前 67 份 docs Markdown；新增本页后 68 份，历史正文保留。导航默认阅读量减少，而不是靠删除历史减少文件数。
- 74 个 Python 文件（src 48、scripts 4、tests 22）全部 AST 可解析，同一 module/class 内未检出重复定义。580 个 `test_*` 函数是静态定义数，不是本轮通过数量。
- 整理前 235 个、整理后 247 个 Markdown 本地路径引用均可解析，68 个 docs 文件均纳入索引。只检查目标文件/目录，不验证外链与锚点语义。
- 3 项短离线回归通过：`test_empty_output_with_zero_return_is_not_experiment_pass`、`test_poll_false_or_missing_timestamp_fails_lifecycle_gate`、`Round5StopChainTests.test_should_stop_interrupts_execute`。其中空输出测试的证据局限已列于 §4，不据此关闭生产反例。
- CLI `--help` 正常；未运行全部测试、formal G1-02 workload、SDK 集成、Docker、网络、模型或权限探测。
- 对整理前 325 个文件建立 SHA-256 基线：非本轮编辑文档、自有代码/测试/schema/catalog、reports、generated raw，以及 references README/manifest。只比较字节是否变化，不声称重新验证所有历史 manifest。大型旧源、venv 与第三方树未遍历或写入。
- 整理后复核 325/325 基线文件哈希不变；G1-02 的真实 approval/marker 均不存在；`git diff --check` 通过。

以上 §6 是仓库整理轮的记录，不代表后续代码修复未发生。随后已按用户授权完成 G1-02 A 修复，当前状态见 §1/§4 与交付；完整 G1 不自动通过。没有新 approval/attempt，也没有提交或推送 Git。
