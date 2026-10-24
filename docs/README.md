# 文档索引

日常只读当前文档，不再默认打开旧任务书。事实源为[project_state.json](../project_state.json)。

<!-- PROJECT_STATE:START -->
当前状态由 [2026-10-24 状态真源](../project_state.json)统一登记；这是进度记录，不是执行授权。

- 当前目标：分析Agent单任务的CPU、内存、磁盘I/O与占用、网络、时长及工具/软件使用，保留过程曲线、环境与采样质量；不要求GPU或函数热点。
- 公开trace已完成限定操作/软件汇总v3：SWE-rebench 9,435轨迹、SWE-bench现登记20,023对象/41组（原v3为19,876，后补147）、OSWorld 755模型×任务记录/108任务（命令解析扩展至v4，原生/源码分层）、H-EPM 414轨迹；AgentX Full/256k及Applied提供宏观证据：AgentX两版同393会话，98,827/68,266请求，仍无业务工具明细或本地资源。未穷尽语义解析，不混合来源分母或把软件声明当实际启动。
- AgentX深入分析第1步完成：Full/256k同393会话、98,827/68,266请求；上下文演化、已完成历史前缀潜力、容量简化模型、请求重叠、筛选影响及时间局部性已分析，生成10张4K PNG/SVG、作图CSV和10页PPT。20项测试与216次真实请求穷举核对通过；模拟潜力不当作缓存命中/硬件并发，本地回放尚未开始。
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
<!-- PROJECT_STATE:END -->

## 当前入口

| 内容 | 入口 |
| --- | --- |
| 项目目标、必采指标和排除项 | [current_scope](current_scope.md) |
| 已有证据、实现能力和缺口 | [project_status](project_status.md) |
| 当前工作、下一建议和授权边界 | [current_task](current_task.md) |
| 采样字段与统计语义 | [trace_contract](trace_contract.md#11-当前目标的连续采样与图表要求2026-10-16) |
| 环境、身份和状态维护 | [reproducibility](reproducibility.md) |
| 并发工作与状态保护 | [自动快照、版本校验与独立worktree](project_state_protection.md) |
| 数据与原始证据保护 | [data_management](data_management.md) |
| 两个视频剪辑仓库的故障、修法与开跑检查 | [视频剪辑排障备忘](video_editing_troubleshooting.md) |
| ViMax生成仓库的故障、固定成功入口与复现清单 | [ViMax排障与快速复现备忘](vimax_troubleshooting.md) |
| VideoWeaver适配、解释器/SSE修复、分阶段结果与复现清单 | [VideoWeaver排障与快速复现备忘](videoweaver_troubleshooting.md) |
| ViMax原生入口、API依赖、任务镜像与验收方案 | [ViMax执行准备分析](vimax_execution_preparation.md) |
| VideoWeaver执行方式、API依赖、任务输入与镜像方案（镜像＋百炼适配＋统一生产入口已交付；原生成/离线恢复/真实Agent仅拼接分阶段验证，修复后完整闭环未实测） | [VideoWeaver执行准备分析](videoweaver_execution_preparation.md) |

## 成果入口

| 内容 | 报告 |
| --- | --- |
| 公开操作构成/工具接口 | [操作v3](../reports/analysis/PUBLIC-TRACE-OPERATIONS-v3/summary.md) |
| 公开数据集收尾 | [最新分析与保存核查](../reports/analysis/PUBLIC-DATASET-CLOSEOUT-20261023/summary.md)，各数据集限定范围完成；HTML及旧综合报告保留历史时点 |
| SWE-bench补充分析 | [逐任务评价补全](../reports/analysis/SWEBENCH-INSTANCE-RESULTS-v1/summary.md)、[剩余来源问题](../reports/analysis/SWEBENCH-INSTANCE-RESULTS-v1/remaining_source_gaps.csv)；新增20,098份评价/配套文件，KGCompass身份更正；[原下载/覆盖复核](../reports/analysis/SWEBENCH-COVERAGE-RESULTS-v1/findings.md)及90条选择保留 |
| SWE-rebench复核 | [调用协议与行为v3](../reports/analysis/SWE-REBENCH-behavior-v3/findings.md)、[逐participant协议](../reports/analysis/SWE-REBENCH-behavior-v3/participant_protocol_details.csv)；598,148调用/616,980结果差额按harness错误与提交请求解释，Junie步骤摘要另列 |
| 具体软件与程序库 | [软件工具集v3](../reports/analysis/PUBLIC-TRACE-SOFTWARE-TOOLKITS-v3/summary.md) |
| 三类本地最新分析 | [合并复核v3](../reports/analysis/LOCAL-THREE-CLASS-REPEAT-01-combined-review-v3/summary.md)，9个固定任务各3次，旧错路由样本单列排除 |
| 本地Coding | [特征化v3](../reports/analysis/P1-12-CODING-REPEAT-01-characterization-v3/summary.md) |
| 本地Office | [REPEAT-02](../reports/analysis/DOCOPS-OFFICE-REPEAT-02-characterization-v1/summary.md) |
| 本地Assistant | [REPEAT-01](../reports/analysis/TOOLSANDBOX-ASSISTANT-REPEAT-01-review-v1/summary.md) |
| 本地历史测量字段与新采集接线 | [覆盖盘点v3](../reports/analysis/LOCAL-MEASUREMENT-COVERAGE-v3/summary.md)，后续新测量见三类合并v3 |
| OSWorld | [命令解析与行为v4](../reports/analysis/OSWORLD-task-behavior-v4/findings.md)、[未知项审查](../reports/analysis/OSWORLD-task-behavior-v4/remaining_unknown_review.md)；[任务与原生层v3](../reports/analysis/OSWORLD-task-behavior-v3/summary.md) |
| H-EPM / ToolSandbox | [工具身份与终止复核v3](../reports/analysis/TOOLSANDBOX-HEPM-behavior-v3/summary.md)、[26次身份补全](../reports/analysis/TOOLSANDBOX-HEPM-behavior-v3/recovered_tool_identities.csv)；[原行为v2](../reports/analysis/TOOLSANDBOX-HEPM-behavior-v2/summary.md)保留 |
| AgentX/Applied | [AgentX Full与256k对照](../reports/analysis/AGENTX-FULL-MACRO-v1/summary.md)；[既有256k/Applied宏观分析](../reports/analysis/AGENTX-APPLIED-MACRO-v1/summary.md) |
| AgentX深入分析第1步 | [发现与10页PPT](../reports/analysis/AGENTX-DEEP-ANALYSIS-v1/findings.md)、[逐页讲解](../reports/analysis/AGENTX-DEEP-ANALYSIS-v1/presentation_notes.md)；10张4K PNG/SVG、CSV，尚未运行本地回放 |
| 视频剪辑与资源 | [video-use PILOT-04验收](../reports/resource/VIDEO-USE-EDIT-PILOT-04/acceptance-revision-01.md)、[PILOT-03](../reports/resource/VIDEO-USE-EDIT-PILOT-03/summary.md)、[边界诊断](../reports/analysis/VIDEO-USE-EDIT-PILOT-03-boundary-review-v1/summary.md)；OpenStoryline[正式attempt与评分](../reports/resource/OPENSTORYLINE-EDIT-PILOT-02/summary.md)；ViMax[PILOT-04收尾](../env/video/vimax/VIMAX-GENERATION-PILOT-04/closeout-summary.md)；VideoWeaver[仅拼接验收](../env/video/videoweaver/evidence/VIDEOWEAVER-MERGE-VALIDATE-01/merge-acceptance.json) |
| 后续可选工具覆盖 | [暂缓待办](current_task.md#video-use-optional-coverage-backlog)，不构成新运行批准 |
| 离线HTML | [v5](../reports/html/PROJECT-RESULTS-v5/index.html)，最新成果最后统一更新 |

## 历史只按需查询

旧方法、逐轮任务、交接、批准说明、CPU/G1/IR/适配器设计等77份历史文档已移入本机Git忽略的local_archive。见[历史索引](history_index.md)、[迁移登记](archive_index.json)、[引用审计](archive_reference_audit.json)。2026-10-16编辑前快照位于local_archive/20261016-full-docs/before-edit；最新文档整理快照见[2026-10-21历史入口](history_index.md#docs-refresh-20261021)与[2026-10-24历史入口](history_index.md#docs-cleanup-20261024)。

报告历史原文及其manifest不改写。需要历史证据时按原逻辑路径查索引，再核对原登记SHA；不能把当前新目标当作旧批准或旧运行的证据。迁移后代码库仍不包含全部本地数据/归档，不承诺GitHub克隆后可核验全部历史证据。
