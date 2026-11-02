# 视频剪辑排障与复现契约

更新：2026-10-31。当前结果见 [视频结果](video_results.md)，逐项路径见 [登记JSON](video_results_index.json)。本页保留修法；后半部历史轮次按当时版本阅读，不覆盖现行策略。

## 现状

video-use E01/E02/E03连续完成并完整评分、reward=0；OpenStoryline E01/E02/E03真实到render后经独立恢复导出及完整评分、reward=0。现另有video-use REPURPOSE真实执行及OpenStoryline ASSEMBLY-TASK1真实render＋独立恢复成果，四仓总体14组／8个输入。记录有效不等于官方任务通过；恢复不追溯改变原attempt失败，不为满分或单独验证自动收尾补跑。当前不再以E03 blocked作为门禁。
E02素材为854×480、60000/1001fps、约30.029317s，源时长不能当成片时长。

## video-use

| 问题 | 固定处理/下次检查 |
| --- | --- |
| bash -lc重置PATH，裸python落到系统解释器 | v6固定venv；实际工具shell检查解释器，不给系统Python重装依赖 |
| 只换task标签、ASR/报告/verifier仍用E01 | 使用统一task entry应用完整上下文；检查实际容器输入、说明、judge/golden和新输出 |
| 宿主评分缺skimage/解释器错误 | 使用登记的专用verifier venv＋显式解释器，完整性/进程RC/reward分列 |
| 默认1080p、调色淡化改变提交 | 使用保源规格overlay；不添加任务外效果；EDL/cuts/实际render输入一致 |
| 报告包装递归、冻结准备时间当起点 | 保存底层writer引用；正式调用前取新的monotonic起点；报告失败不阻止清理 |
| reward=0 | 检查评分完整性；词时间只是候选，波形/RMS/截图不证明听懂音频，不能用golden指导下轮答案 |

生产入口：`scripts/video_use_task_entry.py --task-config <新配置> --check|--freeze|--approve|--execute`，具体按实际CLI使用。
镜像 `video-use-task:arm64-codex-bailian-v6`；正式配置绑定完整ID。Scribe使用外部ElevenLabs，Codex使用百炼Responses；不混同本地ASR。

## OpenStoryline

| 问题 | 固定处理/下次检查 |
| --- | --- |
| FunASR 1.3.1英文词表/时间戳接线 | 保留paraformer-en薄适配：tokens.json、声学时间戳、VAD偏移一次、标点句子对齐；不伪造均匀时间 |
| MCP schema丢内部媒体和前序artifact | 原生拦截器/ClientContext＋服务端按本session恢复，统一ArtifactStore/history；缺前序明确失败 |
| 容器找不到模型缓存 | 只读挂载16个登记必需文件；实际路径预检，不自动联网下载 |
| 默认render无声音或改画布 | 显式保原声、源尺寸/帧率，无配乐字幕等任务外效果 |
| Agent展示计划后等待确认 | 同session沿用历史和deadline，仅在用户预授权范围内确认等价计划；否定/冲突拒绝 |
| 宿主改写容器所属结果文件PermissionError | 宿主写独立记录，容器agent-result/session-status只读；启动和execute返回及时落盘 |
| 多节点复用tool_call_id导致导出失败 | render选择使用session+node+artifact+call_id及事件顺序；对应同一timeline，合法路径，不能选最新mp4 |
| E02错挂E01：默认参数定义时绑定旧INPUT_DIR | input_dir必传，execute_once显式传任务输入；测试真实execute_once，不只测辅助函数 |
| spec正确不代表实际Docker挂载 | inspect_mounts只取实际Mounts/Id，检查Source/Destination/bind/RW=false，再验容器内bytes/SHA/规格；失败不启动Agent |
| 60000/1001与2997/50微小舍入被字符串拒绝 | 项目策略abs≤0.0001fps且rel≤2ppm；分别记录exact_equal和容差通过；坏帧率拒绝，不覆盖上游硬要求 |
| speech_rough_cut 丢任务要求只传“split at pauses” | 任务作用域`edit_policy.content_deletion`传入removal_target/keep_rest并注入内部提示；无策略保留默认，不用全局子串黑名单 |
| plan_timeline_pro 双模式/无数据静默空轨 | mode 冲突/无 groups/无 clips/空视频轨 fail-closed；空 timeline 不再 `isError=false` 当成功 |
| speech 模式自动加字幕 | 用`edit_policy.forbid_added_subtitles`显式控制，不用speech模式替代任务要求；无策略保留默认 |
| 语义删除时额外裁掉停顿/首尾，或恢复被删首尾句 | 明确删除区间合并后对源区间求补集；非目标内容不额外清洗，E01/E02原路径保持 |
| MoviePy将23.976…格式化为23.98 | `build_write_ffmpeg_params`追加精确有理数输出-r；非法fps在writer前失败；合成编码和E03真实输出24000/1001均已验证，不放宽容差 |
| 外层超时杀宿主、采样只存内存 | 使用已修复`--launch-detached`及`--launch-status`；资源运行中JSONL追加落盘，目标间隔与实测时间戳分列 |
| 宿主导出`PurePosixPath`缺失导入 | 导入已修；RUNTIME-CONFIRM-03原宿主失败保留，独立closeout同一render/timeline导出及一次评分单列；新运行须冻结修复后入口 |
| assembly筛选仍保留80%、group套通用叙事 | storyboard专用模板按配置K选片并按slot组织；非assembly默认策略保持。EXECUTION-04已真实验证选K、group、plan、render，结构正确不等于语义正确 |
| assembly render成功但完成判定要求ASR/粗剪 | `required_steps_for_task_kind()`统一完成/确认节点集合，入口`persist_completion_check()`按类型写render身份；修复后自动收尾仅离线验证，未来任务再验证，不要求专门重跑task1 |
| assembly source范围10ms与成片帧时间量化混用 | 源完整性/连续性仍10ms；成片策略`openstoryline-assembly-final-media-frame-quantization-v1`为`1/fps+0.002`。EXECUTION-04旧策略FAIL、新策略PASS分列，不改历史判定、不冒充官方评分 |
| assembly原状态缺render身份，需要独立恢复 | 仅在新命名空间通过唯一成功render事件及session/node/artifact/call_id、timeline/group、路径/SHA证明来源；不补写原状态、不找任意最新mp4。同字节复制与同timeline派生solution；已完成recovery-COMPLETION-01，无需重渲染 |

生产入口：
`env/video/openstoryline/edit-pilot-02/runtime/openstoryline_pilot_entry.py --task-config <新配置> --check-task-config|--launch-detached|--launch-status`；`--execute`为受管理宿主子进程执行路径，不再用外层长等待代替后台监控。
冻结使用现行freeze_identity/批准机制，不猜不存在的CLI；旧preflight若固定历史目录不得直接覆盖。

镜像 `openstoryline-task:arm64-native-confirm-flow-03`，完整ID以当前正式配置登记为准。LLM/VLM使用百炼Chat Completions，本地ASR不需要ElevenLabs。共享runtime新增的inspect_mounts只读Docker字段，不留存Config.Env。

## 回归与收尾

用真实生产入口，只fake外部Docker/供应商/凭据/Agent进程边界；不得替换掉要验证的控制分支。输入错配时应证明Agent入口0次。现行测试包括：
`test_openstoryline_input_gate_execute_once.py`、`test_openstoryline_render_selection.py`、`test_openstoryline_fps_recovery.py`。

先取最终边界、停采样、存日志产物再删除并核验容器。无提交不评分，完整reward=0不是基础设施失败。独立恢复用新目录，视频字节保持，cuts从同一render的timeline导出，不重选段、不修改原raw。

<a id="video-use-optional-coverage-backlog"></a>

## 后续可选覆盖

批量转写、动画、字幕、多素材调色/音乐/下载保持可选，仅在任务要求时覆盖；不为覆盖率强行调用。E03已真实验证工具表达和执行路径，官方语义边界仍可能不命中；不以此无限追分。实际CPU回放另行批准。

## 历史轮次（以下为各轮当时版本，不是当前待执行清单）

## 2026-10-29：VideoWeaver/ViMax G03 一批两仓执行（VIDEO-G03-TWO-REPO-EXPANSION-01）

VideoWeaver G03（athletes_gym_training_duo，9 镜头→45s）真实执行成功：entry_rc=0、技术验收 passed
（image 9/9、video 9/9、downloads 18/18、final 45s/1280x720/30fps/H264/无音轨）；CPU 侧工具轨迹完整
（exec_command 49、write_stdin 7、merge 1、ffprobe 1）。run_id `20261029T065904Z-videoweaver-g03-c01`。
ViMax G03 规划单次 attempt（run_id `vimax-g03-expansion-planning-20261029T072745Z-b1a631cb`）：Agent 产出
有效 9 镜头规划（storyboard 0..8、9 camera、8 过渡、2 角色），但登记 `plan_verifier.py`（从 G02 复制后
未充分适配）仍按 10 镜头校验（storyboard indices 0..9）→ 规划门失败；按“每阶段正式 attempt 至多一次”
不补跑，媒体阶段未授权。已修正 9 镜头 verifier 供未来另行授权规划 attempt 使用（需新 run_id/身份/批准）。
报告 `reports/analysis/VIDEO-G03-TWO-REPO-EXPANSION-01/`。

## 2026-10-29：E03 两仓能力核对与离线准备（VIDEO-E03-TWO-REPO-READINESS-01）

- E03（exp-content-cut-mkbhd）为**单段、内容级（语义陈述）删除**：移除“手机壳能立起”陈述段，保留其余；
  素材 90.006583s/854×480/24000-1001fps/AAC16k mono（SHA `c66f380a…`）。golden 数值未泄漏进 instruction
  （instruction 中 12000/38500 为格式示例，非 golden）。
- **video-use**：现有生产入口（`video_use_task_entry.py`）`build_context` 对 E03 字段/哈希/泄漏检查全过
  （仅 capability_blocked 拒绝）；Codex Agent（exec_command＋view_image）＋ElevenLabs 转写可表达内容级删除。
- **OpenStoryline**：`speech_rough_cut` 的 `user_request` 可承载内容级删除要求；`plan_timeline_pro` 消费
  保留片段、render 导出、`export_cuts_from_final_timeline` 从 timeline 派生 cuts；合成删除区间沿真实
  timeline→cuts 接口传播（测试通过）；实际挂载错配在 Agent 边界前拒绝。
- 判定：两仓均 **existing_tools_expressible＋wiring_ready**，可将旧 capability-blocked 更正为
  “可申请一次真实验证”（≠真实成功，≠批准）。7 项定向测试通过；报告
  `reports/analysis/VIDEO-E03-TWO-REPO-READINESS-01/`（manifest 13 项回读 0 错）。未创建批准/attempt，
  未调用付费服务。

## 2026-10-29：E03 两仓各一次真实执行（VIDEO-E03-TWO-REPO-EXECUTION-01）

- **video-use E03**（run_id `20261029T110903Z-video-use-e03-c01`）：E03 素材真实消费（SHA `c66f380a…`）；
  Agent 自主切除手机壳立起陈述段 [29120,34480]ms；导出 output.mp4/cuts.json；官方 verifier complete、
  **range 门 1/1 通过**、honesty SSIM 0.7485<0.8 → **reward=0**（audio xcorr 0.9974、duration 通过）。
  技术检查通过、评分完整；reward=0 为合法结果。
- **OpenStoryline E03**（run_id `20261029T111519Z-openstoryline-e03-expansion-01`）：输入门禁 passed
  （实际 Source=E03、容器内 11,604,798/`c66f380a…`、90.006583s/24000-1001）；链推进到 render_video（3 次
  render 尝试）后 Agent 因 LangGraph `GraphRecursionError`（recursion limit 32）终止，**无提交物** → verifier
  `not_run_no_submission`、reward=null。59 逻辑请求/494,167 tokens（<1M）。**单次 attempt 不补跑**；失败原因
  记录为本次真实观察（E03 内容级任务递归步数超限），不作为成功。容器删除回验。
- 报告 `reports/analysis/VIDEO-E03-TWO-REPO-EXECUTION-01/`（manifest 22 项递归回读 0 错）。

## 2026-10-29：OpenStoryline E03 工作流修复＋离线验证（OPENSTORYLINE-E03-WORKFLOW-REPAIR-01）

**只修确定性缺陷并离线验收，不重跑、不渲染、不评分；真实语义选段与端到端仍待新授权。**

- 根因（真实失败轨迹）：`speech_rough_cut.user_request` 只传通用“split at natural speech pauses”回退、
  丢失删除目标；`plan_timeline_pro` 双模式/无 groups/无 clips 静默空视频轨且 `isError=false`；空 timeline
  反复送入 render 耗尽步数；speech 模式自动加 45 条字幕。`GraphRecursionError`（limit 32）只是终止机制。
- 修复（fail-closed，不改变用户 instruction / E01-E02 语义）：
  - `OPENSTORYLINE-ENV-01/…/speech_rough_cut.py`：空/通用 `user_request` → `ValueError`。
  - `OPENSTORYLINE-ENV-01/…/plan_timeline_pro.py`：模式冲突、无 `generate_ai_transition.groups`、无
    `group_clips.groups`、无 `speech_rough_cut.clips`、空视频轨，均 fail-closed；speech 模式抑制字幕。
  - `edit-pilot-02/runtime/openstoryline_pilot_entry.py`：`build_container_spec` 新增 2 条只读源码覆盖挂载
    （镜像仍固化旧版，覆盖挂载在 import 时生效，无需重建镜像）；`request["instruction"]` 追加 task-scoped
    原生工作流引导（`split_shots(mode="skip")`、真实删除要求进 `user_request`、`is_speech_rough_cut=true` +
    `is_ai_transition=false`、保原声/规格、不新增字幕配乐配音转场）。
- 离线验证（镜像内 network=none、覆盖挂载修复模块、无凭据/模型/ASR/渲染，调用真实生产函数）：4 组测试通过。
- 事实更正（独立修订，不覆盖原报告）：调用闭合（原生 Agent 工具 16/16、MCP 节点 18/18、模型请求 59/59
  均有结束记录，`GraphRecursionError` 不构成右删失）；attempt wall 1770.55s / Agent wall 1768.77s，CPU
  765.68 core-s 是累计、非墙钟/采样时长。
- 修订目录 `env/video/openstoryline/OPENSTORYLINE-E03-WORKFLOW-REPAIR-01/`。未创建身份/批准/attempt，
  未构建镜像，未提交推送。

## 2026-10-29：OpenStoryline E03 4 处收尾（OPENSTORYLINE-E03-REPAIR-FINAL-WIRING-01）

**只补齐 WORKFLOW-REPAIR-01 的 4 处缺口，不重跑、不渲染、不评分。**

- 覆盖文件与身份同源：`_SOURCE_OVERLAYS`/`overlay_sources()`（plan_timeline_pro、speech_rough_cut、
  task_policy 三文件）同时驱动 `build_container_spec` 挂载与 `freeze_identity` 绑定；新增
  `frozen_overlay_mismatches()`（执行前重散列）与 `verify_overlay_sources()`（docker inspect 证明
  bind+readonly、容器内 SHA=冻结），不符在 Agent 边界前拒绝。
- 粗剪门禁去黑名单：任务约束来自 `edit_policy.content_deletion`（removal_target+keep_rest），经
  `OPENSTORYLINE_TASK_POLICY` env 进容器节点；启用时空请求/缺 removal_target 失败，否则把权威删除目标
  注入逐句提示；辅助“split at pauses”措辞不再误拒；“clean up the video”不再冒充完整要求。
- 字幕策略任务化：`forbid_added_subtitles` 显式控制字幕，不再用 `is_speech_rough_cut` 代替；无策略保留
  默认（含 speech 路径照常出字幕）。
- 工作流表述纠正：上一轮只是 instruction 追加工作流**引导**，非强制 skill 调用；代码措辞改为
  “guidance only, not an enforced skill call”。
- 新 manifest 采用仓库根相对路径，可从任意 cwd 独立回读。修订目录
  `env/video/openstoryline/OPENSTORYLINE-E03-REPAIR-FINAL-WIRING-01/`。

## 2026-10-29：OpenStoryline E03 真实运行——render_video 帧率不保真（新缺陷）

- E03 RUNTIME-CONFIRM-02 一次真实运行：Agent 完整走通原生链并成功渲染（6-clip 非空 timeline、
  0 字幕、内容删除要求注入），但 `export_rendered_video` 因帧率拒绝。
- 现象：源 `24000/1001`（23.976）vs 渲染 `1199/50`（23.98），相对偏差 165.83 ppm，超过注册的
  有界帧率容差 2 ppm（该容差只容忍有理数字符串舍入，如 2997/50 vs 60000/1001≈1ppm）。
- 归因：render_video 节点 ffmpeg 合成时间基落到 1199/50，尽管 Agent 传入的
  `load_media.metadata.fps` 与 plan_timeline 各 clip `fps` 均为 23.976023976023978 → 节点未按源
  帧率写时间基。
- 处理：按 policy 不临时放宽门禁、不重渲染；如实记录为导出失败（无有效提交物、reward=null）。
  帧率保真缺陷属后续另行授权的修复范围。

## 2026-10-29：OpenStoryline E03 三问题离线修复（OBSERVATION-FPS-SEMANTICS-REPAIR-01）

- **帧率根因**：MoviePy `ffmpeg_writer.py` 的 `"-r" "%.02f" % fps` 把 23.976023976023978 截成
  "23.98"（1199/50）。修复 `render_video.py`：`exact_fps_for_ffmpeg()` 经
  `Fraction(...).limit_denominator` 复原并追加 `-r 24000/1001`；`render_video.py` 加入 overlay 登记。
- **额外删除根因**：`speech_rough_cut` 默认清洗（`group_sentences(400)` 停顿裁剪 + 首尾裁剪 +
  口吃清洗）导致 E03 除 Agent 指定句外多删约 5.92s。修复：`content_deletion` 启用时走
  `content_deletion_ranges()`（保留停顿/首尾，只删显式删除句）+ task-scoped prompt 覆盖；E01/E02 不变。
- **资源样本丢失**：`Sampler` 只存内存、`finalize` 才落盘，宿主被外层超时杀掉即 0 样本。修复：in-run
  JSONL 追加落盘（`sink_path`/`flush_every`，flush/close fsync）+ 托管分离启动 `launch_detached()`。

## 2026-10-29：OpenStoryline E03 三处确定性修复（THREE-POINT-CORRECTNESS-FINAL-01）

- **删除区间求补集**：`content_deletion_ranges` 改为删除集合→合并→对源区间求补集（不再多删边界停顿、
  不再恢复被删首/尾句）；越界/倒序拒绝。
- **CLI 排他启动**：`launch_detached` 用 O_EXCL 在 Popen 前预留 record+log（并发至多一个子进程），
  失败有界回滚；`--launch-status` 走 `require_empty_output=False` 只读查询已存在输出。
- **非法 fps 传播**：`build_write_ffmpeg_params` 在 writer 前抛错（不再 fail-open）；输入侧仍 MoviePy
  `%.02f`=23.98、输出侧追加 `-r 24000/1001`。

## 2026-10-29：OpenStoryline 帧率合成验收（FPS-SYNTHETIC-ACCEPTANCE-01，实测通过）

- 禁网+现有镜像+合成媒体（128×96、二进制帧编号）实测：追加输出 `-r` 后四种帧率（24000/1001、60000/1001、
  25/1、30/1）帧率/帧数/时长/PTS 全部精确，无丢帧/重复/漂移；基线（无 `-r`）在 24000/1001 出现
  -165.81 ppm 累计漂移。帧率修复已具备进入真实 E03 验证的条件；音画同步与真实素材留待真实运行。

## 2026-10-30：OpenStoryline E03 真实运行（RUNTIME-CONFIRM-03，reward=0）

- **执行保真实测生效**：1602行=1600周期点＋2边界，目标0.5s、周期点实测中位0.601382s；CPU809.91 core-s。
  实际剪切与Agent选择一致、无额外默认清洗，但语义结束边界未命中；帧率exact 24000/1001。
- **宿主导出回归缺陷**：`NameError: PurePosixPath`（`from pathlib import PurePosixPath` 导入缺失，`resolve_
  selected_render_media` 使用但未导入）。本轮已修复导入；后续身份绑定宿主入口时确认导入完整。
- 原宿主导出失败，修复导入后独立closeout完成同一产物的导出及一次官方评分complete、reward=0；结束边界未命中。
  这仍是有效研究记录，不是原attempt连续成功。完整口径见[当前修订](../reports/analysis/OPENSTORYLINE-E03-RUNTIME-CONFIRM-03/revision-DOCUMENTATION-CLOSEOUT-01/summary.md)。
