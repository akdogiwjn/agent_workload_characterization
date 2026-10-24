# 项目总览：证据、缺口与下一步

事实源为[project_state.json](../project_state.json)。目标见[当前范围](current_scope.md)，当前工作与待办见[当前任务](current_task.md)。本页不提供执行授权；逐轮日志按[历史索引](history_index.md#docs-refresh-20261021)查阅。

<!-- PROJECT_STATE:START -->
当前状态由 [2026-10-25 状态真源](../project_state.json)统一登记；这是进度记录，不是执行授权。

- 当前目标：分析Agent单任务的CPU、内存、磁盘I/O与占用、网络、时长及工具/软件使用，保留过程曲线、环境与采样质量；不要求GPU或函数热点。
- 公开trace已完成限定操作/软件汇总v3：SWE-rebench 9,435轨迹、SWE-bench现登记20,023对象/41组（原v3为19,876，后补147）、OSWorld 755模型×任务记录/108任务（命令解析扩展至v4，原生/源码分层）、H-EPM 414轨迹；AgentX Full/256k及Applied提供宏观证据：AgentX两版同393会话，98,827/68,266请求，仍无业务工具明细或本地资源。未穷尽语义解析，不混合来源分母或把软件声明当实际启动。
- SWE-bench逐任务评价补全：轨迹登记仍20,023对象/41组，另下载20,098份评价/配套文件，40/41组有公开评价产物。原8,730个未列项补出8,476未解决、140已解决、9未生成、1超时，余74空报告/30缺报告；MAYA补出222项，Mindlink同名公开来源仍缺366项评价。5个结果冲突单列；KGCompass更正300个任务身份，跨组去重实际2,294任务。仍无资源证据。
- H-EPM/ToolSandbox复核v3完成：414轨迹、2,021次调用/返回，按保存请求静态核实全部原生工具身份，原24次未知及2次仅有活动分类的调用均补出确切名称。406条有用户侧结束请求，402条有返回，4条仅保存请求、8条无请求；Agent终止原因及资源等未记录。两组不同源码且均有local changes，只作描述比较。
- SWE-rebench复核v3完成：85分片、9,435轨迹/111任务/17 participant完整核验；598,148请求/616,980结果的差额按589,061唯一ID配对、27,059未调用报告、860提取错误及其1,875候选、7,201提交分支请求与11复杂提交末尾请求核清。Junie 555轨迹的31,449步骤摘要另列，不当作零工具行为；任务失败不等于分析未完成，仍无本地资源证据。
- Coding、Office、Assistant合并分析v3保留9个固定任务各3点，共27个task×round观察；累计35次启动包含8次排除的Office错路由记录。不同scope/配置分层，失败记录不删除，不代表类别总体。
- 新口径已记录可用CPU、内存、有限I/O、共享netns及任务目录边界；旧run缺失字段不回填。资源不是整机、远端模型或单工具独占成本；实际HTTP次数、费用及共享cache归属仍unknown/unsupported。
- video-use已完成核心转写→自主选段→原生工具渲染→局部截图自检和容器资源采样。PILOT-01在ASR前失败，02评分不完整，03/04评分完整且reward=0（剪切范围未过）；03的归档后报告错误已另行修复。不同配置不当作同质重复。
- OPENSTORYLINE repair-07禁网冷启动、confirm-flow-03定向回归及real-native-short-04真实短任务门禁均通过。唯一正式attempt `20261022T150133Z-openstoryline-edit-02` 已提交并完成一次原版评分：reward=0.0，结果保持不变。closeout-review-01离线修订确认内存current峰值6.070053 GiB、内核peak 6.468014 GiB，并核实提交关联至状态选中的RenderVideo artifact；未修改raw/评分/冻结身份。
- 最新正式结果见reports/resource/OPENSTORYLINE-EDIT-PILOT-02/；收尾更正入口为revisions/closeout-review-01/。正式attempt总wall、进程返回码与目录初值仍unknown。容器已删除、镜像/缓存保留；无重跑授权。Gate、CPU-02、Replay不变，未更新HTML。
- ViMax静态准备分析完成：固定源码 commit、原生入口、API依赖和独立ARM64镜像方案已登记；没有构建或调用API，待用户确定服务/模型/预算并批准下一步。详见docs/vimax_execution_preparation.md。
- G1仅登记限定小闭环；G2/G3-R未通过，CPU-02/Replay暂停。当前准备门禁未通过；不将此前授权延伸为新执行授权。
- 状态防丢失保护完成：独立worktree规则、自动快照、协作锁和读取时SHA256校验已接入，33项状态/AgentX测试通过。本次远程检查点继续排除视频修改；完整恢复状态保留本机，Git HEAD不能代替完整本地状态。
- ViMax首次真实八镜头任务已在80次LLM逻辑调用上限处结束并完成停止收尾；未生成媒体、未评分，容器及对应进程无残留、镜像保留。收尾报告与资源曲线见reports/resource/VIMAX-GENERATION-PILOT-01/closeout-01/summary.md；不自动补跑。
- ViMax PILOT-01 离线诊断与最小修复已完成，禁网定向回归8项通过；未调用API、未建新attempt，真实规划仍待单独验证。
- ViMax PILOT-01 第二轮离线修复完成：新 v5 arm64 镜像 14/14 禁网回归通过；真实模型规划仍未验证，无 API 调用或新 attempt。
- ViMax callback repair 03 passed 23 offline tests in the new arm64 image; real planning remains unverified.
- ViMax planning validation 01 used one real native Agent attempt: 8 logical requests, 59,294 observed tokens; planning contract failed after length-finished structured responses, no media generated; container cleaned and image retained.
- ViMax PLANNING-VALIDATE-02 completed one real planning attempt; native planning contract failed on unsupported variation requirements before media generation; 15 logical requests, 39,707 returned tokens, cleanup verified.
- ViMax PLANNING-VALIDATE-03：能力约束对齐后一次真实规划契约通过，13次逻辑请求/36,753 tokens，无媒体生成；容器清理已核验。下一步媒体生成需单独批准。
- ViMax Generation Pilot 02: native pipeline preflight blocked before paid requests because 7 camera transition video jobs plus 8 shot videos require 15 creates, exceeding the authorized cap of 8; no approval or attempt created.
- ViMax GENERATION-PILOT-02 的唯一正式 attempt 在首个请求前因本地 runner TypeError 退出；0 个模型/图片/视频请求，容器删除核验通过，授权已消费且不补跑。
- ViMax当前已通过PILOT-04真实媒体生成闭环：19图、8主体+7过渡、40秒成片及33项技术验收；排障和快速复现入口见docs/vimax_troubleshooting.md。此前规划/启动失败按历史保留，后续复用REPAIR-01固定入口；本次仅整理文档，无新执行授权。
- VideoWeaver执行准备分析完成：官方dataset为空、原生媒体技能硬编码火山ARK SDK、推荐Codex CLI基线流程，同一ViMax八镜头故事可转换复用；详见docs/videoweaver_execution_preparation.md。本轮无安装/构建/调用，未创建执行批准。
- VideoWeaver执行交付完成：独立镜像videoweaver-task-bailian:arm64-v1、百炼适配（image-gen/video-gen/vision-understanding/merge-video/summary/harness）、禁网冷启动全链通过（final 40s/720p/30fps/无音轨、0外部泄漏），异常反例7项发送前拒绝；详见docs/videoweaver_execution_preparation.md。无真实API调用，未创建执行批准。
- VideoWeaver第二轮交付完成：统一生产入口host_runner v2（offline/live共用）、受控网关gateway.py发送前持久化账本（budget0/写失败/deadline发送0）、唯一新run目录保护、逐点资源/netns/目录/exec日志采集、统一judge判定；offline与live分支禁网均PASS，15项异常反例通过；镜像v1不变。详见docs/videoweaver_execution_preparation.md。无真实API，未创建执行批准。
- VideoWeaver真实执行VIDEOWEAVER-GENERATION-PILOT-01完成：8图+8主体视频真实生成（H.264/720p/30fps/5s/无音轨全过），Codex在merge前耗尽80次LLM预算，final.mp4未生成，judge FAIL；账本llm=80/80、图8、视频8、轮询64、下载16；账单unknown；清理核验通过。详见docs/current_task.md与evidence/VIDEOWEAVER-GENERATION-PILOT-01/。
- VideoWeaver PILOT-01修订与离线恢复完成：归因更正（merge SKILL要求运行时pip安装＋login shell解析到系统python）、修复SKILL禁止运行时安装并固定venv python（生产挂载纳入identity）、gateway SSE解析重构＋软阈值下一次转发前检查、usage重算total=3,297,990（80唯一response_id）、额外run核清（404/401各1次未受理）、8段真实视频离线拼接final-recovered.mp4（40s/720p/30fps/H264/无音轨）。详见docs与revisions/PILOT-01-recovery-01/。
- VideoWeaver解释器根因修复与真实仅拼接验证完成：v2镜像/etc/profile venv-first接线（bash -lc解析到venv，复用video-use验证方案）、技能说明统一（禁止运行时安装＋固定venv绝对python）、MERGE-VALIDATE-01一次真实Agent拼接（llm=7、媒体全0、无安装；SSE completed=6、usage total=93,487与rollout一致；final 40s/720p/30fps/H264/无音轨）。详见docs与evidence/VIDEOWEAVER-MERGE-VALIDATE-01/。
- VideoWeaver排障与快速复现备忘已整理至docs/videoweaver_troubleshooting.md：记录适配/生产入口、login-shell依赖安装、SSE与预算等根因及修法；真实生成、离线恢复、真实Agent仅拼接分阶段解释，不冒称v2单次连续端到端成功。仅文档整理，无新执行授权。
- VideoWeaver观测与采集完善完成：共享采集器新增运行中JSONL流与测量质量验收/读取器；VideoWeaver生产入口启用resource-stream.jsonl运行中落盘、monotonic阶段时间、目录受限扫描、quality/stream_state；gateway usage修复（非SSE total计软阈值、缺ID不合并不重复）；ViMax补dir_before/after。13项定向单测＋共享26项回归＋禁网离线run通过。详见revisions/PILOT-01-recovery-01/observation-prep-acceptance.md。未调真实API，未创建执行批准。
- VideoWeaver观测采集审计修复完成：assess重写（空样本/部分缺测/I-O回退/cgroup v1/间隔/边界）、生产judge真正消费质量与流解析、ViMax启用资源流+网络逐行落盘+边界持久化、_StreamSink计数语义、gateway缺ID归到本地请求并按请求去重计入软阈值（handler+fake验证429）、更正video-use/OpenStoryline目录边界误判。69项测试+禁网v2离线run+handler验证通过。详见docs与revisions/PILOT-01-recovery-01/observation-prep-acceptance.md。未调真实API，未创建执行批准。
- VideoWeaver观测验收剩余缺口修复完成：资源流契约校验(validate_resource_stream)、assess v3逐样本read状态与boundary有效性/scope身份核对、judge新增stream_validated/metrics_valid/rows_consistent/quality_recomputed/boundaries.metrics_valid；90项测试通过，正常fixture全过逐项损坏fail，旧记录只读验证通过。详见docs与revisions/PILOT-01-recovery-01/observation-prep-acceptance.md。未调真实API，未创建执行批准。
- VideoWeaver观测验收最后缺口修复完成：judge新增numeric_consistent（文件+边界重算数值vs报告/summary，含sample_metrics_summary）、scope_identity_ok进入最终PASS、boundary_only贯通旧stream非空条件、validate必需字段key校验+read_status结构；实测表A-I反例+J回归，99项测试通过，旧记录只读验证源不变。详见docs与revisions/PILOT-01-recovery-01/observation-prep-acceptance.md。未调真实API，未创建执行批准。
- VideoWeaver观测验收最后漏口修复完成：sample_content_digest全字段摘要（内存生成/文件重算核对）、流计数守恒（received=written+buffered+lost、收尾buffered=0、lost>0不完整）、零I/O状态（ok_no_records_real_zero）、连续采样覆盖（coverage_ok，短窗口通过/长缺样本或大gap失败）；实测表A-M，111项测试通过，旧记录只读验证源不变。详见docs与revisions/PILOT-01-recovery-01/observation-prep-acceptance.md。未调真实API，未创建执行批准。
- VideoWeaver样本摘要生产类型接线修复完成：共享to_stream_record统一CounterSnapshot/dict序列化（流写入器与摘要共用），修复收尾TypeError与schema不一致；read_status稳定排序、null≠缺字段、非法值拒绝；新契约缺摘要judge FAIL、历史unknown放行。真实ResourceSampler集成验证内存摘要==文件摘要，122项测试通过。详见docs与revisions/PILOT-01-recovery-01/observation-prep-acceptance.md。未调真实API，未创建执行批准。
- ViMax已完成PILOT-04真实媒体生成闭环：19图、8主体+7过渡、40秒成片及33项技术验收；此前规划/启动失败按历史保留，后续复用REPAIR-01固定入口。排障与复现入口见docs/vimax_troubleshooting.md与vimax_execution_preparation.md；当前无新执行授权。
- VideoWeaver观测/采集修复（summary用量统一聚合、运行中采样落盘、样本摘要接线、资源流契约与judge验收）已完成限定离线修复，122项离线测试通过；这不等于video-use/OpenStoryline/ViMax/VideoWeaver四个仓库的新采集口径均已由真实任务验证，video-use/OpenStoryline既有目录边界测量按已有证据登记（已更正早期"未见前/后测"误判）。
- 2026-10-24本轮仅整理文档与状态：当前任务页多段历史过程已收拢为当前结论＋历史入口（本机快照见local_archive/20261024-doc-cleanup-647394/）；未改代码、raw、报告、manifest、批准、身份或Docker。Gate、CPU-02、Replay不变，未创建新执行授权。
- 当前范围：本地单任务CPU、内存、磁盘I/O与占用、网络、时长、工具/软件统计和过程图；模型用量、阶段/错误、环境和采样质量一并记录。GPU、热点/PMU/微架构/优化不必交，Replay/并发仅可选。
- 本地三个既有批次的27个显式run已完成字段与manifest盘点；历史区间覆盖v3按CPU、cgroup I/O及可用/proc I/O分列候选/有效/gap，网络字节和任务目录边界占用没有观测，未回填。
- 新口径三链各一次已完成：Office目录扫描cwd修正后0→6629B；Coding Agent/verifier目录分别增长4874269/4614250B；Assistant场景内存状态N/A。主项采集和归档通过，cache仍unsupported导致supplement aggregate partial；共享netns不是任务/API专属字节。
- 火山三链各n=1限定离线分析完成：3张独立四面板资源SVG、作图CSV和目录占用表已生成。请求Office8、Coding20、Assistant Agent/User6/1；原生工具、Submitted控制流与业务错误分别统计。Coding宿主末次process_exited保留gap；共享netns不代表API字节，不合并旧27次。报告：reports/analysis/VOLCANO-THREE-CHAIN-characterization-v1/summary.md。
- LOCAL-THREE-CLASS-COMPLETE-02已顺序执行12/12次，identity 8a17109cf441e3ae68e3f9820babe5685467657cbcafb56d765dd1158dc4942d；合并原有效样本后27个固定task×round槽位各n=3，累计35次启动含8个永久排除的旧Office错路由attempt。v3独立复核及资源图已生成；7/7固定镜像批后身份匹配，raw归档哈希回读通过。n=3不代表类别总体，HTTP次数/费用unknown。报告：reports/analysis/LOCAL-THREE-CLASS-REPEAT-01-combined-review-v3/summary.md。
- G1仅登记小闭环通过；G2/G3-R未通过，CPU-02/Replay继续暂停。状态、建议、旧批准和旧execute命令都不是新授权。
- AgentX深入分析第1步完成：Full/256k同393会话、98,827/68,266请求；上下文演化、已完成历史前缀潜力、容量简化模型、请求重叠、筛选影响及时间局部性已分析，生成10张4K PNG/SVG、作图CSV和10页PPT。20项测试与216次真实请求穷举核对通过；模拟潜力不当作缓存命中/硬件并发。后续本地mock回放与DeepSeek客户端重复测量见AgentX五类重复实测报告。
- AgentX后续客户端测量收尾：Full全量分析为393会话/98,827请求；所选5会话各执行3次，为117个唯一源请求、351次正式客户端执行。仅测客户端，未执行原始业务工具，原始长输出负载未完整复现；这三项为证据边界，不是待补跑任务。
- 2026-10-25视频代码与文档远程检查点：合并远程AgentX收尾与状态工具更新，保存四仓库运行/观测代码、122项限定离线回归及小型配置报告；上游适配差异另存文本补丁。模型、媒体、raw轨迹/采样、安装包及local_archive留本机；本次无新执行授权。
<!-- PROJECT_STATE:END -->

公开数据集最新进展、来源边界及保存核查见[收尾总表](../reports/analysis/PUBLIC-DATASET-CLOSEOUT-20261023/summary.md)。已核验64,062项文件哈希并通过79项测试；历史HTML与综合报告未统一重制。

## 证据应如何使用

| 证据 | 已完成内容 | 主要边界与入口 |
| --- | --- | --- |
| 公开Coding | SWE-rebench、SWE-bench操作/工具统计；SWE-bench另补147个Sonar对象和20,098份评价/配套文件，40/41组有公开评价产物，原8,730个未列项逐项核查 | 74个空报告、30个缺报告及两组剩余来源缺口均列证据；5个结果冲突不擅自判定。KGCompass身份更正，仍不等同完整语义/资源覆盖。[逐任务评价](../reports/analysis/SWEBENCH-INSTANCE-RESULTS-v1/summary.md)、[操作v3](../reports/analysis/PUBLIC-TRACE-OPERATIONS-v3/summary.md)、[软件v3](../reports/analysis/PUBLIC-TRACE-SOFTWARE-TOOLKITS-v3/summary.md) |
| SWE-rebench复核 | 85分片/9,435轨迹完整核验；589,061对唯一ID结果，候选提取错误、未调用报告、提交请求分列；Junie 31,449步骤摘要另列 | 调用/返回数量差额已解释，不当作缺下载；步骤与请求不冒充实际执行次数，无资源采样证据。[复核v3](../reports/analysis/SWE-REBENCH-behavior-v3/findings.md) |
| 公开Computer/Office | OSWorld命令解析扩展至v4，全755条、201,050条command重算；原生动作、结果及usage保留v3证据 | 原生与源码分层；剩余控制流未知与保存标记分列；无实际GUI执行/应用/资源证明。[行为v4](../reports/analysis/OSWORLD-task-behavior-v4/findings.md)、[原生/任务v3](../reports/analysis/OSWORLD-task-behavior-v3/summary.md) |
| 公开Assistant | H-EPM两组414轨迹、2,021次调用/返回；v3静态核实全部原生身份，24未知及2活动分类调用补出确切工具名 | 用户侧406个结束请求中402个有返回，Agent终止原因仍未记录；不同源码版本仅描述比较，无资源证据。[H-EPM v3](../reports/analysis/TOOLSANDBOX-HEPM-behavior-v3/summary.md)、[历史v2](../reports/analysis/TOOLSANDBOX-HEPM-behavior-v2/summary.md) |
| 宏观请求/模板 | AgentX Full/256k同393会话，98,827/68,266请求；Applied Compute工作负载模板 | Full与256k重叠，不能合并分母；不足以统计真实业务软件或本地资源。[Full对照](../reports/analysis/AGENTX-FULL-MACRO-v1/summary.md)、[既有宏观分析](../reports/analysis/AGENTX-APPLIED-MACRO-v1/summary.md) |
| AgentX深入分析第1步 | 同393会话Full/256k全量分析；上下文、已完成历史前缀、时间局部性、容量模型及API区间重叠；10张4K图与10页PPT | 仅源记录与声明模型；不是缓存命中、硬件并发、业务工具或资源复现。[报告与PPT](../reports/analysis/AGENTX-DEEP-ANALYSIS-v1/findings.md) |
| AgentX DeepSeek五类客户端重复测量 | Full：393会话、98,827请求；另选5个会话各执行3次，117个唯一源请求、351次正式客户端执行 | 只测客户端；未执行原始业务工具，原始长输出负载未完整复现；没有服务器资源采样 | [报告](../reports/analysis/AGENTX-DEEPSEEK-FIVE-REPEATS-v1/summary.md)、[备份索引](agentx_evidence_backup_20261023.md) |
| 本地Coding/Office/Assistant | 新旧批按任务、身份分层，9个任务各3个观察点；工具、阶段、资源和重复统计 | 累计35次启动含8个排除的错路由Office记录；不同scope不直接排名。[合并v3](../reports/analysis/LOCAL-THREE-CLASS-REPEAT-01-combined-review-v3/summary.md) |
| 本地video-use | 核心转写、选段、渲染、局部截图自检、原生轨迹与容器采样 | 4个pilot不同配置；01前置失败、02评估不完整、03/04完整评分但reward=0。不是成功完成成本或视频总体。[P3](../reports/resource/VIDEO-USE-EDIT-PILOT-03/summary.md)、[P4验收](../reports/resource/VIDEO-USE-EDIT-PILOT-04/acceptance-revision-01.md) |
| 其他视频仓库 | 四仓源码、任务来源与执行拓扑已有可行性核查；OpenStoryline已完成真实剪辑与官方评分（reward=0）；ViMax已完成PILOT-04真实媒体生成闭环；VideoWeaver完成原生成＋离线恢复＋真实Agent仅拼接的分阶段验证 | OpenStoryline/VideoWeaver为分阶段证据，VideoWeaver修复后完整生成→拼接连续run未实测；技术验收不代替全面语义评分，reward、账单等缺口分别登记。[视频排障备忘](video_editing_troubleshooting.md)、[ViMax](vimax_troubleshooting.md)、[VideoWeaver](videoweaver_troubleshooting.md) |

“流程执行”“任务解决”“评估完整”“测量覆盖”“清理归档”分列，不能用reward或returncode互相替代。单任务多次采样不等于多个任务；固定任务重复不代表类别总体。

<a id="当前目标与采样能力2026-10-16"></a>

## 当前目标与采样能力

| 指标 | 已实现/已有证据 | 仍需保留的限制 |
| --- | --- | --- |
| CPU | Coding/Office/video-use cgroup累计CPU差分；Assistant共享worker /proc CPU；按实际相邻时间得到平均core | 不是远端模型、整机或单工具独占CPU；不同scope不相加，不要求函数热点 |
| 内存 | current、RSS时间序列；内核peak可得时单列 | 采样峰值与内核peak不同，RSS/current不能相加 |
| 磁盘I/O | cgroup服务字节、可用/proc计数及有效区间速率 | 各类计数语义不同，不等于完整文件系统流量 |
| 磁盘占用 | 新口径按明确工作区/输出路径量边界与增长；Assistant内存状态单列N/A | 表观字节不等于磁盘实际分配；共享cache未归属，最终归档大小另计，旧缺失不回填 |
| 网络 | 新口径保存逐接口netns累计收发及速率，视频可观测容器接口 | 不是API专属流量；HTTP实际次数、正文/TLS开销和账单无证据则unknown |
| 时间与行为 | 保存attempt/可观测阶段、工具调用返回、bootstrap、错误和usage | 采样窗不冒充完整attempt；逻辑调用、保存响应与HTTP次数不同，累计usage不重复求和 |
| 采样质量 | 目标0.5秒并保留实际间隔、读状态与gap；视频实测约0.6秒 | 不补零或插值，不为凑采样点延长任务；未覆盖阶段明确列出 |
| 图表 | 历史[HTML v5](../reports/html/PROJECT-RESULTS-v5/index.html)、新三类及视频独立SVG/CSV | HTML不是实时总览，最新三类/视频及完整面板待最后统一更新，本次不生成HTML |

机器背景负载可能改变任务性能；计量本身采用任务容器或指定共享进程scope，不把其他独立进程资源直接相加。容器内FFmpeg等子进程纳入cgroup；宿主独立verifier需另列，不能冒称已被Agent容器曲线覆盖。

### AgentCgroup 方法实际采用到哪里

| 参考 | 实际关系 | 不能据此声称 |
| --- | --- | --- |
| [ResourceMonitor](../references/repos/agentcgroup/scripts/run_swebench.py) | 连续采样思路相近；本项目使用自有cgroup/proc reader，不直接运行其podman stats监测器 | 不因参考其方法就声称全部I/O、网络或进程归因已覆盖 |
| [tool_timing](../references/repos/agentcgroup/analysis/tool_timing.py) | Coding分析采用整数ns区间合并/并集及部分分类思路 | 不将重叠时间均摊为工具独占，不把uncovered当思考/等待 |
| 资源展示 | 独立时间序列与任务内median/IQR保留原始点、单位、scope | 不从图线推算函数热点、因果或模型排名 |

### 后续缺口与优先级

1. 保留video-use基础剪辑证据，不为单题满分无上限补跑；批量转写/字幕/动画任务已列为[暂缓待办](current_task.md#video-use-optional-coverage-backlog)。
2. 其余视频仓库需要各自环境与任务接线；新增音频模型不属于当前原生流程路线。任务/API专属网络与共享cache归属仍未实现，需另行决定是否扩展。
3. 最新成果最后统一进入HTML。GPU、函数热点、PMU、微架构和优化不是必补项；CPU-02/Replay继续暂停，Gate裁定未变。

历史字段缺失见[覆盖盘点v3](../reports/analysis/LOCAL-MEASUREMENT-COVERAGE-v3/summary.md)，新样本见[合并复核v3](../reports/analysis/LOCAL-THREE-CLASS-REPEAT-01-combined-review-v3/summary.md)。旧[综合证据矩阵v3](../reports/analysis/PROJECT-characterization-synthesis-v3/evidence_matrix.json)保留原时点，不冒充包含最新视频结果。

## 历史资料

本页与当前任务页的逐轮旧说明已保留在[2026-10-21编辑前快照](history_index.md#docs-refresh-20261021)；更早方法与任务文档按[历史索引](history_index.md)查阅。正式报告、raw、批准和manifest未搬迁或改写。
