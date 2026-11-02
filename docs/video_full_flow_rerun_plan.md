# 视频完整流程重跑清单（9组：R01/R02/R03/R04/R05/R06/R07/R08/R09均已完成）

更新：2026-11-02。保留原8组（含ViMax正常分阶段3组），加入video-use E03完整trace补采，共9组，目标均为完整跑通，不缩减为5组或6组。R01-02、R02-01、R03-02、R04-01、R05、R06、R07、R08均已完成完整正常流程；R09（video-use E03）也已于2026-11-02完成唯一正式完整流程attempt——完整原生rollout、操作时间、资源、输入产物和manifest持久化并回读，独立raw副本建立。R01-01、R03-01、R05-MEDIA-01、R06-MEDIA-01、R08-MEDIA-01失败观察及历史16组基线原样保留。本页是计划，不是API、容器、模型或Replay执行批准。

## 16组历史基线如何理解

R09 归档补充：[ARCHIVE-CLOSEOUT-01](../reports/analysis/VIDEO-USE-E03-FULL-FLOW-R09-01/revision-ARCHIVE-CLOSEOUT-01/summary.md) 独立绑定 control、宿主资源报告及 raw/副本，纠正旧报告 manifest 路径声明但不改原文件；无新运行或评分，九组完成状态与覆盖计数不变。

16是历史保留的仓库×任务组合数，来自9个不同输入，不是16次连续成功运行，也不是16组已经逐条验收通过的回放轨迹。来源与路径见[成果索引](video_results.md)及[机器登记](video_results_index.json)。

| 当前类别 | 数量 | 任务 |
| --- | --- | --- |
| 连续主流程记录、索引raw可定位 | 7 | video-use E01、E02、REPURPOSE/Bolt；VideoWeaver G01、G02、G03、MUSICIANS-AUDIO |
| 规划与媒体分阶段保留 | 3 | ViMax G01、G02、G03 |
| 原运行＋独立恢复 | 5 | OpenStoryline E01、E02、E03、ASSEMBLY-TASK1；ViMax MUSICIANS-AUDIO |
| 原始trace位置待核实 | 1 | video-use E03：历史报告记录连续完成，但索引raw父目录当前为空 |

“连续主流程记录”不代表整段attempt每个瞬间都有资源数据，更不代表逐条命令字段已统一验收。video-use Bolt流程已执行至导出和验收，但原165.88s视频流时长门FAIL仍保留；VideoWeaver G02原judge FAIL与离线修订PASS仍分列。两者不混入本次9组重跑范围。

## 一次列齐的9组

| 编号 | 仓库/任务 | 现有记录的边界（不是都执行失败） | 后续新运行必须覆盖 |
| --- | --- | --- | --- |
| R01 | OpenStoryline E01 | 已真实剪辑/render；原宿主来源匹配导出失败，独立恢复提交及评分 | **已完成（2026-10-31）：R01-02 完整正常流程成功——输入/overlay门禁通过、原生interview链到render、Agent rc=0（1076.69s<1800s）、完成判定写入、宿主导出output.mp4/cuts.json、技术检查通过、一次官方评分 complete/reward=0（合法）、容器清理。R01-01（1800s截止、无提交物）失败观察原样保留。** 输入门禁→原生Agent/ASR/剪辑→render→原宿主正常导出→技术检查→既有官方评分完成→正常收尾；无事后恢复兜底 |
| R02 | OpenStoryline E02 | 已消费E02并完成render；旧帧率门拒绝，独立FPS恢复导出及评分 | **已完成（2026-11-01）：OPENSTORYLINE-E02-FULL-FLOW-R02-01 完整正常流程成功——输入/overlay门禁真实通过（实际挂载E02输入、容器内bytes/SHA=冻结、25项overlay）、原生interview链到render、Agent rc=0（479.66s<1800s）、完成判定写入、宿主导出output.mp4/cuts.json（从final render实际消费的timeline派生）、技术检查通过（帧率源/输出精确60000/1001 exact_equal、0 ppm，未出现2997/50舍入）、一次官方评分 complete/reward=0（合法）、容器清理回验。** E02-EXPANSION-01/02失败及独立恢复原样保留，不因新运行改写。不复用旧render |
| R03 | OpenStoryline E03 | 历史render后独立closeout保留；R03-01失败观察；R03-02完整正常流程 | **已完成（2026-11-01）：OPENSTORYLINE-E03-FULL-FLOW-R03-02 完整正常流程成功——批准单任务逻辑预算100下，输入/overlay门禁真实通过（实际挂载E03、27项overlay）、原生内容删除链load_media→split_shots→local_asr→speech_rough_cut（41/41调用与解析成功后推进，不代表删除目标完整落实）→plan_timeline_pro→render_video、Agent rc=0（950.95s<1800s）、完成判定写入、宿主导出output.mp4/cuts.json（从final render消费的timeline派生，删除区间[29190,30810]）、技术检查通过（帧率源/输出精确24000/1001 exact_equal、0 ppm）、一次官方评分complete/reward=0（合法，end_offset 3.518s未命中golden）、容器清理回验。预算100/1M/32768贯穿配置/冻结/request/容器/ledger，实际用52/100。R03-01失败观察与预算防线收尾（FINAL-CLOSEOUT-01）原样保留。** 完整流程目标达成，R03标完成。[R03-02成功](../reports/analysis/OPENSTORYLINE-E03-FULL-FLOW-R03-02/success-summary.md) [R03-01失败](../reports/analysis/OPENSTORYLINE-E03-FULL-FLOW-R03-01/failure-observation-summary.md) [预算核定](../reports/analysis/OPENSTORYLINE-E03-REQUEST-BUDGET-READINESS-01/summary.md) [防线与整链收尾](../reports/analysis/OPENSTORYLINE-E03-BUDGET-READINESS-FINAL-CLOSEOUT-01/summary.md) |
| R04 | OpenStoryline ASSEMBLY-TASK1 | EXECUTION-04选片/group/plan/render成功；原completion误用interview节点，独立恢复solution | **已完成（2026-11-01）：OPENSTORYLINE-ASSEMBLY-FULL-FLOW-R04-01 完整正常流程成功——12素材门禁/27项overlay真实通过、原生链understand(12)→filter(K=4不同clip)→group(slot顺序10→4→5→3)→plan→render、Agent rc=0（475.00s<1800s）、assembly完成判定正常（task-kind-aware，不再误用interview）、宿主导出solution.mp4/solution.json（与render逐字节一致，SHA `4e1bc351…`，4段连续half-open）、技术验收结构10项全PASS、容器清理；官方not_integrated/reward=null/semantic not_evaluated；EXECUTION-02/03/04原样保留。发送前修复：assembly-offline-gate.json资产SHA过期刷新（留快照）。** 完整流程目标达成，R04标完成。[R04-01成功](../reports/analysis/OPENSTORYLINE-ASSEMBLY-FULL-FLOW-R04-01/success-summary.md) |
| R05 | ViMax G01 | 规划与媒体分别保留，媒体复用规划后已生成40s成片；不是任务失败 | **已完成（2026-11-01）：第一阶段（规划）VIMAX-G01-FULL-FLOW-R05-PLANNING-01 新规划通过（8镜头/1角色/8相机/7过渡、plan_verifier 14/14、0媒体、13逻辑请求37,873 tokens、attempt 77.99s）；媒体预算按真实生产分支修正（image_creates 19、video_creates 15、下载34、video_polls 1380）；MEDIA-01（首次正式媒体attempt）媒体生成与原生拼接成功但宿主 COMPLETE v3 最终路径所有权校验失败（final_artifact_missing rc=1，失败观察原样保留）；MEDIA-02（修复后正式媒体attempt）绑定 VIMAX-MEDIA-FINAL-PATH-REPAIR-01 host_runner 走通完整正常流程——19图/15视频/34下载、final 40.000s H.264 1280×720 30fps 无音轨 SHA `639e778b68eb101d…`、远端15/15 SUCCEEDED audio=false、COMPLETE v3 全维度 True（final_path_resolution 证明原生相对路径真实映射到本次 workspace）、宿主 native_agent_done rc=0、清理回验、测量质量 complete。**R05 标完整流程完成。**[R05-MEDIA-02成功](../reports/analysis/VIMAX-G01-FULL-FLOW-R05-MEDIA-02/final-report.md) [R05-MEDIA-01失败](../reports/analysis/VIMAX-G01-FULL-FLOW-R05-MEDIA-01/final-report.md) [路径修复](../reports/analysis/VIMAX-MEDIA-FINAL-PATH-REPAIR-01/summary.md) [R05规划](../reports/analysis/VIMAX-G01-FULL-FLOW-R05-PLANNING-01/summary.md) |
| R06 | ViMax G02 | 新规划已通过；媒体经托管器完整正常流程成功（R06已完成） | **已完成（2026-11-01）：规划 VIMAX-G02-FULL-FLOW-R06-PLANNING-01 新规划通过——10镜头/2角色/10相机/9过渡、plan_verifier 16/16 checks、0媒体、15逻辑请求（43,675 tokens）、attempt 95.92s、测量质量complete。媒体 VIMAX-G02-FULL-FLOW-R06-MEDIA-02 经 `scripts/vimax_managed_launch.py`（托管supervisor独立session/PGID、persistence proof绑定、越过120s采样持续）启动唯一正式attempt——12图（6肖像+6候选）/19视频（10主体+9过渡）/31正常下载/原生concat/final 50.000s H.264 720p30fps 无音轨 SHA `a85c603d…`/完整解码；COMPLETE v3全维度True（final_path_resolution owned/exists/accepted、required_work在deadline内）；宿主 termination=native_agent_done、容器退出0、清理回验、资源边界齐全（5229样本/190.93 core-s/netns 1309行）；supervisor runner_exited rc=0；远端closeout 19/19 SUCCEEDED audio=false复下载独立记账。**R06 标完整完成。** R06-MEDIA-01（宿主中断失败观察）原样保留。 |
| R07 | ViMax G03 | 9镜头规划产物有效，旧验收器错误经离线复验；媒体已生成45s成片 | **已完成（2026-11-02）：第一阶段（规划）VIMAX-G03-FULL-FLOW-R07-PLANNING-01 新规划通过——9镜头/2角色/9相机/8过渡、生产plan_verifier ok（16项checks中15项True＋1项语义非机器证明）、0媒体请求、14逻辑请求（40,666 tokens）、attempt 87.42s、测量质量complete；经规划阶段持久托管启动器执行。第二阶段（媒体）VIMAX-G03-FULL-FLOW-R07-MEDIA-01 经 `scripts/vimax_managed_launch.py`（stage=media）完整正常流程成功——8图（6肖像+2候选）/17视频（9主体+8过渡）/25正常下载/原生concat（仅主体shots/0..8）/final 45.000s H.264/1280×720/30/1fps/无音轨 SHA `d4150200f5dc1b7b…`/完整解码；COMPLETE v3全维度True（final_path_resolution owned/exists/accepted、required_work在deadline内）；宿主 native_agent_done rc=0、容器退出0、清理回验、测量complete；supervisor runner_exited rc=0；远端closeout 17/17 SUCCEEDED audio=false复下载独立记账。**R07 标完整正常流程完成。** |
| R08 | ViMax MUSICIANS-AUDIO | 新规划成功，11图/25视频成功；原concat失败，独立恢复65s AAC成片 | **已完成（2026-11-02）：第一阶段（规划）VIMAX-MUSICIANS-AUDIO-FULL-FLOW-R08-PLANNING-01 新规划通过——13镜头/3角色/13相机/12过渡、生产plan_verifier ok、0媒体/音频、18逻辑请求（54,941 tokens）、attempt 102.36s、测量complete。第二阶段（媒体）VIMAX-MUSICIANS-AUDIO-FULL-FLOW-R08-MEDIA-01 有声attempt已执行但final音轨为MP3（libmp3lame）而非AAC，`expected.audio=aac`未满足（技术缺口，失败观察保留）。**第三阶段（媒体修复链）VIMAX-MUSICIANS-AUDIO-FULL-FLOW-R08-MEDIA-02 经 `scripts/vimax_managed_launch.py`（stage=media）在修复版生产链上完整正常有声流程成功——13图（9肖像+4候选）/25视频（13主体+12过渡，audio=true/AAC）/38正常下载/原生AAC拼接（仅主体shots/0..12）/final 65.10s（video_stream，主判定65±0.5 PASS）H.264/1280×720/30/1fps/AAC SHA `ce54ee583a85586e…`；正式技术验收applied+ok（12项checks全True、契约digest `b15d5f66…`）；COMPLETE v3全维度True、宿主 native_agent_done rc=0、容器退出0、清理回验；supervisor runner_exited rc=0；远端closeout 25/25 SUCCEEDED（usage.audio=true）。**R08 标完整正常流程完成。** R08-MEDIA-01 MP3失败观察原样保留。** |
| R09 | video-use E03 | 历史报告记载完整执行，但当前索引raw为空，未找到完整rollout副本 | **已完成（2026-11-02）：VIDEO-USE-E03-FULL-FLOW-R09-01 完整正常流程成功——E03输入/指令门禁通过、官方ASR一次真实提交（611词）、Agent自主定位并删除phone-case stand-up claim段（EDL删除[29.17,34.43]s，rc=0，177.83s<1800s）、原生render、宿主导出output.mp4/cuts.json、技术检查全通过、一次官方评分complete/reward=0（合法，cut命中golden但ssim 0.7244<0.8）、原生rollout完整（28/28配对无右删失）、资源/时间/清理完整、manifest绑定最终run-record字节、独立raw副本24/24比对一致。** 历史E03 raw缺失、历史失败/报告及PILOT-01两项UNKNOWN保护状态原样保留。[R09-01成功](../reports/analysis/VIDEO-USE-E03-FULL-FLOW-R09-01/summary.md) |

对应旧运行和限制以机器索引每行及原报告为准：

- R01：[E01恢复证据](../env/video/openstoryline/OPENSTORYLINE-E01-RUNTIME-CONFIRM-02/recovery-01/recovery-report.json)。
- R02：[E02恢复证据](../reports/analysis/OPENSTORYLINE-E02-EXPANSION-02/recovery-FPS-01/summary.md)。
- R03：[E03当前修订](../reports/analysis/OPENSTORYLINE-E03-RUNTIME-CONFIRM-03/revision-DOCUMENTATION-CLOSEOUT-01/summary.md)。
- R04：[assembly恢复证据](../reports/analysis/OPENSTORYLINE-ASSEMBLY-TASK1-EXECUTION-04/recovery-COMPLETION-01/recover-report.json)。
- R05：[G01媒体分析](../reports/analysis/VIDEO-THREE-REPO-RUNTIME-CONFIRM-02/vimax-g01-media/summary.md)。
- R06：[G02验收修订](../reports/analysis/VIMAX-G02-EXPANSION-01/revision-ACCEPTANCE-01/summary.md)、[R06新规划（规划通过，媒体待批准）](../reports/analysis/VIMAX-G02-FULL-FLOW-R06-PLANNING-01/summary.md)。
- R07：[G03规划/媒体证据](../reports/analysis/VIDEO-G03-TWO-REPO-EXPANSION-01/summary.md)。
- R08：[musicians原媒体运行](../reports/analysis/VIMAX-MUSICIANS-AUDIO-MEDIA-EXECUTION-02/summary.md)、[独立拼接恢复](../reports/analysis/VIMAX-MUSICIANS-AUDIO-CONCAT-RECOVERY-01/summary.md)。
- R09：[E03原分析](../reports/analysis/VIDEO-E03-TWO-REPO-EXECUTION-01/video-use-e03/summary.md)、[原输入/rollout哈希登记](../reports/analysis/VIDEO-E03-TWO-REPO-EXECUTION-01/video-use-e03/manifest.json)。原报告保留，不能冒充新run的trace。

## 新目标的验收定义

1. **完整跑通不等于语义满分。** 产物按冻结技术契约验收；采访既有评分器应完整运行，reward=0合法。assembly/生成任务官方裁判未集成时继续not_integrated/not_run、reward=null，不额外接裁判凑“成功”。语义未评估明确保留。
2. **不靠事后独立恢复补成连续成功。** 正常宿主导出/closeout属于本次声明执行链，应正常完成；出错后离线修复或独立恢复不能顶替新目标。
3. **ViMax可以保留原生分阶段架构。** 新规划、验收、预算核定/批准、媒体是一个统一可追溯的新执行批次；每阶段可有独立run_id/容器/采样窗，但须以共同run-family、规划SHA和身份衔接。不能为了“一次完整”跳过阶段批准或伪称单容器连续运行；审批等待与非观测间隔单列。
4. **完整工具记录与资源窗口。** 命令/参数/cwd、输入输出、起止/clock、rc、异步session及调用关联齐全；工具错误也记录。资源在各实际执行阶段前就绪、运行中落盘，声明Agent、导出、拼接、验收/评分、清理等scope和覆盖。缺失/外部等待/无法采集的指标如实标记，不能报零或把协议耗时称独占CPU。
5. **真实执行，不能替换为宿主代做。** 不注入golden、旧cuts/选片答案或历史生成媒体；ViMax新目标从新规划开始。G01/G02/G03保留原已登记媒体范围，musicians保持有声；不默认把历史无声故事全部改成有声。
6. **逐项新授权。** 每组新配置、唯一输出、冻结身份和批准；规划/媒体预算与费用先核定。仅更换身份不代表同版本受控重复。串行、每次批准至多一个正式attempt，失败保存证据并停，不无限重试或边跑边改代码。

R01–R09为固定清单编号，不是批量执行命令。可先用R09确认完整trace持久化，再按R01→R04、R05→R08逐项申请执行；这是顺序建议，仍需每项预算与新批准。未来的新run与历史结果并存，历史失败、修订、独立恢复不删除、不改写。9组重跑不新增9个不同输入，也不能预先计为成功。

## R09：video-use E03的trace留存缺口

历史报告记载原生剪辑/导出/评分完成、25/25工具闭合，300点采样；但2026-10-31只读核查发现：

`data/raw/generated/VIDEO-USE-E03-C01/` 为空，机器索引中的run子目录不存在。当前找到的是身份/批准、执行日志、分析result/CSV/SVG与摘要，不能替代原生rollout。原因及是否另有完整副本未知，不能直接称已永久丢失。

已在可访问的项目、常见本地归档、临时目录及应用会话记录中查找，未找到完整原始副本；原manifest可供以后找到的副本校验。用户现已将其明确纳入9组重跑计划，不再只是候选，寻找旧副本不作为申请新运行的前置。新执行仍需另行授权；不从报告/CSV补造旧trace。若后续找回旧副本，只恢复历史证据，不擅自取消用户的新重跑目标。

R09结束前必须核验原生rollout、原始采样、输入/输出、命令/参数/cwd/起止/返回和manifest实际存在，保留独立副本；清理只针对明确的测试临时目录，不以宽泛匹配删除正式raw。

**R09 已于 2026-11-02 完成唯一正式完整流程 attempt（VIDEO-USE-E03-FULL-FLOW-R09-01）**：
原生rollout、原始采样、输入/输出、命令/参数/cwd/起止/返回和manifest实际存在并经读回核验；
独立raw副本建立（24/24逐字节SHA/bytes比对一致）。历史E03 raw缺失、历史失败/报告及
PILOT-01两项UNKNOWN保护状态全部保留，未覆盖、未用git HEAD恢复。清理仅针对本次明确对象。

## 当前动作

**R09 完整正常流程成功（2026-11-02）：VIDEO-USE-E03-FULL-FLOW-R09-01 ——E03输入/指令门禁通过、官方ASR一次真实提交（611词/6.4s）、Agent自主定位并删除phone-case stand-up claim段（EDL删除[29.17,34.43]s，rc=0、177.83s<1800s）、原生render、宿主导出output.mp4/cuts.json（cut [29170,34430]ms）、技术检查全通过（源/输出854×480/24000-1001 exact、完整解码pass）、一次官方评分complete/reward=0（合法：cut命中golden start/end offset 0.027/0.102s 在容差内，但ssim 0.7244<0.8→content lie suspected）、原生rollout 28/28配对无右删失、资源/时间完整（302样本/184.68s窗/CPU 60.82 core-s）、清理回验removed、manifest绑定最终run-record字节（SHA实算一致）、独立raw副本24/24一致。**R09 标完整正常流程完成；历史E03 raw缺失、历史失败/报告、PILOT-01两项UNKNOWN保护状态原样保留；R01–R09全部完成。**25正常下载/原生concat（仅主体shots/0..8）/final 45.000s H.264/1280×720/30/1fps/无音轨 SHA `d4150200f5dc1b7b…`/完整解码；COMPLETE v3全维度True、宿主 native_agent_done rc=0、容器退出0、清理回验、测量complete；supervisor runner_exited rc=0；远端closeout 17/17 SUCCEEDED audio=false。R07 标完整正常流程完成；R08/R09 不启动。** R01 已按新授权完成完整正常流程（OPENSTORYLINE-E01-FULL-FLOW-R01-02，2026-10-31）：Agent rc=0、原生链到render成功、完成判定写入、宿主导出output.mp4/cuts.json、技术检查通过、一次官方评分 complete/reward=0（合法）、容器清理回验；R01-01（1800s截止、无提交物）失败观察原样保留。**R02 已按新授权完成完整正常流程（OPENSTORYLINE-E02-FULL-FLOW-R02-01，2026-11-01）：Agent rc=0（479.66s）、原生链到render、宿主导出output.mp4/cuts.json、技术检查通过（帧率精确60000/1001）、一次官方评分 complete/reward=0（合法）、容器清理回验；E02-EXPANSION-01/02失败及独立恢复原样保留。** **R03 已完成完整正常流程（2026-11-01）：OPENSTORYLINE-E03-FULL-FLOW-R03-02 在批准单任务逻辑预算100下，Agent rc=0（950.95s）、原生内容删除链到render、宿主导出output.mp4/cuts.json（删除[29190,30810]）、技术检查通过（帧率精确24000/1001）、一次官方评分complete/reward=0（合法）、容器清理回验；R03-01（预算60耗尽、无提交物）失败观察原样保留。** **R04 已完成完整正常流程（2026-11-01）：OPENSTORYLINE-ASSEMBLY-FULL-FLOW-R04-01 原生装配链understand(12)→filter(K=4)→group(slot)→plan→render、Agent rc=0（475.00s）、assembly完成判定正常、宿主导出solution.mp4/solution.json（逐字节一致、技术验收10/10 PASS）、官方not_integrated/reward=null；EXECUTION-02/03/04历史原样保留。** **R05 第一阶段（规划）已完成（2026-11-01）：VIMAX-G01-FULL-FLOW-R05-PLANNING-01 新规划通过（8镜头/1角色/8相机/7过渡、plan_verifier 14/14、0媒体、13逻辑请求37,873 tokens、attempt 77.99s）；媒体预算按真实生产分支修正（image_creates 19、video_creates 15、下载34、video_polls 1380）。** **R05 已完成（2026-11-01）：VIMAX-G01-FULL-FLOW-R05-MEDIA-02 修复后正式媒体attempt走通完整正常流程——19图/15视频/34下载、final 40.000s H.264 1280×720 30fps 无音轨 SHA `639e778b68eb101d…`、远端15/15 SUCCEEDED audio=false、COMPLETE v3 全维度 True（final_path_resolution 证明原生相对路径真实映射到本次 workspace）、宿主 native_agent_done rc=0、清理回验、测量质量 complete；MEDIA-01（媒体生成/concat成功但宿主最终路径校验失败 rc=1）失败观察原样保留；绑定 VIMAX-MEDIA-FINAL-PATH-REPAIR-01 修复后 host_runner。R05 标完整流程完成。** **R06 第一阶段（规划）已完成（2026-11-01）：VIMAX-G02-FULL-FLOW-R06-PLANNING-01 新规划通过——10镜头/2角色/10相机/9过渡、plan_verifier 16/16 checks、0媒体、15逻辑请求（43,675 tokens）、attempt 95.92s、测量质量complete；媒体预算草案（image_creates 12、video_creates 19、下载31、closeout复下载19、自然轮询上界1748）已推导未授权；媒体阶段未启动。** **R06 已完成（2026-11-01）：VIMAX-G02-FULL-FLOW-R06-MEDIA-02 经 `scripts/vimax_managed_launch.py` 托管启动器走通完整正常流程——12图（6肖像+6候选）/19视频（10主体+9过渡）/31正常下载/native concat/final 50.000s H.264 1280×720 30fps 无音轨 SHA `a85c603d…`、远端closeout 19/19 SUCCEEDED audio=false、COMPLETE v3 全维度 True（final_path_resolution owned/exists/accepted）、宿主 native_agent_done rc=0、清理回验、资源边界齐全（5229样本/190.93 core-s/netns 1309行）、supervisor runner_exited rc=0；R06-MEDIA-01（宿主中断失败观察）原样保留。R06 标完整流程完成。** 其余 R09 仍未授权启动。CPU-02/Replay 与 execution_authorization 不变。
