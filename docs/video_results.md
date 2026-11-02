# 视频有效结果与下一阶段入口

更新：2026-11-02。这里是四仓视频结果的当前索引，不是执行批准。
机器可读路径见 [video_results_index.json](video_results_index.json)。共 **16个历史保留的仓库×任务组合、9个输入**（四仓各4项；ViMax新增MUSICIANS-AUDIO原运行＋独立拼接恢复）。不是16次连续成功或同配置重复实验，也不保证16份原始trace当前都可定位；规划/媒体、原attempt/独立恢复分别统计。assembly的12个候选clip为一个任务输入包；恢复不额外算输入或Agent执行。**R01-02（OPENSTORYLINE-E01-FULL-FLOW-R01-02）已完成完整正常流程并经只读复核通过；R02-01、R03-02、R04-01（2026-11-01）已完成完整正常流程；R05–R08（2026-11-01/02）已完成完整正常流程；R09（VIDEO-USE-E03-FULL-FLOW-R09-01，2026-11-02）已完成完整正常流程：E03输入/指令门禁通过、官方ASR一次真实提交（611词）、Agent自主删除phone-case stand-up claim段（EDL [29.17,34.43]s、rc=0、177.83s）、原生render、宿主导出output.mp4/cuts.json（cut [29170,34430]ms）、技术检查全通过（源/输出854×480/24000-1001 exact、完整解码pass）、一次官方评分complete/reward=0（合法，cut命中golden但ssim 0.7244<0.8）、原生rollout 28/28配对无右删失、测量完整、清理回验removed、manifest绑定最终run-record字节、独立raw副本24/24一致。** 历史失败观察（R01-01/R03-01/R05-MEDIA-01/R06-MEDIA-01/R08-MEDIA-01）与历史E03 raw缺失、PILOT-01两项UNKNOWN保护状态原样保留；新运行不增加组合/输入计数。

**完整流程重跑清单9组全部完成：R01–R09（2026-10-31至11-02）。** 保留OpenStoryline E01/E02/E03/ASSEMBLY-TASK1及ViMax G01/G02/G03/MUSICIANS-AUDIO原8组，加入video-use E03补采，详见[完整流程重跑清单](video_full_flow_rerun_plan.md)。清单制定时包括3组正常分阶段、5组独立恢复、1组raw留存缺口；不是9次历史任务失败，也不缩减为5/6组。

“有效记录”表示存在真实工具轨迹、资源及产物/验收证据，可用于后续CPU工具回放整理；**不以 reward>0 为条件**，也不表示每项操作已完成独立回放验收。官方任务成败、技术验收、测量质量和恢复状态分别报告。

当前简明入口：[四仓视频现状总览](video_status_overview.md)。以下表格保留历史基线及其修订；最新九组完成状态以重跑清单与机器索引为准，历史行中的阶段性停止说明不代表现在仍未完成。

## 保留的主要结果（历史基线与修订）

| 仓库/任务 | 可用结果 | 最新报告 |
| --- | --- | --- |
| video-use E01 | 连续剪辑、完整官方评分 reward=0 | [报告](../reports/resource/VIDEO-USE-E01-BASELINE-01/summary.md) |
| video-use E02 | 连续剪辑、保留60000/1001fps、完整评分 reward=0；源30.029317s，成片容器29.276517s | [修订说明](../reports/analysis/VIDEO-TASK-EXPANSION-C01/revision-CLOSEOUT-01/summary.md) |
| video-use E03 | 历史报告记录连续剪辑及完整评分reward=0；当前索引raw父目录为空，暂不认定当前可回放；**R09 完整正常流程成功（VIDEO-USE-E03-FULL-FLOW-R09-01，2026-11-02）：输入/指令门禁通过、官方ASR一次真实提交（611词）、Agent自主删除phone-case stand-up claim段（EDL [29.17,34.43]s、rc=0、177.83s）、原生render、宿主导出output.mp4/cuts.json（cut [29170,34430]ms）、技术检查全通过（源/输出854×480/24000-1001 exact、完整解码pass）、一次官方评分complete/reward=0（合法，cut命中golden但ssim 0.7244<0.8）、原生rollout 28/28配对无右删失、测量完整、清理removed、独立raw副本24/24一致** | [批报告](../reports/analysis/VIDEO-E03-TWO-REPO-EXECUTION-01/summary.md)、[R09-01成功](../reports/analysis/VIDEO-USE-E03-FULL-FLOW-R09-01/summary.md) |
| video-use REPURPOSE | 单次正式 attempt、Agent rc=0；Bolt 100m 竖屏复剪 repurpose.mp4 导出（1080×1920/H.264/AAC 立体声/166s 容器）；技术验收 5/6 项通过、`duration_166s` 未过（视频流 165.88s vs 166.0±0.1s）；官方 not_run、reward=null、语义 not_evaluated | [分析](../reports/analysis/VIDEO-USE-REPURPOSE-BOLT-EXECUTION-01/summary.md) |
| OpenStoryline E01 | 真实渲染＋独立恢复提交及完整评分 reward=0；原导出失败保留；**R01 完整正常流程成功（OPENSTORYLINE-E01-FULL-FLOW-R01-02，2026-10-31）：原生interview链到render、Agent rc=0、宿主导出output.mp4/cuts.json、技术检查通过、一次官方评分 complete/reward=0（合法）；R01-01失败观察（1800s截止、无提交物、reward=null）原样保留** | [恢复记录](../env/video/openstoryline/OPENSTORYLINE-E01-RUNTIME-CONFIRM-02/recovery-01/recovery-report.json)、[R01-01失败观察](../reports/analysis/OPENSTORYLINE-E01-FULL-FLOW-R01-01/failure-observation-summary.md)、[R01-02成功](../reports/analysis/OPENSTORYLINE-E01-FULL-FLOW-R01-02/success-summary.md) |
| OpenStoryline E02 | 输入门禁真实通过、完整Agent至render＋独立FPS恢复及评分 reward=0；**R02-01（OPENSTORYLINE-E02-FULL-FLOW-R02-01，2026-11-01）完整正常流程成功：原生链到render、Agent rc=0、宿主导出output.mp4/cuts.json、技术检查PASS（帧率源/输出精确60000/1001 exact_equal、0 ppm）、一次官方评分complete/reward=0（合法）；E02-EXPANSION-01/02失败及独立恢复原样保留** | [恢复验收](../reports/analysis/OPENSTORYLINE-E02-EXPANSION-02/recovery-FPS-01/summary.md)、[R02-01成功](../reports/analysis/OPENSTORYLINE-E02-FULL-FLOW-R02-01/success-summary.md) |
| OpenStoryline E03 | Agent至render、资源完整；原宿主导出因缺失导入失败，独立closeout完成同一产物导出及评分 reward=0；语义结束边界未命中；**R03-01（OPENSTORYLINE-E03-FULL-FLOW-R03-01，2026-11-01）失败观察：预算60耗尽未到render，无提交物；R03-02（OPENSTORYLINE-E03-FULL-FLOW-R03-02，2026-11-01）完整正常流程：批准预算100、Agent rc=0（950.95s）、一次粗剪41/41调用与解析成功后推进（不代表语义正确）、宿主导出output.mp4/cuts.json（删除[29190,30810]）、技术检查PASS（帧率精确24000/1001）、官方评分complete/reward=0（合法，end_offset 3.518s未命中golden）；E03-EXPANSION-01/02与RUNTIME-CONFIRM-03原样保留** | [当前修订](../reports/analysis/OPENSTORYLINE-E03-RUNTIME-CONFIRM-03/revision-DOCUMENTATION-CLOSEOUT-01/summary.md)、[R03-01失败观察](../reports/analysis/OPENSTORYLINE-E03-FULL-FLOW-R03-01/failure-observation-summary.md)、[R03-02成功](../reports/analysis/OPENSTORYLINE-E03-FULL-FLOW-R03-02/success-summary.md)、[预算核定](../reports/analysis/OPENSTORYLINE-E03-REQUEST-BUDGET-READINESS-01/summary.md)、[防线与整链收尾](../reports/analysis/OPENSTORYLINE-E03-BUDGET-READINESS-FINAL-CLOSEOUT-01/summary.md) |
| OpenStoryline ASSEMBLY-TASK1 | EXECUTION-04真实选片→分组→时间线→四段渲染；原入口误用采访完成判定而失败；同一视频独立恢复为solution.mp4/json，新帧周期策略技术验收通过，旧10ms策略失败保留；官方未评分、reward=null；**R04-01（OPENSTORYLINE-ASSEMBLY-FULL-FLOW-R04-01，2026-11-01）完整正常流程：原生understand(12)→filter(K=4)→group(slot)→plan→render、Agent rc=0、assembly完成判定正常、宿主导出solution.mp4/solution.json（与render逐字节一致、结构10/10 PASS）、官方not_integrated/reward=null、semantic not_evaluated** | [恢复报告](../reports/analysis/OPENSTORYLINE-ASSEMBLY-TASK1-EXECUTION-04/recovery-COMPLETION-01/recover-report.json)、[R04-01成功](../reports/analysis/OPENSTORYLINE-ASSEMBLY-FULL-FLOW-R04-01/success-summary.md) |
| ViMax G01 | 8主体＋7辅助过渡、40s成片；规划和媒体分阶段；**R05规划阶段完成（2026-11-01）：VIMAX-G01-FULL-FLOW-R05-PLANNING-01 新规划通过——8镜头/1角色/8相机/7过渡、plan_verifier 14/14、0媒体、13逻辑请求（37,873 tokens）；媒体预算按真实生产分支修正（image_creates 19、video_creates 15、下载34、轮询时间窗上界92/1380，ledger cap 1800另计），资源派生与采样收尾见[R05修订](../reports/analysis/VIMAX-G01-R05-MEDIA-BUDGET-AND-RESOURCE-CLOSEOUT-01/summary.md)，四缺口握手/真实控制链/轮询时序/helper一致见[四缺口收尾](../reports/analysis/VIMAX-R05-FOUR-GAP-OFFLINE-FINAL-CLOSEOUT-01/summary.md)，生产边界共享函数/ACK v2/helper严格校验见[生产边界校验最终](../reports/analysis/VIMAX-R05-PRODUCTION-BOUNDARY-AND-VALIDATION-FINAL-01/summary.md)，观测质量归纳与ACK幂等语义见[观测质量ACK语义收尾](../reports/analysis/VIMAX-R05-OBSERVATION-QUALITY-AND-ACK-SEMANTICS-CLOSEOUT-01/summary.md)，观测质量正确性（统一schema/开始边界逐指标/整体汇总/entry归属）见[观测质量正确性最终](../reports/analysis/VIMAX-R05-OBSERVATION-QUALITY-CORRECTNESS-FINAL-01/summary.md)，媒体阶段未启动** | [媒体分析](../reports/analysis/VIDEO-THREE-REPO-RUNTIME-CONFIRM-02/vimax-g01-media/summary.md)、[R05规划](../reports/analysis/VIMAX-G01-FULL-FLOW-R05-PLANNING-01/summary.md)、[R05修订](../reports/analysis/VIMAX-G01-R05-MEDIA-BUDGET-AND-RESOURCE-CLOSEOUT-01/summary.md)、[四缺口收尾](../reports/analysis/VIMAX-R05-FOUR-GAP-OFFLINE-FINAL-CLOSEOUT-01/summary.md)、[生产边界校验最终](../reports/analysis/VIMAX-R05-PRODUCTION-BOUNDARY-AND-VALIDATION-FINAL-01/summary.md)、[观测质量ACK语义收尾](../reports/analysis/VIMAX-R05-OBSERVATION-QUALITY-AND-ACK-SEMANTICS-CLOSEOUT-01/summary.md)、[观测质量正确性最终](../reports/analysis/VIMAX-R05-OBSERVATION-QUALITY-CORRECTNESS-FINAL-01/summary.md) |
| ViMax G02 | 全新10镜头规划、19视频任务、50s成片；核心契约/预算通过，图片来源完整性PARTIAL | [验收修订](../reports/analysis/VIMAX-G02-EXPANSION-01/revision-ACCEPTANCE-01/summary.md) |
| ViMax G03 | 原9镜头规划离线复验后单独执行媒体，17视频任务、45s成片；没有重新规划 | [规划恢复与媒体](../reports/analysis/VIDEO-G03-TWO-REPO-EXPANSION-01/summary.md) |
| ViMax MUSICIANS-AUDIO | 新13镜头规划；11图＋25有声视频生成/下载成功，原concat失败；独立本地拼接恢复出65.13s H.264/720p30/AAC非静音成片，解码通过；原3015样本与恢复49样本独立，不冒称连续端到端性能 | [原媒体运行](../reports/analysis/VIMAX-MUSICIANS-AUDIO-MEDIA-EXECUTION-02/summary.md)、[拼接恢复](../reports/analysis/VIMAX-MUSICIANS-AUDIO-CONCAT-RECOVERY-01/summary.md) |
| VideoWeaver G01 | 8图/8视频、Agent原生merge、40s成片，连续完成 | [报告](../reports/analysis/VIDEO-THREE-REPO-RUNTIME-CONFIRM-03/summary.md) |
| VideoWeaver G02 | 10图/10视频、50s成片，连续完成；下载门槛配置误设的原FAIL与离线修订PASS分别保存 | [验收修订](../reports/analysis/VIDEO-TASK-EXPANSION-C01/revision-CLOSEOUT-01/summary.md) |
| VideoWeaver MUSICIANS-AUDIO | 一次真实13镜头有声运行：13图+13视频（wan2.6 audio=true）+原生merge→65.13s final（AAC非静音/解码ok），judge 44/44；语义not_evaluated、官方not_run；探针不计 | [分析](../reports/analysis/VIDEOWEAVER-MUSICIANS-AUDIO-EXECUTION-01/summary.md) |
| VideoWeaver G03 | 9图/9视频、Agent原生merge、45s成片；技术验收通过，无官方语义评分 | [批报告](../reports/analysis/VIDEO-G03-TWO-REPO-EXPANSION-01/summary.md) |

原始轨迹、账本、采样、提交物、身份/批准和manifest按索引逐项定位；video-use E03的历史raw路径缺失，不能笼统称全部原始证据仍保留（R09已补采完整新trace并保留历史缺口事实）。OpenStoryline及ViMax musicians恢复成本不并入原Agent成本，原始失败状态不改写。
早期已完成且有用的video-use PILOT-03/04、OpenStoryline EDIT-PILOT-02及ViMax PILOT-04也保留；不要把不同配置合并成n次同质重复。

## 解释边界

- reward=0且评分完整，是合法实验结果，不因未满分删除。
- OpenStoryline E03“无额外删除”仅表示实际剪切与本次Agent选择一致，不代表语义选段正确；原attempt导出失败与恢复评分不能合写为一次连续成功。
- assembly以“原运行＋独立恢复”保留：原attempt的failed/无自动提交不变；恢复视频与原render逐字节一致（SHA `33b4343d…`），solution.json来自同一render消费的timeline。timeline末端21.686s、媒体21.666667s；旧10ms检查失败，新`openstoryline-assembly-final-media-frame-quantization-v1`策略通过，不追溯为原运行当时PASS，亦不等于官方/语义选片正确。
- assembly原运行1598点资源样本、CPU 96.410294 core-s，质量complete仅针对原声明观测窗口；独立恢复成本不并入该窗口。原EXECUTION-02/03仍为未选入覆盖的失败历史，filter额度探针不计为完整任务样本。
- assembly实际使用storyboard选择＋可靠性适配版本，身份绑定当时21项overlay；完成判定修复后的23项overlay属于后续版本，不能冒称原运行版本。未来自动收尾仅离线验证，可在以后另行授权的assembly任务中验证；不要求专门重跑task1。
- E03最新资源共1602行（1600周期点＋2边界），目标间隔0.5s，周期点实测中位0.601382s、均值0.614553s；边界窗口983.826245s。质量complete限于该原始窗口，不包含独立closeout/verifier资源。
- 视频/图片由百炼远端生成；本地负责Agent、工具、下载和拼接，本地CPU/内存不含远端推理。
- `complete`只表示声明观测窗口和相应来源的数据质量，不保证整段attempt覆盖。
- ViMax规划与媒体分阶段；G02图片请求14、视频创建19分别统计，文件复制/抽帧不算新模型请求。原轮询238条事件为119条open＋119条close；独立收尾查询另外列，不能按事件行数当HTTP请求数。
- OpenStoryline帧率策略为abs≤0.0001fps且rel≤2ppm；60000/1001与2997/50并非数学相等，但在已记录策略下允许微小舍入。无需专门重跑E02追求精确字符串相等。
- 无官方语义评分的生成任务不虚构reward；G02来源或用量缺口保留PARTIAL/unknown。

## 下一阶段

上述[9组完整流程重跑](video_full_flow_rerun_plan.md)已完成。下一阶段是将保留的原生命令或Python/MCP调用整理成本地工具链回放配方、冻结依赖和定义测量区间；目前尚未完成统一回放执行器验收，不自动执行Replay。历史基线仍按7连续＋3分阶段＋5恢复＋1旧raw缺口分列，不因新重跑改写。仓库清理仅完成候选审计，用户暂不删除；重复副本/派生数据的取舍需另行批准。

分析命令：

```bash
python3 -B scripts/video_analysis_chain.py --run <实际run目录> --repo <video-use|openstoryline|vimax|videoweaver> --out <不存在的新目录>
```

执行入口/环境见 [剪辑排障](video_editing_troubleshooting.md)、[ViMax](vimax_troubleshooting.md)、[VideoWeaver](videoweaver_troubleshooting.md)；分析口径见 [video_analysis_guidelines.md](video_analysis_guidelines.md)。

旧`video_four_repo_baseline_analysis.py`批包装器依赖已清理的失败基线，已增加发送/输出前缺失检查，不再用于当前成果分析；不要为运行旧批脚本而恢复失败中间数据。上述通用逐run入口不变。

## 2026-10-29 直接清理

用户明确要求不归档中间数据，已完成的代表性结果和依赖保留，未完成/错误输入/重复诊断及旧视频专属快照直接删除。精确处置依据见 [删除计划](video_cleanup_20261029_plan.json) 和 [删除回执](video_cleanup_20261029_receipt.json)；回执仅保留路径、大小和SHA，不保存被删内容。
生产源码、配方、测试及必要小型fixture仍保留；`references/`、原素材、模型缓存、venv、凭据、Docker镜像、非视频数据及其他对话工作不动。未删除的失败ledger仅作为回归fixture，不作为结果样本。
旧状态条目中被删除路径只是历史标识，当前结果必须从本页进入。旧manifest不改写成“仍完整可读”。
