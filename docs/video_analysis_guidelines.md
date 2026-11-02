# 视频分析口径与验收说明（VIDEO-ANALYSIS-CORRECTNESS-REPAIR-01）

本文记录四仓视频分析链的口径、单位和质量规则，作为后续分析的验收依据。
实现：`scripts/video_analysis_chain.py`（可复用入口），历史批脚本为兼容包装器。

## 通用入口

```bash
python3 -B scripts/video_analysis_chain.py \
  --run <run目录> --repo <videoweaver|vimax|video-use|openstoryline> --out <新目录>
```

- 输出目录已存在即拒绝（防覆盖封存分析）。
- 导入模块无写入副作用（不自动生成报告/改写文件）。
- 不支持格式明确报错，不猜测解析。

## 输入格式

- JSONL 读取为质量感知：返回行号、解析错误、非对象行、截断末行、缺文件状态；
  损坏不能静默忽略后判 complete；保留可分析有效部分，整体质量 partial/error。
- 资源流：`resource-stream-v1`（VideoWeaver）/ video-use/OpenStoryline 的
  `sampler_rows[].cgroup` / ViMax 的 `resource-samples.jsonl`。
- 用量：video-use `token_usage_record`；VideoWeaver `ledger/ledger.json` usage 事件；
  ViMax `model-events.jsonl` + `ledger-state.json`。
- 媒体：ViMax `model-events.jsonl`（video_create/video_poll/video_call/video_download）。

## Scope

- 容器 cgroup + netns 各自独立 scope；宿主 gateway/verifier 不与任务容器混 scope。
- 资源区间校验端点 scope/容器身份一致；身份缺失如实标“无法确认”，不补造。
- 历史缺身份字段的样本保留可用限定描述，不强行改 raw。

## 单位

- CPU：`cpuacct.usage`(v1) 纳秒→采样器转 usec→`usec/1e6 = core-seconds`，只换算一次；
  `cpu_average_cores = 有效 CPU 秒 / 对应有效墙钟秒`（不是利用率）。
- v2 `cpu.stat` usec 直接 `usec/1e6`。其他来源先明确适配，不猜。
- 内存：bytes（CSV/机器结果），MiB 仅用于图表展示；`current` 与 `kernel peak` 分列不相加。
- I/O：累计量（bytes）与速率（Bps）分别标注，不混称。
- 网络：netns 逐接口累计，不盲加回环与外网。

## unknown / partial 规则

- `null`、缺字段、真实 0 分别处理；不用 `or 0` 把未知变测得零。
- 缺部分值时报告“已观测部分和 + 覆盖数量”，不冒充完整总量。
- 缺失采样/长 gap 标 partial/error，不插值、不补零。

## 去重与事件关联

- video-use：按 response_id 去重；同 ID 冲突显式报告（不 first/last-wins）；
  缺 ID 单列不按位置猜配；逐响应值与累计快照分开；多 turn 按 thread/session
  作用域交叉核验（不拿最后 turn 累计与整个 thread 求和直接比较）。
- VideoWeaver：按真实 response_id（SSE）或本地 request_id（非 SSE）去重；
  无 ID 事件不跨请求合并；缺 total 不填 0。
- ViMax 媒体：按 request_id + task_id 关联（不按位置/最近请求）；
  open 无终结 = 右删失尝试（不计 0、不断言未受理）；重试次数、受理、明确拒绝、
  结果未知、轮询终态、下载与本地产物分别统计；轮询状态按可靠事件顺序取最新已观测，
  终态后矛盾状态报异常。

## 质量判定

- 质量结论从实际数据计算，禁止写死 `measurement_quality="complete"`。
- 资源区间：两端时间有效且递增；scope/身份一致；读取状态有效；计数非负有限；
  CPU/I/O 无回退；读缺测不丢有效写；CPU 缺测不影响有效内存点；内存下降合法。
- 零有效区间不能给出“完整 CPU 总量 0”。

## CSV / 图表来源

- CSV、机器结果、图表共享同一份计算结果（单位只换算一次）。
- 四面板横轴为完整任务/采样窗口（即使只有前 50s 有效也显示完整约 507s）；
  缺测中间/尾部区间阴影展示，不先过滤 null 后跨缺测连线；gap 判定来自采样契约。
- 图例标注累计量或速率，不把 CPU 累计称利用率。

## 已支持 / 未支持

- 已支持：四仓 BASELINE 当前实际出现的格式；`analyze_run` 的四个 repo 分支。
- 未实现：逐调用耗时（tool 级耗时归因）——不得用协议返回间隔冒充进程实际耗时。
- 未实现：超出当前四仓格式的新来源（明确报错，不猜测）。

## 入口接线（VIDEO-ANALYSIS-ENTRY-WIRING-FIX-01）

- 来源识别：ViMax 规划/媒体按实际存在的文件明确识别——资源：`samples/resource-stream.jsonl` →
  `samples/resource-samples.jsonl` → 根级 `resource-samples.jsonl` → 根级 `resource-stream.jsonl`；
  网络：`samples/netns-stream.jsonl` → `samples/netns-samples.jsonl` → 根级 `netns-samples.jsonl`
  → 根级 `netns-stream.jsonl`；`result.resource_sources` 记录实际采用文件。
- 剪辑仓网络：从 `sampler_rows[].netns_proc_net_dev.raw` 解析，保留时间戳/接口/RX/TX/读取状态/
  scope；逐接口输出，不把 lo 与 eth0 相加，不称 API 专属流量；单样本解析失败不丢整 run 有效记录。
- OpenStoryline 用量：读取原生 `workspace/output/model-requests.jsonl`（request_started/finished 按
  request_id 关联；phase 区分 llm_validation/vlm_validation/agent/node；budget_snapshot 记 observed
  totals 与 logical_requests；无 finished 或缺 usage 单列为 unknown）。
- analyze_run 成功保存 result.json（完整机器结果）、summary.md、curves/CSV、manifest.json
  （实际输入＋分析代码＋输出 bytes/SHA，不自哈希）；输出目录已存在拒绝；导入无写入副作用。
- 剪辑仓资源**重算**：`sampler_rows` 经共享区间逻辑重算；raw `resource_metrics` 仅作 reported 对照，
  输出 recomputed/reported 及差异，不改 raw。
- 未知 vs 实测零：无账本/全部 total 缺失/全关联冲突/读取损坏 → `status` 为
  missing/all_usage_missing/partial，`sum_total_tokens=None`（允许 `observed_partial_sum=0`、
  `covered=0`）；真实 total=0 且读取完整、关联可靠时保留合法零。

## 顶层数据质量（VIDEO-ANALYSIS-FINAL-CLOSEOUT-01）

- `analysis_status.program` 只表示分析程序是否执行成功；`analysis_status.data` 表示本次实际分析
  的数据质量（resource 各指标、usage 来源、media 事件、stream 读取），与程序成功或原任务成败解耦。
- 判定规则：resource 任一指标 partial_missing/read_failed/invalid/regression、coverage large_gap、
  scope 冲突、usage missing/partial、media 读取非 ok、stream 读取 partial/missing → 至少 partial；
  仅当所有适用来源 ok 才 complete；无任何适用来源 → missing。不强制要求“本来就没有”的字段
  （如未内嵌 boundary 标记的流格式不因 boundaries 缺失而降级）。
- VideoWeaver 采样空窗与 null 不被汇总为全程完整，保留 partial。
- CLI 报告程序成功的同时展示真实数据质量。

## 批次聚合与归档（VIDEO-ANALYSIS-FINAL-CLOSEOUT-01）

- 批包装器仅聚合 analyze_run 的逐 run 实际结果（resource/usage/media/analysis_status/来源），
  不重新实现算法；摘要从机器结果结构读取，不写死关键数字。
- ViMax planning 与 media 用量分别列出；原运行观测（RUNNING）与远端补收尾（SUCCEEDED）单列；
  签名下载 URL 不复制进新摘要/归档。
- 所有正式输出（总摘要、机器结果、事实核验、每 run result/summary/CSV/SVG）完成后才生成 manifest
  （不自哈希），并直接或递归（子 manifest）覆盖；回读校验 SHA/bytes。
- 归档目录已存在即拒绝，不覆盖历史报告。

## 最终聚合入口（VIDEO-EIGHT-ANALYSIS-FINAL-WIRING-01）

`scripts/video_eight_final_aggregate.py` 是 8 组/10 单元结果的**一条命令完整交付**入口：

```bash
python3 -B scripts/video_eight_final_aggregate.py \
  --index docs/video_results_index.json \
  --per-run-root <已有 per-run 结果目录> \
  --out <全新目录> \
  [--root <仓库根>]
```

- 输出根排他创建：已存在即在写入前拒绝（无 force/清空/默认覆盖）；失败留证据，重跑须换新目录。
- 一次生成：summary.md、correction-notes.md、limitations.md、run-overview.csv/json、coverage.csv、
  stage-tool-summary.csv、stage-timing.csv、request-usage-media.csv、machine-results.json、manifest.json。
- 时间口径：attempt/entry/agent/lifecycle/采样窗/CPU 有效区间分列，各含来源/clock/精度/范围；
  entry 区间绝不放入 attempt_wall；VideoWeaver attempt_wall 无纳秒级边界时保持 unknown。
- 网络：逐 (identity,interface) 有效区间增量；全缺测 None、有效零 0；回退/读取失败/时间倒序/大 gap
  断开不累计；RX/TX 独立；首末累计另列；身份继承自 per-run scope 证据（无法证明标 unverified）。
- 阶段/工具区间：协议区间＋完整配对身份与源行号；OSL 同键并发标 ambiguous；right_censored/
  start_missing 分列；finish<start 不产出负时长。
- manifest 在所有输出后生成，递归回读（含 per-run 子 manifest），绑定实际输入、聚合器、共享代码、
  输出；不自哈希。

## 三处收尾（VIDEO-EIGHT-ANALYSIS-THREE-POINT-CLOSEOUT-01）

- 网络 gap：CLI 显式参数 `--netns-gap-s`（默认 5.0s）；原始记录未记录网络采样契约 → `contract_unknown`；
  超阈值相邻样本缺口断开、不累计字节/覆盖时间，存在缺口时接口状态为 partial；参数/依据写入
  machine-results 与 netns-parameter.json 并绑定 manifest。
- 工具区间：仅合法区间 op（video_create/video_poll/media_download/video_download/image_generation/
  image_create_http_send/llm_chat/llm_attempt/video_call）建配对组；usage/diagnostic 等非区间事件
  排除并计数（正常过滤，非数据丢失）；缺 request_id 标 unattributed。
- ViMax Agent 时长：仅当 run-record `phase_boundaries.agent_work` 存在独立单调起止才计算；
  否则 agent_wall=None（reason 明确），不再令 agent_wall=attempt_wall。
- 复现：`python3 -B scripts/video_eight_final_aggregate.py --index docs/video_results_index.json
  --per-run-root <per-run结果目录> --out <全新目录> [--root <仓库根>] [--netns-gap-s 5.0]`。
