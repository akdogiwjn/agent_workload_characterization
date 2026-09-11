# P0-10 执行交接：VideoWeaver 本地 Trace 小样

状态：执行计划，**尚未开发或验收**。本任务先覆盖一种本地来源，不表示 DocOps/AgenticVBench/WorkArena 等全部接入完成。

## 1. 协作方式与授权

用户确定的后续工作方式：规划/验收模型准备详细交接 → 用户另开会话选择实现模型 → 实现模型交付实际代码与证据 → 规划/验收模型独立复核。不要以自报 PASS 替代独立验收。

本轮仅执行本文 P0-10 小样范围。完成后停止，不自动做 P0-06、P0-07/08/09 或 P1，不自动提交/推送。禁止回写旧源、修改 references 第三方、下载数据/模型、运行旧 pipeline/exporter、发远端 API、运行 benchmark、恢复归档或全量转换。

项目根 `/home/lcq/agent_workload_characterization`。当前 P0-00-r2～P0-05 小样已验收，IR 0.2.0；最近独立复核 122 项 unittest 通过，执行者须重跑。工作树包含大量已有修改和未跟踪交付，禁止清理、reset、覆盖。不读取或修改 opencode.json、密钥或模型设置。

## 2. 必读与基线

完整阅读四份文件（过长可分段，不能只搜索关键词）：

1. `methodology.md`
2. `docs/development_tasks.md`
3. `references/README.md`
4. `references/manifest.yaml`

接着阅读 `docs/data_management.md`、`docs/trace_contract.md`、`docs/ir_v0_2.md`、`docs/adapter_framework.md`、`docs/legacy_asset_audit.md`、`data/catalog/sources.yaml`、`data/catalog/sample_candidates.yaml` 与相关 known_issues。

检查公共代码 `ir.py`、`adapters/{base,catalog,ingest}.py`、已有 AgentX/Applied 小样检查模块、CLI 及测试。文档历史版本描述不能盖过当前代码能力：公共 ingest 当前仅允许一个 catalog JSONL 文件，不能直接接受目录、多文件组合或同一 run 的多个部分文档。

```bash
cd /home/lcq/agent_workload_characterization
git status --short
PYTHONPATH=src python3 -B -m unittest discover -s tests -v
```

## 3. 限定输入与证据优先级

以下根路径相对 `/home/lcq/agent_workload/benchmark/`，实际代码必须通过 catalog 定位而非拼另一套硬编码 data_root。

| catalog source_id | locator/作用 |
| --- | --- |
| gen_videoweaver_traces | agent_benchmark_traces/gen_videoweaver_traces/bundles；归档 bundle |
| sidecar_videoweaver | traces_generation/sidecar/videoweaver；派生结果，仅对照 |
| telemetry_video_weaver | telemetry/video_weaver.jsonl；原始 proxy 请求记录 |

主样例 `VW-LONG`：

```text
trace_id = videoweaver:text_long_video:VBench-Long:run-006
bundle = trace_videoweaver_text_long_video_VBench-Long_run-006
manifest.json
model_telemetry/model_telemetry.jsonl
native_trajectory/original_ReAct.jsonl
```

辅助缺失样例只选原始 telemetry 的下列明确记录：

```text
trace_id = videoweaver:reference_image_video:UniVBench-R2V:run-003
call_id = b6c324adb8dd40179883ecead5cb4262
当前 line_1based = 326（定位辅助；必须同时匹配 trace_id/call_id）
```

规划时只读确认：该请求 input/output=null，ttft=3.716896、api_latency=5.253902、http_status=200。不能因 HTTP 200 判字段完整，也不能因 token 缺失删掉请求。执行时重新核实，变化即报告，不能硬凑预期。

证据优先级按字段划分：proxy 行提供请求与 usage；原始 ReAct 的 toolCall/toolResult 提供工具调用关联；manifest 提供明确的源状态/配置声明。sidecar 用于对照，不作为优先真值，不能把 sidecar 的 complete/Observed 当独立测量。

读取旧 `traces_generation/sidecar/gen_sidecar.py` 的 `_parse_vw_react` / `gen_videoweaver`、`telemetry_proxy/proxy.py` 的时间和 context 字段写入处；若需找 exporter 只读定位，不执行。登记所读代码 SHA-256；不要把当前代码推断为历史运行时必然使用的同一版本。

## 4. 已核实线索，不是免验证真值

主 bundle manifest 声明：

- generation_status=success，但 pipeline_reported_status=failed；备注称归档查找大小写导致假阴性。
- openclaw_session_id=3ae8aceb-c912-4bab-acde-71be6ffad847。
- manifest trajectory 起止跨度 1616.424 秒，是源日志边界声明，不自动等于精确运行 E2E。
- 70 条模型请求；input 4041546、output 28631、最大输入 token 80378。
- 88 个 Tool 调用。规划时独立扫描 original_ReAct：88 个唯一 toolCall ID、88 个匹配 toolResult ID、无缺结果/孤立结果/重复调用 ID。
- 首个请求：input=20797、output=428、context_tokens=21225。**context_tokens 不能未经核对直接作为输入 context；该样例等于 input+output。**区分原始 source_context_tokens 与基于 input 的 max_input_context。
- api_latency/upstream_latency/model_latency 在例子中相同，都是 proxy 边界度量；不得标为三段可相加时间或服务端纯推理。

历史全来源 491→235→233 是 P0-00 审计关系，不是本次全量目标。主样例只选一个 run；辅助只选一条缺失请求。即使为找到 selector 流式读完整小 telemetry 文件，也只规范化已选记录，不重新全量导出。不可将 233/491 标成本次已验证请求数量。

## 5. 实现架构：局部组合，不扩建全库 ingest

建议文件（可调整，但文档列出实际接口）：

- `adapters/videoweaver.py`：纯规范化函数/类，输入已读取的 manifest、带 source refs 的 proxy/native records，输出一个闭合主 run TraceDocument。
- `adapters/videoweaver_checks.py`：catalog selector、只读读取、独立断言、质量摘要。
- `tests/test_videoweaver.py`：合成 fixtures、反例和 round-trip。
- CLI `check-videoweaver-samples`：只读检查后 JSON stdout，失败非零，不写正式 normalized 批次。

主 run 组合必须有多个 provenance：每个输入文件自己的 snapshot hash，记录实际行号/JSON pointer。不能用 manifest 哈希冒充所有文件快照。请求字段指向 proxy provenance，Tool 字段指向 native provenance，状态声明指向 manifest provenance。

允许增加小样专用组合接口，不要求继承单记录 Adapter 或骗过现有 ingest。禁止为了接目录而取消 ingest 的真实路径/单文件保护。多文件批次持久化、active-view、跨 run 共享实体和通用目录 ingest 属于未来范围；本次用重复 normalize 的确定性与稳定 ID 验证，不声称已有多文件 writer 幂等。

读取文件由 manifest 提供相对路径时：必须验证相对路径、解析真实路径并限制在已选 bundle 内，拒绝绝对路径、`..` 逃逸和 symlink 逃逸；不打开任意 manifest 指定路径。不加载媒体文件、prompt、凭据或工具输出正文来“增强报告”。strict JSON/JSONL，非法行显式计入拒绝，不 errors=ignore，不空行静默吞掉。

## 6. 身份、关联与 IR 语义

### run / request / Tool

- 主 run 用 canonical VideoWeaver namespace + 原始 trace_id 生成 ID；不能用 workload 或 task_id 单独标 run，不从路径/转换版本造新 run。
- 同一请求在 raw/bundle/sidecar 中出现是证据副本，不是三次调用。匹配键 `(trace_id, call_id)`；相同键字段冲突报告 conflict，不静默选一个。request_sequence 非本 run 连续序号也合法，不擅自重编号并丢源含义。
- Tool Event 用 trace_id + toolCall ID；toolResult 按 toolCallId 关联，不能按相邻时间戳猜。重复相同记录可记去重，冲突 ID 必须拒绝/隔离；result 无 call 单独列 orphan，不能造调用起点。
- 只在 manifest 明确 session id 时建 Session 并保留来源；task/attempt 信息不足时允许 null。不能以成功生成视频说明 verifier 通过。
- 不强行把每个请求关联到最近 Tool，亦不把消息编号当 Agent turn 数；agent_id 无证据可为 null。

### 未绑定与不完整是两件事

辅助真实请求属于另一 trace_id，不能挂到 VW-LONG，也不能据此标成源本来缺 run ID。此检查范围没有装配对应 run 时，可输出独立 unassigned document：run_id=null、batch_id 明确、association.status=unresolved，method 说明 `run_not_loaded_in_selection`，provenance.source_record_ref 保留原 trace_id/call_id/行号。原 trace_id 并未丢失，不按时间临近重新关联。

合成测试另外覆盖真正没有 trace_id 的 telemetry、源 ID 冲突和与已装配 run 匹配的 incomplete 请求。字段不完整但有明确 run 证据时仍 resolved；关联未决不等于请求失败。

### 三轴状态和来源声明

- execution：manifest 的 generation_status=success 可按明确规则映射 completed，注明是源声明；不因 pipeline_reported_status=failed 改成执行失败。
- evaluation：缺失→unknown；not_run→not_evaluated；context_overflow 等基础设施/评估错误若映射 error，必须有原字段与规则证据，不能映射任务能力失败。
- archive：存在 manifest 或几个文件不证明完整归档。只检查本次文件覆盖，不读取全部媒体/文件时优先 unknown；旧 sidecar complete 作为未独立验证的声明，不强行沿用。
- 保留三者原始字段及归一化规则在质量摘要，以 JSON pointer/hash 指向源。现有 Run 没有任意 source metadata 字段时，不把字符串塞进 Metric，也不要默默丢冲突；用 companion quality record 保存。
- profile=semantic_trace。所选运行有真实模型调用、使用替代模型/媒体服务，需注明 adapted 配置；不是 production、oracle 或 replay。原始遥测全集 trace_type=unknown，不因一条已选 benchmark run 给整文件改标。

### 时间与指标

- proxy 的 UTC/epoch 与 duration 的 perf_counter 来源分开核对；没有 monotonic 起止值则不编造坐标。UTC wall-clock 差与 monotonic API latency 可有误差，不能互相覆盖。
- 原始 ReAct timestamp 是消息/日志时间，Tool span 用 log_receipt；未知执行边界明确声明。结果缺失→end=null，不补成 start；取消/丢日志无明确证据不擅自标 censored。
- 只有可核查 durationMs 才记录对应源 duration；相邻消息间隔不能标独占 Tool 实测时间，不把异步 submit 返回当后台任务结束。
- 不能对 log_receipt 区间直接调用只接受 native_event 的 interval_totals 后改标签蒙混过关。不要求本轮计算 Tool busy/CPU/critical path。
- source clock 精度未知使用 IR 0.2 的 null + missing_reason；输出纳秒位数不代表真实精度。跨 clock 不做精确相减。
- 请求 token、TTFT、API latency、source_context_tokens 分别保留 scope/unit/evidence；缓存/推理 token 是可能的子集，不额外加到 input/output 总数。
- run token 汇总只加同一组请求一次，manifest summary 与 sidecar totals 仅对照，不再相加。缺输入时精确总值为 null；部分已知和如输出必须另命名并给分母。
- 完整 run_elapsed、远端 CPU、Tool CPU 无证据则 unavailable；日志 observed_span 与 manifest_reported_wall_time 另名，不能偷换。
- job/session/process/scope 不因看到命令字符串便凭空创建。原生 provider job ID 若无法可靠提取，报告本样例未覆盖 submit/poll/wait 关联；本次不得宣称异步资源归因验收通过。

若现有 IR 确实无法表达关键事实，先记录缺口和最小改动方案，请用户确认后再做 Schema 升级；本轮默认保持 0.2，优先 companion 证据摘要而非无类型扩展字段。

## 7. 实际检查与报告契约

在项目自有 catalog 新增小样 selector 文件或扩展 sample_candidates，保留历史 entries；明确 sample_id、source_id、bundle 相对路径、trace_id、辅助 call_id 与 gold/smoke 类别。

一个可重复命令应完成：主 run、辅助 incomplete 请求、sidecar 对照。所有声称 PASS 的真实检查都必须在命令结果中有对应记录，不手工填哈希/计数。

主样例必须独立核对（不要用同一个 summarize 函数生成 expected 和 actual）：

| 检查 | 本地已登记/初查期望 |
| --- | --- |
| 归一化模型请求 | 70；唯一 `(trace_id,call_id)` 也为70 |
| 请求 input/output 合计 | 4041546 / 28631 |
| 最大输入 context | 80378，依据 input_tokens，不是 source_context_tokens |
| 原生 Tool call/result | 88 / 88；无缺结果/孤立结果/重复 ID（执行时复核） |
| sidecar 同 run 对照 | 请求键集/关键数值、Tool ID 集合；若不一致保留差异并 FAIL，不改 expected |
| 辅助请求 | 上述固定 call_id 保留，input/output=null，已有 latency 保留 |
| 证据边界 | 无 resource/process CPU、无伪 run_elapsed、三轴不混淆 |

主 bundle telemetry 与 raw proxy 对应键集可只读比较；发现多余/缺失行要报告 selector 与排除理由，不用 complete-only 条件过滤掉不完整请求后声称原始全集完整。

报告 `reports/quality/videoweaver_sample_validation.json` 应由检查结果机械生成并保存：实际 UTC 时间、adapter/schema 版本、每个输入真实路径和内容哈希（仅所读范围）、sample kind、expected/actual、计数守恒、mismatches、缺失/关联/状态依据、限制。建议 CLI 可输出含时间戳的完整 JSON，由执行者保存到明确项目报告位置；CLI 默认只 stdout，无任意输出 writer。

必须区分：physical_lines / selected / nonselected / malformed / duplicates / accepted / unresolved / conflicts。分类不可重叠求和；若 resolved/unresolved 是 accepted 的子集，应明示关系。无关记录是 nonselected，不是错误；坏行即便未知属于哪个 run 也不能默默过滤。

数据文件变动时以 FAIL/无法完成报告，不把旧审计数字重新写为本轮事实。采样范围外的历史 491/235/233、全部四 bundle 无需重验，若提及要引用 P0-00 而非贴本轮 PASS。

## 8. 合成测试清单

默认 unittest 不需要旧 trace 文件、不联网，所有写入在 TemporaryDirectory。至少覆盖：

1. 主组合 IR round-trip，多个 provenance 真实指向各输入；重复 normalize 相同 ID/内容。
2. 同 task 不同原 trace/attempt 的 run ID 不同；路径移动不变身份。
3. raw/bundle/sidecar 同请求不重复计数，冲突不静默接受。
4. run 汇总不叠加 manifest 与逐请求 token；cached/reasoning 不重复相加。
5. source_context_tokens=input+output 的样例不冒充 input context。
6. 未绑定请求、其他 trace 请求、明确绑定但缺 token 请求分别正确处理。
7. HTTP 200 但 usage 缺失、请求失败但有 latency，均保留原有信息。
8. Tool 重复调用、重复冲突结果、缺结果、孤立结果、错误关联 ID。
9. 异步样例 submit result 很早、后台后续结果很晚：不造 job 完成/CPU，也不猜测不同工具之间关系。
10. completed execution + evaluation unknown/error + archive unknown 共存；pipeline failed 不覆盖 execution；archive 存在文件不自动 complete。
11. 时间零值、缺失端点、非法负 duration、epoch/ISO 单位、不同 clock 不相减、log_receipt 保留。
12. 数值 bool/字符串/NaN/Infinity/巨大值；严格读取/拒绝，不抛未捕获 OverflowError 中断全部样例。
13. 非法/空 JSONL 行、缺文件/权限、selector 不存在、manifest 绝对路径/父路径/symlink 逃逸，失败显式可复核。
14. CLI 用临时 catalog/合成 bundle 跑成功与失败；每项失败应影响总状态和退出码，不只断言 stdout 含 PASS。
15. 报告的哈希/ID/实际值与真实命令结果一致；gold 与结构检查区别明确。

既有 122 项全部回归。新增测试按实际覆盖组织，不预先承诺数量或凑数量；不能仅用 self-generated expected 证明正确性。

## 9. 交付、验收与停手

新增 `docs/videoweaver_adapter.md` 与 `docs/p0_10_delivery.md`，更新 README、任务计划、methodology 的当前状态，保持历史报告不改写。P0-10 标 `DONE（VideoWeaver 小样阶段）` 时必须列出其余本地来源仍未接入；真实源无法读取则标 PARTIAL，不用合成测试替代真实验收。

实际执行并记录：

```bash
PYTHONPATH=src python3 -B -m unittest discover -s tests -v
PYTHONPATH=src python3 -B -m agent_workload_characterization check-videoweaver-samples
PYTHONPATH=src python3 -B -m agent_workload_characterization check-agentx-samples
PYTHONPATH=src python3 -B -m agent_workload_characterization check-applied-samples
git diff --check
```

验收要求：代码/文档都实际存在；报告可以用命令复算；ID/血缘、请求/tool 数及数值匹配独立依据；缺失/失败/未绑定/冲突没有被藏掉；输入保持只读；没有额外创建正式 normalized 批次、执行媒体处理或发 API。

完成后给实际测试数、命令退出状态、产物路径、剩余限制；由用户交回规划/验收模型独立复核。G0/M1 仍缺 P0-07/08/09 等证据，禁止直接勾选或进入资源实验。

## 10. 发给实现模型的启动指令

```text
请在 /home/lcq/agent_workload_characterization 实现 P0-10 的 VideoWeaver 小样阶段。
先完整阅读 docs/p0_10_handoff.md，按其要求阅读四份必读文档、检查工作树和测试基线。
仅按交接范围实现组合规范化、合成测试、可重复真实小样检查与交付文档。
保留所有已有修改；旧源和 references 只读；不全量 ingest、不发 API、不运行旧 exporter，
不自动 commit/push、不推进后续任务。无法确认的关联/时间/资源保持未知，不能猜测补齐。
所有 PASS 必须来自实际命令，报告包含真实哈希、时间、预期/实际值与限制。
完成后报告结果，等待另一个模型独立验收；不要只给建议或自行宣布 G0 通过。
```
