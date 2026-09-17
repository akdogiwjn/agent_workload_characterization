# CLOSEOUT-01：RUN-02 报告收尾、G1 评审材料与仓库导航整理

日期：2026-09-15。状态：任务书已准备，尚未实施。
配套：[执行提示词](repository_closeout_execution_prompt.md)。

## 1. 目标与授权

按“任务书与提示词 → 实施模型交付 → 原评审验收”一次完成本批。
目标不是增加实验或重新开发框架，而是让用户从 README 看懂已完成什么、证据在哪、下一步待谁决定。

本批只允许自有导航文档、评审材料及新版本派生报告。允许只读分析已有数据、临时离线核算和相关定向检查。
不调用 Docker（包括查询）、网络、模型、READY/smoke、Agent/Verifier；不安装、下载、拉镜像、读取生产配置/凭据或环境变量全集。
不修改执行代码、采集器、分析器、测试、catalog、schemas 或第三方内容；不新增通用工具或空目录。
不删除、移动或重命名现有文件，不提交/推送 Git，不创建新的运行批准或 attempt。

## 2. 先读什么

完整阅读既定四份基础材料：`methodology.md`、`docs/development_tasks.md`、`references/README.md`、`references/manifest.yaml`。
再读 `docs/data_management.md`、`docs/trace_contract.md`、本任务书、`docs/g1_consolidated_review.md`、`docs/run_02_r2_delivery.md`。
核对 RUN-02 新旧报告时按需阅读现有 `analyzers/run_02_analysis.py`、`resource_summary.py`、`tool_timeline.py`，只读，不重写它们。
仓库导航按实际目录和文档用途盘点，不要求阅读每轮历史返修正文或逐文件遍历 venv/wheelhouse/第三方仓库。

## 3. 已确认事实与输入

真实 run：`20260915T012427Z-2d75aa`，attempt：`20260915T012427Z-2d75aa-a1`。

| 输入 | 路径 | 使用方式 |
| --- | --- | --- |
| 封存运行 | `data/raw/generated/RUN-02/20260915T012427Z-2d75aa/` | 原始权威证据，10 文件（含 manifest），647461 字节；manifest 列出其余 9 文件 |
| 原派生报告 | `reports/resource/RUN-02/20260915T012427Z-2d75aa/` | 保留原字节，修正版本指明 supersedes，不覆盖 |
| R2 批准/marker/原审批备份 | `reports/resource/RUN-02/retries/R2/` | 只读血缘，不更新身份或状态 |
| 本次交付 | `docs/run_02_r2_delivery.md` | 原件保留，SHA-256 `fb18bec406cc3fffa832194da7414596df1444d31082c16c1f983207296b09ae` |
| G1 既有判定 | `docs/g1_consolidated_review.md` | 六条既定标准，不能降低或自行签署通过 |
| 历史证据 | RUN-01-C/v2、G1-01 A/B、原 RUN-02/R1、READY | 保留，不重跑、不重封存 |

原评审已接受本次真实运行与联合观测范围，G1 整体尚未通过：

- 管道 execution/evaluation/archive/cleanup 为 ok、report complete；resolved=true；官方日志 10 项测试通过、exit=0。
- 30 请求（27 正常、3 失败），26 steps，11007 输出 tokens；steps、请求数、工具数不是同一指标。
- Agent 为 LimitsExceeded、submitted=false；补丁来自容器工作树 git diff，不是主动提交完成。
- 28 次工具 open/closed，0 个 hook error；其中 1 个工具 returncode 非零。closed 不等于工具成功。
- 宿主 717 次快照、716 可读；mini 首末可读快照 CPU 增量 4.19 s，不是完整生命周期 CPU，退出后的最终值不可用。
- Agent 容器 51.007123 core-s / 143.651636264 s；Verifier 3.64963 core-s / 12.264456124 s。正式 I/O 为 null。
- 两次真实运行 RUN-01、RUN-02 属于同一 task 的不同 attempt；启动前失败与合成 canary 不算真实任务样本。不能据两次 CPU 数值差异推断开销或倍率。

以上是核算对照，不是要求把报告硬编码为期望值。输入不符时保留并一次列明，不修原数据。

## 4. 工作包 A：新版本派生报告，原件不动

独占创建 `reports/resource/RUN-02/20260915T012427Z-2d75aa-review-v2/`。
若目录已存在，先检查是否已有本批完整交付；不得覆盖、删除或自动再开 v3。

产物限定为 `summary.json`、`summary.md`、`corrections.md`、`manifest.json`。
可复用原摘要并以原始证据核对后作显式投影修正，不改变原始计数，不把文本更正写成重新测量。

必须集中修正：

1. 删除/替换“真实工具仅 fake 有 hook”“宿主 CPU/RSS 未采集”的旧模板结论；保留实际覆盖缺口：后代不完整、进程峰值未采、非独占 Tool CPU、collector 不应重复计入。
2. 原生工具起止和 duration 以 `mini_tool_events.jsonl` 为准。历史 receipt 推估若保留，只能作为明确标注的辅助视图；不得继续声称本次没有 native hook 或把估计窗口当误差上界。不要求扩展工具分类器。
3. 体现 LimitsExceeded/未提交/工作树 candidate、27/3 请求状态、28 工具/1 非零返回码；说明各自计数语义。宿主 4.19 s、RSS last-readable 与 sampled-max 分开，不能称退出时精确值。
4. 归档计账按本次 metadata、实际全树和 manifest 核对：旧摘要中的“354904 字节未进入计账/未来才全树计账”不能直接沿用 RUN-01 模板。分开报告 metadata 快照值、最终实际字节和清单覆盖；差额只在确有证据时解释，未知则注明，不能捏造 supplement 文件。
5. 容器 CPU/Wall 按边界计数核算；I/O formal=null、diagnostic 原值可保留。工具时长不是 CPU，scope 峰值不可相加；不做 RUN-01/02 性能因果比较。

manifest 记录全部读取的证据文件相对路径、bytes、SHA-256；原 raw/report manifest 本身也入输入血缘。
记录 supersedes 原报告路径与哈希、派生方法、生成时间及明确“未运行新实验”。输出 files 覆盖其余三个文件，不递归自哈希；写后回读验证 missing/mismatch/unlisted。
corrections 列旧字段/问题/新口径/证据，不复制全部返修历史。
不要运行会覆盖原目录的旧报告命令。现有分析器遗留问题可在交付中记录为后续维护项，本批不修改执行或分析代码。

## 5. 工作包 B：G1 集中评审材料

更新 `docs/g1_consolidated_review.md`，以既有六条为行，逐条列：既有结论、本次新增证据（文件和字段）、已满足范围、剩余缺口、建议判定。
更新前的文件作为本批输入记录哈希；在同一文档保留上次评审的日期与结论摘要，不冒充过去已经验收了新证据。

本次已接通真实 hook/mini 宿主/容器联合观测，应消除“下一步才接通”的过时判断，但不能因此把短命后代、服务、异步作业、开销比较容差等未覆盖项标为完成。
整体状态保持 `PARTIAL / REVIEW_PENDING`；实施模型可提出限定范围建议，由原评审裁定，不自行更改 G1 标准或授权 P2。
最后只列最多三项真正影响下一阶段研究的缺口/候选任务，区分已接受降级与必须新增证据。不要为历史样式开新的阻塞项，不自动生成一系列执行任务书。

## 6. 工作包 C：全仓导航与当前状态收敛

“全仓整理”是职责、入口和状态整理，不是物理迁移。

### C1 唯一文档导航

新增 `docs/README.md`，作为唯一文档索引，包含：

- 新读者最短阅读路径、执行者按任务阅读路径、评审者证据阅读路径。
- 长期规范、当前有效任务/评审、历史阶段交付、历史执行提示词四类。
- 列出所有现有 `docs/*.md`（包括本任务书/提示词/交付）和根目录 README/methodology 的用途、状态、后继或对应关系。没有后继就注明历史记录，不编造替代关系。
- 旧提示词含批准/执行旗标仅代表历史任务文本，不提供当前授权。
- 明确“当前任务”仅指 CLOSEOUT-01；旧 RUN-02/R1/R2 的启动准备不再是下一步。

只在索引标注历史文档，不给每个旧文档加状态横幅，避免改变历史证据哈希。

### C2 根 README 与计划

- README 保留项目目标、技术路线、一个当前状态块、最短导航与已核实的基本离线使用说明；删除堆叠的多个“最新/当前下一步”段落，以索引中的简短阶段时间线保留其历史信息与链接。
- `docs/development_tasks.md` 保留任务编号、目标和 Gate 条款；顶部只保留一份当前摘要。修正显著过时的状态标题和里程碑状态，但不以存在代码/测试数量证明整项 DONE。
- `methodology.md` 仅更新进度/导航类段落；不重写研究方法、指标定义或验收门槛。
- 当前事实：G0 有已通过记录；RUN-02-R2 真实联合观测已验收；G1 整体待集中评审。P0/P1 各项是否完成须有既有交付依据，不能全批标 DONE。

### C3 目录与产物地图

在 docs/README 中加入实际目录树（浅层即可）：src 内 adapters/runners/collectors/analyzers、tests、scripts、schemas、workload_catalog、data/catalog/raw/normalized、reports、references、venv/软件缓存。
明确现存/仅规划目录，不把目标树当已实现。说明哪些是源代码、合成测试、第三方软件、外部旧数据 locator、封存证据、可再生派生报告及可编辑导航。
数据/报告按批次建导航，不枚举数万条 trace。至少链接 RUN-01、G1 A/B、RUN-02-R2、新修正报告及失败/READY 证据组。
“57/数百项测试”不等于任务数、模型请求数或独立实验数。
疑似重复文档、将来可迁移/合并/删除内容只列建议（源→拟去向→引用/哈希风险），本批不执行。

## 7. 允许修改与交付清单

| 类型 | 路径 |
| --- | --- |
| 新派生报告 | §4 固定 review-v2 目录的四文件 |
| 新导航 | `docs/README.md` |
| 当前状态与评审 | `README.md`、`docs/development_tasks.md`、`docs/g1_consolidated_review.md`、`methodology.md`（仅进度段） |
| 本批唯一交付 | `docs/repository_closeout_delivery.md` |

上述以外不修改。尤其保留所有旧 handoff/prompt/delivery、references、data、workload_catalog、旧 reports、批准/marker 和代码原字节。
发现重叠的用户未提交改动先记录并保留，不 reset、不覆盖无关内容。新文件若已存在先核实归属。

## 8. 有界验证与停止

1. 实施前后核对输入 raw、原报告、R2 状态目录、旧 RUN-02/R1/READY 证据哈希；只读/只哈希，不输出原始消息、密钥或环境全集。清点 references/旧源无需遍历全文；用改动清单确认不在修改范围。
2. 新报告 input/output 哈希全核对，数值与本次边界/事件/宿主证据一致；旧目录不变。缺失/不一致不能标 PASS。
3. 索引覆盖全部 docs Markdown（明确排除范围），新增/修改文档本地链接有效；不联网验证外链，不扫描第三方缓存。检查所有顶层“当前下一步”不互相矛盾。
4. 不改代码则无需再跑全量 unittest、SDK 集成、模型/容器 canary；以离线数据断言、JSON/Markdown 链接、哈希与 `git diff --check` 为验收。只报告实际执行的检查及数量。
5. 交付文档写清实际改动、新旧报告关系、G1 待判事项、导航入口、保护文件核验、未执行事项；未来清理建议放同一交付，不再增加一堆独立文档。

完成即停止。原评审集中验收报告语义、证据保真和导航可用性；不因排版/命名偏好单开返修。仓库整理不授权任何真实实验或 G1 自动通过。
