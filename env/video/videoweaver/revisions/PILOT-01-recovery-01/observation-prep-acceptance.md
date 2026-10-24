# VideoWeaver 观测与采集完善——下一批任务准备验收表

日期：2026-10-24。本轮只做采集/观测代码修复与定向离线验证；不调真实模型/API、不读凭据、不执行正式任务、不创建 APPROVAL/ATTEMPT。本表逐仓库记录当前采集范围、本轮修复、离线验证边界与仍需真实任务确认项。

## 2026-10-24 观测验收剩余缺口修复（本页第三轮）

修复 4 项明确缺口（修订上一轮"缺口已全部闭合"表述）：

1. **实际资源流与声明/汇总一致**：新增 `validate_resource_stream`（每行契约校验：schema/scope/scope_kind/时间 int 非 bool/指标字段合法 null 或有限非负数值；拒绝 bool/负值/NaN/Infinity/非对象/缺字段）；生产 judge 新增 `stream_validated`、`stream_metrics_valid`、`stream_schema_scope`、`stream_rows_consistent`（valid 行数==stream_state.rows_written==内存汇总 n_samples）、`quality_recomputed`（从实际文件+`boundaries.json` 重算质量并与报告声明核对）；起止边界独立核对（`boundaries.metrics_valid`）；短任务 boundary_only 单独处理（不要求周期样本非空，但要求有效边界）。
2. **读取失败不被后来成功覆盖**：`assess_resource_quality` 逐样本检查对应指标 read_status，明确 ok 值集合（v1 cpuacct.usage `ok_ns_converted_to_usec`、v2 cpu.stat `ok`、memory.current/usage_in_bytes `ok`、io.stat/io `ok[_summed_devices[:…]]`），不靠任意 startswith("ok")；read_failed/status_missing/invalid_value 分别保留，后续恢复只形成新的有效区间（不跨失败连接）；不拿其他指标状态代替。
3. **boundary_only 必须有有效测量依据**：`_boundary_metric_row` 逐指标验证边界两端数值、read_status、scope；全 null/单端缺失/计数回退/状态失败/边界倒序/身份变化均不能通过；计数指标两端非负不回退、内存 gauge 下降合法、有效零保留；boundary_only 明确"连续采样覆盖受限（非完整曲线）"。
4. **scope 与运行身份核对**：`scope_identity`（expected/samples/boundaries/conflict/missing）逐项核对；样本、边界、stream_state、预期 scope_kind 一致；身份缺失与冲突分别报告；不靠强改 scope 修复历史错配；schema 未保存的容器 ID 等身份不猜测补齐（标 unknown，仅后续记录用）。

**验证**：90 项定向测试通过（audit2 21、audit 16、round 13、sse 7、gateway 7、共享 execution_measurement 26）；正常 fixture 全部 contract 检查通过、每个损坏 fixture 单独 fail（一行 {}、scope 替换、负值、bool、行数不一致、边界全 null、计数回退）；旧记录 `audit-verify-133803` 只读复制到临时目录：原数据通过、替换资源文件后失败、源字节不变。

## 2026-10-24 观测验收最后缺口修复（本页第四轮）

修复 4 个已复现漏口（修订上一轮"4 项全部闭合"表述）：

1. **数值与汇总真正一致**：judge 新增 `numeric_consistent`——从实际资源文件＋`boundaries.json` 重算可复核值（n_samples、cpu_core_seconds 边界差分、memory_sampled_max 采样峰、memory_kernel_peak、wall_s），与报告 `resource_samples`/`summary` 数值核对（浮点容差 1e-6 相对）；新增 `sample_metrics_summary`（mem_sum/mem_count，新 run 收尾保存）供内部样本内容核对（修改内部样本但峰值/数量不变也能发现）；旧 run 无该依据时标 unknown（不补造）；rows_received/buffered/written/lost 与文件行数关系经 `stream_rows_consistent` 核对。
2. **scope 冲突进入最终验收**：judge 新增 `scope_identity_ok`——expected、周期样本、起止边界、stream_state 的 scope/scope_kind 核对；conflict/missing 直接影响最终 PASS；缺失检测修复（按 `(scope, scope_kind)` 的 scope 字段判缺失，不再与 None 元组比较）；不靠强改 scope 消除冲突。
3. **boundary_only 贯通最终 judge**：旧 `stream_ok`（去掉"必须≥1行"）、`stream_parse`（去掉"rows 非空"）与 boundary_only 统一；短任务只有有效边界时通过边界测量验收（逐指标数值/状态/顺序/scope 验证）；明确 continuous_sampling 受限（"not a complete curve"）；缺失/损坏/合法空流分别处理；不因短任务放宽普通任务。
4. **必需字段缺失不能当合法 null**：`validate_resource_stream` 逐一检查必需 key 存在（schema/scope/scope_kind/t_monotonic_ns/5 指标/read_status），缺 key → invalid；值 null 合法（由指标质量判缺测）；read_status 校验为 dict（或 null）；保留 bool/负值/NaN/Infinity/非对象/时间类型检查。

**实测表（完整正常 fixture，每次仅损坏一项，断言最终 judge.passed）：**

| 反例 | 预期 | 最终 judge | 失败项 |
| --- | --- | --- | --- |
| A 正常数据 | PASS | PASS | 无 |
| B 一条内存=1TiB | FAIL | FAIL | numeric_consistent (mem_sampled_max) |
| C 改一内部样本（峰/数不变） | FAIL | FAIL | numeric_consistent (mem_sum) |
| D 边界两端 scope=other | FAIL | FAIL | scope_identity_ok (conflict) |
| E 样本缺 scope | FAIL | FAIL | stream_metrics_valid/rows_consistent/numeric |
| F 短任务空流+有效边界+声明0行 | PASS（边界验收，连续受限） | PASS | 无（cpu=boundary_only, not complete curve） |
| G 空流但边界全 null | FAIL | FAIL | quality_recomputed/boundaries.metrics_valid |
| H 必需指标 key 缺失 | FAIL | FAIL | stream_metrics_valid (io_read_bytes_missing) |
| I 指标 key 存在但 null | 结构合法，指标缺测 | FAIL（缺测不判完整） | stream_validated=PASS；指标缺测致质量 FAIL |
| J 计数回退/读取失败恢复/真实零/v1v2 正常 | 回归通过 | PASS | 无（audit2 覆盖） |

**验证**：99 项定向测试通过（audit3 9、audit2 21、audit 16、round 13、sse 7、gateway 7、共享 execution_measurement 26）；旧记录 `audit-verify-133803` 只读复制：7 项 contract 全 True、替换资源文件后失败、源字节不变。

## 2026-10-24 观测验收最后漏口修复（本页第五轮）

修复 4 个已复现漏口：

1. **完整样本内容核对**：新增 `sample_content_digest`/`normalize_sample_row`（全字段规范化序列化：schema/scope/scope_kind/时间/CPU/内存current+peak/读写I/O/read_status，null 与缺字段区分、NaN/Infinity 拒、顺序敏感）；host_runner 收尾从**内存采集样本**（ScopeSamples）生成摘要存 `sample_content_summary`（不读待验文件自背书）；judge `content_digest_consistent` 从实际流文件重算摘要核对——CPU/时间/read_status 被改或两行交换，即使行数与峰值不变也 FAIL；历史无摘要标 unknown（不补造）。
2. **流计数守恒**：judge `stream_counters_valid`（字段存在、非负 int 非 bool）、`stream_counters_conserved`（received==written+buffered+lost，缺失不归零）、`stream_flush_state`（收尾 buffered==0）、`stream_no_loss`（lost>0 不完整）、`stream_written_rows`（written==实际有效行数）。
3. **零 I/O 状态**：`_read_status_ok` 支持 `ok_no_records_real_zero:...` 前缀（真实零合法）与 `ok_summed_devices:...`；`io_files_unavailable` 等非 ok 保持失败（不冒充真实零）；v1/v2 与边界/周期样本同一规则。
4. **连续采样覆盖**：assess 新增 `interval_target_s` 与 `coverage`（expected/actual 样本数、sample_span、coverage_ratio、first/last gap、max gap）；区分 boundary_only_limited（有效短窗口<目标间隔）/ missing_periodic_samples（长窗口缺样本）/ large_gap / edge_gap / continuous；judge `coverage_ok` 实际消费（长任务缺样本→FAIL，短任务边界通过且连续覆盖受限）。

**实测表（完整正常 fixture，每次损坏一项，断言最终 judge）：**

| 反例 | 预期 | 最终 judge | 失败项 |
| --- | --- | --- | --- |
| A 正常 | PASS | PASS | 无 |
| B 内部 CPU+1（单调/行数/峰不变） | FAIL | FAIL | content_digest_consistent |
| C 时间改/read_status 改/两行交换 | FAIL | FAIL | content_digest_consistent |
| D received≠written+buffered+lost | FAIL | FAIL | stream_counters_conserved |
| E 守恒但 lost>0 | FAIL | FAIL | stream_no_loss |
| F 收尾 buffered>0 | FAIL | FAIL | stream_flush_state |
| G 字段缺失/负/bool | FAIL | FAIL | stream_counters_valid |
| H 真实 reader 零 I/O（ok_no_records_real_zero+0） | PASS | PASS | 无 |
| I reader 不可读（io_files_unavailable） | FAIL（保留状态非零） | FAIL | mq_io_read |
| J 短窗口+空流+有效边界 | PASS（边界，连续受限） | PASS | coverage=boundary_only_limited |
| K 63s 窗口+0.5s目标+空流 | FAIL | FAIL | coverage_ok=missing_periodic |
| L 中间 10s 长 gap | FAIL | FAIL | coverage_ok=large_gap |
| M 回归（111 项全部通过） | 通过 | PASS | 无 |

**验证**：111 项定向测试通过（audit4 12、audit3 9、audit2 21、audit 16、round 13、sse 7、gateway 7、共享 execution_measurement 26）；旧记录 `audit-verify-133803` 只读复制：13 项 contract 全 True、替换资源文件后失败、源字节不变（content digest 对历史无摘要标 unknown）。

## 2026-10-24 样本摘要生产类型接线修复（本页第六轮）

修复已复现的生产缺陷：`host_runner.py` 收尾调用 `sample_content_digest(samples.samples)` 时传入的是 **CounterSnapshot 对象列表**，而 `normalize_sample_row` 按字典执行 `if f in row` 抛 `TypeError`；且仅 `to_dict()` 不够——流写入器附加 `schema="resource-stream-v1"` 而内存对象没有，摘要本会不一致（已实测确认）。此前 111 项测试未覆盖真实生产对象类型。

修复：
- **共享序列化**：`resource_sampler.py` 新增 `to_stream_record(sample, schema)`（CounterSnapshot→to_dict+schema；dict→复制+契约 schema），`_StreamSink.write` 改用它；`execution_measurement.py` 的 `sample_content_digest` 对每行先经同一 `to_stream_record` 归一（内存对象与流文件记录完全一致）；schema/version 由明确契约提供，文件缺 schema/必需字段仍被 validate 拒绝、不自动补齐。
- **规范化规则**：read_status 用 `json.dumps(sort_keys=True)` 稳定排序；null 与缺字段区分（`null` vs `_missing`）；bool/NaN/Infinity/负值明确抛错拒绝（不转占位字符串）；CPU、内存、I/O、时间、scope、状态与样本顺序全部纳入摘要。
- **新契约 vs 历史区分**：judge `content_digest_consistent` 三分支——有摘要则文件重算核对；无摘要但 `sample_interval_s` 存在（新契约运行）→ FAIL（不能伪装 legacy）；两者皆无（历史）→ unknown 放行（不回填）。

**真实对象集成验证**（真实 `ResourceSampler`＋合成 `ScopeReader`＋`enable_stream`→`sample_once`×5→`stop`/`close_streams`，从 `sampler.samples(scope).samples` 取真实 CounterSnapshot）：
- 内存摘要（生产收尾调用，无异常）与落盘 JSONL 文件摘要**逐字节相等**（digest 与 n_samples 一致）；样本类型断言为真实 CounterSnapshot；stream_state 计数守恒；边界非空有序。
- 反例：文件 CPU 改 1→摘要不同；时间改/read_status 值改/两行交换→摘要不同；read_status 键序不同内容相同→摘要一致；null vs 缺字段→不等价；bool/NaN/Inf/负→抛错；文件缺 schema→validate 拒绝；空周期短任务→摘要一致＋coverage=boundary_only_limited；新契约缺摘要→judge FAIL；历史无摘要→unknown 通过。

**验证**：122 项测试全过（audit5 11、audit4 12、audit3 9、audit2 21、audit 16、round 13、sse 7、gateway 7、共享 26）；旧记录 `audit-verify-133803` 只读复核：legacy digest 检查 True（unknown）、源字节不变。

## 2026-10-24 审计修复（本页第二轮，更正上轮"全部通过"中的错误表述）

上轮验收后审计发现并修复：
1. `assess_resource_quality`：空样本被标 complete、内存部分缺测仍 complete、I/O 回退仍 passed、只识别 cpu.stat 不识别 cgroup v1 cpuacct.usage、stream_rows 间隔不计算、边界只查存在。——**已重写**（schema 升 v2）：CPU/读I/O/写I/O 按计数器回退检测（相邻有效样本间，不跨缺测连接）、内存按 gauge（不判回退）、支持 cpu.stat/cpuacct.usage 与 memory.current/memory.usage_in_bytes、间隔从时间戳计算、边界核对存在/顺序/样本在窗内、空数据→no_samples/boundary_only、部分缺测/回退/读失败→passed=False。
2. 生产 judge 只查 summary 文件存在：——**已修复**，judge 消费 `measurement_quality`（cpu/memory/io_read/io_write/timeline/boundaries 各 passed）、`stream_state`、`read_resource_stream` 解析结果（空/截断/解析错误判失败）；质量计算异常经 `quality_computed` 反映；必需测量不完整时 judge FAIL。
3. 流式接线：ViMax 上一轮只共享组件提供接口、未启用——**已启用** `enable_stream`＋网络样本运行中逐行 JSONL＋`boundaries.json`（boundary_start/end 持久化）；VideoWeaver 网络样本从收尾集中写改为**运行中逐行追加**（netns-stream-v1：monotonic 起止、read_status、scope/接口、utc）；资源起止边界持久化。
4. `_StreamSink` 计数语义：rows_received/rows_buffered/rows_written/lost_undelivered 明确；rows_written 只计实际 flush 成功的记录；写失败计 lost_undelivered（不清缓冲冒充写入）；fsync_calls 改为真实 os.fsync（close 时一次）；不完整末行由读取器报告。
5. gateway usage 缺 ID：SSE usage 缺 response_id 时归到**本地请求关联**（每请求唯一 request_id），同一请求多 usage 事件**按请求去重**（last-wins 记一次），不同请求不合并；缺 ID 的 total 计入统一软阈值；非 SSE summary 分字段（input/prompt、output/completion、total）且 total 计入软阈值；经**真实 handler＋fake 上游**验证（非 SSE 进入总量、缺 ID/多事件/重复事件、阈值后下一转发 429=0、硬门禁不退化）。
6. 更正 video-use/OpenStoryline 目录边界误判（见下）。
7. 内存 gauge 不被误判为计数器回退（真实 run 中 memory.current 波动属正常）。

**验证**：69 项定向测试通过（audit 16、round 13、sse 7、gateway 7、共享 execution_measurement 26）；禁网 v2 离线 run（VideoWeaver）judge PASS 且 measurement_quality 全 complete、stream_state rows_received=rows_written=64/lost=0/fsync=1、boundaries.json 含起止、netns-stream 落盘；gateway handler+fake 验证 429 软阈值生效。

## 共享采集组件（src/agent_workload_characterization/collectors/）

| 组件 | 当前能力 | 本轮修复 | 离线验证 | 待真实确认 |
| --- | --- | --- | --- | --- |
| `resource_sampler.py` | cgroup CPU/内存 current/内核 peak/I/O 采样，boundary+gaps，默认内存汇总 | 新增**可选运行中 JSONL 流**（`enable_stream(scope,path,flush_every)`，默认关闭，每 N 行 flush、写失败经 `stream_state` 暴露、`close_streams` 收尾）；`stop()` 时 flush | 13 项定向单测（追加写入、写失败暴露、截断末行）＋共享 26 项回归通过 | 真实任务容器下 stream 行数与内存汇总一致 |
| `execution_measurement.py` | 受限目录扫描（`directory_footprint_snapshot`：timeout/symlink/overlap/missing/partial）、网络采样、速率区间 | 新增 `assess_resource_quality`（每指标质量：cpu 回退/顺序/gap/边界/覆盖窗/读取状态）与 `read_resource_stream`（JSONL 读取器，保留完整行＋报告截断） | 定向单测（质量正常/回退/乱序、目录 missing/symlink/overlap） | 在真实 run 上核对测量质量与 stream 解析 |

## 逐仓库

### VideoWeaver（env/video/videoweaver/runner/host_runner.py + gateway/gateway.py）

- **实际采集 scope**：cgroup（`videoweaver` agent_container）、netns 逐接口、目录前后（本轮由简易 `dir_bytes` 改为共享 `directory_footprint_snapshot`）、逐点资源 JSONL＋summary、阶段时间。
- **本轮修复**：
  - 采样线程启用 `enable_stream` → `samples/resource-stream.jsonl` **运行中追加落盘**（schema `resource-stream-v1`），`close_streams` 收尾，`stream_state` 暴露写状态。
  - 阶段事件新增 `stages_rel_s`（monotonic 相对时间原点），与 UTC `stages` 并存。
  - 目录前后用共享受限扫描（timeout/symlink/overlap/partial/missing 分列），不再用无限制 rglob。
  - 收尾写 `measurement_quality`（assess）与 `stream_state`。
  - gateway usage 聚合修复：非 SSE（summary Chat Completions）分字段提取 input/prompt、output/completion、total，`total_tokens` 计入统一 soft 阈值（不再把 total 当 output）；缺 `response_id` 的 SSE usage 记 `usage_unattributed` 且不合并、不重复累计软阈值；`Ledger.record` 仅在 kind=="usage" 时累计（unattributed 只记录）。
- **离线验证**：13 项定向单测（含非 SSE total→soft、unattributed 不累计、无 ID 不合并、软阈值越过）+ 禁网 v2 镜像离线 run（resource-stream.jsonl 64 行、measurement_quality cpu=complete/timeline=ok/boundaries=present、dir snapshot 全 complete、stages_rel_s 落盘）。
- **待真实任务确认**：真实 run 的 stream 行数 vs summary、SSE/非 SSE usage 与 rollout 交叉核对、soft 阈值在真实大 usage 的边界。

### ViMax（env/video/vimax/VIMAX-MEDIA-ENTRY-REPAIR-01/host_runner.py）

- **实际采集 scope**：cgroup（agent_container）、netns、阶段 boundary、startup gate。
- **本轮修复**：补齐目录前后测量——`record["dir_before"]`/`record["dir_after"]` 用共享 `directory_footprint_snapshot`（workspace/attempt），容器前测、删除后测，异常记 cleanup_errors。
- **离线验证**：代码编译通过；FakeOps 生命周期回归未重跑（不重跑历史）；目录测量是宿主函数，禁网临时 out 可验证。
- **待真实任务确认**：ViMax 正式 run 上 dir_before/after 非空与增长、与现有收尾并存。

### video-use / OpenStoryline（按真实调用链核对）

- **实际已有（更正上一轮"两者未见目录前/后测"的误判）**：
  - video-use：`scripts/video_use_edit_pilot_01.py` 中 `directory_boundaries.before_agent / after_agent`、`container_directory_boundaries`（343/392/660），后续 pilot 复用该入口。
  - OpenStoryline：`env/video/openstoryline/edit-pilot-02/runtime/openstoryline_pilot_entry.py` 中 `boundaries_before`、`directory-boundaries-before.json`（714-718）与收尾 `directory_boundaries`（207-223）。
- **结论**：两者**已具备**目录边界测量能力（字段名不同但功能存在）；本轮**未修改**其生产入口。其边界测量与共享 `directory_footprint_snapshot` 的 timeout/symlink/overlap/partial 语义是否一致、失败状态是否落入 report，列为"待下一次真实任务核对/必要时最小补齐"。
- 不补造历史缺失的目录初值。

## 字段契约（新增）

- `resource-stream-v1`：每行 `{schema, scope, scope_kind, t_monotonic_ns, cpu_usage_usec, mem_current_bytes, mem_peak_bytes, io_read_bytes, io_write_bytes, read_status}`（CounterSnapshot.to_dict() 加 schema）。读取器 `read_resource_stream` 保留完整行、报告截断末行/解析错误；不覆盖旧 `resources.jsonl`（收尾 evidence 保留旧结构兼容）。
- `measurement_quality`：`{schema, scope_identity, n_samples, cpu{passed,status,counter_regressions,read_ok}, memory, io, timeline{order_ok,max_gap_ns,actual_median_interval_s}, boundaries{coverage_window_s}, notes}`。
- `dir_before/dir_after`：`directory_footprint_snapshot` 结构（role/scope/status/bytes/observed_subtotal/files_seen/symlinks_skipped/scan_wall_ns，partial/missing/symlink/overlap 分列）。
- `stages_rel_s`：与 `stages`（UTC）并存的 monotonic 相对秒。

## 仍需下一次真实任务确认项（汇总）

1. 四链（VideoWeaver/ViMax/video-use/OpenStoryline）真实 run 的 stream 与内存汇总一致、目录增长非空。
2. video-use/OpenStoryline 目录前/后测补齐与确认。
3. VideoWeaver 真实 SSE/非 SSE usage 与 rollout 交叉核对、soft 阈值真实边界。
4. 采样器自身开销（读取耗时）在真实 run 的 `collector_self_observation` 记录。
