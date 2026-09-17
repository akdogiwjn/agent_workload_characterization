# G1-01：工具时间证据、宿主开销与资源计量核对

日期：2026-09-13。最新状态：**A 已通过功能与离线证据复核（R4，420 项默认测试、5 项 mini 集成）；B 待批准。** 以下保留 A 原任务范围，B 当前实施依据见 [B 任务书](g1_01_b_handoff.md) 与 [B 提示词](g1_01_b_execution_prompt.md)。G1 不自动通过。

本任务服务 RQ2/RQ3，对应 P1-01/02/04/05/11/13 的最小增量；不是完整 P1 或 G1 验收。执行提示词见 [配套提示词](g1_01_execution_prompt.md)。沿用“任务书＋提示词 → 用户交给实施模型 → 原评审复核”的三步流程。

## 1. 目标与停止位置

RUN-01 已证明一次真实 Coding Agent 能运行、candidate 可评估、容器 CPU/memory 可采。下一步回答：

- 26 次工具调用中，哪些能恢复身份、顺序、结果和可信时间？哪些只有日志时间/顺序？
- 后续运行怎样同时观测宿主 mini 进程和 collector，而不重复累加 CPU、RSS？
- 短任务、后台进程、采样结束、超时等情况下，计量覆盖与开销有何限制？

本批先完成 **A：历史只读分析＋自有离线实现＋受限本地合成验证**，交付后停止。**B：无模型容器验证仅生成审批清单**，明确批准后另行执行。没有第二个真实 Agent attempt，也不进入 perf/hotspot。

## 2. 开始前阅读与复用

实施者完整阅读 methodology.md、docs/development_tasks.md、references/README.md、references/manifest.yaml，再读 docs/trace_contract.md、docs/data_management.md、本任务书、RUN-01 任务书及交付 §5.19。优先阅读现有 semantic_recorder、resource_sampler、resource_summary、mini_agent_adapter、coding_pilot 和相关测试，只补必要接口，不新建第二套 runner/IR 框架。

references 与旧工程仅设计参考；不修改、不执行其中代码，不重复遍历全部论文/仓库。默认测试不得依赖真实数据、SDK、容器、凭据或本机特定 cgroup 布局。

## 3. 固定输入与可信基线

| 输入 | 用途/边界 |
| --- | --- |
| `data/raw/generated/RUN-01-C/20260912T125202Z-840e49/` | 封存只读：8 文件，共 520,090 字节，不改写补字段 |
| `reports/resource/RUN-01-C-v2/` | 当前有效派生报告与 supplement_manifest；历史 `RUN-01-C/` 同样不覆盖 |
| RUN-01 C 原生轨迹 | 30 请求（26 正常＋4 格式错误）、26 tool calls/26 tool observations；agent exit=LimitsExceeded、未提交，candidate 从工作树提取；resolved=true |
| 原有资源证据 | Agent 6.411718 core-s、verifier 3.423041 core-s；native arm64/cgroup v1；不是宿主总 CPU 或独占 Tool CPU |
| 已知缺口 | 正式 I/O=null；宿主 mini CPU/RSS 未测；collector 未量化；工具分类未接线；容器无磁盘配额 |
| 已验收代码基线 | 默认 395 项通过；此前真实 mini 离线 3 项、evaluator 解析 5 项通过；本批分别记录实际复跑项，不直接复制通过声明 |

读取前核对原 manifest 与补充完整性清单，读取后复核全部 8 文件哈希；历史与新采身份分开。新增报告写全新目录，例如 `reports/resource/G1-01-A/<batch_id>/`，默认独占创建，不覆盖已存在批次。禁止为了消除缺口重跑 C、smoke、gold 或 canary。

## 4. A 的授权边界（用户转发提示词并明确开始后）

允许自有代码/测试/新派生报告与任务进度文档增量修改；允许读取固定来源和已安装 SDK 源码。真实 SDK 验证只使用显式 fake transport＋fake 工具执行器，并阻止网络。

本地合成验证仅能运行本项目创建的确定性小程序，不执行 trace 中的命令或 candidate。每用例 wall≤10 s、单进程 busy≤2 s、并发 worker≤2、内存分配每 worker≤64 MiB、临时文件总≤8 MiB；整个机制实验批 wall≤120 s、报告≤20 MiB。先写明用例清单、固定次数与预算再执行，到限停止且保留失败，不自动追加轮次。用例不足以统计时报告低置信，不为“通过”追跑。

默认测试每次外层 timeout≤60 s；显式 SDK 套件≤60 s。不允许安装/下载、网络请求、真实密钥读取、容器/镜像操作、宿主 cgroup 改动、提权、perf/eBPF、迁移进程、修改全局配置、删除旧数据、提交/推送 Git。临时进程仅清理本次创建且 PID/starttime 可确认的身份，禁止宽泛 pkill。

## 5. 工作包 A1：历史 Tool 时间与采样有效区间审计

从原生 tool_call_id 关联 action/result，报告缺失、重复、冲突、多 action/message 与失败；没有 tool 来源时 null/unknown，不用 0。命令只输出类别或白名单安全摘要，不输出完整响应、reasoning、环境或原始 traceback。

mini 消息已有 `extra.timestamp`，status 有 `t_start_ns/t_end_ns`，但**字段存在不证明是工具执行起止**。核对固定安装版中时间赋值位置，形成简短字段语义表：来源 locator、clock domain、native/log_receipt、精度及可用用途。

- 对每个工具记录身份、顺序、结果、时间来源和关联状态。无可信起止时 start/end/duration=null＋原因；允许顺序图，不要求填满时间线。
- 用相邻 LLM/消息时间推断的窗口只能标 estimated/bound，不当真实工具 duration，不把所有 LLM 间隙自动归为工具。
- 同机 monotonic 与 UTC anchor 明确转换规则；无法校准时不相减。父 recorder 接收时间与子进程实测时间分开。
- 工具与容器资源只做 shared_scope/window association；稀疏累计计数器插值若使用必须标 estimated，不造 per-tool 独占 CPU。
- 核对 samples 的每个采样是否在对应 scope 的 boundary_start/end 内。边界外数据保留在原始文件，在新派生视图单列，不混进该区间峰值/样本数。若 sampler.stop 后仍采样，修未来代码，不能删除历史样本。

产出 `tool_timeline.jsonl`、`scope_coverage.json`、`timing_semantics.md`。基线调用数必须与 26/26 对上；可信工具 duration 覆盖率允许为 0，只要原因正确。

## 6. 工作包 A2：未来真实工具事件接线

在现有 AttachedDockerEnvironment/mini adapter 路径加入最小 hook，不改工具执行方式、动作协议或模型上下文。围绕实际 execute 记录开始/结束、tool_call_id、request/step、returncode/异常摘要、容器/scope 与同机时钟来源。

- 开始事件必须在调用前可持久化；异常/取消/超时保留开口或明确取消状态。execute 返回与后台 job 完成不能等同。
- 输出先做安全投影再持久化，canary 覆盖命令/结果/错误路径；不将认证环境送入容器。
- 不再只钩 fake harness：显式测试应使用安装版 mini、fake transport 与假执行器，验证真实接线路径的调用前后事件及格式错误分支；可扩现有测试，不新建另一套 SDK mock。
- 真实模型、工具容器验证留 B，不将 fake transport 通过写成真实链路已测。旧 RUN-01 的缺失不因新增 hook 被追溯改标 observed。

## 7. 工作包 A3：宿主 mini 与 collector 最小观测

优先标准库和 /proc，读取限定在本次创建的进程/线程，不扫描无关进程命令行或 environ。为后续运行接入：

- mini 主进程身份：host/boot、PID、starttime（或等价防 PID 复用键）；子进程作为独立身份，并注明扫描覆盖/短命遗漏。
- CPU：utime/stime ticks 转 seconds，记录实际 CLK_TCK、区间起止和最后可读值。进程退出/重用/reset/读取失败保留 null 或 partial；不可拿“上一次采样”当已验证最终值。
- RSS：按当前页大小换算；current、sampled max 与内核 peak 不混。不同进程 RSS 相加不能称独占内存，峰值不相加。
- Collector 若与 runner 共进程，进程 CPU/RSS 只能叫 host_runner_process（包含 collector）；可以用线程 CPU 或读取耗时单独描述 collector 工作，但不能冒充独占 RSS，也不重复求和。
- 新证据附 raw counters、采样时间、scope/coverage；真实历史 run 的 host 缺口继续 null，不用本批合成数据补算。

无需全功能 process tracing 或独立监控服务。主进程＋可解释的后代覆盖已足够本批；P1-02 全生命周期/eBPF 等留后续。

## 8. 工作包 A4：确定性计量与开销核对

以机制覆盖为目的，不要求 Agent 解题。合成 fixtures 与受限本地小程序分开报告：

| 最低用例 | 断言/证据 |
| --- | --- |
| 串行正常＋工具异常 | 身份关联、真实 hook 边界、错误状态、未知不补零 |
| 双 worker 重叠 | work/union/span 区分，资源共享不复制求和 |
| 后台工作超出调用返回 | 工具已返回不等于 job/scope 完成；后台未结束不伪闭合 |
| 短进程、PID 复用、计数 reset、读取失败 | fixtures 确定性覆盖，真小程序揭示实际遗漏；退出最后值可信度明确 |
| 采样停止 | final boundary 后不再追加有效采样；历史边界外样本可检测且不污染指标 |
| CPU/RSS 单位 | ticks/页换算有独立期望；不要用同一个解析函数互相验证 |
| 开销 | 固定工作量（不是仅固定 busy 秒数）的观测开/关对照；最多 3 对，提前固定；报告 wall/CPU 原值、配对差与测量噪声，不保证样本足以给稳定百分比 |
| 安全与归档 | 真临时产物销毁前扫描并断言 scanned>0；全树文件/hash/字节对账、旧源与 symlink 拒绝、无网络/容器副作用 |

定时 busy 可验证 CPU 单位，不能推算等量工作加速比。collector 读耗时与有/无 collector 的执行差是不同指标。可选容差必须执行前写明：计数与哈希精确一致、时序顺序确定；实际计量容差按计时分辨率说明，不能结果出来后改阈值。

## 9. 交付物与验收

最小改动现有 collectors/analyzers/mini adapter 与测试，按需新建小模块；不预设必须采用某框架。建议新增 `docs/g1_01_delivery.md` 和新批报告包，至少包含：

- `tool_timeline.jsonl`、`scope_coverage.json`、`timing_semantics.md`；
- `mechanism_checks.json`：fixture 与真实本地合成结果分开，含次数/范围/停止证据；
- `overhead.json`：观测开关配置与每次原始结果，不以结论代替测量；
- `summary.md`、`manifest.json`：完整输入/输出血缘、原 manifest 链、代码/配置身份及文件哈希；
- `g1_evidence.md`：对 development_tasks 的 G1 六条逐项标 evidenced/partial/missing，注明只支持哪些 scope；
- `container_validation_approval.md`：B 仅提案，无容器操作。

验收条件：A1 26/26 身份核对与缺失解释；A2 真实 mini 离线 hook 集成；A3 宿主/collector scope 不误导；A4 最低机制用例与开销原始数据；395 项既有默认回归无退步（用例调整须解释）；项目内外 cwd；输入与历史报告哈希保持不变；新输出不含密钥 canary；无未经授权执行。

只读审计若发现本批 scope/安全/计量直接错误，集中修正；历史措辞、完整分类器、全平台兼容、PMU、其他 benchmark 不加为验收条件。只增产物不代表通过：交付后由原评审核对源码与反例。本批不自行宣布 G1/P1 全项完成。

## 10. B 容器验证提案与最终停止

A 完成后，提交一次无模型容器验证清单：已有固定 arm64 digest、具体确定性用例/命令、容器数量、预算、产物与清理身份；验证实际 Tool hook 与容器资源窗口、宿主进程采集和停止后边界。建议至多 2 个顺序容器，wall 总≤180 s、各≤2 CPU/256 MiB、合成写入≤16 MiB；仍无磁盘硬配额，审批需明示。若与实际实现不符，列实值再请批准，不自动扩限。

不重跑 gold、C 或新增任务。不因无法从历史补出 Tool 时间而自动申请第二次模型任务；先用无模型机制证据验证新增采集链。B 的运行后是否足以通过目标 scope 的 G1，由评审决定；不足时列明确缺口而不是要求凑齐四场景。

**本次执行提示词仅放行 A。A 交付后停止，B 待用户单独批准。**
