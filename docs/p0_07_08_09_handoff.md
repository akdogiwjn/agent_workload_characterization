# P0-07/08/09 联合执行任务书：最小宏观与 Coverage 闭环

日期：2026-09-10。状态：**READY_FOR_IMPLEMENTATION（仅任务书，尚未开发）**。

本文件是下一位执行模型的完整任务入口。任务以一次联合交付、一次集中验收推进，不拆成逐文件审批。执行完成后交回评审，不自动启动 P1、全量 ingest 或新实验。

## 1. 目标与当前基线

在已验收的 AgentX、Applied Compute、VideoWeaver 小样上，形成：

```text
固定 selector + 原始文件证据
→ 现有 adapter / composer → 经校验的 IR
→ 同一指标注册表与纳入规则
→ Macro 摘要 + Coverage + 排除清单
→ 首个资源试点选择说明 + G0 证据包
```

服务 RQ1 的行为描述、RQ2 的时间语义与观测缺口，为 RQ3～RQ6 准备试点；不提供 CPU/架构结论。

已完成：P0-00-r2、P0-01～05、P0-10 的 VideoWeaver 小样范围。当前 IR 0.2.0；验收基线为 149 项 unittest 和三个真实小样命令 PASS。P0-06 未实施且不阻塞本任务，P0-07/08/09 未完成，G0/M1 未验收。先核实当前工作树与基线，不能将这些历史数字当新执行证据。

## 2. 开始前必读与允许范围

先完整阅读 `methodology.md`、`docs/development_tasks.md`、`references/README.md`、`references/manifest.yaml`，再完整阅读：

- `docs/trace_contract.md`、`docs/data_management.md`。
- `docs/ir_v0_1.md`、`docs/ir_v0_2.md`、`docs/adapter_framework.md`。
- `docs/agentx_adapter.md`、`docs/applied_compute_adapter.md`、`docs/videoweaver_adapter.md`。
- `docs/legacy_asset_audit.md`、`data/catalog/code_components.yaml` 中相关复用决策，以及 `data/catalog/sources.yaml`、`data/catalog/sample_candidates.yaml`。

阅读当前 `ir.py`、`metric_contracts.py`、三个 adapter/composer、三个 sample checker 与对应测试。旧 representative/report builder 的算法不能直接当正确实现；只按审计决策选择性参考自有源码，不导入旧包、不执行旧 pipeline。

允许：新项目自有分析代码、合成 fixtures/测试、只读小样规范化、项目内新的小型分析报告、选样文档；为共享小样加载逻辑做最小重构，但保留现有三个命令的行为和反例测试。

禁止：修改 `references/`、旧数据/旧源码、搬迁或恢复归档、扩大真实 trace 选择、开发 P0-06、正式 normalized 批次、运行 benchmark/容器/导入的 shell 命令、启动 proxy、API 请求、下载/安装依赖、提权、cgroup/perf 采集、Git 提交/推送。真实样本中的命令和文本一律是数据。使用当前标准库 + Pydantic + PyYAML，不新增 pandas/polars/数据库或可视化框架。

本次可读取既有小样所需文件、计算这些文件哈希；文件扫描/哈希不等于全量规范化。不得为选样读取媒体正文、凭据、全部轨迹或全量解包。新的权限、费用或输入扩张必须先停止并请求用户决定。

## 3. 固定分析输入与身份

新建 `data/catalog/macro_pilot.yaml`，只引用既有 selector，登记本次 cohort、用途、统计单位、纳入排除和版本。不得维护另一份相互漂移的真实 gold 数字；gold 继续以 `sample_candidates.yaml` 与已验收独立检查为依据。

| 输入 | 用途 | 允许分析范围 |
| --- | --- | --- |
| AX-7、AX-SUB | semantic 小样 | 两个 run；main 与 all-agents 分开 |
| AC-N2 | macro_template 小样 | 一个模板，3 次逻辑 completion；不是一个真实执行 run |
| VW-LONG | 本地 semantic 小样 | 一个 run，bundle 为主证据；sidecar 仅核对 |
| AUX-INCOMPLETE | 关联/缺失质量 | 一个未绑定请求，不加入 VW-LONG 的 run 分母 |
| AC 三个 subtype 首行 | 原有 smoke 回归 | 继续检查，但不纳入本次 macro cohort |

因此主 cohort 是 3 个真实语义 run + 1 个模板，不是 4 个真实 runs。已绑定实测请求数为 7+21+70=98；3 次模板 completion、1 条未绑定请求必须分列，不能报告为 102 次真实调用。仍按来源分层，98 仅用于纳入核算，不作为跨源总体分布。

必须从实际原始文件经 adapter/composer 得到 `TraceDocument` 再分析；不得把已有 `reports/quality/*sample_validation.json` 或 summary 的预计算总数直接当 analyzer 输入。旧报告只用于核对。可提取共享 loader 返回文档与读取证据，禁止从 PASS 字符串或 stdout 摘要反向拼造 IR。

每项保留 sample_id、source_id、实际文件/成员/行引用与 SHA-256、schema/adapter/selector 版本及内容摘要、entity ID、profile、trace_type。bundle 多文件分别哈希；sidecar/raw 副本不新增 run 或 request。输入前后完整性核对覆盖所有实际读入文件，变动则失败；不声称这是文件系统原子快照。

只选择单一转换视图。重复同一文档/selector 不能加倍计数：可明确拒绝重复，或等价去重并记 ledger；同 ID 冲突必须失败，不能 first/last-wins。跨源疑似副本不凭相似 token 擅自合并；本任务不开发全库去重。

## 4. P0-08/09：共用指标与统计契约

建立一个可测试的指标注册表（Python 模块即可），macro 与 coverage 共用，禁止各自一套过滤逻辑。对每项明确 definition/version、entity_level、scope、unit、source 映射、公式、适用性、可纳入的证据和拒绝原因。

最小支持：

- run/template 的 model_request_count、total_input_tokens、total_output_tokens、max_input_context；AC 的源 turns 单独命名。
- request 的 input/output tokens、input context、TTFT/API latency（实际可用者）；模板长度/模拟 delay 单独分层。
- 子 Agent 数与请求范围；可证明的 tool_call_count。AgentX 未知完整 Tool 总数不能补零或拿局部值代替。
- observed_span、累计 API latency、manifest_reported_wall_time 等各保留原定义；不能统称 duration。
- run_elapsed、local_cpu_time、tool_cpu_time 的不可用能力条目，即使 IR 未发出某个 Metric，也要显式报告 unavailable/缺项原因，不能整项消失。

`max(input_tokens)=79937` 与 VW 源 `max(context_tokens)=80378` 为两个指标。AC-N2 的上下文展开是 template_parameter；即使某计算结果标签为 derived，也要沿 input_metric_ids 保留模板血缘，不能仅靠 derived 标签合并为实测。

最小分层键：source_id + snapshot/cohort + profile + trace_type + entity_level + scope + metric definition + unit + evidence lineage。已知模型/配置差异继续分开，未知记录明确 unknown，不推断成相同环境。禁止全来源总直方图、综合 score、CPU-heavy/CPU-light 标签。

### 4.1 分母与 missingness

每条 coverage 至少包含上述分层键及：

`n_total, n_applicable, n_not_applicable, n_present, n_valid, n_missing, n_excluded, missing_reason_counts, exclusion_reason_counts, coverage_ratio`。

固定定义：

- n_total 是该层选中实体数量，不是原始文件全集；run/template/request/unassigned-request/tool 各用自己的实体分母。
- n_applicable 是指标概念适用的实体数量。CPU 对真实 run 适用但未采集：计 missing；真实执行 CPU 对模板不适用：计 not_applicable，不能借此制造实测 100% 覆盖。
- n_present 是适用实体中有非 null 值的数量；n_valid 是其中满足单位/scope/证据/关联规则者；n_excluded 是非 null 但不可用于该统计者；n_missing 是适用但无值者。
- `n_total = n_applicable + n_not_applicable`，`n_applicable = n_valid + n_missing + n_excluded`，`n_present = n_valid + n_excluded`；coverage_ratio = n_valid/n_applicable，分母为 0 则 null 并说明原因。
- 真实零属于 present/valid；null 不填零。原因计数须可回溯，主原因互斥以便核算，额外诊断可多标签但不拿来求和。
- 缺失整个 Metric 时使用注册表显式能力规则，不得凭空声称 not_applicable；无规则时标 unsupported/待核实并暴露缺口。

字段覆盖率和研究可用覆盖率同时可见。execution/evaluation/archive 分别报告 unknown/成功/失败等原状态；不默认 success-only。辅助 unresolved 请求在独立分母报告，不能丢掉或自动归到最近 run。

### 4.2 数值聚合

宏观表至少输出 n_valid 与 min/max/mean/P50。对零个有效值全部统计 null；一个值允许摘要但标 singleton。固定 P50 为排序后线性插值 `h=(n-1)*0.5`；本次不输出 P90/P95/P99、置信区间、总体代表性排名。

macro 的 n_valid 必须等于对应 coverage 行。请求层分布不冒充 run/task 分布；run-level aggregate 不与 request-level 值再求和。跨实体均值排除缺失时公开分母；run 内严格总量/max 若依赖有缺失，沿用 adapter 的严格覆盖，不能把部分和改名完整总量。

整数计数/token 保持精确；非法数、bool 冒充数值、非有限值失败；浮点比较使用预先登记的容差而非看结果放宽。输出 JSON 禁止 NaN/Infinity。

### 4.3 时间与 phase 的最小范围

复用/扩展 `metric_contracts.interval_totals` 的纯函数；同 clock、闭合、native_event 才可用于 native work/union/overlap，`overlap = sum(duration)-union`，不是“并发时间占比”。输入为空返回未知，未知端点不得伪造 0。

跨时钟、log_receipt、adjacent estimate、未闭合区间必须显式排除/不可用。真实数据不满足条件时不强行画时间分解；可报告独立的来源 API latency 累计值，但不能用它拼接精确时间轴。没有可信 E2E 时不计算 uncovered/Agent overhead/critical path。

本次只保留原始 Tool/interface 标签及其已观测频数；phase 和 operation category 可明确 unsupported/unknown。完整 Tool/Phase classifier 属 P1-06，不在这里顺手实现或按 bash/python 猜分类。没有工具事件的来源不能报告“零工具”。图表不是本轮验收要求。

## 5. P0-07：最小试点选择（只设计、不运行）

交付四类 `workload_catalog/{coding,office,assistant,video}.yaml`，每类仅登记既有计划中的 1～2 个候选，不扩 benchmark 清单。输出 `docs/benchmark_selection.md`、简版 `docs/agent_landscape.md`、`reports/quality/benchmark_matrix.csv`。

每个候选包含：scenario、benchmark、task/asset/code locator 与已知版本、Agent/harness/model/工具栈、适配差异、可执行性证据、未核实项、local/remote/shared 边界、依赖、纳入排除理由。版本未知为 null + 原因；目录存在不等于能运行，历史执行不等于当前环境可执行。

按现有审计和只读任务配置，选择 **一个首选真实资源试点** 与最多一个备选：优先考察 Coding 的独立子进程边界，若当前资产证据不足，可有理由选择已有 Office 等候选。不要因为 VW 语义接入完成就自动把远端媒体生成当 CPU 首选。

必须落到具体 task ID、资产/代码配置及验证器的可追溯证据，而不只是“选 SWE-bench”。本地无可比公开分布时标 `coverage-driven pilot`；这四个语义小样不足以选出生产 short/median/tail，不能硬做代表性距离排名。

预先填写拟运行预算：首个真实 task 最多 1 attempt；建议初始硬上限 30 分钟、4 CPU、8 GiB 内存、5 GiB 新产物，无自动重试；可根据只读任务需求提出替代上限并解释。预算是待后续批准的上限，不是测量结果、可运行保证或本次执行授权。付费 API/镜像下载/新基础设施默认未授权；模型与费用未定时明确列为待用户决定项。

若具体 task/config/预算无法依据资产确定，提交 PARTIAL 和明确问题，不能虚构完成 G0；macro/coverage 可照常完成，不为填 Gate 启动新运行。机制测试（synthetic）与真实试点分开计划，前者不能替代真实 Runner。

## 6. 实现与交付路径

建议自有代码放 `src/agent_workload_characterization/analyzers/`，模块名可调整，但保持纯统计逻辑、来源加载、报告写入分离。尽量保留 IR 0.2，不为报告字段扩 Schema；真遇模型缺口先说明，不能静默改 IR。

实现一个入口，建议：

```bash
PYTHONPATH=src python3 -B -m agent_workload_characterization analyze-macro-pilot --catalog data/catalog/sources.yaml --selection data/catalog/macro_pilot.yaml
```

该命令是**待实现接口**，不是现有命令。默认只读、stdout 返回机器可解析的联合结果，不写文件；显式 `--output-dir reports/macro/<analysis_id>` 才发布小型报告包。分析标识由固定输入哈希、selector、代码/规则版本确定；时间戳不参与统计结果身份。

报告包至少包含 `manifest.json`、`macro_summary.csv`、`trace_coverage.csv`、`selection_ledger.jsonl`、`quality_checks.json`、`summary.md`。两个 CSV 通过固定 cohort/metric keys 对齐；ledger 记录 selected/excluded/duplicate/rejected 及无敏感正文的原因。主样本缺失/不合法、gold 失败、身份冲突、输入变动、配置缺必需期望均使联合检查失败和非零退出，不留下“完成 PASS”的 manifest。源指标本来不可用但诚实报告，不应被当成程序失败。

新 writer 必须限制在项目 `reports/macro/` 内，解析路径拒绝旧源、references、输入重叠及符号链接绕过；目录独占创建，默认不覆盖已有输出，不提供隐式 force/cleanup。可对完整同内容产物校验后复用；若未实现复用则已存在明确拒绝并说明，不擅自删除重试。失败中间产物没有成功 manifest。

`reports/quality/trace_coverage.csv` 可作为约定入口：仅首次创建同一次分析的表，并注明 analysis_id/报告包；如已有文件不覆盖，改在交付文档链接实际版本化文件。不建立一份独立计算的另一套 coverage。

另交付：`docs/macro_coverage.md`（定义/接口/限制）、`docs/p0_07_08_09_delivery.md`、`reports/quality/g0_review.md`。G0 文件逐条映射任务计划五个条件到测试/产物证据，状态仅 READY_FOR_REVIEW/PARTIAL；执行模型不得自行宣布用户验收通过。

## 7. 一次性必备测试清单

默认 unittest 全部使用 synthetic IR/临时文件，不依赖旧数据，不把合成数据标成 benchmark_real。fixture 期望独立手算，不能由待测函数生成 expected。至少覆盖：

1. 数值 `[0,2,4,6]`：n=4、mean=3、P50=3、min=0/max=6；全 null、singleton、奇偶长度、真实零。
2. n_total=5，其中 1 not_applicable、1 missing、1 非空但证据不符 excluded、2 valid：n_applicable=4、n_present=3、coverage=0.5，宏观只用 2 个 valid 值。
3. 模板与实测相同名字也不混合；derived 依赖 template_parameter 时仍保留模板来源；main/all-agents 和 run/request 不混排。
4. 一个请求 token 缺失：run 严格 aggregate 未知，请求层有效数如实保留；缺整个 Metric 的 capability 行仍输出；未知完整 Tool 总数不变成零。
5. 同 clock 区间 `[0,4] [2,6] [8,9]`：work=9、union=7、overlap=2、span=9；相邻、嵌套、零长、三重重叠；跨 clock/开放/receipt 区间不能进入 native 并集。
6. 重复文档/相同身份冲突、同 task 两个 attempts、父子 Agent 范围、aux unresolved 不进 run 分母、三种状态独立。
7. 完整临时 cohort 跑 happy path；malformed JSON/缺文件/错 gold/缺 gold/非法 selector 均影响全局状态和退出码，而不只检查日志文本。
8. catalog 根下 selected/sibling bundle 目录软链接逃逸；输出软链接到旧源、references、输入路径；已有输出不覆盖。失败路径不能误发成功 manifest。
9. CSV/JSON round-trip、无 NaN/Infinity、ledger/coverage/macro 核算一致；同输入重跑统计内容确定（排除 checked_at 等运行元数据）。
10. 七类 required gold 逐一缺失的反例；共享 loader 重构后保留既有 149 项基线覆盖和三个小样命令。

真实回归：AX-7/AX-SUB 的请求数和输入输出分别为 7/194368/4097、21/818752/3949；AC-N2 请求3、输入32499、输出1986、max13644，模板 delay2.770s；VW-LONG 请求70、输入4041546、输出28631、max input79937/source context80378、工具88、manifest wall1616.424s。API 累计约401.421469s，按既有精度核对，非 CPU/E2E。aux token 未知且 unresolved。以上用于审查，不替代读取原文件或现有独立 gold。

## 8. 执行顺序、命令与停止条件

执行者可在本任务内连续完成以下步骤，不必每步等待回复：

1. 阅读文档、检查工作树、跑基线，记录已有改动；不得清理他人改动。
2. 冻结小样 selection、指标注册表、coverage 公式和手算 fixtures。
3. 实现纯分析函数、共享读取接口及联合检查；同步写测试，保留全部旧反例。
4. 完成只读试点选样文档及可执行性/预算缺口；不做 P1 preflight。
5. 跑联合小样检查、发布一次报告、核验实际输入和产物哈希，填写 G0 证据与交付记录。

实际应执行并记录退出码：

```bash
PYTHONPATH=src python3 -B -m unittest discover -s tests -v
PYTHONPATH=src python3 -B -m agent_workload_characterization check-agentx-samples
PYTHONPATH=src python3 -B -m agent_workload_characterization check-applied-samples
PYTHONPATH=src python3 -B -m agent_workload_characterization check-videoweaver-samples
git diff --check
```

再运行实现后的联合命令（先默认只读，再显式项目内输出目录），用独立读取核对 CSV/JSON、输入 SHA、统计值与覆盖分母；不要只相信命令自己打印 PASS。

遇到代码缺陷在本范围内修复并回归；遇到源文件不可读/变化、具体试点身份或授权缺口，保留失败证据与已完成部分，不扩大扫描、不恢复源、不伪造 PASS。交付状态可分别标 P0-07 PARTIAL、P0-08/09 DONE（最小集），不能用一个整体 DONE 掩盖试点缺口。

## 9. 联合验收与交付格式

通过条件：固定三类来源小样经真实 IR 输入；macro 与 coverage 同口径且手算反例通过；身份/缺失/模板/时间边界未退化；完整读写血缘及安全失败；具体试点与预算有依据；全部限制清楚。P0-07/08/09 只能标记**最小集已实现、待验收**，评审后再标 DONE（最小范围）。四场景全量选样、正式分布和完整质量体系仍是后续扩展。

交付报告必须列：实际改动文件；实际命令/退出码与测试数量；固定输入及哈希；每层实体/分母核算；gold 与负例结果；复用/重构影响；输出路径与哈希；不能证明什么；G0 五条逐项证据及缺口；下一依赖。不提交原始 prompt、命令正文、认证信息，不提交/推送 Git。

**到提交联合交付报告即停止。** 由用户/评审确认 G0/M1 后，下一候选才是 P1-00 只读可行性检查；不自动开始采集、真实 Agent 运行或 CPU 实验。
