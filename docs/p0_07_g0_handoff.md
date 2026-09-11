# P0-07 收尾与 G0 评审任务书

状态：READY_FOR_IMPLEMENTATION（仅文档与只读证据核实，尚未执行本任务）。

## 1. 本轮目标与基线

把一个真实资源试点从“候选名称”推进到可评审的 task/asset/harness/model/verifier 配置，并准备 G0 五条证据。不是实现 Runner，也不是提前运行试点。

已验收：P0-00-r2、P0-01～05、P0-10 VideoWeaver 小样、P0-08/09 最小宏观/coverage。P0-08/09 以 `reports/macro/macro-pilot-v6/` 和测试隔离收尾为当前依据；175 项隔离全量测试、三个小样命令和只读 analyze-macro-pilot 已通过。历史 v1～v5 不是当前验收依据，不删除或改写这些报告。

P0-07 仍 PARTIAL，G0/M1 未通过，P0-06 暂缓。当前首选 `django__django-16485`，备选 DocOps；这些是待核实候选，不是本任务预先保证正确的任务身份或环境配置。

本次服务 RQ3 的资源试点设计，以及 RQ1/RQ2 的最小语义 Gate。完成的是设计证据，不声称本机可执行性、资源归因或 CPU 测量已验证。

## 2. 必读材料与只读入口

先完整阅读 `methodology.md`、`docs/development_tasks.md`、`references/README.md`、`references/manifest.yaml`，再阅读：

- `docs/data_management.md`、`docs/trace_contract.md`。
- `docs/p0_07_08_09_handoff.md`、`docs/benchmark_selection.md`、`docs/agent_landscape.md`。
- `docs/legacy_asset_audit.md`、`data/catalog/sources.yaml`、`data/catalog/code_components.yaml`。
- `workload_catalog/coding.yaml`、`workload_catalog/office.yaml`、`reports/quality/benchmark_matrix.csv`。
- 当前 v6 manifest、quality_checks 与 ledger；`reports/quality/g0_review.md`、`docs/p0_07_08_09_delivery.md` 包含过时返修描述，不能直接当现状。

按 catalog 定位旧 SWE-bench trajectory、已有自有 runner 配置、DocOps 任务/验证器证据。按需要阅读 `references/repos/SWE-bench`、DocOps、Harbor 等相关源码/配置；不遍历所有参考仓库，不重新审计全部 trace。

允许只读操作：`rg`、文件读取、`git -C <repo> rev-parse HEAD/status`、固定少量文件哈希、压缩包目录清单和指定小型元数据成员读取。执行前检查工作树，保留用户改动。只核实一个首选、最多一个备选。

## 3. 明确不授权的操作

- 不修改 references、旧项目源码、原始数据、历史报告包或系统配置。
- 不运行 benchmark、Runner、验证器、gold patch、轨迹里的命令或第三方 Python 模块；静态阅读不等于导入执行。
- 不创建/启动容器、安装依赖、拉镜像、下载任务/模型、不发 API、不探测凭据有效性。
- 不做 P1-00 的 cgroup/perf/namespace/PMU 能力检查，不提权、不启动资源采样。
- 不修改分析器、IR、adapter 或扩展真实 macro cohort；不全量 ingest，不重放，不迁移/恢复归档。
- 不读取 `.env`、认证 header、token 文件或整个用户配置来寻找密钥；环境变量只记录后续需要的名称，不读取/输出值。
- 不 Git commit/push。需要网络、权限、费用或新任务范围时列为待决事项，不能自行扩大行动。

现有小样和 unittest 可用于核实回归，但这不是重新实施 P0-08/09 的任务。不要为了填全配置启动一次真实运行。

## 4. 核实清单：每项都要证据或缺口

每条事实记录 evidence_id、实际 locator、文件 SHA-256、行号/JSON pointer、读取日期、适用版本、结论类型（静态确认/历史运行/设计建议/待验证）。目录存在不等于能运行，历史模型名称不等于当前可调用。

### 4.1 Task 与资产

- 核对 `django__django-16485` 是否确实属于所登记的 benchmark/subset；记录数据 release/revision、instance_id、repository、base_commit 和对应任务记录证据。
- 核对现有 trajectory 的实际位置、Agent/harness/model、attempt/outcome。先检查文档声称的路径，找不到时不得原样沿用。
- 分开 benchmark 仓库 commit、任务数据版本、被修复仓库 base_commit、历史提交配置版本；不能用一个短 SHA 代替四者。
- 找出所需任务资产、依赖规格、镜像构建说明/引用；digest 本地未知则 null + 原因，不下载或编造。
- 如果数据只在压缩包内，记录包哈希和指定成员；不全量解包。prompt/issue 内容只做必要只读核实，不复制敏感正文到交付。

### 4.2 Agent、harness 与未来执行入口

- 明确 Agent 执行 harness 和 benchmark evaluator 的区别；SWE-bench evaluator 不是会自主生成 patch 的 Agent Runner。
- 首选配置必须收敛为一个 Agent/harness 组合，不写“OpenHands / SWE-agent”作为已冻结配置。
- 记录代码完整 commit、入口脚本/函数、配置文件、工作目录、依赖锁或其缺失、产物出口、最大步数/超时/失败处理的配置入口。
- 历史 trace 使用的版本和拟运行版本分列；不声称无需适配。可提供未来命令模板，但参数应有源码/帮助文档依据，显著标记“未执行、待 P1 实现与授权”；未知参数不编造。
- 缺少可执行自有 wrapper 时只列所需 P1-07 适配工作，不在本任务实现。

### 4.3 模型与授权分离

- 记录历史模型与拟用模型两列，区分 provider/model ID/version、温度/采样参数、token/turn 上限、endpoint 配置方式和未知项。
- 只能基于用户已有明确选择冻结模型；当前无选择时给一个推荐配置与一个备选，标 proposed，并说明已有资产兼容依据、适配风险、需用户确认的准确字段。
- 不假定旧 Sonnet/GPT 名称现在可用，也不假设已有 API key 可以使用。无本地证据的价格/可用性标未核实，不输出猜测费用。
- 费用上限待用户确定时单独记录；模型/API 的实际执行授权和设计选择是两件事。没有运行授权不妨碍提交设计评审，但未定模型不能写成已冻结。

### 4.4 Verifier

- 静态追踪 task → test specification → evaluator → 结果文件/成功判定的链条，记录配置/函数位置。
- 明确 candidate patch、test patch、gold/reference patch 各自用途；不得让 Agent 输入参考解答，也不能把应用 gold patch 当成 Agent 完成任务。
- 记录预期验证命令来源、测试集合/判定字段、退出码与 evaluation_status 映射、基础设施失败与任务失败的区分。
- “静态判定逻辑已核实”不等于“在本机复现验证器通过”。后者属于后续 Runner/评估验证，不是 G0 设计阶段强制运行要求。

### 4.5 资源边界与预算

- 为选定配置列出 Agent runtime、工具接口、实际执行进程/服务、容器、远端模型的关系。不得仅因叫 bash/python 就断言一次调用必有独占子进程/cgroup。
- 区分已见源码机制与待 P1 验证假设；常驻 shell、进程内编辑、子进程后代、后台任务、共享服务和远端不可测部分都列出。
- 计划采用 run/service/scope 测量作底线，per-tool 独占归因仅作为待验证目标；资源缺口不通过改造 workload 后冒充原配置来消除。
- 保留建议预算：1 task、1 attempt、30 分钟、4 CPU、8 GiB 内存、5 GiB 新产物、0 自动重试。若依据任务需求建议调整，明确原因和等待批准，不自动放宽。
- 分开未来 build/setup、Agent 执行、verifier 的计时与产物范围；明确 timeout/失败是否还需 verifier、残留产物处理方案。这里不创建资源、不执行 cleanup。

## 5. 交付文件与内容

新增：

1. `docs/pilot_execution_spec.md`：上述任务、配置、验证器、边界、预算、未来实施依赖及非目标。
2. `workload_catalog/pilot.yaml`：机器可读设计清单，字段至少包括 spec_version、status、primary/backup、task/config/asset 版本、evidence_refs、budget、pending_decisions、execution_authorized=false；未知值 null 并附原因。它不是可直接运行的配置，不自动读取凭据。
3. `reports/quality/pilot_evidence.json`：证据索引与核实结果，不复制日志正文或凭据。file SHA 与 record/member 引用明确区分。
4. `docs/p0_07_g0_delivery.md`：实际改动、读取范围、实际命令、结果、剩余缺口和用户需决定的事项。

增量修订：`docs/benchmark_selection.md`、相关 workload catalog、`reports/quality/benchmark_matrix.csv`、`reports/quality/g0_review.md`。只改与本次试点有关的条目；不把四场景候选扩成正式代表性集合。

修正文档漂移：联合交付记录把历史错误输出标为 superseded，当前依据链接 v6；纠正 model_busy/observed_span 混用和旧测试数量，不改写历史报告字节。README/开发计划/方法论使用准确范围：P0-08/09 最小集已验收，P0-07 待收尾，G0 未通过。

## 6. G0 证据与状态规则

`g0_review.md` 按开发计划原有五条条件逐条列证据、适用范围、缺口与待评审结论：

| 条件 | 本轮处理 |
| --- | --- |
| 资产审计与只读边界 | 引用既有验收，不重做全量审计；区分文档规则与已有测试 |
| 三类输入 Schema | 引用已验收 AX/AC/VW 小样及当前 IR |
| 身份/缺失/context/时间 fixtures | 引用实际测试；默认合成测试与显式真实回归分开 |
| Macro 与 coverage | 引用 v6 及测试隔离验收，不重新证明正式总体分布 |
| 具体试点任务/配置/边界/预算 | 使用本轮证据及明确用户决策；缺口不能被“待授权”一词掩盖 |

配置证据充分且用户选择已明确时，执行者最多标 `READY_FOR_REVIEW`；最终 G0/M1 由用户/评审确认。仍缺模型/关键任务资产/harness 或 verifier 证据时，P0-07 保持 PARTIAL，明确缺的是设计信息还是未来执行授权。

不要求本阶段本机运行 verifier 或真实 Agent 才能提供设计证据；不因为 G0 尚未通过而启动 P1-00 来“补证明”。

## 7. 自检与集中交付

- 检查 YAML/JSON 可解析、所有 evidence 引用唯一且可解析、文件存在性及实际 SHA；缺文件是缺口而不是假填版本。
- 校对 spec/catalog/selection/G0 的 task、版本、预算、状态完全一致。每项动态能力写“未检查”，不是“支持”。
- 检查 Markdown 本地链接和 `git diff --check`，不使用测试数量替代配置证据。
- 只改文档时无需为凑交付重跑全部真实数据；若实际跑现有回归，记录命令/退出码，不能把历史175测试写成本轮新执行。
- 不修改源码、fixtures 或输出正式分析包。发现已验收实现疑点可附后续 issue，本任务不顺手重构。

一次性提交：证据包、首选和备选差异、可静态确认事项、待 P1 验证事项、最少必要用户决策。最多合并为三个问题：模型/provider 选择、预算/费用上限、不可缺少的资产或配置来源；不询问可自行只读核实的路径和版本。

**完成文档与核实后停止。** 用户解决待决项并通过 G0 后，再单独准备 P1-00 只读能力预检任务书；不自动进入预检、采集或运行。
