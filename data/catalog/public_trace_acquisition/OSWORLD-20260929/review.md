# DocOps / OSWorld 公开 Agent trace 有限核查

日期：2026-09-29。范围是公开来源定位、一个小样获取和离线结构检查；没有执行轨迹、benchmark、Docker、模型或 Replay。

## 对照结论

| 来源 | 固定身份 | 本轮实际可见内容 | 是否选取 |
|---|---|---|---|
| DocOps | 本地官方仓库 commit `ccf7a751bc5c8a69c1cdd0400125d53455b33be3` | 任务、输入资产、Harbor harness 结构和 artifact-level deterministic verifier；本地核查未发现真实 Agent trajectory、运行结果或资源样本 | 否 |
| OSWorld / OSWorld 2 | 官方 OSWorld-V2 release `osworld-v2-2026.08.08`；本次样本来自 Hcompany/trajectories revision `ede2a362c99ddba0d03f439c47a0b8fea6abae22` | Hcompany README、索引和三条 per-run JSON；README 将 OSWorld 上游归属为 `xlang-ai/OSWorld`，并声明 Apache 2.0、PII masking 和截图占位符 | 是，明确为第三方公开镜像，不冒称官方发布物 |

官方 OSWorld 页面说明 verified trajectories 已托管在 Hugging Face；官方 `osworld2.0-trajectory` 数据集本轮查询显示需同意分享联系信息且总量约 288GB，因此没有接受条款或下载整包。选择 Hcompany 镜像是为了取得可追溯的 per-run 轨迹正文，同时保持本轮 30 MiB 上限；这降低了来源权威性，后续若需正式研究应再核对官方发布物。

## 选样

从保存的 `raw/index.json` 过滤 `benchmark=OSWorld`、`model=Holo4 27B`、`run=1`，按 `(task,id)` 字典序取前三个不同 task：`chrome_1`、`chrome_10`、`chrome_11`。没有按成功分数或轨迹“漂亮程度”筛选。三条正文 URL 绑定同一固定 revision，文件 bytes/SHA 见 `manifest.json`。

## 离线结构检查

| task / run | 步数 | 动作调用 | 动作名摘要 | verifier | 时间字段 | 资源字段 |
|---|---:|---:|---|---|---|---|
| chrome_1 / 1 | 9 | 9 | click_desktop 4、wait_desktop 3、scroll_desktop 1、answer 1 | `execution_time_s`、`exception`、`details` 存在；exception 为 null | 顶层只有 `duration_s`，无逐步时间戳，时钟语义 unknown | CPU/内存 missing |
| chrome_10 / 1 | 8 | 8 | click_desktop 3、write_at_desktop 2、wait_desktop 2、answer 1 | 同上 | 同上 | CPU/内存 missing |
| chrome_11 / 1 | 10 | 10 | click_desktop 5、shell 3、write_at_desktop 1、answer 1 | 同上 | 同上 | CPU/内存 missing |

三条均有明确 `id`、`benchmark`、`model`、`run`、`task`、`success`、`score`、`duration_s`、token usage 和 steps。每步存在 action call；参数字段可检查但本报告不复制其值。第一、二条没有结构化 `results` 条目，第三条有 3 个字符串结果；结果是否完整不能由存在性推定，因此工具返回完整性为 unknown。截图引用存在；README 声明敏感信息已掩码、部分截图替换占位符，但本轮不把这视为逐字段隐私审计证明。

没有逐步 `timestamp`、明确时钟/单位或 CPU/内存数据；`duration_s` 是发布的 run 汇总字段，不能拆成 tool wall，也不能推算系统资源。模型为 Holo4 27B，harness/version 和桌面环境只由 README/数据集说明提供，未形成不可变软件镜像身份。

## 能支持的有限用途

- 可做 OSWorld Computer-use 行为序列的描述性小样：任务身份、动作类型/顺序、步骤数、部分结果字段、发布的总时长、verifier outcome 和 token usage。
- 在同样明确限制下，可与 Coding 的请求/工具计数等宏观行为字段做字段级描述对照；不能把任务、模型、harness、时间语义或观测 scope 当作相同。
- 不能支持 CPU、内存、热点、I/O 或等待归因；不能把三条样本当作 OSWorld 总体或类别代表，也不能把成功结果当成资源结论。

## 缺口与唯一下一步

仍缺少官方发布物的无条款小样、不可变 harness/环境身份、逐步时间语义、结构化且完整的工具返回、资源观测和更广任务覆盖。唯一建议是：先由用户单独决定是否接受 Hcompany 镜像的许可/来源作为行为分析输入；若不接受，应申请官方 OSWorld 轨迹数据的合规访问方式，再单独设计 adapter。当前不进入 adapter 开发、不执行 OSWorld、不恢复 CPU-02 或 Replay。

请求与文件完整性、失败请求和响应预算记录见 `manifest.json`；manifest 不自哈希。
