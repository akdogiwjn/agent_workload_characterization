# 旧资产与指标语义审计报告

审计日期：2026-09-10；修订：P0-00-r2。范围：审计返修，不执行 P0-01 或后续开发。

状态：**P0-00-r2 审计返修通过**，依据 [validation.json](../reports/quality/validation.json)。已检查 46 个来源 locator、22 个代码 locator、5 个真实小样、198 行 CSV 与 86 个当前 sidecar 来源路径；66 个文件及 96 个 trial result 条目的 SHA-256 复核一致。旧实现缺陷尚未修复；P0-00 完成不等于 G0、Schema、adapter 或采集链路通过。

## 1. 本次纠正与证据层次

上一版把历史 sidecar 数量写成当前扫描、混淆公开与生产、缺少可定位小样，并提出证据不足的重写建议。本版替代上一版结论，不沿用其“所有路径已验证”“约 30K 有效样本”或“唯一完整遥测源”等表述。

本轮实际执行：

- 全量逐行解析 AgentX、三个 Applied 文件、MLPerf 和 TraceBench manifests。
- 解析当前 sidecar 与 sidecar_before；分别统计行数、状态和模型请求关联。
- 只读 ZIP 中央目录，检查 OSWorld 文件数与 SpreadsheetBench ID 碰撞；不全量解压。
- 扫描指定生成目录中的 result.json，记录有/无 trial_name、权限异常和 result 内容哈希。
- 对比 Video 原始遥测、四个 bundle 的导出、sidecar 的 trace_id/call_id 集合。
- 记录已读取关键源文件和旧 Python 代码 SHA-256；只读获取参考仓库完整 HEAD。
- 静态核对旧 adapter、selector、sidecar 和 export filter，不导入或运行这些模块。

机器证据见 [audit_evidence.json](../reports/quality/audit_evidence.json)，已执行命令见 [audit_commands.md](../reports/quality/audit_commands.md)。统计时间是证据中的 UTC 时间，不是旧文件创建时间。

证据分为：本轮直接计数、既有文件声明、旧实现静态行为、待验证风险。侧车状态是“派生文件所报告状态”，不等于本轮重新验证了原始任务正确性。

## 2. 资产与计数

所有以下路径以 catalog roots 明确定位；实际 locator 见 [sources.yaml](../data/catalog/sources.yaml)。CSV 是标准表头数据，不再用大括号示意路径冒充实际文件。

### 2.1 公共数据

| 来源 | 本轮直接核对 | 身份与限制 |
| --- | --- | --- |
| AgentX | 393 行 session；28,444 顶层请求；39,822 子 Agent 内请求；共 68,266 模型请求；1,697 subagent groups | production_derived；本地 dataset card 说明 proxy 来源、v7、256k cap、去重/筛选与时间平移，不是完整生产会话总体 |
| Applied Compute | 三文件各 8,192，总计 24,576 模板；无 N=0 | production_derived / macro_template；长度与 delay 是模板参数 |
| TraceBench | full manifest 3,316；verified manifest 1,000 | benchmark_real 来源；verified 是子集，不另加；本轮未全量解包 artifacts |
| SWE-bench | 三个提交的 trajectory 文件分别 500、465、500，共 1,465 | benchmark_real；文件数不等于有效成功任务数 |
| OSWorld | ZIP 内 361 个 traj.jsonl，359 个 result.txt | benchmark_real；本轮不复核 success 总数，保留 null |
| SpreadsheetBench | 160 个 .traj 成员，旧 basename-stem 规则仅产生 20 个 ID | benchmark_real；20 个 ID 全部碰撞，各关联 8 个成员 |
| MLPerf Edge Agentic | 2,014 行，20 个 conversation_id，无缺失 ID | 本地 SOURCE.txt 仅证明 SWE-bench-derived 性能子集；real/oracle/synthetic 生成身份 pending，登记 unknown，不标 production |

AgentX + Applied + SWE 的上述记录数算术和为 **26,434**，但混合 session、模板和轨迹文件，没有资格称“26,434 个有效独立 runs”。旧 ingest_summary.json 的 30,266 是多来源旧 pipeline 的 traces 行数，本轮未重新验证 Parquet 或旧指标正确性。

AgentX 的 1,697 个 subagent group 中 tool_use_count 全部缺失/null，不能聚合为零。68,266 个模型请求本轮未发现缺失 api_time，因此缺失耗时的回归是代码防御性测试设计，不是已观测的数据故障。

### 2.2 当前与历史 sidecar

表中三项均为可解析 JSONL 记录数，不自动代表原始完整任务集：

| 来源 | 当前 run / model / tool | 清理前 sidecar_before run / model / tool |
| --- | --- | --- |
| DocOps | 44 / 134 / 655 | 68 / 29 / 1,067 |
| AgenticVBench | 6 / 21 / 0 | 78 / 21 / 0 |
| VideoWeaver | 4 / 233 / 262 | 4 / 233 / 262 |
| WorkArena | 32 / 0 / 600 | 32 / 0 / 600 |

当前路径为 benchmark root 的 traces_generation/sidecar/<dataset>/；历史路径为 trace_cleanup_archive/20260908T060905Z/sidecar_before/<dataset>/。这些集合不可相加。

当前模型关联：

- DocOps：105 resolved + 29 unresolved；105 条分属五个 trace_id。
- AgenticVBench：21 unresolved，不能归到任意成功运行。
- VideoWeaver：233 resolved，分属四个选定 trace_id。
- WorkArena：oracle，无模型请求合理。

当前 run_manifest 中三个状态分别计数如下，含义不能合并：

| 来源 | execution | evaluation | archive |
| --- | --- | --- | --- |
| DocOps | completed 39 / failed 5 | success 40 / failed 4 | complete 39 / partial 5 |
| AgenticVBench | completed 6 | success 6 | unreadable sessions 1 / archive_permission 4 / missing trajectory 1 |
| VideoWeaver | completed 4 | not_run 2 / context_overflow 1 / null 1 | complete 4（旧 sidecar 声明） |
| WorkArena | completed 32 | success 32 | complete 32 |

AgenticVBench 当前 6 条中是 **1 codex + 5 oracle**；清理前为 71 codex + 7 oracle。不得把整个数据源标为 benchmark_real。Video 旧代码硬写 archive_status=complete，本轮未对全部 artifact 完整性独立背书。

86 条当前 run_manifest 的 source_path 均可在 traces_generation 根下解析为现存路径。路径可访问不等于所有嵌套 session 可读，也不等于 sidecar 覆盖全部原始 attempts。

### 2.3 原始目录与生成快照不等于 sidecar

| 目录（benchmark root 相对路径） | result.json 文件 | 含 trial_name | 不含 trial_name |
| --- | ---: | ---: | ---: |
| agent_benchmark_traces/gen_docops_traces | 50 | 38 | 12 |
| traces_generation/DocOps/results | 53 | 39 | 14 |
| agent_benchmark_traces/gen_agentic_vbench_traces | 31 | 6 | 25 |
| traces_generation/agentic-vbench | 47 | 13 | 34 |

统计跳过 .git/.venv/node_modules/__pycache__；AgenticVBench 遍历观察到四处 sessions/2026 PermissionError，未提权或改权限。无 trial_name 的文件只登记为“未认定 trial”，不把它们都断言为 job 汇总。

DocOps 两目录有 38 个相同 trial result 内容哈希，AgenticVBench 有 6 个。它们证明这些 result 文件重复，不证明整个目录逐文件相等或完整 run 身份一致。不能把生成快照再算一套新样本。

AgenticVBench 可见原始 trial_name 记录 13 条，而当前 sidecar 6 条，表明侧车并非全目录覆盖，未在本轮重建。DocOps 当前 sidecar 也不应拿仅 results 子目录的数量作同范围分母；它记录的 source_path 范围更广。

WorkArena 快照有 32 个 JSON 文件；原生 trace_id 的有无应逐记录映射，不能把 task/seed 拼接身份宣称为所有记录原生 UUID。

### 2.4 Video 491 → 235 → 233 的明确关系

原始 telemetry/video_weaver.jsonl 有 **491 条记录，491 个唯一 (trace_id, call_id)**，因此这里不是重复行去重造成数量差异。

1. 选四个已归档 bundle 对应的 trace_id：保留 235，其他 ID 的 256 条不进入该集合。
2. 按旧 export_trace.py 的 complete-only 条件检查 token、TTFT、api_latency、model_latency 与 model：235 中两条缺关键字段，剩 233。
3. 这 233 条的 (trace_id, call_id) 集合与当前 sidecar 精确相等。
4. 四份模型导出文件与对应 traces_generation/VideoWeaver 下文件 SHA-256 相同，不能重复计算。

| 选定 trace | 原始匹配行 | complete/sidecar 行 |
| --- | ---: | ---: |
| reference_image_video / R2V / run-003 | 31 | 30 |
| reference_video_edit / RV2V / run-001 | 96 | 95 |
| text_long_video / VBench-Long / run-006 | 70 | 70 |
| text_video_edit / TV2V / run-002 | 38 | 38 |

这是按实际记录复算出的集合关系，不声称本轮重新执行过 exporter，也不把 complete-field 条件当“任务成功”。原始 debug、其他 attempts 和不完整请求仍存在，应按研究范围单独统计。

### 2.5 历史归档

manifest.json 的 keep 列表 89 项（DocOps 77 / AgenticVBench 12）、move 列表 199 项（DocOps 57 / AgenticVBench 142）。

它们是历史路径清单项，不是重新去重的 run 数。真正存在的是 removed/ 和 sidecar_before/，不存在 keep/、move/ 数据目录。本轮只登记选择偏差，不恢复、删除或合并归档。

## 3. 语义问题与复用决策

详细 issue 位于 [known_issues.yaml](../data/catalog/known_issues.yaml)，所审代码哈希在 audit_evidence.json。以下是尚未修复的代码行为，而不是本轮测试通过的实现：

| 项目 | 核实结论与处理边界 |
| --- | --- |
| AgentX duration | 开始时间跨度不是完整 run；保留 observed span，缺少终点时不补造 E2E |
| AgentX turns | 源 main_turns 与 all-agent model requests 不同；不把所有请求直接叫 turn |
| AgentX scope | token 递归包含子 Agent，但 total_model_time_s 只遍历顶层；跨字段范围不一致 |
| AgentX Tool count | 1,697 个 group 的缺失/null 被 or 0 聚合为零；未知不能当零 |
| AgentX identity/hash | 模型行 parent_agent_id 可自指；prefix hash 截断丢信息 |
| Applied | N+1 请求；初始 prompt 不等于累计输入/最大 context；模板证据类型需独立 |
| SpreadsheetBench | ID 冲突已由 ZIP 成员实证；需完整源成员键与独立 run/attempt 映射 |
| OSWorld | action span 不是 E2E；未知 timestamp_end 不是必须凭空补齐的 bug |
| Selector | source/profile/config 混排和不同 coverage 维度需修正；heavy/light 只按 turns，不表示 CPU |
| Sidecar | 日志接收时间与执行边界分开；未闭合事件、submit/poll/wait 关联需补设计 |
| Proxy/export | complete-only 的排除项和 failed/unresolved 分母必须保留，不能只分析“完整”而不披露 |

Applied token 长度和秒级模拟 delay 已由本地 trie README 的 Workload format 确认，不再挂“token 还是 char”待办。client 实现还有 tokenizer/BOS/响应长度影响，因此手算公式仅是模板逻辑量，不冒充 provider 实测。

撤回上一版不成立或过强的判断：

- “Typical 选中等值就是设计缺陷”没有依据；重点是可比维度、来源分层和选择目标。
- selector 缺陷不证明“无法修补”；可保留经过测试的距离/分类基础。
- Plotly/Jinja2 或 schema 耦合不证明 report builder 必须整体替换。
- 七表还是 event-based 视图留给 P0-02，审计不预设必须合并。
- 场景/domain、operation category、temporal phase 是不同维度，不能用 Read/Search 等标签直接替换 Coding/Office/GUI 域。
- tool_use_count 与请求 type_counts 没有上一版描述的因果联系。

复用建议：[code_components.yaml](../data/catalog/code_components.yaml)。Adapter/schema/selector/report/sidecar 以修正后复用为候选；proxy 仅静态可复用候选，未跑 smoke；runtime 深入兼容性留到后续相关任务，不以“接口已存在”宣称可直接接入。

## 4. 可定位小样与手算目标

详见 [sample_candidates.yaml](../data/catalog/sample_candidates.yaml)。行号从 1 开始，数组索引从 0 开始；hash 关联原始文件。当前仅登记，没有建立测试代码或生成 IR。

### 4.1 AgentX

源：agent_benchmark_traces/agentx_256k/traces.jsonl。

- 第 39 行，id=1493faffdc8942e99daa22277f44871a40b8：7 个模型请求、0 子 Agent，input 合计 194,368，output 合计 4,097。它是本次扫描中最短保留会话，不是“单请求 session”。
- 第 307 行，id=bbdcb12440a7ab3496b9fac8b5f9824b1672：2 个顶层模型请求 + requests[2] 内 19 请求，共 21；一个 subagent，input 818,752、output 3,949。
- requests[2].agent_id=subagent_001_59efc8e7；其自身 ID 不得同时作为父 Agent ID。

源过滤发生在不同步骤，dataset card 的 minimum 20 不能替代对 cap 后记录的实际计数。复杂嵌套/并发/join 另设 synthetic 设计，不能声称此单个 group 已覆盖全部拓扑。

### 4.2 Applied Compute

源：agent_benchmark_traces/applied_compute/agentic_coding_8k.jsonl，第 1729 行：

- N=2，initial=6,318；
- assistant lengths=[101, 1,084]；
- tool output lengths=[6,118, 23]；
- final output=801。

手算模板输入序列：6,318 → 12,537 → 13,644；请求数 3；总输入 32,499；最大 context 13,644；总输出 1,986。它不是实测 token 和 wall time。

三个文件全量未找到 N=0；N=0 设计单独标 synthetic，不能拿 num_turns=1 替代。

### 4.3 本地 VideoWeaver

源：agent_benchmark_traces/gen_videoweaver_traces/bundles/trace_videoweaver_text_long_video_VBench-Long_run-006/manifest.json。

trace_id=videoweaver:text_long_video:VBench-Long:run-006。该 bundle 是 **70 条模型请求**，不是全来源的 233；输入合计 4,041,546、输出 28,631、max context 80,378，已与对应 sidecar 模型行复核。

manifest 声明 tool_call_count=88、wall_time_s=1616.424；Tool 数仍须在实现阶段与 native trajectory 对齐，不能把 manifest 声明当独立测量通过。视频调用远端媒体/文本模型，为 adapted 配置；本地无法测远端 CPU。

### 4.4 边界与冲突测试设计

- 单模型请求：使用明确 synthetic 单记录；可参考第 39 行 requests[0] 的标量，不冒充原始会话。
- N=0：initial=32、final=64，预期一次 completion；无 Tool；只作模板设计。
- 缺 api_time、未闭合 Tool、真实零、嵌套/并发/join、同 task 多 attempt：synthetic，未来再实现 fixtures。
- SpreadsheetBench：ZIP 中 Debugging/claude opus 4.6/04_06/04_06.traj 与 Debugging/deepseek v3.2/04_06/04_06.traj（完整成员含 trajectory_example/ 前缀）是实际可定位冲突对。
- 未绑定请求：当前 DocOps 有 29 条，AgenticVBench 有 21 条；保持 run_id=null，不靠最近时间强行绑定。

## 5. 能支持与不能支持的结论

可以开始：逐来源语义适配、手算指标测试、来源内宏观统计、分类覆盖检查、已绑定模型遥测与原始/派生血缘核对。但需要先修正 adapter 口径，旧报表不能直接当有效基线。

当前已审阅的这些 Agent trace/sidecar 未提供可验证的 per-tool CPU/system 测量，不能支持 per-tool CPU 归因、远端 CPU 推断或 Replay 保真结论。这是对审计集合的判断，不声称整个旧 runtime 工程从未产生系统监测结果。

必须保留失败/重试、未绑定和不可读状态；成功筛选集合不代表完整生产总体；调用、文件、模板与 task 数不混成“总有效样本”。

## 6. 非阻塞缺口与后续约束

- 部分来源上游 release/license 未独立核实；catalog 明确 null/pending。本地试点读入前检查适用来源，任何复制发布前完成许可核对。
- 参考仓库 full HEAD 已登记，但 dirty worktree、asset 与 references/manifest.yaml 同步未做；未变更第三方或 manifest。
- 两个 ZIP 已补算完整 SHA-256，并检查成员目录；未全量解析 archive payload，仍不宣称整个来源目录已冻结。
- AgenticVBench session 子树有四处权限错误，sidecar 覆盖缺口已发现；不提权、不重采。该部分不进入完整 trace 验收。
- 历史归档 path entries 与唯一 run 的全面去重未完成；登记未决，不相加、不恢复。
- 旧 normalized 产物未重跑验证；runtime 接口兼容性和采集开销需后续专项测试。

这些限制不要求在 P0-00 修复原始数据或实现 adapter；但须随来源进入后续任务，不得丢失。

## 7. 验收与下一步

P0-00 验收限定为：来源可定位、统计范围可复核、原始/派生与历史/当前分开、身份不明项显式、代码复用有证据、三路真实小样可定位且边界测试不冒充原始数据。

校验记录应覆盖 YAML/JSON/CSV 解析、catalog/代码路径、样例行和 ZIP 成员、当前 sidecar source_path、计数交叉检查与源文件 hash 前后比较。Hash 相等只能证明本次返修窗口内的已登记文件内容未变，不能替上一轮提供历史证明；mtime 不是充分证据。

下一项候选为 P0-01 最小骨架与复用边界。本次没有创建工程骨架、实现 schema/adapter、重建 sidecar、运行 benchmark、调用模型、安装依赖、迁移数据、修改第三方或 commit/push。
