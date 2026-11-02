# 当前任务与下一步

当前简明状态见[四仓视频现状总览](video_status_overview.md)：R01–R09完整流程重跑已完成，回放尚待适配，清理暂不执行。本次只发布文档与小型状态检查点；raw、媒体及生产代码未提交改动仍保留本机，远程检查点不等于完整执行环境备份。

## 全仓库清理清点（2026-11-02，UTC；仅清单，零删除）

用户明确选择“先出完整清单，暂不删除任何文件”。[清点报告](../reports/analysis/REPOSITORY-CLEANUP-INVENTORY-20261102-01/summary.md) 按时间点扫描 202,529 个文件/链接、68,468 个目录，唯一 inode 文件分配空间约 23.47GiB（不含目录 inode 块，不等同可释放量）；无扫描错误、不跟随符号链接、不跨设备。完整逐文件元数据与逐目录大小均已输出。43 个根缓存/源码字节码候选共约 1.68MiB；56 个疑似测试目录（35 个为空，59 文件约 451KiB）尚未证明可删除；18 个 raw 独立副本约 1.45GiB 必须保留，改变留存策略需另行批准。公开输入/trace、九组运行与失败观察、分段媒体/时间线、身份批准、模型、venv、上游源码、离线 build 包和恢复快照不自动清理。旧 2026-10-29 清理脚本保留名单过时，未运行。R01–R09 完成状态及 16组合/9输入计数不变，无新运行、无删除/移动、无提交推送。

## R09 归档收尾完成（2026-11-02，UTC）

新增[独立归档修订](../reports/analysis/VIDEO-USE-E03-FULL-FLOW-R09-01/revision-ARCHIVE-CLOSEOUT-01/summary.md)：明确旧报告 manifest 的条目实际相对原报告目录，保留旧文件不改；以仓库根相对路径的新清单绑定 65 项，覆盖 5 个 control 文件、3 个资源报告、正式 raw 与逐字节一致的独立副本。62 个既有归档文件的 bytes/SHA 修改前后相同，验证器可从任意 cwd 只读回验。R01–R09 完整流程完成状态不变；R09 官方评分完整但 reward=0（SSIM 未过），不称官方任务通过。本次已实测约 248 秒完成，但不保证未来时延。未补跑、未重评、未改生产代码或 execution_authorization；PILOT-01 两项历史保护 UNKNOWN 保留。

## 最新正式完整流程完成：VIDEO-USE-E03-FULL-FLOW-R09-01（2026-11-02，UTC）——R09标完整正常流程完成

R09 唯一正式 video-use E03 完整流程 attempt 经托管启动器正常收尾。未追加运行，未补跑/改片/重评；历史E03 raw缺失、历史失败/报告、PILOT-01两项UNKNOWN保护状态原样保留。

- **task/run**：`VIDEO-USE-E03-FULL-FLOW-R09-01` / `20261102T112320Z-video-use-e03-full-flow-r09-01`（UTC）；镜像 `sha256:1a48c7b0…`（arm64/linux codex 0.163.0）；冻结身份 `b1dd3f433339c8c441193644492754c9640cddcbbdfe195b5dd9b5162ed1bb31`（23绑定文件，含 managed launcher SHA `c01ac98e…` 与持久性证明）；APPROVAL 绑定身份完整SHA，`no_retry:true`。
- **门禁**：输入SHA `c66f380a…`/11604798B、指令SHA `bc36a568…` 实算一致；真实生成Agent提示含E03内容删除目标、无E01/E02/repurpose串入、无golden泄漏；持久性证明在持久宿主执行域实际 validate 通过；gate-only PASS；正式launch READY→supervisor 3020596（独立session/PGID）→runner 3020602→runner_exited rc=0。
- **流程**：ASR一次真实提交（611词/6.4s，缓存为本run产生）→ Agent自主定位并删除phone-case stand-up claim段（EDL删除[29.17,34.43]s；rc=0、177.83s<1800s；28/28工具配对）→ 原生render → 宿主导出 output.mp4/cuts.json（cut [29170,34430]ms，H.264/yuv420p/854×480/24000-1001/AAC，完整解码pass、源规格匹配）→ 技术检查全通过 → 一次官方评分 complete/reward=0（cut命中golden start/end offset 0.027/0.102s在容差内，但ssim 0.7244<0.8→content lie suspected）。
- **trace/测量/清理**：原生rollout JSONL（2,076,088B）28/28配对、session可归属、无右删失；302样本/184.68s窗/中位0.60s/CPU 60.82 core-s；thread_ended=True、sink closed/error null；容器removed回验；manifest绑定最终run-record字节（SHA实算一致）；独立raw副本24/24逐字节一致。
- **状态**：`final_state` overall ok/full_flow true/blockers []/host_exit_code 0（run-record/CLI/report-generation-status三方一致）。**R09标完整正常流程完成，R01–R09全部完成。** [报告](../reports/analysis/VIDEO-USE-E03-FULL-FLOW-R09-01/summary.md)

## 最新限定离线收口：VIDEO-USE-R09-FINAL-STATE-AND-TEST-ISOLATION-CLOSEOUT-01（2026-11-02，UTC）

独立复核确认的三处问题已限定离线收口，并补充/更正历史报告保护声明。本轮未调用真实模型/ASR/媒体/评分，未启动 R09，未创建正式身份/批准/attempt，未提交推送；**R09 仍保持未正式执行**，R01–R08 保持完成，覆盖计数不变。

- **A（Thread.join 误用）**：`Thread.join()` 正常结束与超时均返回 None，`sampler_thread_ended` 曾直接存 join 返回值（落盘 null、join 超时仍存活却判 complete）。修复：新增共享生产函数 `stop_sampler`（main 正常/异常两分支统一调用）——有界 join 后用 **`not sampler.is_alive()`** 记真实 bool，线程已结束才 close，close 完成后读最终 `sink_state()`（flush/fsync/close 错误进入质量），线程未结束不 close 且保守 partial；`_measurement_quality_state` 对 `is not True`（None/缺字段/False）一律 partial。
- **B（正常路径未落盘真实证据/跳过读回）**：`finalize_run` 重写为固定两轮 + 总是读回核验——正常 rc=0 也落盘真实证据状态（`evidence.report_status` 由 unknown 修正为 complete），磁盘与 CLI 完整 final_state 一致（含 evidence 维度），manifest 绑定最终 run-record，报告/状态失败进入证据，读回不一致保守证据失败；每轮诊断分离到 `report["save_protocol"]`（final_state 只含稳定判定字段，避免自引用随重写变化）；固定两轮+读回一次有界，退出优先级不变（程序+证据失败返回 1 且保留全部 blocker）。
- **C（测试重复 tearDown）**：移除 `TestSaveProtocol` 重复的 `tearDown`；所有被改模块全局（pilot01/shared runner、pilot04、RAW_ROOT/REPORT_ROOT、被替换函数）经 `_patch_module` 在修改前登记 `addCleanup` 精确恢复（setUp 部分失败/断言失败也恢复）；新增 `TestIsolation`（前后状态一致/人为失败仍恢复/顺序交换不泄漏/独立临时根/不写历史路径）与 `TestSamplerThreadSemantics`（真实 threading：正常结束/join 超时/close 错误/两分支统一收尾）；`TestProductionControlChain` 报告根重定向到 temp。
- **历史报告保护声明更正**：7 个历史报告文件逐文件核对——PILOT-04 三项与 PILOT-02 两项 **VERIFIED**（project_state evidence 行 / 90 个早于误改的 project-state 快照独立登记一致）；PILOT-01 两项 **UNKNOWN**（仅与 git HEAD 提交基线一致，无误改前独立参照，不伪称已证明）。本轮未再覆盖任何历史文件，测试运行后历史 7 文件零变化。
- **启动器/证明**：`video_use_managed_launch.py` 未改（SHA `c01ac98e…`），上轮 130s 持久性证明仍有效；未重做探针、未改旧证明内容。
- **测试**：`test_video_use_r09_four_gap_closeout.py` **52 PASS**；回归 gates/dispatch/final/e03/r09/managed_launch **146 PASS**，openstoryline+video-use wiring **97 PASS+9 subtests**，单独 pilot01/03/04/02/boundary **39 PASS**。组合运行 6 项失败为既有跨文件顺序依赖（pre-change 复测同样失败），按既有顺序运行全过；本轮隔离修复消除了本轮自身泄漏，未将新失败归为既有。
- **验证**：`check_project_state.py` PASS；`git diff --check` 0 错；本轮 manifest 报告目录相对路径、跨 cwd 回读 0 错。

结论不变：**限定离线修复与验收已完成；R09 真实运行仍需新配置、新冻结身份与批准；不保证模型语义或预算内完成。** 本轮停止，不自动启动 R09。[验收报告](../reports/analysis/VIDEO-USE-R09-FINAL-STATE-AND-TEST-ISOLATION-CLOSEOUT-01/summary.md)。

## 最新限定离线修复与验收：VIDEO-USE-R09-FOUR-GAP-FINAL-CLOSEOUT-01（2026-11-02，UTC）

独立复核发现的上轮四处遗漏已限定离线修复并验收；本轮未调用真实模型/ASR/媒体/评分，未启动 R09 正式 Agent，未创建正式身份/批准/attempt，未提交推送；**R09 仍保持未正式执行**，R01–R08 保持完成，计数不变。

- **A 技术汇总 fail-open**：`_technical_acceptance_state`（interview）要求必需项全显式合法成功才 PASS——files_present 严格 True、cuts.json parseable、输出 ffprobe pass、完整解码 pass、源规格匹配严格 True；缺字段/None/not_run/False/非法类型 → fail（逐项 reason），未运行（not_run / not_run_no_submission）与失败分开；无提交物仍由 submission 独立记退出码 2；reward=0 且评分完整合法；repurpose 沿用自身契约。
- **B 子步骤复用入口 remaining**：生产使用单一单调绝对 deadline `verifier_deadline = shared_deadline(verifier_budget)`（total 2700 / Agent 1800 / verifier 600 / cleanup 300 不变）；输出 ffprobe / 源 ffprobe / 解码 / 官方评分每步 `remaining = deadline - clock()`，`timeout=min(声明,remaining)`，耗尽零启动，不用 `max(1,remaining)`；实测前步耗 20s 后下一步 timeout 30→10。
- **C 证据保存失败未贯通**：`finalize_run` 有界两轮（每产物至多两次），run-record/manifest/报告实际结果进入 `evidence` 维度与退出码；run-record 写失败 exit 8 且不在磁盘留陈旧成功；manifest 失败后 run-record 保存失败事实；报告生成失败入 evidence；读回一致性核验保证 CLI/run-record/report-generation-status 一致或保守失败；固定退出优先级不变。
- **D 采样 sink 状态未进质量**：`main()` 记录 `sampler_sink_state`（路径/行数/未刷缓冲/错误）与 `sampler_thread_ended`；`_measurement_quality_state` 叠加为 partial；`recover_sampler_stream` 可验证恢复才回 complete 且保留原始故障事实；测量 partial 不改写 Agent rc/评分。
- **测试**：新增 `test_video_use_r09_four_gap_closeout.py` 41 PASS（技术严格性/共享截止含可注入时钟与子进程边界/保存协议故障注入读回真实文件/sink 质量/生产控制链/历史 E02 原生 rollout/启动器证明）；回归 gates/dispatch/task_entry_final/e03/r09/managed_launch 135 PASS，openstoryline+video-use wiring 97 PASS+9 subtests，单独 pilot01/03/04/02/boundary 39 PASS。组合运行 6 项失败为既有跨文件顺序依赖（pre-change 复测同样失败，非本轮引入）。
- **保留**：原生 trace 支持与 `video_use_managed_launch.py`（SHA `c01ac98e…`）及上轮 130s 持久性证明仍有效（未改启动器、未刷新旧证明）；重跑修复前误改的 7 个历史 `reports/resource/VIDEO-USE-EDIT-PILOT-0*` 报告文件已按 git HEAD 原字节恢复。上轮 manifest 路径声明以独立勘误说明（不改旧 manifest）。
- **验证**：`check_project_state.py` PASS；`git diff --check` 0 错；本轮 manifest 采用报告目录相对路径声明，跨 cwd 回读 0 错。

结论不变：**限定离线修复与验收已完成；R09 真实运行仍需新配置、新冻结身份与批准；不保证模型语义或预算内完成。** 本轮停止，不自动启动 R09。[验收报告](../reports/analysis/VIDEO-USE-R09-FOUR-GAP-FINAL-CLOSEOUT-01/summary.md)。

## 最新限定离线修复与验收：VIDEO-USE-R09-COMPLETION-TRACE-AND-LAUNCH-READINESS-01（2026-11-02，UTC）

video-use R09 正式运行前的限定离线修复与生产链验收已完成。未调用真实模型/ASR/图片/视频/付费评分；未启动 R09 正式 Agent；未创建正式 identity/APPROVAL/attempt；未提交推送；未改 execution_authorization；**R09 保持未正式执行**，R01–R08 保持完成，组合/输入计数不变。

- **工作A（结果模型与退出语义）**：单一生产函数 `assemble_final_result` 独立汇总 program/submission/technical_acceptance/official_evaluation/trace_integrity/measurement_quality/cleanup/evidence 八维度 + overall/full_flow + 宿主退出码（0-8，固定优先级）。CLI（`video_use_task_entry --mode execute`）、run-record `final_state`、报告与 report-generation-status 共用同一结果；不再无条件返回 0。Agent 非零/超时/异常不能因存在视频或评分完成而升级；技术失败不被评分 rc=0 掩盖；reward=0 且评分完整合法；无提交物记 `not_run_no_submission` 不伪造评分；原始失败/归档/清理错误分开保存。
- **工作B（原生 rollout 留存与完整性）**：消费 `export_native_rollouts` 返回码/异常/超时；`audit_native_rollouts` 区分 导出目录缺失/无 rollout 文件/空文件/损坏 JSONL/无法归属/未配对（按本版本 call_id 记 missing/orphan/duplicate）/右删失/complete；空目录或空文件不再称 complete；"零协议错误"不等于完整轨迹；派生索引不替代原生 JSONL；无可靠字段标 unknown。
- **工作C（技术检查与共享截止）**：保留 total 2700 / Agent 1800 / verifier 600 / cleanup reserve 300；ASR/Agent 剩余预算 ≤0 不再 `max(1,remaining)` 复活；`isolated_run_verifier` 与 `run_verifier`/`_ffprobe_submission` 在 remaining≤0 不启动新子进程并落盘 `not_run_budget_exhausted`；超时子进程有界回收、分阶段计时保留。
- **工作D（当前执行域持久启动）**：新增最小受限托管入口 `scripts/video_use_managed_launch.py`（仅派发 `video_use_task_entry.py --mode execute`，真实身份/批准门禁 + launcher/proof 绑定 + 同执行域 status；非任意命令执行器，不复用 vimax_managed_launch）。130s 离线探针在 boot `dd9aa657…`/pid[4026531836]/sshd.service/uid 1000 域验证：启动工具调用已返回、被测进程持续运行、样本持续增长（2596 行/130.0s）、自然结束 rc=0；异常子进程 rc=7 被 supervisor 准确报告。
- **E03 隔离**：输入 SHA `c66f380a…`、指令 SHA `bc36a568…` 实测一致；实际生成 E03 Agent 提示，内容删除目标存在、格式示例中性化为 `<integer>`、无 E01 hesitation-only/E02 filler-only/repurpose 目标或 golden 值串入。
- **测试**：新增 `test_video_use_r09_closeout.py`（41 项：13 类反例的 status/reason/退出码断言 + rollout audit + 共享截止 + 真实 dispatch 退出码 + E03 隔离 + ASR 一次提交 + repurpose 不回归）与 `test_video_use_managed_launch.py`（10 项）；回归 gates/dispatch/task_entry_final/e03_readiness 94 项、openstoryline 及 video-use wiring 112 项 + 9 subtests 全过。pre-change 快照与 SHA 留档；manifest 跨 cwd 回读 0 错；`check_project_state.py` PASS；`git diff --check` 0 错。

结论：**限定离线修复与验收已完成，R09 真实运行仍需新配置、新冻结身份与批准；不保证模型语义或预算内完成。** 本轮停止，不自动启动 R09。[验收报告](../reports/analysis/VIDEO-USE-R09-COMPLETION-TRACE-AND-LAUNCH-READINESS-01/summary.md)。

## 最新媒体阶段完成：VIMAX-MUSICIANS-AUDIO-FULL-FLOW-R08-MEDIA-02（2026-11-02，UTC）——修复链完整正常有声流程成功，R08标完整完成

R08 有声媒体 MEDIA-02 经托管启动器（stage=media）在修复版生产链上启动唯一正式 attempt（run_id `musicians-audio-full-flow-r08-media-02-20261102T070109Z-e37817d9`，supervisor 2684876 / runner 2684877）：**13逻辑图片（9肖像＋4候选，候选数固定2）→ 25视频（13主体＋12过渡，audio=true/AAC）→ 38正常下载 → 原生AAC拼接（仅主体shots/0..12，concat审计 `-acodec aac`）→ 65.10s（video_stream，主判定65±0.5 PASS）H.264/1280×720/30/1fps/AAC成片（SHA `ce54ee583a85586e…`）；正式技术验收applied+ok（12项checks全True、契约digest `b15d5f66…`与冻结一致）；COMPLETE v3全维度True、required_work在deadline内；宿主native_agent_done、容器退出0、清理核验；supervisor runner_exited rc=0；远端closeout 25/25 SUCCEEDED（usage.audio=true）；trace/资源/后处理计时齐全（3113样本/255.68 core-s/781 netns行、attempt 1560.71s/total 1576.92s含技术验收0.93s）。** 修复链真实生效：pipeline_fix_mount（`9a69b0ea…`）只读挂载+import解析验证、media_technical（`ca96d007…`）必需绑定、technical_contract冻结+门禁重算、技术验收共享close_deadline。**R08 标完整正常流程完成**（规划通过＋媒体完整正常有声流程）；R08-MEDIA-01 MP3技术失败观察原样保留；R09 不启动。[媒体报告](../reports/analysis/VIMAX-MUSICIANS-AUDIO-FULL-FLOW-R08-MEDIA-02/summary.md)。

## 最新离线闭合：VIMAX-AUDIO-CONTRACT-FOUR-GAP-FINAL-CLOSEOUT-01（2026-11-02，UTC）

在上一轮 AAC 部署/拼接/技术验收基础上集中闭合四个缺口。未调用真实模型/媒体/音频/评分；未正式媒体 attempt；未创建正式身份/批准；未改写 R08；未改其他三仓/模型/预算/资源限制；未提交推送；未改 execution_authorization。

- 反例（pre-change 快照复现，`repro/repro-gaps.json`）：A 缺省 audio+AAC 通过且 generation_audio=false；B media_technical 不在必需冻结绑定集；C 技术验收无共享绝对截止（每步整额 120/300/300）；D 显式 vp9 被归一化 h264、duration_basis/A-V 阈值不保留；E 缺容差归一化 0.0 却实际精确零执行。
- 修复：有效 generation_audio 总是与 expected 比较（缺省/false+AAC、true+none、缺对象/null 发送前拒绝）；`media_technical.py`＋`pipeline_fix_mount` 宿主进必需冻结集，identity 强制 `technical_contract`（schema+digest）摘要绑定；`verify_media_technical` 共享 close_deadline（剩余预算 gate、min(timeout,剩余)、耗尽零启动、超时回收）；duration_basis/A-V 阈值/audio_tracks 显式消费、不支持显式能力拒绝；容差缺失拒绝、显式 0 合法；`attempt_wall_s` 保持 Agent 窗口、`total_wall_s` 含技术验收、分阶段计时记录。
- 测试（fresh）：146 passed＋49 subtests（含新增 test_four_gap_closure 31）。启动器未改（`ff875bc4…` 不变，证明仍有效）。未批准 65s 有声契约草案见报告 draft/（duration_basis=video_stream 建议、容差 0.5 建议，依据 AAC/帧量化与 container-vs-stream 差值，非旧成片倒推）。[闭合报告](../reports/analysis/VIMAX-AUDIO-CONTRACT-FOUR-GAP-FINAL-CLOSEOUT-01/summary.md)。

## 最新离线修复：VIMAX-AUDIO-DEPLOYMENT-AND-TECHNICAL-CONTRACT-REPAIR-01（2026-11-02，UTC）

一次性离线闭合 ViMax 有声媒体的部署→契约→原生拼接→正式技术验收→退出语义→回归。未调用真实模型/媒体/音频/评分；未正式媒体 attempt；未创建正式身份/批准；未改写 R08 判定；未改其他三仓/模型/预算/资源限制；未提交推送；未改 execution_authorization。

- 根因（repro-before 于 pre-fix 快照复现）：pipeline 冻结却未真实部署到容器 import 路径（R08 final MP3 根因）；load_expect 丢 audio/duration_tolerance_s；final_audio_mode 只查音轨存在；host 汇总未消费技术验收；Infinity/NaN/坏 fps 过旧校验；audio="true"/1/null 静默变 false；第三个 clip 打开失败泄漏前两个；旧测试复制判定逻辑。
- 修复：`pipeline_fix_mount`（只读挂载 + 容器内 SHA + 真实 import 解析 `pipelines.script2video_pipeline`，发送前拒绝错挂载/错 SHA/错 import 源）；新增 `media_technical.py` 共享契约归一化/校验与 ffprobe 技术验收（AAC/MP3 正确区分、非静音 mean_volume>-60dB、严格有限数/fps 有理数/audio 显式 bool/冲突拒绝、缺容差记录 strict 0.0）；`_concat_final_videos` 受保护清理集合（部分打开失败/编码异常均释放、AAC 保留）；宿主退出语义（程序 PASS＋技术 FAIL→rc1 且 native_agent_done 保留）；acceptance.py 技术检查改调共享消费者。
- 真实容器（network=none 无凭据）验证部署与原生 AAC concat；测试 115 passed＋49 subtests（fresh）。启动器未改（SHA `ff875bc4…` 不变，持久性证明仍有效）。R08-MEDIA-01 历史 MP3 失败保持；未来正式有声 run 需新 config（pipeline_fix_mount＋完整 contract）＋新身份/批准，另行授权。[修复报告](../reports/analysis/VIMAX-AUDIO-DEPLOYMENT-AND-TECHNICAL-CONTRACT-REPAIR-01/summary.md)。

## 最新媒体阶段执行：VIMAX-MUSICIANS-AUDIO-FULL-FLOW-R08-MEDIA-01（2026-11-02，UTC 时间戳；Asia/Shanghai 参照 +08:00）——有声attempt已执行，final音轨非AAC（技术缺口，R08未标完整完成）

R08有声媒体 attempt（run_id `musicians-audio-full-flow-r08-media-01-20261102T031747Z-7124a95b`，supervisor 2251946 / runner 2251947）经托管启动器（stage=media）执行完毕：**13逻辑图片（9肖像＋4候选，候选数固定2）→ 25视频（13主体＋12过渡，audio=true）→ 38正常下载 → 原生concat（仅主体shots/0..12）→ 65.15s H.264/1280×720/30/1fps成片（SHA `8efad3133146f257…`）；COMPLETE v3全维度True、required_work在deadline内；宿主 native_agent_done、容器退出0、清理核验、cleanup_errors=[]；资源边界齐全（5011样本/261.77 core-s/netns 1256行）、采样跨120s持续至结束；supervisor runner_exited rc=0；远端closeout 25/25 SUCCEEDED（usage.audio=true）。** audio=true端到端：video_generation.audio=true/expected.audio=aac、video_call payload `"audio": true`、远端usage.audio=true、subject clips audio=aac。**但final原生concat将音轨重编码为MP3（libmp3lame）而非AAC，`expected.audio=aac`在final文件层面未满足（aac_contract_met=False）；音轨非静音（max −0.0 dB/mean −19.1 dB）、A/V start均0.0s时长差~0.05s。按"首次真实发送后禁止修改生产代码/不宿主另起FFmpeg"约束不修不改，如实记录技术缺口；R08未标完整正常流程，R09不启动。** [媒体报告](../reports/analysis/VIMAX-MUSICIANS-AUDIO-FULL-FLOW-R08-MEDIA-01/summary.md)。

## 最新规划阶段完成：VIMAX-MUSICIANS-AUDIO-FULL-FLOW-R08-PLANNING-01（2026-11-02，UTC 时间戳；Asia/Shanghai 参照 +08:00）

R08第一阶段（新规划）经**规划阶段持久托管启动器**完成：真实 musicians 有声规划 attempt（run_id `musicians-audio-full-flow-r08-planning-01-20261102T025402Z-91e194be`）通过生产 plan_verifier——13镜头/3角色/13相机/12过渡、0媒体/音频请求、18逻辑请求（54,941 tokens）、attempt 102.36s、测量质量complete、容器自然退出0+清理回验、supervisor runner_exited rc=0。[规划证据](../reports/analysis/VIMAX-MUSICIANS-AUDIO-FULL-FLOW-R08-PLANNING-01/summary.md)。**有声路线**：native wan2.6-i2v-flash audio=true；保留环境声/room tone、吉他/键盘/cajón 演奏声、故事内笑声及自然动作声音；禁止无关对白/旁白/背景配乐；silent count 不升级为整镜头绝对静音。媒体预算草案（image_creates 13＝9肖像＋4候选、video_creates 25＝13主体＋12过渡、下载38、closeout复下载25、图片HTTP上界26、视频尝试上界50、自然轮询上界2300；候选数 env>config>default 2建议显式固定2；audio=true/AAC 单列待批准确认）已推导但未授权。**媒体阶段未启动、未创建媒体身份/批准；R08仅记"新规划通过，媒体待批准"，不等同完整任务完成；R09不启动。** 本轮未改生产代码；历史musicians/G01/G02/G03规划/媒体未复用。

## 最新媒体阶段完成：VIMAX-G03-FULL-FLOW-R07-MEDIA-01（2026-11-02，UTC 时间戳；Asia/Shanghai 参照 +08:00）——完整正常流程成功，R07标完整完成

R07媒体阶段经托管启动器 `scripts/vimax_managed_launch.py`（stage=media）启动唯一正式 attempt（run_id `g03-full-flow-r07-media-01-20261102T021018Z-bc2d3e00`，supervisor 2133557 / runner 2133559）：**8逻辑图片（6肖像+2候选）→ 17视频（9主体+8过渡）→ 25正常下载 → 原生concat（仅主体shots/0..8）→ 45.000s H.264/1280×720/30/1fps/无音轨成片（SHA `d4150200f5dc1b7b…`，完整解码）；COMPLETE v3全维度有效、final_path_resolution owned/exists/accepted全true、required_work在deadline内；宿主 termination=native_agent_done、容器退出0、清理核验、cleanup_errors=[]；资源边界齐全（3055样本/190.80 core-s/netns 767行0失败）、采样跨120s持续至结束；supervisor runner_exited rc=0；远端closeout 17/17 SUCCEEDED audio=false复下载独立记账。** [媒体报告](../reports/analysis/VIMAX-G03-FULL-FLOW-R07-MEDIA-01/summary.md)。**R07 标完整正常流程完成**（规划 R07-PLANNING-01 通过＋媒体 MEDIA-01 完整正常流程）。R08/R09 不启动。

## 最新规划阶段完成：VIMAX-G03-FULL-FLOW-R07-PLANNING-01（2026-11-02，UTC 时间戳；Asia/Shanghai 参照 +08:00）

R07第一阶段（新规划）经**规划阶段持久托管启动器**完成：真实 G03 athletes_gym_training_duo_typeC 规划 attempt（run_id `g03-full-flow-r07-planning-01-20261102T014721Z-1db09049`）通过生产 plan_verifier——9镜头/2角色/9相机/8过渡、0媒体请求、14逻辑请求（40,666 tokens）、attempt 87.42s、测量质量complete、容器自然退出0+清理回验、supervisor runner_exited rc=0。[规划证据](../reports/analysis/VIMAX-G03-FULL-FLOW-R07-PLANNING-01/summary.md)。媒体预算草案（image_creates 8＝6肖像＋2候选、video_creates 17＝9主体＋8过渡、下载25、closeout复下载17、图片HTTP上界16、视频尝试上界34、自然轮询上界1564；候选数 env>config>default 2，建议后续显式固定2；work/closeout 5400/600与entry默认300冲突待确认）已推导但未授权。**媒体阶段未启动、未创建媒体身份/批准；R07仅记"规划通过、媒体待批准"，不等同完整任务完成；R08/R09不启动。** 本轮新增 `scripts/vimax_managed_launch.py` 显式 planning 阶段（默认仍 media，原门禁不退化）：真实规划 `load_context`/`validate_approval` 门禁 + preflight 归属/attempt 保护；同 OUT 首次 run 放行、已有 attempt 拒绝。修改启动器后旧证明保留，在同一持久宿主执行域用最终启动器（SHA `ff875bc4…`）重做 130.00s 离线探针（2595 样本/start+end 边界/rc=0）；托管器/阶段适配/证明绑定进本次冻结身份。历史G03/G01/G02/musicians规划未复用。

## 最新限定修复：VIMAX-MEDIA-MANAGED-LAUNCH-REPAIR-01（2026-11-02，Asia/Shanghai）

仅修复ViMax媒体启动托管，新增独立会话supervisor、带身份握手、心跳/退出码与同宿主执行域持久性证明门禁；原媒体生成/拼接/预算/验收代码不改。操作端外层超时属于报告的原因，原始证据直接证明的是宿主/采样提前中断，信号链尚未完整取证。当前沙箱跨工具退出会清理子进程已实测，不能仅凭`nohup/setsid`宣布可靠。[使用说明](vimax_managed_launch.md)。本轮无真实模型/媒体、无新正式身份/批准/attempt；R06-MEDIA-01及缺失采样仍保留原判定，后续媒体须另行授权。

## 最新媒体阶段完成：VIMAX-G02-FULL-FLOW-R06-MEDIA-02（2026-11-01）——完整正常流程成功，R06标完成

R06媒体阶段经托管启动器 `scripts/vimax_managed_launch.py` 启动唯一正式 attempt（run_id `g02-full-flow-r06-media-02-20261101T172522Z-20b731fa`）：**12逻辑图片（6肖像+6候选）→ 19视频（10主体+9过渡）→ 31正常下载 → 原生concat → 50.000s H.264/1280×720/30fps/无音轨成片（完整解码，SHA `a85c603d…`）；COMPLETE v3全维度有效、required_work在deadline内、final_path_resolution owned/exists/accepted全true；宿主 termination=native_agent_done、容器退出0、清理核验、cleanup_errors=[]、资源边界齐全（5229样本/190.93 core-s/netns 1309行）、测量质量complete；supervisor runner_exited rc=0；远端closeout 19/19 SUCCEEDED audio=false复下载独立记账。** [媒体报告](../reports/analysis/VIMAX-G02-FULL-FLOW-R06-MEDIA-02/summary.md)。**R06 标完整完成**（规划通过＋媒体完整正常流程）。R06-MEDIA-01 中断失败观察原样保留；R07–R09 不启动。

## 最新媒体阶段执行：VIMAX-G02-FULL-FLOW-R06-MEDIA-01（2026-11-01）——中断attempt失败观察

一次授权媒体 attempt（run_id `g02-full-flow-r06-media-01-20261101T155226Z-5ebe4b38`）执行：**容器内媒体流水线完整成功**——12逻辑图片（6肖像+6候选）→ 19视频（10主体+9过渡）→ 31下载 → 原生concat → 50.000s H.264/1280×720/30fps/无音轨成片（完整解码，SHA `feb348a7…`）；COMPLETE v3 全维度有效（生产 assess_complete_marker 复核）；账本全闭合（unclosed_request_ids=[]）。**但生产宿主生命周期被外层工具120s超时中断**（host_runner.py run 进程在 attempt 开始约2分钟后被杀，PID 1673800；操作端启动基础设施错误，非生产代码缺陷），宿主未记录 termination=native_agent_done、资源/netns 测量仅覆盖前~110s、宿主 closeout 由操作端手动有界完成。[媒体报告](../reports/analysis/VIMAX-G02-FULL-FLOW-R06-MEDIA-01/summary.md)。**R06 未标完整完成；不补跑、不宿主补拼接、不独立恢复、不启动R07–R09。** 规划阶段保持通过（VIMAX-G02-FULL-FLOW-R06-PLANNING-01）。

## 最新规划阶段完成：VIMAX-G02-FULL-FLOW-R06-PLANNING-01（2026-11-01）

R06第一阶段（新规划）已完成：真实 G02 pottery_workshop_studio_space_typeB 规划 attempt（run_id `g02-full-flow-r06-planning-01-20261101T152744Z-cd860dee`）通过生产 plan_verifier——10镜头/2角色/10相机/9过渡、0媒体请求、15逻辑请求（43,675 tokens）、attempt 95.92s、测量质量complete、容器自然退出0+清理回验。[规划证据](../reports/analysis/VIMAX-G02-FULL-FLOW-R06-PLANNING-01/summary.md)。媒体预算草案（image_creates 12、video_creates 19、下载31、closeout复下载19、自然轮询上界1748）已推导未授权。**媒体阶段未启动、未创建媒体身份/批准；R06仅记"规划通过、媒体待批准"，不等同R06完整任务完成；R07–R09不启动。** 本轮无生产代码修改；历史G02/G01/G03/musicians规划未复用。

## 最新限定修复：VIMAX-MEDIA-FINAL-PATH-REPAIR-01（2026-11-01）

媒体宿主现将原生 `.working_dir/<session>/...` 路径明确映射到本次 `/workspace` 挂载，兼容容器绝对路径；拒绝穿越、符号链接逃逸和其他session。新增12项＋回归30项，共42项离线测试通过；真实生产者COMPLETE→宿主消费者及fake外部边界的正常宿主收尾已验证。[修复证据](../reports/analysis/VIMAX-MEDIA-FINAL-PATH-REPAIR-01/summary.md)。未重新规划、生成、下载、拼接或启动正式attempt；R05媒体原运行仍为 `final_artifact_missing` 失败观察，不回写为成功，未来正式执行须绑定新代码并另行批准。

更新：2026-11-01。本页是进度而非执行批准。目标仍是Agent本地CPU、内存、I/O、目录占用、网络、时长及工具行为；不要求GPU/函数热点。
## 当前权威结论：16组合／9输入，9组完整流程重跑计划（2026-10-31）

- **R07第一阶段（规划）经规划阶段托管启动器完成（2026-11-02）：VIMAX-G03-FULL-FLOW-R07-PLANNING-01 新规划通过——9镜头/2角色/9相机/8过渡（候选首帧分支相机1：camera_0）、生产plan_verifier ok（16项checks中15项True＋1项语义非机器证明）、Agent正常完成（container rc=0自然退出）、0媒体请求、14逻辑请求（40,666 tokens，<250K软阈值）、attempt 87.42s、测量质量complete、容器清理核验、supervisor runner_exited rc=0；托管器新增显式planning阶段（默认仍media，原门禁不退化；真实load_context/validate_approval门禁＋preflight归属/attempt保护；同OUT首次run放行）；修改启动器后旧证明保留，同一持久宿主执行域用最终启动器（SHA `ff875bc4…`）重做130.00s离线探针，托管器/阶段适配/证明绑定进冻结身份。媒体预算草案（image_creates 8＝6肖像＋2候选、video_creates 17＝9主体＋8过渡、下载25、closeout复下载17、图片HTTP上界16、视频尝试上界34、自然轮询上界1564；候选数 env>config>default 2建议显式固定2；work/closeout 5400/600与entry默认300冲突待确认）已推导但未授权、媒体阶段未启动、未创建媒体身份/批准。历史G03/G01/G02/musicians规划未复用。**
- **R07第二阶段（媒体）经托管器完整正常流程成功（2026-11-02）：VIMAX-G03-FULL-FLOW-R07-MEDIA-01 ——经 `scripts/vimax_managed_launch.py`（stage=media；supervisor 2133557 独立session/PGID、runner 2133559）启动唯一正式 attempt：8逻辑图片（6肖像+2候选，候选数显式固定2）/17视频（9主体+8过渡）/25正常下载/原生concat（仅主体shots/0..8）/final 45.000s H.264/1280×720/30/1fps/无音轨/SHA `d4150200f5dc1b7b…`/完整解码；COMPLETE v3全维度True（final_path_resolution owned/exists/accepted、required_work在deadline内）；宿主 termination=native_agent_done、container_exit_code=0、cleanup_errors=[]、清理回验；资源边界齐全（3055样本/190.80 core-s/io_write 90,112B/netns 767行0失败）、采样跨120s持续至结束；supervisor runner_exited rc=0；远端closeout 17/17 SUCCEEDED audio=false复下载17独立记账。**R07 标完整正常流程完成。** R08/R09 不启动。**
- **R08第一阶段（规划）经规划阶段托管启动器完成（2026-11-02）：VIMAX-MUSICIANS-AUDIO-FULL-FLOW-R08-PLANNING-01 新规划通过——13镜头/3角色/13相机/12过渡（候选首帧分支相机2：camera_0/9，camera_9 missing_info 非空串）、生产plan_verifier ok（16项checks中15项True＋1项语义非机器证明）、Agent正常完成（container rc=0自然退出）、0媒体/音频请求、18逻辑请求（54,941 tokens，<250K软阈值）、attempt 102.36s、测量质量complete、容器清理核验、supervisor runner_exited rc=0；有声路线 native wan2.6 audio=true（保留room tone/演奏声/笑声、silent count不升级为绝对静音）。媒体预算草案（image_creates 13＝9肖像＋4候选、video_creates 25＝13主体＋12过渡、下载38、closeout复下载25、图片HTTP上界26、视频尝试上界50、自然轮询上界2300；候选数 env>config>default 2建议显式固定2；audio=true/AAC待批准确认）已推导但未授权、媒体阶段未启动、未创建媒体身份/批准。**R08仅记"新规划通过，媒体待批准"；R09不启动。** 历史musicians/G01/G02/G03规划/媒体未复用。**
- **R08第二阶段（媒体）有声attempt已执行（2026-11-02）：VIMAX-MUSICIANS-AUDIO-FULL-FLOW-R08-MEDIA-01 ——经 `scripts/vimax_managed_launch.py`（stage=media；supervisor 2251946、runner 2251947）启动唯一正式 attempt：13逻辑图片（9肖像+4候选，候选数固定2）/25视频（13主体+12过渡，audio=true，subject clips AAC）/38正常下载/原生concat（仅主体shots/0..12）/final 65.15s H.264/1280×720/30/1fps/SHA `8efad3133146f257…`；COMPLETE v3全维度True、required_work在deadline内；宿主 native_agent_done、容器退出0、清理核验、cleanup_errors=[]；资源边界齐全（5011样本/261.77 core-s/netns 1256行）、采样跨120s持续至结束；supervisor runner_exited rc=0；远端closeout 25/25 SUCCEEDED（usage.audio=true）。audio=true端到端（payload `"audio": true`）。**但final原生concat将音轨重编码为MP3（libmp3lame）而非AAC，`expected.audio=aac`在final文件层面未满足（aac_contract_met=False）；音轨非静音（max −0.0 dB/mean −19.1 dB）。按不修不改约束如实记录技术缺口，R08未标完整正常流程；R09不启动。**
- **R08第二阶段（媒体）修复链完整正常有声流程成功（2026-11-02）：VIMAX-MUSICIANS-AUDIO-FULL-FLOW-R08-MEDIA-02 ——经 `scripts/vimax_managed_launch.py`（stage=media；supervisor 2684876、runner 2684877）启动唯一正式 attempt：13逻辑图片（9肖像+4候选，候选数固定2）/25视频（13主体+12过渡，audio=true/AAC）/38正常下载/原生AAC拼接（仅主体shots/0..12，concat审计 `-acodec aac`）/final 65.10s（video_stream，主判定65±0.5 PASS）H.264/1280×720/30/1fps/AAC/SHA `ce54ee583a85586e…`；正式技术验收applied+ok（12项checks全True、契约digest `b15d5f66…`与冻结一致）；COMPLETE v3全维度True、required_work在deadline内；宿主 native_agent_done、容器退出0、清理核验；资源边界齐全（3113样本/255.68 core-s/netns 781行）、采样跨120s持续至结束；supervisor runner_exited rc=0；远端closeout 25/25 SUCCEEDED（usage.audio=true）；attempt 1560.71s/total 1576.92s含技术验收0.93s。修复链真实生效：pipeline_fix_mount（`9a69b0ea…`）只读挂载+import解析、media_technical（`ca96d007…`）必需绑定、technical_contract冻结+门禁重算、技术验收共享close_deadline。**R08 标完整正常流程完成；R08-MEDIA-01 MP3失败观察原样保留；R09不启动。**
- **R06第一阶段（规划）已完成（2026-11-01）：VIMAX-G02-FULL-FLOW-R06-PLANNING-01 新规划通过——10镜头/2角色/10相机/9过渡（候选首帧分支相机3：camera_0/2/3）、生产plan_verifier 16/16 checks全True、Agent正常完成（container rc=0自然退出）、0媒体请求、15逻辑请求（43,675 tokens，<250K软阈值）、attempt 95.92s、测量质量complete、容器清理核验；媒体预算草案按真实生产分支推导（image_creates 12＝6肖像＋6候选、video_creates 19＝10主体＋9过渡、下载31、closeout复下载19、图片HTTP上界24、视频尝试上界38、时间窗自然轮询上界1748；work/closeout 5400/600与entry默认300冲突待确认）已推导但未授权、媒体阶段未启动、未创建媒体身份/批准。本轮无生产代码修改；历史G02/G01/G03/musicians规划未复用。**
- **R06第二阶段（媒体）已执行一次正式 attempt（2026-11-01）：VIMAX-G02-FULL-FLOW-R06-MEDIA-01 ——容器内媒体流水线完整成功（12逻辑图片＝6肖像＋6候选、19视频＝10主体＋9过渡、31下载、远端19/19 SUCCEEDED且audio=false；final_video.mp4＝50.000s/H.264 High/1280×720/30fps/0音轨/SHA `feb348a7…`/完整解码；原生concat按主体shots/0..9、COMPLETE v3 全维度True），但生产宿主host_runner进程在attempt开始约2分钟后被外层bash工具120s默认超时杀掉（PID 1673800）——宿主未记录termination=native_agent_done、资源/netns测量仅覆盖前~110s（测量质量partial）、宿主closeout改由操作端手动有界完成（logs/stop/wait/rm核验、remote_closeout无需）。根因为操作端启动基础设施错误，非生产代码缺陷。**R06未标完整完成；不补跑、不宿主补拼接、不独立恢复。** 媒体阶段如需完整正常流程须另行授权。**
- **R06第二阶段（媒体）经托管器完整正常流程成功（2026-11-01）：VIMAX-G02-FULL-FLOW-R06-MEDIA-02 ——经 `scripts/vimax_managed_launch.py`（托管supervisor 1737437 独立session/PGID、persistence proof 绑定、runner 1737444）启动唯一正式 attempt：12逻辑图片（6肖像+6候选）/19视频（10主体+9过渡）/31正常下载/原生concat/final 50.000s H.264/1280×720/30fps/0音轨/SHA `a85c603d…`/完整解码；COMPLETE v3全维度True（final_path_resolution owned/exists/accepted、required_work在deadline内）；宿主 termination=native_agent_done、container_exit_code=0、cleanup_errors=[]、清理回验；资源边界齐全（5229样本/190.93 core-s/io_write 122,880B/netns 1309行0失败）；supervisor runner_exited rc=0；远端closeout 19/19 SUCCEEDED audio=false复下载19独立记账。**R06 标完整完成。** R06-MEDIA-01 中断失败观察原样保留。**
- **R05第一阶段（规划）已完成（2026-11-01）：VIMAX-G01-FULL-FLOW-R05-PLANNING-01 新规划通过——8镜头/1角色/8相机/7过渡、生产plan_verifier 14/14 checks全True、Agent正常完成（container rc=0）、0媒体请求、13逻辑请求（37,873 tokens，<250K软阈值）、attempt 77.99s、容器清理核验；媒体预算草案（image_creates 5、video_creates 15、下载20、轮询900、work/closeout 5400/600待确认300默认差异）已推导但未授权、媒体阶段未启动。发送前唯一修复：preflight adapter divergence允许集扩展到3个已验收修复文件（留快照）。**
- **R05第二阶段（媒体）已执行一次正式 attempt（2026-11-01）：VIMAX-G01-FULL-FLOW-R05-MEDIA-01 ——媒体生成与原生拼接全部成功（19逻辑图片＝3肖像＋16候选、15视频＝8主体＋7辅助、34正常下载、远端15/15 SUCCEEDED且audio=false；final_video.mp4＝40.000s/H.264 High/1280×720/30fps/0音轨/SHA `4c402731…`/完整解码；账本全闭合、video_polls 55/1380、observed_output_tokens_total 4548<500000软阈值），但宿主 COMPLETE v3 最终路径所有权校验失败：生产者写入工作区相对路径 `final_video_path=.working_dir/…`，旧 `assess_complete_marker.final_path_owned` 以 `os.path.relpath(final_path,'/workspace')` 判定其越出 /workspace → 终态 **final_artifact_missing（rc=1）**。该失败观察及其全部证据原样保留。**
- **R05第二阶段（媒体）修复后再次执行（2026-11-01）：VIMAX-G01-FULL-FLOW-R05-MEDIA-02 完整正常流程成功——绑定 VIMAX-MEDIA-FINAL-PATH-REPAIR-01 修复后 host_runner（`resolve_final_artifact_path` 将原生工作区相对路径映射到本次 /workspace）；媒体生成与原生拼接全部成功（19逻辑图片＝3肖像＋16候选、15视频＝8主体＋7辅助、34正常下载、远端15/15 SUCCEEDED且audio=false、video_polls 148/1380、llm 26次 sum_total 112,385、observed_output_tokens_total 4475<500000软阈值）；final_video.mp4＝40.000s/H.264 High/1280×720/30fps/0音轨/SHA `639e778b68eb101d…`/完整解码；COMPLETE v3 全维度 True（含 `final_path_resolution`：workspace_relative=.working_dir/g01-full-flow-r05-media-02/script2video/final_video.mp4 → host_path=本次 raw/workspace/…，owned/exists/accepted 全 true）；宿主终态 **native_agent_done（rc=0）**、cleanup_errors=[]、容器清理回验；资源 3124 样本/CPU 185.82 core-s/1563.33s/测量质量 complete。R05当前状态：**新规划通过＋媒体修复后完整正常流程成功，R05 标完整流程完成**；MEDIA-01 失败观察原样保留；未补跑、未独立恢复、未改生产代码；未启动 R06–R09，覆盖计数不变。**
- **R04已完成完整正常流程（2026-11-01）：OPENSTORYLINE-ASSEMBLY-FULL-FLOW-R04-01 为完整正常成功——12素材门禁/27项overlay真实通过（docker inspect实际Source=素材目录、只读）、原生assembly链understand_clips(12素材视觉理解)→filter_clips(自主选恰好K=4个不同clip: clip_0001/0002/0003/0005)→group_clips(按storyboard slot排序: clip_0002→clip_0001→clip_0005→clip_0003)→plan_timeline_pro(4 video项10→4→5→3.mp4全片)→render_video、Agent rc=0（475.00s<1800s）、assembly完成判定正常（task-kind-aware，不再误用interview必需节点）、宿主导出solution.mp4/solution.json（与render逐字节一致、SHA `4e1bc351…`、4段连续half-open）、技术验收结构10/10 PASS、容器清理回验。official_evaluation=not_integrated、reward=null、semantic_evaluation=not_evaluated（官方裁判未接入）。EXECUTION-02/03/04历史失败及独立恢复原样保留。发送前唯一修复：assembly-offline-gate.json资产SHA过期刷新（留快照）。**
- **R03已完成完整正常流程（2026-11-01）：OPENSTORYLINE-E03-FULL-FLOW-R03-02 为完整正常成功——批准单任务逻辑预算100（token 1M/输出32768固定防线不变）下，输入/overlay门禁真实通过（实际挂载E03、27项overlay）、原生内容删除链load_media→split_shots→local_asr→speech_rough_cut（41/41调用与解析成功后推进，不代表删除目标完整落实）→plan_timeline_pro→render_video、Agent rc=0（950.95s<1800s）、完成判定写入、宿主导出output.mp4/cuts.json（删除区间[29190,30810]）、技术检查通过（帧率源/输出精确24000/1001 exact_equal、0ppm）、一次官方评分complete/reward=0（合法，end_offset 3.518s未命中golden）、容器清理回验。R03-01（预算60耗尽、无提交物）失败观察原样保留。预算100/1M/32768贯穿配置/冻结/request/容器/ledger，实际用52/100。** 流程与语义分开：Agent指定[29190,38760]ms，实际仅删[29190,30810]ms；52次请求低于旧上限60，预算100提供余量，但不能证明其是本次完成的必要条件。
- **R02已完成完整正常流程（2026-11-01）：OPENSTORYLINE-E02-FULL-FLOW-R02-01 为完整正常成功——输入/overlay门禁真实通过（docker inspect实际挂载E02输入、容器内bytes/SHA=冻结、25项overlay）、原生interview链到render成功、Agent rc=0（479.66s<1800s）、完成判定写入render_artifact_id、宿主导出output.mp4/cuts.json（从最终render实际消费的timeline派生）、技术检查通过（帧率源/输出精确60000/1001、exact_equal=true、0ppm，未出现历史2997/50舍入）、一次官方评分complete/reward=0（合法）、容器清理回验。E02-EXPANSION-01（错误输入）与E02-EXPANSION-02（旧帧率门拒绝＋独立FPS恢复）历史事实原样保留。**
- ViMax musicians已按“原有声媒体运行＋独立拼接恢复”纳入成果索引；当前16是历史组合数，不是16次连续完整运行。重跑前历史基线为7组连续主流程记录可定位、3组ViMax规划/媒体分阶段、5组原运行＋恢复、1组video-use E03原始trace待定位；R01-02新增正常完整流程另行登记，不覆盖历史分类或增加组合数；R02-01同。
- 用户明确保留原8组（包括ViMax分阶段3组），新增video-use E03，合计9组：**OpenStoryline四组、ViMax四组、video-use E03**。不缩减为5/6组。编号R01–R09、边界及验收见[重跑清单](video_full_flow_rerun_plan.md)，机器状态见[成果索引](video_results_index.json)。
- ViMax前三组原先为正常分阶段执行，不改写为失败；新目标是新规划→验收/批准→媒体→正常拼接的统一新执行链，各阶段资源与审批等待仍分别声明。OpenStoryline和ViMax musicians旧恢复成果保留，不替代新运行正常导出/拼接。
- video-use E03的索引raw父目录为空，目前未找到完整rollout副本；现已纳入R09，不再单列为未决候选。新run必须完整执行并核验trace/资源/输入产物/manifest持久化，历史摘要不能替代raw；旧副本查找不作为新运行申请前置。
- **R01已完成完整正常流程（2026-10-31）：R01-02 为完整正常成功——输入/overlay门禁通过、原生interview链到render成功、Agent rc=0（1076.69s<1800s）、完成判定写入 render_artifact_id、宿主导出 output.mp4/cuts.json（从最终render实际消费的timeline派生）、技术检查通过（帧率25/1精确）、一次官方评分 complete/reward=0（合法）、容器清理回验。R01-01（1800s截止、无提交物、not_run_no_submission/reward=null）为完整采集的失败观察，原样保留、不补跑、不自动追加attempt。** 9组逐项新授权、独立新身份/输出；不无限补跑，不以reward>0为目标。以下历史段落的旧计数、“无需重跑”“尚未执行”等按当时状态阅读，以本节为当前目标。

## OPENSTORYLINE-E03-BUDGET-PROPAGATION-REPAIR-01（2026-11-01）：限定离线修复，无重跑

预算拒绝现在通过结构化MCP错误信封传播，粗剪首次收到即停止，不解析为JSON、不继续逐句fallback或返回成功产物；正常模型结果及既有非预算fallback语义保持。共享预算helper与ledger进入统一只读overlay/未来冻结集合（当前27项）。原R03-01报告/raw/身份/批准/manifest字节保留，以[修订报告](../reports/analysis/OPENSTORYLINE-E03-BUDGET-PROPAGATION-REPAIR-01/summary.md)更正因果。未增加60次预算、未改变逐句剪辑策略、未运行真实任务，R03仍未完成；41句全片重做两轮需82次内部请求，预算适配需另行决策。

## OPENSTORYLINE-E03-FULL-FLOW-R03-01（2026-11-01）：R03完整流程唯一真实attempt——完整采集的失败观察（逻辑请求预算60耗尽，无提交物）

**R03-01原失败记录保留：输入/25项overlay门禁和内容删除提示注入真实通过，7次工具调用闭合；第一次粗剪删除不完整，第二次在10次正常采样后达到60次请求上限，31次本地预算拒绝被旧interview路径转成错误文本并误记解析失败，随后Agent本地拒绝而rc=1。未到plan/render，无标准提交和评分。更正及限定离线修复见[预算传播修订](../reports/analysis/OPENSTORYLINE-E03-BUDGET-PROPAGATION-REPAIR-01/summary.md)，不修改原报告或伪称已重跑成功。**
- 配置：`env/video/openstoryline/task-configs/E03-full-flow-r03-01.json`；task_id `OPENSTORYLINE-E03-FULL-FLOW-R03-01`、task_kind=interview、run_id `20261101T032400Z-openstoryline-e03-full-flow-r03-01`；镜像 `sha256:9a1e876c…`；身份内容 SHA `81e8d6e6…`、身份文件 SHA `9334e930…`、绑定 65 文件（48 interview 冻结源 + 25 overlay + task config）；APPROVAL `openstoryline-e03-full-flow-r03-01-approval-v1` 绑定身份文件 SHA。
- 门禁真实通过：container-input-verify passed（实际 Source=E03 输入目录、bind、readonly、容器内 SHA `c66f380a…`/11604798B）；overlay-verify passed（25 项实际挂载、容器内 SHA=冻结）；load_runtime_approval 重校验通过；request.json 含 E03 内容删除目标、明确宿主自动提交职责、edit_policy 未继承 assembly/E02。
- edit_policy消费：内容删除策略及目标真实进入内部粗剪提示，删除补集路径生效。forbid_added_subtitles=true已配置；本次未到plan，不能称已实测最终0字幕timeline。
- 原生链：load 1、split 1、local_asr 1、read_node_history 2、speech_rough_cut 2，共7次start/finish闭合；旧工具协议均未标isError，但第二次粗剪含31项降级，不代表业务全部成功。未到elementrec/render。
- Agent自主选段[29190,38760]ms；首次实际只删[29190,30810]ms，Agent发现不完整后重做。第二轮先达到预算门，再出现31次错误文本解析降级；不是31次供应商坏JSON。原raw保留3个粗剪中间MP4，无最终视频/标准提交。
- 模型请求 60（agent 7 / mcp_sampling 51 / llm_validation 1 / vlm_validation 1）；usage 覆盖 60/60、无右删失；sum_total_tokens 229,950（<1M 软阈值）；达预算上限 60；额外 32 条无 usage `request_finished` 为内部预算跟踪事件，非独立请求。
- 资源：1563 行（boundary 2 + sample 1561），目标 0.5s；CPU 734.78 core-s / 有效 962.94s / 均值 0.763 core；mem.current 峰 5,259,845,632 B、kernel peak 6,944,284,672 B；I/O read 0 / write 1,343,488 B；netns lo/eth0 逐接口（eth0 rx≈4.39MB/tx≈1.40MB、lo rx/tx≈1.25MB 首末累计，非 API 专属）。采样窗 962.94s 覆盖 agent 相位 945.37s；容器 removal=removed；cleanup_errors=[]；host total_wall 964.12s。
- 判定：Agent 失败观察（预算耗尽 rc=1）＋ 技术未导出/未检查 ＋ 官方 not_run_no_submission/reward=null ＋ 测量质量 complete（trace 与资源完整采集该失败窗口）。
- 保护：未补跑、未追加 attempt、未放宽预算门禁、未改旧 raw/身份/批准/评分/manifest、未改生产代码、未提交推送；覆盖计数不变；E03-EXPANSION-01/02 与 E03-RUNTIME-CONFIRM-03 原运行及独立 closeout 未改写。
- 证据：`reports/analysis/OPENSTORYLINE-E03-FULL-FLOW-R03-01/`（原失败报告及analysis/result.json、原raw副本43文件、raw manifest 40项、报告manifest 54项、analysis manifest 6项，原字节保留）；因果修订与当前源码/测试身份见`reports/analysis/OPENSTORYLINE-E03-BUDGET-PROPAGATION-REPAIR-01/`。

## OPENSTORYLINE-E03-REQUEST-BUDGET-READINESS-01（2026-11-01）：E03请求预算离线核定与未批准草案（R03仍失败未完成）

**离线只读核定＋最小通用接线修复＋未批准draft配置；零真实服务/Agent/身份/批准/attempt，未启动R03-02。** 依据R03-01原始轨迹推导：mcp_sampling等于ASR句数/轮（41/轮，经E01=24、E02=5、R03=41+10的association验证，plan/render/elementrec为0额外采样）；60次上限在第二轮第10次后拒绝31句及后续Agent请求，无法容纳两轮完整41句重做。**推荐单任务 `max_logical_requests=100`**：公式=2 validation + 7 agent + 82（2×41逐句粗剪）+ 9余量；结构性下限91，备选96。token观测229,950（1M软阈值充裕）；两轮完整agent时间估算约1581s（1800s内余量~12%，为外推非保证）。**最小修复**：task-config新增可选 `request_budget` 字段贯通宿主apply_task_config→freeze_identity→request→容器configure_budget/request_ledger（无字段默认60，E01/E02不变）；容器侧per-task ceiling改从冻结身份budget取（默认回退FROZEN_MAX_*）。**未批准draft**：`env/video/openstoryline/task-configs/E03-full-flow-r03-02-budget-draft.json`（status=draft、request_budget.max_logical_requests=100、run_id为非正式占位、零发送）。离线测试：宿主7项+14 subtests PASS、既有18项+5 subtests回归PASS、容器network=none只读3项PASS；原R03-01 raw/报告/身份/批准/manifest字节保留。**R03仍标失败未完成**，R01/R02保持完成，覆盖计数不变。真实运行需用户单独批准（预算值+正式配置+新身份/批准）。

## OPENSTORYLINE-E03-BUDGET-READINESS-FINAL-CLOSEOUT-01（2026-11-01）：预算防线恢复与真实冻结→容器消费者整链离线验收（R03仍失败未完成）

**限定离线修复与验收；零真实服务/Agent/身份/批准/attempt，未启动R03-02。** 集中闭合预算准备阶段最后两处缺口并更正报告数字。
- **工作A（恢复防线）**：`configure_budget`（容器侧 `openstoryline_task_entry.py`）改为**仅 `max_logical_requests` 可随冻结身份预算变化**（允许建议值100），`max_observed_tokens_soft_threshold` 固定上限 **1,000,000**、`max_output_tokens_per_request` 固定上限 **32,768**（即使身份自洽soft=2,000,000或output=65,536也拒绝）；新增 `_strict_positive_int`（bool/str/float/非正数发送前拒绝，不先int()再视为合法）；request==identity budget与身份SHA校验保留；RequestBudgetExceeded传播与粗剪首次拒绝立即停止不变。容器实测9项PASS（含soft-2M-rejected、output-65536-rejected、conflict、tamper、bool/str/float-rejected）。
- **工作B（真实整链）**：真实 `apply_task_config`→`preparation_readiness`→`freeze_identity`（65文件、budget 100/1M/32768）→合成APPROVAL绑定实际身份→真实 `load_runtime_approval`→真实 `execute_once` 写出**实际request.json**→真实容器 `configure_budget`→`OPENSTORYLINE_MAX_*` env→真实 `request_ledger` 准入并在cap 100时阻塞+blocked_budget记录。仅fake Docker/凭据/Sampler/Agent替身/verifier。宿主6项PASS（A=100/B=60/C冲突/D篡改拒绝零send/G非法值/I任务切换无残留）；容器链2项PASS。
- **工作C（数字更正）**：请求公式修正为 **82（两轮×41句）＋2 validation＋16 Agent余量＝100**；41句为本ASR观测、非固定；16为规划空间非必用；**91改称"基于观测开销的估算基数"，非结构性最低值**；100不保证无限纠错/不强制恰好两轮。时间：第一轮工具start→finish=567.70s、请求span=557.20s；第二轮10次工具155.39s、请求span=144.18s（**127.16s仅首末start，非完整墙钟**）；**E01/R01-02最后MCP工具finish→agent_finished=43.646s**（修正旧~200s误表述）；两轮完整agent估算修正为约**1424.6s**（1800s内估算余量~375s，单次观测只支持可行性估算非保证）；1M仍为观测token软阈值非绝对计费硬上限。
- 部署：修改后 `openstoryline_task_entry.py` 经既有 `_SOURCE_OVERLAYS`（27项之一）只读挂载，容器内SHA `bc1d95c1…`==宿主，入required_frozen_sources（65项）；宿主entry仍只允许request_budget含max_logical_requests（soft/output字段宿主侧即拒）。未重建镜像、未改历史身份/批准。
- 测试：宿主FINAL-CHAIN 6 PASS＋容器fixed-ceiling 9 PASS＋容器chain-consume 2 PASS＋READINESS-01 7 PASS＋既有回归18+5 subtests PASS＋BUDGET-PROPAGATION 33项已验收。未覆盖：真实两轮E03运行、第二轮完整41次外推、43.646s迁移适用性。
- 保护：R03-01 raw/报告/身份/批准/manifest原字节保留；READINESS-01 manifest保留上一轮task_entry SHA作历史演进（不刷新）；本轮pre-change快照（361f9946…→bc1d95c1…）已留档；覆盖计数不变。
- 证据：`reports/analysis/OPENSTORYLINE-E03-BUDGET-READINESS-FINAL-CLOSEOUT-01/`（summary.md、request-budget-calculation.json、timing-token-assessment.md/csv、deployment.json、evidence/含实际request与redacted副本、pre-change/、tests/含容器与宿主日志、manifest 29项跨cwd回读0错）。
- 结论：**限定预算防线和真实冻结到容器消费者整链已离线验收；100次逻辑请求仍为待批准建议，真实R03-02尚未执行，不保证语义正确或预算内完成。**

## OPENSTORYLINE-E03-FULL-FLOW-R03-02（2026-11-01）：R03完整流程真实attempt——完整正常流程成功（批准预算100）

**一次新授权真实 E03 attempt 已执行完毕并走通完整正常流程：真实门禁（check-task-config→preflight→freeze-identity→APPROVAL→launch-detached）全部通过；容器输入/overlay 核验真实通过（docker inspect 实际 Source=E03 输入目录、只读挂载、容器内 bytes=11604798/SHA=`c66f380a…`=冻结、ffprobe 90.006583s/854×480/24000-1001/AAC 匹配；27 项 overlay 只读挂载、容器内 SHA=冻结）；E03 内容删除策略真实进入容器与内部粗剪提示；原生链真实走通 load_media→split_shots(skip)→local_asr→speech_rough_cut（**41 句内部请求全部成功、0 降级**，Agent 自主选删除区间 `[29190ms,38760ms]` 且**只调用一次粗剪后推进，实际删除 `[29190,30810]ms`，未完整落实Agent指定区间**）→plan_timeline_pro→render_video；Agent 正常返回 rc=0（无超时，agent wall 950.95s<1800s），完成判定真实写入 render_artifact_id 与 submission_export_pending → 宿主从最终 render 实际消费的 timeline 导出 output.mp4/cuts.json（1 cut `[29190,30810]`）→ 技术检查真实通过（帧率源/输出精确 24000/1001、exact_equal=true、0 ppm）→ 官方 verifier 完整执行一次（evaluation_complete=true、reward=0.0 合法）。R03-01 失败观察原样保留，不改写。**
- 配置：`env/video/openstoryline/task-configs/E03-full-flow-r03-02.json`；task_id `OPENSTORYLINE-E03-FULL-FLOW-R03-02`、task_kind=interview、run_id `20261101T054433Z-openstoryline-e03-full-flow-r03-02`；镜像 `sha256:9a1e876c…`；身份内容 SHA `fe05a470…`、身份文件 SHA `bb72d614…`、绑定 66 文件（48 interview 冻结源 + 27 overlay + task config）；APPROVAL `openstoryline-e03-full-flow-r03-02-approval-v1` 绑定身份文件 SHA。
- **预算整链验收**：配置 `request_budget.max_logical_requests=100` → 冻结身份 `{100,1000000,32768}` → request.json 同值 → 容器 configure_budget → ledger 上限 100；token 软阈值 1M 与单请求输出 32768 固定不变；实际使用 52/100（未触及预算）。
- 门禁真实通过：container-input-verify passed（实际 Source=E03 输入目录、bind、readonly、容器内 SHA `c66f380a…`/11604798B）；overlay-verify passed（**27 项**实际挂载、容器内 SHA=冻结）；load_runtime_approval 重校验通过；request.json 含 E03 内容删除目标、宿主自动提交职责、无 golden 泄漏、无 E02/assembly。
- 原生链真实：Agent工具8次，另有2次自动依赖；MCP节点共10 start/10 finish闭合，调用无错误（不等于语义正确）（load 1、split 1、local_asr 1、read_node_history 2、speech_rough_cut 1、plan 1、elementrec_transition 1、elementrec_text 1、render 1；elementrec 与 render 复用 call_id `call_33b6f9a2…`，自动依赖 start/end artifact 显式登记）。
- 内容删除：speech_rough_cut 41 句内部请求全成功（0 降级、0 解析失败），实际删除 `[29190,30810]ms`；rendered_source_intervals `[[0,29190],[30810,90007]]`、source 90007ms；该实际删除区间之外的源区间保留（机械区间结论，不代表目标陈述被完整删除）；timeline 2 video 项、**0 text/subtitle 项**（forbid_added_subtitles 生效）。
- 完成链路：render-candidates.jsonl 1 行（`timeline_source=exact_payload_match`、`candidate_state=bound`、`is_final=true`、timeline `plan_timeline_pro_1793512822.9198933`、payload SHA `19389bda…`）；agent-termination `agent_complete`；agent-result/session-status 均含 `render_artifact_id=render_video_1793512828.5942802`。
- 来源链：render 消费 timeline（2 video 项）→ output.mp4（10,671,049 B、SHA `bada9078…`、88.39s）与 render 源逐字节一致 → cuts.json（1 cut `[29190,30810]`，从同一 timeline 派生）。
- 技术检查：帧率 source `24000/1001` vs output `24000/1001` **exact_equal=true**、0 ppm、tolerance_passed=true；H.264 yuv420p 854×480/23.976fps；AAC 44100 立体声 non_silent、音视频同步；完整解码。
- 官方评分（一次）：verifier complete、evaluation_complete=true、judge SHA `cb5486bac…`==冻结；reward=0.0（`passed 0/1 cuts; ssim=0.9817, audio_xcorr=0.9966`；n_gt=1、n_submitted=1；honesty/audio/duration pass）。具体未命中：golden `[29.143,34.328]s` vs submitted `[29.19,30.81]s`，start_offset 0.047s 通过但 end_offset 3.518s 不通过（Agent 删 29190-30810 与 golden 29143-34328 尾部差约 3.5s）。评分完整、reward=0 合法，如实报告不改 cuts。
- 模型请求 52（agent 9 / mcp_sampling 41 / llm_validation 1 / vlm_validation 1）；usage 覆盖 52/52、sum_total_tokens 248,393（<1M 软阈值）；unknown_requests=[]、0 右删失、0 发送前预算拒绝。
- 资源：1570 行（boundary 2 + sample 1568），目标 0.5s；CPU 780.22 core-s / 有效 967.10s / 均值 0.807 core；mem.current 峰 5,479,772,160 B、kernel peak 6,946,013,184 B；I/O read 0 / write 974,848 B；netns lo/eth0 逐接口（eth0 rx≈4.30MB/tx≈1.36MB、lo rx/tx≈1.03MB 首末累计，非 API 专属）。采样窗 967.10s 覆盖 agent 相位 950.95s；容器 removal=removed；cleanup_errors=[]；host total_wall 1033.82s。
- 判定：程序完成（Agent rc=0 正常）+ 技术验收 PASS（帧率精确 24000/1001）+ 语义评分完整（reward=0 合法）+ 测量质量 complete（1570 行、netns 齐全、无缺测）。**R03 标完成。**
- 保护：未补跑、未追加 attempt、未改旧 raw/身份/批准/评分/manifest、未改生产代码、未提交推送；覆盖计数不变；R03-01 失败观察与历史 E03 原运行/独立 closeout 未改写。
- 证据：`reports/analysis/OPENSTORYLINE-E03-FULL-FLOW-R03-02/`（success-summary.md、final-report.md、result.json、analysis/curves/、launch-record.json、frozen-identity.json、APPROVAL.json、handover-run.md、raw-persistent-copy/ 独立副本：磁盘实际 58 文件 / manifest 登记 55 项 + 3 排除控制文件，逐文件 bytes/SHA 一致、diff -rq 0 差异；报告 manifest 69 项、analysis manifest 6 项，独立回读 0 错；raw manifest 55 项跨 cwd 回读 0 错）。
- 顺手更正：E01 的 43.646s 是最后工具完成后的 Agent 收尾，包含约 43.627s 最后一次模型请求，模型返回到 Agent 结束约 0.0098s（不修改历史证据，仅说明文字）。

## OPENSTORYLINE-ASSEMBLY-FULL-FLOW-R04-01（2026-11-01）：R04完整流程真实attempt——完整正常流程成功（assembly完成判定正常）

**一次新授权真实 assembly attempt 已执行完毕并走通完整正常流程：真实门禁（check-task-config→preflight→freeze-identity→APPROVAL→launch-detached）全部通过；容器输入/overlay 核验真实通过（docker inspect 实际 Source=12素材目录、只读挂载、容器内12文件SHA=冻结、27 项 overlay 只读挂载容器内 SHA=冻结）；原生 assembly 链真实走通 load_media→split_shots(skip)→understand_clips（12素材视觉理解）→filter_clips（**自主选恰好 K=4 个不同 clip：clip_0001/0002/0003/0005**）→group_clips（**按 storyboard slot 排序：clip_0002→clip_0001→clip_0005→clip_0003 = 10.mp4→4.mp4→5.mp4→3.mp4**）→read_node_history→plan_timeline_pro（4 video 项全片）→elementrec×2→render_video→read_node_history×2；Agent 正常返回 rc=0（无超时，agent wall 475.00s<1800s），**assembly 完成判定真实生效（task-kind-aware，不再误用 interview 的 local_asr/speech_rough_cut 必需节点）**，写入 render_artifact_id 与 submission_export_pending → 宿主从最终 render 实际消费的 timeline 导出 solution.mp4/solution.json（solution.json 4 段连续 half-open：source 10→4→5→3，全 source_range 从 0）→ 技术验收结构 10/10 PASS、媒体完整解码 → 归档清理正常。EXECUTION-02/03/04 历史失败及独立恢复原样保留，不改写。**
- 配置：`env/video/openstoryline/task-configs/ASSEMBLY-full-flow-r04-01.json`；task_id `OPENSTORYLINE-ASSEMBLY-FULL-FLOW-R04-01`、task_kind=assembly、run_id `20261101T062526Z-openstoryline-assembly-full-flow-r04-01`；镜像 `sha256:9a1e876c…`；身份内容 SHA `c8017dc9…`、身份文件 SHA `a53d682f…`、绑定 42 文件（assembly 冻结源 + 27 overlay + task config + 8 storyboard 模板）；APPROVAL `openstoryline-assembly-full-flow-r04-01-approval-v1` 绑定身份文件 SHA。
- **预算**：max_logical_requests=**60（assembly，未继承 E03 的 100）**、soft 1,000,000、单请求输出 32768——贯穿配置/冻结身份/request/容器ledger；filter_clips 8192/8192/retries0、group_clips 4096/16384/retries0；recursion_limit=32；实际用 29/60。
- 门禁真实通过：container-input-verify passed（实际 Source=素材目录、bind、readonly、容器内 SHA=冻结）；overlay-verify passed（**27 项**实际挂载、容器内 SHA=冻结）；load_runtime_approval 重校验通过；request.json 含 assembly 引导（Decide the 4 picked clips autonomously）、无 golden 泄漏、无 E02/E03 策略。
- **发送前唯一修复**：首次 `--preflight` 因 `assembly_offline_gate_invalid:assets_valid` 失败——`assembly-offline-gate.json` 的 assets 登记 `openstoryline_pilot_entry.py` SHA `9f280e94…` 过期（READINESS-01/FINAL-CLOSEOUT 改动后为 `fc0e4052…`）。按授权最小修复：留 pre-change 快照、重算 gate assets 为当前磁盘 SHA、保留修复前 preflight 记录到 evidence；修复后 preflight formal_ready=true。未改语义/预算/模型/工具。
- 原生链真实：工具 13 start/13 finish 全成功（load 1、split 1、understand 1、read_node_history 4、filter 1、group 1、plan 1、elementrec_transition 1、elementrec_text 1、render 1；elementrec 与 render 复用 call_id `call_f8ce9815…`，自动依赖 start/end artifact 显式登记）。
- 完成链路：render-candidates.jsonl 1 行（`timeline_source=exact_payload_match`、`candidate_state=bound`、`is_final=true`、timeline `plan_timeline_pro_1793514860.702099`、payload SHA `d9dd3ca1…`）；agent-termination `agent_complete`；agent-result/session-status 均含 `render_artifact_id=render_video_1793514865.485898`；submission_status `assembly_verified`、assembly_export `exported`。
- 来源链：filter(4)→group(10→4→5→3)→timeline(4 video项全片)→render→solution.mp4（2,549,661 B、SHA `4e1bc351…`、1080×608/30fps/AAC、21.049s）与 render 源逐字节一致 → solution.json 4 段（source 10→4→5→3）从同一 timeline 派生。
- 技术验收：verification ok=true，结构 10 项 check 全 PASS（schema/segment_count/contiguous/start_zero/source_format/source_range_full/no_duplicate/total_matches_media/half_open/frame-quantization 策略 `openstoryline-assembly-final-media-frame-quantization-v1`）；media full_decode_ok=true。
- 官方/语义：official_evaluation `not_integrated_official_evaluation`、reward=null、evaluation_complete=false；semantic_evaluation `not_evaluated`（故事板五字段匹配未机器证明；结构验收不等于选片语义正确）。
- 模型请求 29（agent 12 / mcp_sampling 15 / llm_validation 1 / vlm_validation 1）；usage 覆盖 29/29、sum_total_tokens 207,703（<1M 软阈值）；unknown_requests=[]、0 右删失、0 发送前预算拒绝。
- 资源：812 行（boundary 2 + sample 810），目标 0.5s；CPU 81.41 core-s / 有效 492.71s / 均值 0.165 core；mem.current 峰 1,552,654,336 B、kernel peak 1,553,055,744 B；I/O read 0 / write 765,952 B；netns lo/eth0 逐接口（eth0 rx≈1.40MB/tx≈4.38MB、lo rx/tx≈0.70MB 首末累计，非 API 专属）。采样窗 492.71s 覆盖 agent 相位 475.00s；容器 removal=removed；cleanup_errors=[]；host total_wall 494.38s。
- 判定：程序完成（Agent rc=0 正常）+ 技术验收 PASS（结构 10/10 + 解码）+ 语义/官方 not_evaluated/not_integrated（reward=null，如实记录）+ 测量质量 complete（812 行、netns 齐全、无缺测）。**R04 标完成。**
- 保护：未补跑、未追加 attempt、未改旧 raw/身份/批准/评分/manifest、未提交推送；覆盖计数不变；EXECUTION-02/03/04 历史失败与独立恢复未改写。
- 证据：`reports/analysis/OPENSTORYLINE-ASSEMBLY-FULL-FLOW-R04-01/`（success-summary.md、final-report.md、result.json、analysis/curves/、launch-record.json、frozen-identity.json、APPROVAL.json、handover-run.md、pre-change/、evidence/、raw-persistent-copy/ 独立副本：磁盘实际 56 文件 / manifest 登记 53 项 + 3 排除控制文件，逐文件 bytes/SHA 一致、diff -rq 0 差异；报告 manifest 69 项、analysis manifest 6 项，独立回读 0 错；raw manifest 53 项跨 cwd 回读 0 错）。

## VIMAX-G01-FULL-FLOW-R05-PLANNING-01（2026-11-01）：R05第一阶段（规划）——新规划通过，媒体待预算批准

**一次新授权真实 G01 规划 attempt 执行完毕并通过生产 plan_verifier：8 镜头 / 1 角色 / 8 相机 / 7 过渡边，0 媒体请求，13 LLM 逻辑请求（37,873 tokens），attempt 77.99s，容器自然退出与清理核验。** 新规划，未复用历史 G01/G02/G03/musicians storyboard/camera_tree。规划产物（storyboard/camera_tree/characters/8 shot_description）已冻结；为媒体阶段提供数量依据。**规划通过不等同成片完成；本记录是媒体阶段的前置，不增加完整生成任务覆盖数。**
- run_id：`g01-full-flow-r05-planning-01-20261101T070459Z-3f4e2dab`；session：`g01-full-flow-r05-planning-01`；镜像 `sha256:a97ea6076fbcd456ada0d0e1267ebf50058daa52698e0996cffaf66da1f176f3`；身份文件 SHA `9085c6100b75cbf907777b9aa9048b91aed4bf692c41b0c356035e066d5a6aca`（= APPROVAL identity_sha256）。
- 输入：源故事 `photographer_urban_timelapses_typeA.json` SHA `aaf6545c…`（metadata requested_shots=8）；registered script SHA `447e4d88…`。8 镜头/5s/40s/landscape；720p/30fps/无音轨；单首帧 i2v、variation_type=small。
- plan_verifier：ok=true，14 项 checks 全 True（fresh session/script/expected_shot_count/schema/camera acyclic/capability/characters/native success/无源复制/请求记录/媒体缺席）；语义等价 not machine-proven。
- 请求/资源：13 逻辑（outer 2 + inner 11）、sum_total_tokens 37,873（<250K）；155 样本、mem 峰 122MB、CPU null（counter_boundary 如实记录）、netns eth0 rx≈92KB/tx≈181KB；覆盖 75.97s。
- 媒体预算草案（media-budget-draft.json/.md）：主体 8、过渡 7、角色 1；image_creates 估算 5（3 肖像+2 候选）、video_creates 估算 15（8+7）、下载 20、轮询上界 900；work/closeout 采用 5400/600（当前正式配置口径，media entry 默认 300 冲突列待确认）；**不沿用旧 G01"19图/15视频"**。媒体阶段未启动、未创建媒体身份/批准，需另批批准。**（随后经 R05-MEDIA-BUDGET-AND-RESOURCE-CLOSEOUT-01 修订：真实生产分支 `camera.parent_shot_idx is None OR camera.missing_info is not None` 使 8 相机全命中候选分支，媒体预算修正为 image_creates 19、video_creates 15、下载 34、轮询上界 1350、复下载 15；原 5/20 draft 保留为历史。）**
- 发送前唯一修复：preflight 首次因 adapter-src 与镜像 divergence（`script2video_pipeline.py`、`image_generator_bailian_api.py`）失败——这两个是已验收宿主生产 adapter 修复；将 MEDIA_FIX_RELS 允许集扩展为三个已修复文件。pre-change 快照 `pre-change/host_runner.py.pre`（旧 `0b54899e…`→新 `d7a4b17a…`）。
- 证据：`reports/analysis/VIMAX-G01-FULL-FLOW-R05-PLANNING-01/`（summary.md、final-report.md、result.json、analysis/curves/、identity、APPROVAL、handover、media-budget-draft、pre-change、raw-persistent-copy/ 独立副本：磁盘 44 文件 / manifest 43 项，diff 0、跨 cwd 回读 0 错）。
- R05 状态：**新规划通过；媒体一次正式 attempt 已执行（VIMAX-G01-FULL-FLOW-R05-MEDIA-01，媒体生成/concat 成功但宿主 COMPLETE v3 final-path 校验失败，失败观察）；未标完整流程完成。**
- 修订（VIMAX-G01-R05-MEDIA-BUDGET-AND-RESOURCE-CLOSEOUT-01）：工作A 媒体预算按真实生产分支修正为 19 图/15 视频/34 下载（8 相机全候选 + 3 肖像），新 helper `media_budget_helper.py`；工作B 从原始 155 周期样本独立派生有效区间 77.068s / CPU 4.575 core-s / write 98KiB（边界法总量因 boundary_end 缺失不可得，partial）；工作C 修复 planning host_runner 采样收尾顺序（agent_completed 先 sampler.stop 读 boundary_end 再 docker wait 自然退出），真实 network=none 容器测试验证；媒体 entry 无同类缺陷。详见该修订目录（media-budget-derivation.json、resource-derived-evidence.json、deployment.md、tests/、manifest）。
- 修订（VIMAX-R05-FOUR-GAP-OFFLINE-FINAL-CLOSEOUT-01）：缺口A 规划entry完成握手（wait_for_boundary_ack + BOUNDARY-ACK，boundary_end_read_before_container_exit 为真实结果变量）关闭退出竞态；缺口B 空壳测试替换为真实 host 控制链 + 真实 entry 生产者 + 真实容器协议测试；缺口C 按真实 _poll_task 时序推导轮询上界每任务 92（floor(window/interval)+2）、15任务聚合 1380，ledger 显式 cap 1800 另计，closeout 另计；缺口D helper 与生产条件严格一致（missing_info is not None，空串/空白串仍候选）+ 非法参数/冲突拒绝。详见该修订目录（summary.md、final-report.md、pre-change/、tests/、manifest）。
- 修订（VIMAX-R05-PRODUCTION-BOUNDARY-AND-VALIDATION-FINAL-01）：工作A 共享生产函数 `read_boundary_and_send_ack`（host_runner.py）由 run_attempt 实际调用、测试调用同一函数（删除镜像实现）；工作B ACK schema v2 全字段/类型/run/session/attempt/容器身份/COMPLETE token 校验（陈旧/重复/错归属/partial/超时/写失败/原子落盘），per-resource 指标贯通 run-record→observation_quality（CPU成功≠整体complete）；工作C helper 派生0冲突（显式99 vs derived 0 拒绝）与尝试次数严格整数（拒 bool/float/str/NaN/Inf/0/负）。测试 boundary 24 + helper 40 + poll 6 + 容器协议 PASS；详见该修订目录。
- 修订（VIMAX-R05-OBSERVATION-QUALITY-AND-ACK-SEMANTICS-CLOSEOUT-01）：工作A 新增生产质量归纳函数 `derive_observation_quality`（host_runner.py）由 run_attempt 实际调用、summarize_run/final_outcome 消费——逐指标（CPU/IO 需 start+end、memory gauge/peak 需 end、零值有效）与整体 complete/partial/unknown 贯通 run-report，ACK 分 host_write/entry_accept/超时/unknown，rows_lost=0 不等同测量 complete；工作B ACK 选幂等消息契约（方案一），删除不可达 seen_accept/duplicate_ignored，更正测试不再声称"重复读取被拒绝"。测试 boundary 33 + helper 40 + poll 6 + 容器协议 PASS；entry 动态验证范围为握手子链（完整 run_native 仅源码核对）。详见该修订目录。
- 修订（VIMAX-R05-OBSERVATION-QUALITY-CORRECTNESS-FINAL-01）：统一指标 schema（`_metrics_from_snapshot` 共享 cpu/memory_current/memory_kernel_peak/io_read/io_write，生产者/归纳/测试同一映射）；开始边界逐指标检查（interval 需 start+end 计数 present 且 end>=start 非回退，缺一端→unknown）；overall 真正汇总 ACK/丢行/写流错误/netns/scope（各必需维度 complete 才 complete，无内部矛盾）；entry 观察记录验证 run/session/attempt/container/complete_token 归属（错token/错run/容器/仅status无ack→entry_accept 非ok）；五个反例（A 正常一致/B 无start CPU非complete/C ACK失败非complete/D 丢行非complete/E 错token拒绝）修复。测试 boundary 40 + helper 40 + poll 6 + 容器协议 PASS；entry 动态范围仍为握手子链。详见该修订目录。

## VIMAX-G01-FULL-FLOW-R05-MEDIA-01（2026-11-01）：R05第二阶段（媒体）正式 attempt——媒体生成与原生拼接成功、宿主 COMPLETE v3 最终路径校验失败（完整采集的失败观察）

**一次新授权真实媒体 attempt 执行完毕（attempt 1/retry 0）：媒体阶段真实发送并全部成功（19逻辑图片、15视频、34正常下载、原生 concat 生成 40.000s 有效成片），但宿主生命周期以 `final_artifact_missing`（rc=1）结束，R05 未标完整流程完成。** 未补跑、未独立恢复、attempt 开始后未修改生产代码。
- run_id：`g01-full-flow-r05-media-01-20261101T121447Z-18973ef8`；session：`g01-full-flow-r05-media-01`；source session：`g01-full-flow-r05-planning-01`；镜像 `sha256:a97ea6076fbcd456ada0d0e1267ebf50058daa52698e0996cffaf66da1f176f3`；新媒体身份文件 SHA `b5d37ebf9bf3e7c78262d50b076ca919f60ed396181815775aed5ace21d4db18`（= APPROVAL frozen_identity_sha256，绑定源规划身份 `9085c610…` 与全部语义文件，非 synthetic）。
- 配置：`env/video/vimax/task-configs/G01-full-flow-r05-media-01-formal.json`；staged-planning 与 R05 规划 raw 逐字节一致（diff -rq 0）；零重新规划。
- 预检全部通过：planning source、19/15/34（8 相机全候选＋3 肖像）、budget→env→ledger（video_polls=1380 ledger cap 覆盖默认 1800）、audio=false→payload（远端 usage.audio=false 15/15）、adapter 只读挂载+容器内 SHA=冻结（9a35f7b1…/612976cc…）、COMPLETE v3、资源流、原生 concat 顺序。本轮 fresh 测试：媒体预算 helper 40、轮询上界 6、视频创建策略 17、图片创建策略 25、COMPLETE v3 定向正反例、verify_identity_approval、docker image inspect 全 PASS（旧日志不计）。
- 门禁真实通过：verify_identity_approval PASS（非 synthetic）；容器归属、cgroup 采样、startup gate 全放行；adapter 容器内 SHA==冻结。
- **预算/账本**：image_generations 19/19、image_create_http_send 19（0 429）、video_create 15/30（尝试口径）、video_polls 55/1380、media_downloads 34/34、llm_calls 26/80；observed_output_tokens_total 4548（<500000 软阈值，非金额硬上限）；`unclosed_requests={}` 全闭合。
- 媒体产物：3 肖像（front/side/back）＋16 候选（8×2）＝19 图；8 主体（shots/0..7/video.mp4）＋7 辅助过渡（shots/1..7/transition_video_from_shot_0.mp4）＝15 视频，全部 H.264/1280×720/30fps/5.000s/0 音轨；远端 15/15 SUCCEEDED（usage.audio=false）；正常下载 34 全有效，closeout 复下载 15 落盘复核。
- **成片（原生 concat 产物）**：`workspace/.working_dir/g01-full-flow-r05-media-01/script2video/final_video.mp4`＝40.000s / H.264 High / 1280×720 / yuv420p / r_frame_rate=avg_frame_rate=30/1 / 0 音轨 / 完整解码 OK / bytes 12,477,388 / SHA `4c402731…`；顺序主体 0→7，时长 8×5s 一致。
- **根因（确定性，宿主消费者与既有生产者契约不一致）**：生产者 `vimax_adapters.vimax_render_video` 把 `final_video_path` 写成工作区相对路径 `.working_dir/<session>/script2video/final_video.mp4`；宿主 `assess_complete_marker.final_path_owned` 以 `os.path.relpath(final_path,'/workspace')` 判定其越出 /workspace（以 `..` 开头）→ `final_artifact_accepted=False` → 终态 `final_artifact_missing`（rc=1）。实际产物在磁盘上存在且有效。历史 G01 媒体（RUNTIME-CONFIRM-02）同格式相对路径被旧宿主接受（无 v3 结构化检查）；当前 v3 检查首次在成功 concat 路径触发（musicians EXECUTION-02 在 concat 前即 render_failed）。发送前预检正例用绝对 `/workspace/…` 构造，未覆盖真实相对路径格式（如实记录盲区）。
- 资源：1238 样本；CPU 166.60 core-s / 有效 619.24s / 均值 0.269 core；mem.current 末 499,126,272 B、kernel peak 1,547,530,240 B、sampled max 1,530,765,312 B；I/O read 0 / write 200,704 B；netns eth0 rx≈93.5MB/tx≈266.9MB（逐接口累计，非 API 专属）；容器 removal=removed；host total_wall 620.52s。阶段分列：规划 77.99s、媒体 Agent/必需工作 619.2s、remote closeout（<10s）、审批等待不计入媒体窗口。测量质量 complete。
- 判定：程序 FAIL（rc=1、final_artifact_missing）；技术=媒体生成/下载 PASS＋原生 concat PASS（40.000s 有效成片）＋宿主验收 FAIL（final-path 所有权）；语义 not_evaluated；官方 not_integrated/not_run、reward=null；测量质量 complete。
- 保护：未补跑、未追加 attempt、未独立恢复、未改生产代码/冻结配置/镜像；R01–R04 与历史证据原样保留；覆盖计数不变；未提交推送、未改 execution_authorization。
- 证据：`reports/analysis/VIMAX-G01-FULL-FLOW-R05-MEDIA-01/`（launch-record.json、final-report.md、failure-observation-summary.md、result.json、media-sha-manifest.json、build_manifest.py、artifacts/manifest_lib.py、raw-persistent-copy/ 独立副本 129 文件逐文件 bytes/SHA 一致、raw manifest 129 项、报告 manifest 138 项跨 cwd 独立回读 0 错）。raw：`data/raw/generated/VIMAX-G01-FULL-FLOW-R05-MEDIA-01/g01-full-flow-r05-media-01/`。
- R05 状态：**新规划通过＋媒体一次正式 attempt 已执行（媒体生成/concat 成功、宿主验收失败观察），未标完整流程完成**。后续修复（生产者路径契约或消费者所有权判定）与重新运行需单独授权。

## VIMAX-G01-FULL-FLOW-R05-MEDIA-02（2026-11-01）：R05第二阶段（媒体）修复后正式 attempt——完整正常流程成功，R05 标完成

**一次新授权真实媒体 attempt 执行完毕并走通完整正常流程（attempt 1/retry 0）：媒体阶段真实发送并全部成功，原生 concat 产出 40.000s 有效成片，修复后宿主 COMPLETE v3 全维度验收通过（含 `final_path_resolution`），宿主终态 `native_agent_done`（rc=0）、清理回验正常。R05 标完整流程完成。MEDIA-01 失败观察与全部证据原样保留，未复用其媒体产物。**
- run_id：`g01-full-flow-r05-media-02-20261101T141641Z-6e4a9447`；session：`g01-full-flow-r05-media-02`；source session：`g01-full-flow-r05-planning-01`；镜像 `sha256:a97ea6076fbcd456ada0d0e1267ebf50058daa52698e0996cffaf66da1f176f3`；身份文件 SHA `7b8d66340d719ea436e3358d2ecab0333b69102b2c4f6a711c0699155ae5e103`（= APPROVAL frozen_identity_sha256，非 synthetic；绑定源规划 `9085c610…`、修复后 host_runner `fe7d6b4d…` 与全部语义文件）。
- 配置：`env/video/vimax/task-configs/G01-full-flow-r05-media-02-formal.json`；staged-planning 与规划 raw 逐字节一致；新工作区无旧媒体；零重新规划。
- 预检（发送前）全 PASS：planning source、19/15/34、budget→env→ledger（video_polls=1380 硬 cap）、audio=false 贯通、adapter 只读挂载+容器内 SHA=冻结、修复后 host_runner 绑定、COMPLETE v3、原生 concat、资源流/startup gate。本轮 fresh 测试：修复链 42（final_path 12 + schema 19 + lifecycle 4 + race 7）、预算 helper 40 + 轮询 6、容器内视频策略 17/17、容器内图片策略 25/25、resolve_final_artifact_path 定向正反例全 PASS（旧日志不计）。
- **预算/账本**：image_generations 19/19、image_create_http_send 19（0 429/0 重试）、video_create 15/30（尝试口径）、video_polls 148/1380、media_downloads 34/34、llm_calls 26/80；observed_output_tokens_total 4475（<500000 软阈值，非金额硬上限）；`unclosed_requests={}` 全闭合。
- 媒体产物：3 肖像＋16 候选＝19 图；8 主体（shots/0..7/video.mp4）＋7 辅助（shots/1..7/transition_video_from_shot_0.mp4）＝15 视频，全部 H.264/1280×720/30fps/5.000s/0 音轨；远端 15/15 SUCCEEDED（usage.audio=false）；正常下载 34，closeout 复下载 15。
- **成片（原生 concat）**：`workspace/.working_dir/g01-full-flow-r05-media-02/script2video/final_video.mp4`＝40.000s / H.264 High / 1280×720 / yuv420p / 30/1 fps / 0 音轨 / 完整解码 OK / bytes 13,986,232 / SHA `639e778b68eb101d…`；顺序主体 0→7，时长 8×5s 一致。
- **final_path_resolution 证据（修复验证）**：生产者原生工作区相对路径 `.working_dir/g01-full-flow-r05-media-02/script2video/final_video.mp4` 未被改写为绝对路径；run-record `complete_marker_assessment.final_path_resolution`＝`{owned:true, exists:true, workspace_relative:…, host_path:<本次 raw>/workspace/.working_dir/…, reason:null}` → final_path_owned/exists/accepted 全 True → 宿主 `native_agent_done`（rc=0）。
- 资源：3124 样本；CPU 185.82 core-s / 有效 1563.33s / 均值 0.119 core；mem kernel peak 1,558,937,600 B / sampled max 1,551,814,656 B；I/O read 0 / write 200,704 B；netns 784 行、eth0 rx≈105.1MB/tx≈258.6MB（逐接口累计，非 API 专属）；容器 removal=removed；host total_wall 1564.65s。阶段分列：规划 77.99s、媒体 Agent/必需工作 1563.3s、remote closeout（收尾窗内）、审批等待不计入媒体窗口。测量质量 complete。
- 判定：程序完成（Agent rc=0 + COMPLETE v3 全维度 + 宿主 native_agent_done）+ 技术 PASS（媒体生成/下载/原生 concat/final 规格全达标）+ 语义 not_evaluated + 官方 not_integrated/not_run（reward=null）+ 测量质量 complete。**R05 标完整流程完成。**
- 保护：MEDIA-01 失败观察/raw/manifest（138/129）原样保留；未补跑、未独立恢复、未改生产代码；覆盖计数不变；未提交推送、未改 execution_authorization；未启动 R06–R09。
- 证据：`reports/analysis/VIMAX-G01-FULL-FLOW-R05-MEDIA-02/`（launch-record.json、final-report.md、success-summary.md、result.json、media-sha-manifest.json、build_manifest.py、artifacts/manifest_lib.py、raw-persistent-copy/ 独立副本 133 文件逐文件 bytes/SHA 一致（副本仅多 1 个 manifest.json）、raw manifest 133 项、报告 manifest 142 项跨 cwd 独立回读 0 错）。raw：`data/raw/generated/VIMAX-G01-FULL-FLOW-R05-MEDIA-02/g01-full-flow-r05-media-02/`。

## OPENSTORYLINE-E02-FULL-FLOW-R02-01（2026-11-01）：R02完整流程唯一真实attempt——完整正常流程成功

**一次新授权真实 E02 attempt 已执行完毕并走通完整正常流程：真实门禁（check-task-config→preflight→freeze-identity→APPROVAL→launch-detached）全部通过；容器输入/overlay 核验真实通过（docker inspect 实际 Source=E02 输入目录、只读挂载、容器内 bytes=689288/SHA=`13d716c6…`=冻结、ffprobe 30.029317s/854×480/60000-1001/AAC 匹配；25 项 overlay 只读挂载、容器内 SHA=冻结）；原生 interview 链真实走通 load_media→split_shots(mode=skip)→local_asr→speech_rough_cut→plan_timeline_pro→render_video 并成功渲染；Agent 正常返回 rc=0（无超时，agent wall 479.66s<1800s），完成判定真实写入 render_artifact_id 与 submission_export_pending → 宿主从最终 render 实际消费的 timeline 正常导出 output.mp4/cuts.json → 技术检查真实通过（帧率源/输出精确 60000/1001、exact_equal=true、0 ppm，未出现历史 E02 的 2997/50 舍入）→ 官方 verifier 完整执行一次（evaluation_complete=true、reward=0.0 合法）。E02-EXPANSION-01/02 历史失败及独立恢复原样保留，不改写。**
- 配置：`env/video/openstoryline/task-configs/E02-full-flow-r02-01.json`；task_id `OPENSTORYLINE-E02-FULL-FLOW-R02-01`、task_kind=interview、run_id `20261101T025952Z-openstoryline-e02-full-flow-r02-01`；镜像 `sha256:9a1e876c…`；身份内容 SHA `251cda2368…`、身份文件 SHA `f21db2534a…`、绑定 65 文件（49 interview 冻结源 + 25 overlay + task config）；APPROVAL `openstoryline-e02-full-flow-r02-01-approval-v1` 绑定身份文件 SHA。
- 门禁真实通过：container-input-verify passed（实际 Source=E02 输入目录、bind、readonly、容器内 SHA `13d716c6…`）；overlay-verify passed（25 项实际挂载、容器内 SHA=冻结）；load_runtime_approval 重校验通过；request.json 含 E02 填充音目标（非 E01）、明确宿主自动提交职责、edit_policy 未继承 E03 content_deletion/assembly。
- 原生链真实：Agent工具8次，另有2次自动依赖；MCP节点共10 start/10 finish闭合，调用无错误（不等于语义正确）（load 1、split 1、local_asr 1、read_node_history 2、speech_rough_cut 1、plan 1、elementrec_transition 1、elementrec_text 1、render 1；elementrec 与 render 复用 call_id `call_52059561…`，自动依赖 start/end artifact 显式登记）。
- 完成链路：render-candidates.jsonl 1 行（`timeline_source=exact_payload_match`、`candidate_state=bound`、`is_final=true`、timeline `plan_timeline_pro_1793502522.3580658`、payload SHA `24c72d13…`）；agent-termination `agent_complete`；agent-result/session-status 均含 `render_artifact_id=render_video_1793502527.8456743`。
- 来源链：render 消费 timeline（3 个 video 项；rendered_source_intervals [[750,2970],[3810,5190],[6710,28910]]、source_duration 30029ms）→ output.mp4（834,081 B、SHA `6a628611…`、25.8s）与 render 源逐字节一致 → cuts.json（4 cuts：[0,750]/[2970,3810]/[5190,6710]/[28910,30029]，从同一 timeline 派生）。
- 技术检查：帧率 source `60000/1001` vs output `60000/1001` **exact_equal=true**、0 ppm、tolerance_passed=true；H.264 yuv420p 854×480/59.94fps；AAC 44100 立体声 non_silent、音视频同步；完整解码。
- 官方评分（一次）：verifier complete、evaluation_complete=true、judge SHA `cb5486bac…`==冻结；reward=0.0（passed 0/2 cuts；ssim=0.9914、audio_xcorr=0.9873、honesty/audio/duration pass；n_gt=2、n_submitted=4）。评分完整、reward=0 合法，Agent 自主剪切与 golden 不完全对齐，如实提交评分。
- 模型请求 16（agent 9 / mcp_sampling 5 / llm_validation 1 / vlm_validation 1）；usage 覆盖 16/16，sum_total_tokens 107,437（<1M 软阈值）；unknown_requests=[]、无右删失。
- 资源：808 行（boundary 2 + sample 806），目标 0.5s；CPU 341.88 core-s / 有效 497.06s / 均值 0.688 core；mem.current 峰 5,967,896,576 B、kernel peak 6,940,819,456 B；I/O read 0 / write 462,848 B；netns lo/eth0 逐接口（eth0 rx≈2.15MB/tx≈0.62MB、lo rx/tx≈0.50MB 首末累计，非 API 专属）。采样窗 497.06s 覆盖 agent 相位 479.66s；容器 removal=removed；cleanup_errors=[]；host pre_archive_wall 521.52s。
- 判定：程序完成（Agent rc=0 正常）+ 技术验收 PASS + 语义评分完整（reward=0 合法）+ 测量质量 complete（808 行、netns 齐全、无缺测）。
- 保护：未补跑、未追加 attempt、未改旧 raw/身份/批准/评分/manifest、未改生产代码、未提交推送；覆盖计数不变；E02-EXPANSION-01/02 失败观察未改写。
- 证据：`reports/analysis/OPENSTORYLINE-E02-FULL-FLOW-R02-01/`（success-summary.md、final-report.md、result.json、analysis/curves/、launch-record.json、frozen-identity.json、APPROVAL.json、handover-run.md、raw-persistent-copy/ 独立副本56文件逐文件 bytes/SHA 一致；报告manifest 70项、analysis manifest 6项，独立回读0错；raw manifest 56项跨 cwd 回读0错）。

## OPENSTORYLINE-E01-FULL-FLOW-R01-02（2026-10-31）：R01完整流程第二次真实attempt——完整正常流程成功

**一次新授权真实 E01 attempt 已执行完毕并走通完整正常流程：真实门禁（check-task-config→preflight→freeze-identity→APPROVAL→load_runtime_approval→launch-detached）全部通过；容器输入/overlay 核验真实通过（实际只读挂载、容器内 bytes/SHA=冻结、25 项 overlay）；原生 interview 链真实走通 load_media→split_shots→local_asr→speech_rough_cut→plan_timeline_pro→render_video 并成功渲染；Agent 正常返回 rc=0（无超时，agent wall 1076.69s<1800s），完成判定真实写入 render_artifact_id 与 submission_export_pending → 宿主从最终 render 实际消费的 timeline 正常导出 output.mp4/cuts.json → 技术检查真实通过 → 官方 verifier 完整执行一次（evaluation_complete=true、reward=0.0 合法）。上一轮 R01-01 失败观察原样保留，不改写。**
- 配置：`env/video/openstoryline/task-configs/E01-full-flow-r01-02.json`；task_id `OPENSTORYLINE-E01-FULL-FLOW-R01-02`、task_kind=interview、run_id `20261031T183007Z-openstoryline-e01-full-flow-r01-02`；镜像 `sha256:9a1e876c…`；身份内容 SHA `9cc0e363…`、身份文件 SHA `7e9cbbb8…`、绑定 65 文件（49 interview 冻结源 + 25 overlay + task config）；APPROVAL 绑定身份文件 SHA。
- 门禁真实通过：container-input-verify passed（实际 Source=E01 输入目录、bind、readonly、容器内 SHA `a9bce74a…`）；overlay-verify passed（25 项实际挂载、容器内 SHA=冻结）；load_runtime_approval 重校验通过。
- 原生链真实：工具 11 start/11 finish 全成功（load 1、split 1、local_asr 1、speech_rough_cut 1、plan 1、render 1、elementrec_transition 1、elementrec_text 1、read_node_history 3；elementrec 与 render 复用 call_id `call_44f36897…`，自动依赖 start/end artifact 显式登记，与历史 E01 一致）。
- 完成链路：render-candidates.jsonl 1 行（`timeline_source=exact_payload_match`、`candidate_state=bound`、`is_final=true`、timeline `plan_timeline_pro_1793472429.4117346`、payload SHA `9ae7447c…`）；agent-termination `agent_complete`；agent-result/session-status 均含 `render_artifact_id=render_video_1793472486.4214995`。
- 来源链：render 消费 timeline（2 个 video 项；11 是含自动依赖的 MCP 节点调用数，不是片段数；rendered_source_intervals [[490,21990],[22940,36980]]、source_duration 37000ms）→ output.mp4（2,009,938 B、SHA `ccfd7d62…`、35.54s）与 render 源逐字节一致 → cuts.json（3 cuts：[0,490]/[21990,22940]/[36980,37000]，从同一 timeline 派生）。
- 技术检查：帧率 source 25/1 vs output 25/1 exact_equal=true、0 ppm、tolerance_passed=true；H.264 yuv420p 854×480/25fps；AAC 44100 立体声 non_silent=true；完整解码。
- 官方评分（一次）：verifier complete、evaluation_complete=true、judge SHA `cb5486bac…`==冻结；reward=0.0（passed 0/1 cuts；ssim=0.9849、audio_xcorr=0.980994、honesty/audio/duration pass；n_gt=1、n_submitted=3）。评分完整、reward=0 合法。
- 逻辑请求 36（agent 10 / mcp_sampling 24 / llm_validation 1 / vlm_validation 1）；usage 覆盖 36/36，sum_total_tokens 205,470（<1M 软阈值）；unknown_requests=[]、无右删失。
- 资源：1757 行（boundary 2 + sample 1755），目标 0.5s、周期中位 0.6015s、最大 gap 0.7068s；CPU 471.43 core-s / 有效 1078.44s / 均值 0.437 core；mem.current 峰 5,525,487,616 B、kernel peak 6,944,653,312 B；I/O read 0 / write 774,144 B；netns lo/eth0 逐接口（eth0 rx≈5.53MB/tx≈1.36MB、lo rx/tx≈0.78MB 首末累计，非 API 专属）。采样窗 1078.44s 覆盖 agent 相位 1076.69s；容器 removal=removed；cleanup_errors=[]；host pre_archive_wall 1105.44s。
- 判定：程序完成（Agent rc=0 正常）+ 技术验收 PASS + 语义评分完整（reward=0 合法）+ 测量质量 complete（1757 行、netns 齐全、无缺测）。
- 保护：未补跑、未追加 attempt、未改旧 raw/身份/批准/评分/manifest、未改生产代码、未提交推送；覆盖计数不变；R01-01 失败观察未改写。
- 证据：`reports/analysis/OPENSTORYLINE-E01-FULL-FLOW-R01-02/`（success-summary.md、result.json、analysis/curves/、launch-record.json、frozen-identity.json、APPROVAL.json、handover-run.md、raw-persistent-copy/ 独立副本59文件逐文件 bytes/SHA 一致；报告manifest 72项、raw manifest 56项、analysis manifest 10项，独立回读0错）。

## VIDEO-COMPLETION-RESPONSIBILITY-AND-DEADLINE-REPAIR-01（2026-10-31）：限定离线修复——职责说明/产物-终止分离/粗剪降级/媒体竞态/程序-技术结果分离

**只做离线修复与生产链验收，未运行真实任务、未启动 R01/R02。** 围绕 R01 暴露的四个确定性缺口完成最小修复，测试全部只 fake Docker/凭据/模型等外部边界，真实控制链/节点/宿主函数真实执行：
- 工作A（职责说明）：interview/assembly 请求文本与引导统一——Agent 完成原生剪辑/组接与 render，宿主从最终渲染实际消费的 timeline 自动导出 output.mp4/cuts.json（interview）或 solution.mp4/solution.json（assembly）；官方 instruction 交付契约保留；不注入旧 cuts/golden/旧选片；不通过截断 Agent 伪造成完成。断言真实写盘 request.json（E01/E02 interview、E03 content-deletion、assembly 契约、切换无残留）。
- 工作B（产物证据 vs Agent 终止）：成功 render 当场原子写 `render-candidates.jsonl`（session/node/artifact/tool_call_id、timeline 身份、产物引用、时间；is_final=false）；完成判定通过才置 is_final；`agent-termination.json` 单独记录正常/超时/异常/预算终止；宿主权威选择器不变，超时保持 not_verified、不导出不评分。宿主级验证：render 候选存在 + Agent rc=124 → 不导出/不评分/清理正常。
- 工作C（粗剪降级）：speech_rough_cut 返回 payload 携带 `degradation_records`（节点/句/错误类型/动作/完整性）+ `internal_requests` 计账；不再因 is_error=false 概括为内部请求全部成功；语义不变（保留原句、无自动重试/并发/提额）。
- 工作D（ViMax 媒体竞态）：媒体 runner 截止/退出前复检 COMPLETE（规划 runner 已有同等逻辑）；COMPLETE 内容单独判定（main_agent_returncode/render_tool_ok/final_video_path），错误归属记为 complete_marker_invalid；真实 start_attempt + FakeOps 时序复现 A–G（正常/临界/超时/损坏/失败/异常/证据落盘）。
- 工作E（VideoWeaver 分离）：judge 新增程序终止检查（program_termination/entry_rc_normal_exit/pipeline_rc_normal_exit/program_not_timeout/program_no_exception）；缺失/非法/bool/未知 rc 不为 0；媒体合格但程序超时/异常仍不汇总为完整连续成功。
- 部署：新增 1 项 overlay（node_interceptors.py，现 24 项，只读挂载到生产 import 路径，容器内 SHA=宿主源码）；assembly-offline-gate assets 刷新；source-manifest 三条目同步。未创建正式身份/批准/attempt。
- 测试（本轮实测）：宿主 OpenStoryline 148 passed+9 subtests、ViMax 11、VideoWeaver 32；容器内（真实镜像+24 overlay+network=none）completion_recovery 22、reliability_unit 29(skip1)、selection_contract 19、confirmation_flow 16、native_entry_repair 8、request_budget 6、completion_responsibility 5、speech_rough_cut_degradation 4。
- 保护：未改模型/预算/推理；未改历史 raw/身份/批准/评分/manifest；未改 video-use 生产代码；未提交推送。证据 `reports/analysis/VIDEO-COMPLETION-RESPONSIBILITY-AND-DEADLINE-REPAIR-01/`（summary/state-design/deployment/pre-change-snapshots/new-tests/manifest 21 项跨 cwd 回读 0 错）。

## OPENSTORYLINE-E01-FULL-FLOW-R01-01（2026-10-31）：R01完整流程第一次真实attempt——失败观察（render成功但1800s截止）

**一次新授权真实 E01 attempt 已执行完毕：真实门禁（check-task-config→preflight→freeze→approval→launch-detached）全部通过；容器输入/overlay 核验真实通过（实际挂载源、容器内 bytes/SHA、23 项 overlay）；原生 interview 链真实走通 load_media→split_shots→local_asr→speech_rough_cut→plan_timeline_pro→render_video 并成功渲染 31.64s/854×480/25fps/AAC 视频；但 Agent 在 render 后整理阶段被 1800s agent 截止（`step_share_deadline_expired`，rc=124）终止，容器入口未执行 `persist_completion_check`（无 agent-result.json）→ 宿主导出/技术检查/官方评分未运行，submission_status=not_verified、verifier=not_run_no_submission、reward=null。属完整采集的失败观察，不补跑、不追加第二次 attempt。**
- 配置：`env/video/openstoryline/task-configs/E01-full-flow-r01-01.json`；task_id `OPENSTORYLINE-E01-FULL-FLOW-R01-01`、task_kind=interview、run_id `20261031T142400Z-openstoryline-e01-full-flow-r01-01`；镜像 `sha256:9a1e876c…`；身份 SHA `9890204575…`、身份文件 SHA `ef6cfa8e…`、绑定 65 文件；APPROVAL 绑定身份文件 SHA。
- 门禁真实通过：container-input-verify passed（实际 Source=E01 输入目录、bind、readonly、容器内 SHA `a9bce74a…`、ffprobe 规格匹配）；overlay-verify passed（23 项实际挂载、容器内 SHA=冻结）；load_runtime_approval 重校验通过。
- 原生链真实：工具 12 start/12 finish 全成功（load 1、split 1、local_asr 1、speech_rough_cut 1、plan 1、render 1、elementrec_transition 1、elementrec_text 1、read_node_history 4；elementrec 与 render 复用 call_id `call_f4ef0fba…`，自动依赖 start/end artifact 显式登记）。render `render_video_1793458139.6233687` 消费 timeline `plan_timeline_pro_1793458037.103275`（11 video 项）；输出 `output_e6ca6fd9_1793458139707.mp4`（31.64s、H.264 yuv420p、854×480、25/1、AAC 44.1k、完整解码）。
- 逻辑请求 38（agent 12 / mcp_sampling 24 / llm_validation 1 / vlm_validation 1）；usage 覆盖 36/38，sum_total_tokens 258,768（<1M）；unknown_requests 2（1 无 usage、1 截止右删失 started_without_finished）。
- 资源：2958 行（boundary 2 + sample 2956），目标 0.5s、周期中位 0.6013s、均值 0.6083s、最大 gap 0.802s；CPU 444.73 core-s / valid 1798.86s / 均值 0.247 core；mem.current 峰 6,777,483,264 B、kernel peak 6,943,748,096 B；I/O read 0 / write 774,144 B；netns lo/eth0 逐接口。窗口 1798.86s 覆盖 agent 相位 1797.01s；容器 removal=removed；host total_wall 1800.37s。
- 判定：Agent 失败观察（render成功但截止）；trace 完整；资源质量 complete；导出/技术检查未运行；官方 not_run_no_submission/reward=null；清理正常、raw manifest 51 项回读 0 错。
- 保护：未补跑、未追加 attempt、未改旧 raw/身份/批准/评分/manifest、未改生产代码、未提交推送；覆盖计数不变。
- 证据：`reports/analysis/OPENSTORYLINE-E01-FULL-FLOW-R01-01/`（failure-observation-summary.md、result.json、curves/、manifest 14 项回读 0 错、revision-LAUNCH-RECORD-PERSIST-01 启动记录副本、raw-persistent-copy/ 独立 raw 副本逐文件 bytes/SHA 一致）。

## VIMAX-MUSICIANS-AUDIO-CONCAT-RECOVERY-01（2026-10-31）：原运行＋独立本地拼接恢复成功

**根因确认并最小修复：13 个有声 clip 同时打开的 ffmpeg 读取器线程/进程数超过 `--pids-limit 512`，第 13 个（shots/12）读取器无法建线程 rc=1 → MoviePy 报 "failed to read the first frame"（文件本身有效）。修复=读取器 ffmpeg `-threads 1` 有界 + 每 clip 读取器/音频读取器释放 + 显式 AAC（资源 profile 不变）。用已生成的 13 真实主体 clip 独立本地拼接恢复出 final：65.13s / 1280×720 / H.264 / 30fps / AAC 立体声 / mean -17.0dB 非静音 / 完整解码。**
- **修复函数**：`generation_entry.install_ffmpeg_audit`（`is_ffmpeg` 覆盖 imageio aarch64 二进制 + 读取器 `-threads 1`）；`script2video_pipeline.__call__` concat（`audio_codec="aac"` + try/finally 关闭全部 clip）。
- **验证**：回归 8/8（禁网 synthetic：多 clip/顺序/释放/损坏缺失失败/有声+无声/AAC）+ 生产入口真实 13 clip（峰 pids 424<512）+ 恢复最终验收。恢复独立资源：49 样本@0.5s、CPU 164.39 core-s、mem 采样峰 1.74GB、network=none。
- **登记**：原运行（EXECUTION-02）仍标"媒体生成成功、原生拼接失败、无 final"；恢复标"原生成运行＋独立本地拼接恢复，形成成片"；不作为新输入/新 attempt/同配置重复；资源分阶段不混加。语义 not_evaluated；官方 not_integrated/not_run、reward=null。证据 `reports/analysis/VIMAX-MUSICIANS-AUDIO-CONCAT-RECOVERY-01/`；恢复产物 `…/VIMAX-MUSICIANS-AUDIO-MEDIA-EXECUTION-02/recovery-CONCAT-01/`。

## VIMAX-MUSICIANS-AUDIO-MEDIA-EXECUTION-02（2026-10-31）：唯一正式媒体运行已执行——媒体生成成功、原生拼接失败（无 final，不补跑）

**本次授权唯一正式媒体运行已执行完毕（attempt 1/retry 0，run_id `musicians-band-rehearsal-audio-media-02-20261031T103514Z-1ac583f2`，镜像 `sha256:a97ea607…`，身份 `a2bf4285…`）。复用已验收 musicians 规划（17 文件 SHA 一致、零重新规划），最新修复生产链。媒体生成与下载阶段完整成功：11 图（9 肖像+2 候选）+ 25 视频（13 主体+12 过渡）全部有效、0 媒体错误、无 429、audio=true 端到端成立（25 clip 均 AAC 立体声、远端 usage.audio=True）。但原生拼接（MoviePy concat）读取 `shots/12/video.mp4` 首帧失败（读取器 ffmpeg rc=1/0.07s；文件本身有效）→ final 未生成。**
- **结果**：程序 PASS（Agent rc 0、startup gate 全通过、容器清理回验、无 cleanup_errors）；技术=媒体生成/下载 PASS + 原生拼接 FAIL（无 final）；语义 not_evaluated；官方 not_integrated/not_run、reward=null。完整采集的失败观察，不增加已完成覆盖计数。
- **计数**：LLM 5（sum_total 26,032/sum_output 1,301，partial_output_only）；图片发送 11×200（429/取消 0）；视频尝试/受理 25/25（closeout 复核 25 SUCCEEDED）；轮询 132；账本下载 36（另 closeout 复下载 25）。
- **资源**：3015 样本；attempt_wall 1510.36s；CPU 94.13 core-s；mem 峰 current 2,222,198,784 B / kernel peak 2,244,194,304 B；I/O write 102,400 B；netns eth0 rx 111,167,655 B / tx 132,656,444 B；`unclosed_requests={}`。
- **收尾**：容器删除回验、remote-closeout 25 任务 SUCCEEDED 复核、启动记录持久化、manifest（父 18 项/子 1 项独立回读 0 错）。未补跑、未追加 attempt；再次运行需新授权。证据 `reports/analysis/VIMAX-MUSICIANS-AUDIO-MEDIA-EXECUTION-02/`。
- 附：上一轮测试计数笔误更正——`134`→分项合计 `144`（30+28+9+25+17+35，另控制链场景）；只更正说明，不重跑/不改原日志。

## VIMAX-IMAGE-POLICY-FOUR-POINT-FINAL-CLOSEOUT-01（2026-10-31）：四点离线闭合（manifest/deadline/数值校验/Retry-After），不启动真实媒体

**闭合上一轮审计确认的 4 项问题：① 新 manifest 不再自哈希（子先父后、独立回读 0 错；旧 manifest 错误保留）；② 图片绝对 deadline 覆盖排队/实际发送/HTTP/退避（超时零新增发送、发送中超时 right-censored 不重发、不伪装供应商 429）；③ 图片策略严格数值校验（isfinite/拒 bool/拒字符串，发送前拒绝、零凭据/容器/发送触达）；④ Retry-After 正确消费（不再截短到 8s，超剩余 deadline 停止重试，缺失/非法走 fallback）。未调用真实 LLM/图片/视频/音频服务，未重新规划，未启动新正式 attempt。**
- **保留**：图片单在途/间隔、首次与重试共用发送边界、`image_create_sends` 独立、取消父子落盘、failure-stop、adapter 只读挂载+SHA 核验、视频策略/有声配置/资源落盘/清理、预算推导（9 肖像+2 候选=11 图，25 视频，36 下载）不变。
- **测试（离线）**：容器内 deadline/Retry-After 28/28、宿主数值校验 28/28、宿主 manifest 9/9、图片策略回归 25/25、视频策略回归 17/17、宿主既有 35/35、控制链 fake 429 场景通过（容器内图片 adapter SHA 核验 `612976cc…`、父子全闭合）。
- **口径更正**：① 429 表述更正为“并发突发后观察到 429；本地并发可能加剧限流，尚不能证明是唯一原因，账号共享配额仍未知”；② attempt 表述更正为“旧 attempt 已结束，不自动补跑；用户可另行授权一个新 run（新身份/批准），新运行结束后不自动追加下一次 attempt”。
- **边界**：未改历史 raw/正式配置/身份/批准/评分/历史 manifest；未提交推送。证据 `reports/analysis/VIMAX-IMAGE-POLICY-FOUR-POINT-FINAL-CLOSEOUT-01/`；下一次媒体草案 `next-media-run/`（新 run_id 授权时自动生成）。

## VIMAX-MUSICIANS-IMAGE-THROTTLING-AND-CLOSEOUT-REPAIR-01（2026-10-31）：图片流控与取消收尾离线修复 + 历史失败归档（不启动真实媒体）

**补齐上次中断会话未完成的离线分析/归档；修复图片侧请求流控与取消收尾记账中的确定性缺口；按真实规划+生产分支重核媒体预算；给出下一次媒体运行草案。未调用真实模型/图片/视频/音频服务，未重新规划，未启动新正式 attempt。**
- **历史归档（只读修订）**：失败 run `20261031T085308Z-vimax-musicians-audio-media-01`（图片 HTTP 429、`render_tool_ok=false`）账本 4 项 `unclosed_requests` 确认为确定性缺口；LLM 用量更正 sum_total=3011/sum_output=620；图片计数更正（不能写“3 个请求全部 429”；HTTP 发送 4 次=2×429+2 取消）；费用口径（无账单、2 个取消请求是否计费 unknown）；容器启动 2 次（第 1 次发送前缺 script.txt）与正式执行分列。产出 `historical-analysis/`（9 项，回读 0 错）。
- **修复（确定性缺口）**：① `image_create_policy`（单在途图片发送、显式间隔、429 有界重试、per-request deadline）在真实 `_post_json` 发送边界生效，首次与重试共用同一许可/间隔；② 任一图片失败→`image_failure_stop`（queued sibling 不再产生新 HTTP）；③ 取消任务父 `image_generation` right-censored 闭合（含 entry 收尾 cancel 未完成 sibling 并有界落盘）；④ `image_create_sends` 发送 cap 与逻辑 `image_generations` 独立；⑤ 视频父 `video_call` 取消闭合（同链）；⑥ acceptance 支持 characters/portrait_views/candidate_shots。
- **预算重核**：9 肖像（3 角色×front/side/back）+ 2 候选（仅 1 个生成首帧的相机×2）= 11 逻辑图；图片 HTTP 发送正常 11/上界 ≤22；25 视频（13 主体+12 过渡）；轮询 ≤3000；下载 36。历史“3 肖像+13×2 候选=29”更正；草案 `next-media-run-draft.json/.md`（CLI、发送前核对、验收边界）。
- **部署/身份**：图片 adapter 与视频 adapter 同机制只读挂载（容器内 SHA 发送前核验）；下一次身份 required 集合新增图片 adapter/request_ledger/script2video_pipeline；未创建正式身份/批准/attempt。
- **测试（离线）**：容器内图片策略 25/25、视频策略回归 17/17、宿主 35/35、控制链 fake 429 场景通过（父子全闭合 `unclosed_requests={}`、清理核验、图片 adapter SHA 核验）。
- 边界：未改正式配置/身份/批准/原 raw；语义/官方 not_evaluated/not_integrated/reward=null。证据 `reports/analysis/VIMAX-MUSICIANS-IMAGE-THROTTLING-AND-CLOSEOUT-REPAIR-01/`。

## VIMAX-MUSICIANS-PLANNING-EXECUTION-01（2026-10-31）：一次 ViMax musicians 真实规划成功（plan_verifier 通过，0 媒体）

**ViMax musicians 真实规划执行成功：13 镜头 / 3 角色 / 13 相机 / 12 过渡边，生产 plan_verifier ok=True，0 图片/视频/音频请求，18 LLM 逻辑请求（54,229 tokens），attempt 93.45s，容器自然退出与清理核验。为媒体阶段提供数量依据；规划通过不等同成片完成，不增加完整生成覆盖数。**
- 输入：musicians_typeC 故事（SHA `4d52835e…`）、registered script（`657acb1e…`）；音频路线 native wan2.6-i2v-flash audio=true（非 visual_only）；requirements 区分"故事内演奏/环境声"与"无关配乐"（silent count 不升级整镜头静音）。
- 运行：run_id `…-083918Z-4dc061b2`、镜像 `sha256:a97ea607…`、身份 `a4782e2c…`；preflight + run（--approval）经既有身份/批准门禁。
- 确定性修复（发送前）：planning_entry `_env_int` 容忍数值字符串；requirements 有声措辞；正式 context（0 媒体预算）。
- plan_verifier：storyboard 13、shot_description 13、camera 13、character 3、transition 12；checks 全 True（fresh session/registered script 匹配/契约/camera tree 无环/capability/角色引用/媒体 0）；语义等价明确标 not machine-proven。
- 资源：186 样本、CPU 3.93 core-s / 有效 92.57s、mem 峰 123 MB、io_w 102 KB、netns 逐接口；usage 54,229 tokens、0 媒体。attempt_wall 93.45s。
- 媒体预算草案（未授权）：主体 13 + 过渡 12（observed）；图片/视频/轮询/下载按实际核算；audio=true + AAC 验收为待冻结项；需新身份/批准。
- 边界：未生成媒体、未进入媒体阶段、未重跑 VideoWeaver、未提交。规划不增加覆盖数（组合/输入索引维持 15/9）。证据 `reports/analysis/VIMAX-MUSICIANS-PLANNING-EXECUTION-01/`。

## VIDEOWEAVER-MUSICIANS-AUDIO-EXECUTION-01（2026-10-31）：一次完整有声13镜头任务真实执行成功

**VideoWeaver musicians 完整有声任务（13 首帧 + 13 段 720P/5s/audio=true + 原生 merge → 65.13s final.mp4，AAC 立体声非静音、完整解码），judge 44/44 通过；探针记录已整理、不计组合；语义/官方未评估。**
- 工作A：探针已有记录整理（授权依据/命令/模型地域参数/媒体SHA/task_id终态/缺失项）→ `reports/analysis/VIDEOWEAVER-MUSICIANS-AUDIO-EXECUTION-01/revision-probe-record-consolidation-01/probe-record.md`（不补跑、不倒填）。
- 正式运行：run_id `20261031T074737Z-videoweaver-musicians-audio-01`、镜像 `sha256:933363d72000…`、身份 `f03bad06…`、命令 `python3 -B scripts/videoweaver_managed_launch.py --config <formal> --out <run> --mode live`（READY，PID 83316）。正式有声配置 media_profile.audio=aac；case task.txt 消除"无音轨"表述（SHA 记录）。
- 结果：image 13 / video 13 / downloads 26 / polls 110 / llm 53；final 18,449,914 B（SHA `10630e37…`）、65.13s、H.264 1280x720 30fps + 1 AAC 立体声、mean_volume -17.2 dB、完整解码；13 段各 1 音轨全非静音；Agent 真实 merge（rollout 证据）+ ffprobe 自检；judge 44/44。
- 资源/时间：3045 样本（complete）；CPU 192.38 core-s / 有效 1528.58s；mem 峰 2.567 GB；io_w 30.55 MB；usage 53 事件 / 2,168,816 tokens。
- 四类结果：技术 PASS；程序 PASS（rc 0/全媒体下载/merge 完成）；任务语义 not_evaluated；官方 not_integrated/not_run、reward null；数据质量 complete。
- 边界：未运行 ViMax；未改其他仓；未补跑；未切换模型/供应商；未新增音频服务；未改历史；未提交。成果索引更新为 15 组合/9 输入（探针不计）。证据 `reports/analysis/VIDEOWEAVER-MUSICIANS-AUDIO-EXECUTION-01/`。

## VIDEO-MUSICIANS-NATIVE-AUDIO-INTEGRATION-AND-PROBE-01（2026-10-31）：两仓原生有声接线补齐 + 一次真实有声生成探针成功

**按官方文档确认 wan2.6-i2v-flash 支持有声（audio boolean、有声/无声计费不同），补齐 ViMax/VideoWeaver 配置→payload audio 贯通与有声媒体验收（profile 驱动），并在离线验收通过后执行一次真实 720P/5s/audio=true 生成探针：成功输出 1 个 AAC 立体声音轨、非静音（-25.6 dB）、完整解码。未启动完整 musicians 故事。**
- **能力更正（上轮 404→unknown）**：官方文档 `wan2-6-i2v-flash` 与 `legacy-image-to-video-api-reference`（2026-10-31 核对）确认 audio 支持；北京 720P 有声 0.043006 USD/s（无声 0.021503）。详见 capability-correction.md。
- **接线修复**：VideoWeaver `_profile_audio_env` 从 media_profile.audio 派生 `VW_VIDEO_AUDIO` 并注入 start_container（+VW_VIDEO_DURATION/RESOLUTION、video-gen SKILL.md/generate.py overlay）；generate.py payload audio 真实进入；ViMax `VIMAX_BAILIAN_VIDEO_AUDIO` 受配置、acceptance `final_audio_mode`+`final_audio_non_silent`（expected.audio none/aac，-60dB 技术阈值）；skill_query/SKILL 有声表述更新。
- **离线验收**：VideoWeaver 5 项 + ViMax 3 项（真实消费者、仅 fake 网络/凭据；payload audio true/false、start_container env、非法 audio 发送前拒绝、合成媒体 final 音频判定）。
- **真实探针**：一次创建（task_id `716e2dca…`）720P/5s/audio=true，SUCCEEDED（31.3s）；输出 4,385,752 B（SHA `c7b03723…`）、H.264 1280x720 30fps + 1 AAC 44100Hz 立体声、完整解码、mean_volume -25.6 dB、音视频 start 0 对齐。语义（是否像吉他/与动作同步）**not_evaluated**（ffprobe 不推导）。
- 边界：未运行完整故事/规划/媒体批量；未切换模型/供应商；未新增音频服务；未创建身份/批准/attempt；未构建镜像；未提交推送。探针容器为临时 `--rm`，探针期资源样本未采集（如实记录）。
- 证据：`reports/analysis/VIDEO-MUSICIANS-NATIVE-AUDIO-INTEGRATION-AND-PROBE-01/`（summary/capability-correction/next-execution-plan/tests/probe/manifest 19 项回读 0 错）。
- 下一步：ViMax 新身份+批准→真实规划→camera-tree 预算→另批媒体；VideoWeaver 有声 profile/预算冻结→新身份+批准→managed_launch。两仓完整运行均不在本轮。

## 当前视频成果与后续边界（2026-10-31 文档收尾）

当前保留 **14个仓库×任务组合、8个输入**：video-use和OpenStoryline各4项，ViMax和VideoWeaver各3项。[成果总览](video_results.md)与[机器索引](video_results_index.json)为当前入口；下面各轮记录按当时版本阅读，不作为新的执行要求。

- assembly task1已形成“EXECUTION-04真实选片→分组→规划→渲染＋独立恢复导出”的成果。原attempt完成判定失败不变；恢复视频逐字节一致，solution.json从同一render消费的timeline派生，新帧周期技术验收PASS与旧10ms FAIL分列。官方/语义未评估，reward=null。
- 资源1598点、CPU 96.410294 core-s来自原运行窗口；恢复不另算Agent执行、输入或覆盖组合，恢复成本不并入该窗口。
- **task1无需专门重跑。** 修复后自动收尾仅离线验证，可在将来另行授权的其他assembly任务中顺带验证，不是当前成果的待补跑门禁。
- 下一步先整理已有轨迹/工具/时间与资源依赖；若继续新增生成任务，ViMax/VideoWeaver musicians先核查原生音频能力及声音要求，不能默认批准visual-only。实际新运行、音频接入或Replay均需另行授权。
- 本轮只整理文档/索引/状态，不修改生产代码或历史证据，不调用API，不创建运行身份/批准。

## OPENSTORYLINE-ASSEMBLY-COMPLETION-AND-RECOVERY-01（2026-10-31）：assembly完成判定与时间策略修复 + EXECUTION-04 独立恢复成功

**修复两处确定性缺口并独立恢复 EXECUTION-04 产物：① 完成判定按任务类型贯通（assembly 不再被 interview 必需节点误拒）；② 源范围/连续性/成片时长容差分开。随后从 EXECUTION-04 实际 render/timeline 独立导出 solution.mp4/solution.json 并通过技术验收（新帧周期策略；旧 10ms 策略如实 FAIL）。**
- **修复一（完成判定）**：`confirmation_flow` 新增 `ASSEMBLY_REQUIRED_STEPS` 与 `required_steps_for_task_kind()` 单一权威；`complete_native_chain/plan_is_preapproved/confirmation_decision` 按 task_kind 消费；容器入口 `persist_completion_check()` 真实判定+真实写 session-status/agent-result（成功写 render_artifact_id+submission_export_pending，不绕过/不伪填/不因目录有 mp4 完成）；`openstoryline_task_entry.py` 从 env 读 task_kind（缺省 interview 兼容、未知拒绝）。
- **修复二（时间策略）**：`openstoryline_assembly` 新增 `parse_frame_rate/final_media_duration_tolerance/FINAL_MEDIA_STRATEGY_ID`；源完整性/连续性保持 10ms（毫秒量化），成片时长用 `1/fps+0.002` 帧周期容差；非法 fps 拒绝；不按 19.333ms 反推；源截短不被成片容差掩盖。
- **独立恢复（EXECUTION-04）**：`select_render_from_trace` 来源证明（唯一成功 render 事件/artifact/session/node/call_id/顺序、render 消费 timeline、timeline↔group 匹配、来源 10/2/5/8.mp4、视频在 artifact 目录、bytes/SHA）；原视频逐字节复制→solution.mp4；从同一 timeline 派生 solution.json（4 段连续 half-open、source_range 全片）；技术验收 LEGACY(10ms) `total_matches_media=False`（21.686 vs 21.666667）、FINAL(帧周期 0.03533s) `True`、完整解码 OK。原 agent-result/session-status/视频字节未改。
- **部署**：`_SOURCE_OVERLAYS` 新增 `openstoryline_task_entry.py`/`confirmation_flow.py` 只读挂载（现 23 项）；gate assets 刷新。
- **测试**：容器内 completion_recovery 22、reliability_unit 29、selection_contract 19 全 PASS；宿主 time_strategy 8、recovery_provenance 7（真实 EXECUTION-04 来源/错 session/歧义/错 timeline/缺视频拒绝/原状态不修改）、回归 142 全 PASS；source/tests 30+1 既有条件。
- 边界：未调用真实模型/Agent/媒体；未创建身份/批准/attempt；未改原 raw/视频/状态/身份/批准/manifest；未提交推送；恢复成本独立记录。
- 证据：`env/video/openstoryline/OPENSTORYLINE-ASSEMBLY-COMPLETION-AND-RECOVERY-01/`（time-strategy-spec/deployment/summary/pre-change-snapshots/tests/manifest）；恢复产物 `…/OPENSTORYLINE-ASSEMBLY-TASK1-EXECUTION-04/recovery-COMPLETION-01/`。
- 下一步：恢复现有成果已完成，无需专门重跑task1；修复后未来自动收尾尚未真实验证，可在将来另行授权的其他assembly任务中确认（`persist_completion_check` 成功路径真实写 render_artifact_id 并被宿主导出），不作为当前成果的阻塞。

## OPENSTORYLINE-ASSEMBLY-TASK1-EXECUTION-04（2026-10-31）：storyboard 选择契约真实生效，完整渲染成功；入口 completion 检查误判导致无自动导出

**基于 storyboard-assembly 适配 + 可靠性修复版本的一次新正式 attempt。新选择契约真实生效：filter 选出恰好 4 段、group 按 slot 4 组、plan 消费该 group、render 消费匹配 timeline 生成 21.686s 4 段视频（完整解码）。但容器入口 `complete_native_chain` 仍按 interview 链（含 local_asr/speech_rough_cut）检查 assembly 完成 → 误判 failed → agent-result 无 render_artifact_id → 宿主无法自动导出 solution → 无提交物（本轮禁止修改生产代码，如实记录）。**
- **真实流程**：check-task-config（12 文件 SHA 全匹配、segments=4）→ preflight（formal_ready、镜像 ID 匹配）→ freeze-identity（身份 SHA `e110d42e…`、身份文件 SHA `42bf9067…`、40 文件绑定含 8 storyboard 模板 + 21 overlay + 配置/指令/输入）→ APPROVAL（`osl-asm-ex04-approval`，绑定身份文件 SHA+task/run）→ load_runtime_approval 通过 → --launch-detached（PID 4055950）。
- **门禁**：容器输入核验 passed（12 文件容器内 SHA=冻结）；overlay 核验 passed（21 overlay 含 8 模板、容器内 SHA=冻结）。
- **重点链真实验证**：load→split(skip)→understand（12 clip，03:34→03:38）→ **filter 选出恰 4 段**（`Successfully filtered 4 clips`，clip_0002/0004/0005/0008）→ **group 4 组按 slot 排序**（`Grouping successful: 4 groups`）→ plan_timeline_pro（4 段连续 timeline 0→4566→9628→14920→21686ms，group 匹配 True）→ render_video（`Video generated successfully, duration: 21.686 seconds`）→ 完整解码 OK，视频 H.264 1080x608/30fps、实际时长 21.667s。**无 80% 保留、无旧 12 段 timeline 复用。**
- **入口缺陷（确定性阻塞，未修）**：容器 `run_request` 的 `complete_native_chain` 使用 interview required_nodes `{load_media,split_shots,local_asr,speech_rough_cut,plan_timeline_pro,render_video}`；assembly 无 local_asr/speech_rough_cut → `missing_nodes=['local_asr','speech_rough_cut']` → agent-result `failed`（reason "Agent returned without the complete native render chain"）→ 宿主 `_select_render_artifact` 因 agent-result 无 render_artifact_id 报 "missing or ambiguous: set()" → `assembly_export=error`、`submission_status=not_verified`、`verifier=not_run_no_submission`、reward=null。渲染产物完整保留于 raw（未补导出、未补跑、未修改代码）。
- **闭合**：15 工具开始/15 完成全成功（load 1/split 1/understand 1/read_history 6/filter 1/group 1/plan 1/elementrec_transition 1/elementrec_text 1/render 1）；32 逻辑请求全部闭合（agent 14/mcp_sampling 16/llm_validation 1/vlm_validation 1；multimodal 13、text 3；finish_reason stop 15/length 1=understand VLM 截断重试后完成）；unknown_requests=[]；sum_total_tokens 275,579（<1M）。
- **资源**：1598 样本（quality complete）；CPU 96.41 core-s / 有效 972.52s / 均值 0.099 core；memory.current 峰 1,525,456,896 B、kernel peak 1,526,853,632 B；I/O read 0/write 860,160 B；netns 逐接口。agent 相位 969.85s（<1800s）；pre_archive 974.14s；容器 removal `removed`；raw manifest 42 项回读 0 错。
- **分析**：`reports/analysis/OPENSTORYLINE-ASSEMBLY-TASK1-EXECUTION-04/`（result/summary/curves/render-evidence.json/manifest 13 项回读 0 错，含 launch-record 副本）。
- **判定**：完整采集的失败观察（渲染成功但入口 completion 检查缺陷导致无提交物），非完成的组接负载；不增加完成覆盖。新选择契约的 filter/group/plan/render 真实路径全部通过；未触发分支：无截断工具错误、无旧 timeline 拒绝重试、无 solution 导出/技术验收。修复该 entry 缺陷需后续授权（不属本轮）。

## OPENSTORYLINE-ASSEMBLY-SELECTION-CONTRACT-REPAIR-01（2026-10-31）：storyboard Top-K 选择/排序提示与配置契约一致（离线完成）

**修复 filter 通用 80% 保留规则与 group 通用叙事重排对 assembly 任务（按故事板 Top-K 选片组接）的内部指令冲突，新增任务类型专用选择/排序策略；未调用真实模型/Agent。**
- **根因确认**：filter system 模板要求输入>5 时保留严格>80%（12 候选至少 10）+ 至少 5，与 task1 "选 K 段"冲突；group system 模板要求"所有片段必须使用"+ Hook/Core/Vibe/End 通用叙事 + 同场景打包 + 2–4 段分组，与"按故事板 slot 排序已选 K 段"冲突。前序探针证明模型遵守了 filter 的 80% 规则（返回 10 段）而非听不懂。
- **实现**：新增 8 个 assembly 专用模板（filter_clips_storyboard/group_clips_storyboard，zh/en system+user），仅 task_kind=assembly 且存在 `assembly_storyboard` 契约时由节点调用；宿主 `apply_task_config` 从冻结原 instruction 的 `## Storyboard` 解析 N/K/storyboard（N=声明输入、K=output_contract.segments，slot 数必须等于 K，冲突发送前拒绝），经 `OPENSTORYLINE_TASK_POLICY` 传入容器，`task_policy.assembly_storyboard_contract()` 校验消费。
- **filter strict 分支**：取消 80%/至少5/<=5全保留；按 K 个槽位五字段选 K 个互不相同片段；解析后校验数量==K、无重复、全合法，不符返回工具错误（不静默裁切/补齐）；max_tokens=8192（`[filter_clips] base=8192,cap=8192`）真实消费者证明。
- **group strict 分支**：输入必须是 filter 已选 K 段；全部 K 段恰好一次；raw 输出 ID 必须精确匹配已选集合（不增删重，防静默过滤凑数）；展开序列数量 K、集合一致；不套用通用叙事规则；输出简洁 JSON。
- **通用性**：3/4/5 段与候选子集同一实现（注入契约）；slot 数与 K 冲突发送前拒绝；原通用 filter/group 模板与 interview 行为不变（默认模板仍含 80%/Hook，属有意保留的通用策略）。
- **部署**：8 个模板 + filter/group/task_policy/config/宿主进入 `_SOURCE_OVERLAYS`（现 21 个 overlay，含 8 模板），进入冻结 required_frozen_sources；`assembly-offline-gate.json` assets 刷新。
- **测试**：新 selection_contract 19 项（容器内 network=none、fake 模型：提示加载无冲突/N-K-storyboard 进入请求/3-4-5 段/数量过多过少/未知重复/截断坏JSON/group 遗漏新增重复/render 一致性/模板路径与默认保留）；reliability_unit 29 项；宿主回归 68（wiring 22/contract 10/identity_freeze 21/e2e 6/control_chain 8）+ interview 宿主 59。既有条件：source/tests formal 目录 1 项。
- 证据：`env/video/openstoryline/OPENSTORYLINE-ASSEMBLY-SELECTION-CONTRACT-REPAIR-01/`（design/pre-change-snapshots/tests/deployment/summary/manifest）。
- 边界：未调用真实模型/Agent、未启动 assembly、未创建身份/批准/attempt、未改历史 raw/身份/manifest、未提交推送。
- 准确结论：storyboard assembly 的内部选择/排序提示已与配置契约一致，离线生产链验证通过；真实语义选片及端到端完成仍待单独授权。

## OPENSTORYLINE-ASSEMBLY-FILTER-BUDGET-PROBE-01（2026-10-31）：filter 输出额度 2048→8192 单次真实探针通过

**确认把 filter 实际请求输出额度调整到 8192 后，当前真实供应商能返回完整、可解析的筛选结果（finish_reason=stop、output 2345 tokens < 8192）。单次真实 filter 文本请求；非完整 assembly、非选片保证。**
- **旧额度归因（EXECUTION-03）**：filter 实际始终 `min(2048,8192,32768)=2048`（cap 不自动提升）；10 次 length：understand overall 1 次（1024，推断）、filter 9 次（2048，时间窗口推断）、group 0（strict default 拒绝无采样）；**"1024 截断"归属 understand overall，非 filter**。详见 attribution-table.md。
- **探针**：复用 EXECUTION-03 understand 12 描述 + split 12 映射（来源 SHA 登记），筛选需求来自原 storyboard 四槽位（无历史选片）；独立诊断 config（filter base=8192/cap=8192/parse_retries=0）；真实生产链 FilterClipsNode→提示→sampling_requester→sampling_handler→qwen3.7-plus（Bailian，retries=0）→生产解析；仅 MCP 传输层用夹具直连回调，供应商返回未 fake。
- **结果**：严格一次请求（probe_guard 防重复、request_attempted=1）；finish_reason=stop；input 1796 / output 2345 / total 4141 / reasoning 2097；生产解析通过；选中 10 个候选（全属输入、无未知/重复），符合生产 filter 提示硬约束（12 输入保留≥10）；4 段最终选择属 group 层不在本探针范围；golden 未读、语义未评估。
- **离线测试 11 项 OK**（network=none）：旧 2048/新 8192 消费/cap 约束/非法拒绝/无隐式重试/length→节点失败/解析错误不保存成功/不触发 Agent-VLM-ASR-render/输出根已存在拒绝覆盖/来源缺失不发送/无历史选择。
- **变更与保护**：未改生产源码/提示/模型/思维模式/递归/预算；生产 config.toml 未改；旧身份/批准/正式输出根未动；容器 --rm 无残留；凭据 env 文件已删除；不增加覆盖计数、不创建正式 attempt。
- 证据：`reports/analysis/OPENSTORYLINE-ASSEMBLY-FILTER-BUDGET-PROBE-01/`（attribution-table/summary/config/inputs/tests/results/manifest 14 项回读 0 错）。
- 后续：若推进正式端到端，需新授权将 filter 节点预算正式改为 8192 并重新冻结身份；语义选片与端到端仍待新授权。

## OPENSTORYLINE-ASSEMBLY-TASK1-EXECUTION-03（2026-10-31）：可靠性修复版本首次真实运行，Agent 反复截断后 32 步递归超限，无提交物

**基于 OPENSTORYLINE-ASSEMBLY-RELIABILITY-REPAIR-01 修复版本的一次新正式 attempt（run_id `20261031T020236Z-openstoryline-assembly-task1-execution-03`）。修复链真实生效：截断被正确标记为工具错误、默认全选被拒绝、render 门禁/旧计划复用未出现；但供应商在 filter 节点 2048 输出上限下持续截断，Agent 在 filter/group 阶段反复重试耗尽 recursion_limit=32，未到 plan/render。**
- **真实流程**：check-task-config（12 文件 SHA 全匹配、4 段契约）→ preflight（formal_ready、镜像 ID 匹配、命名空间干净）→ freeze-identity（身份 SHA `302d49e9…`，身份文件 SHA `88cb8a7f…`，32 个文件绑定含 13 overlay/配置/指令/12 输入）→ APPROVAL（绑定身份文件 SHA+task/run，`osl-asm-ex03-approval`）→ load_runtime_approval 通过 → --launch-detached（PID 3946967）。
- **真实门禁**：容器输入核验 passed（实际 docker Mounts 只读、12 文件容器内 SHA=冻结）；overlay 核验 passed（13 overlay 实际挂载、容器内 SHA=冻结）；request 含 recursion_limit=32、预算 60/1M/32768。
- **修复链真实生效**：10 次 `finish_reason=length` 截断全部被 `LLMTruncationError` 捕获 → filter_clips 12 次调用中多次 `is_error=True`（summary ERROR "model response is incomplete (truncation/provider error); no filter artifact saved"）；一次默认路径被 strict 拒绝（"assembly requires an explicit selection"）；Agent 收到错误后自适应缩短请求（"Select clips 1,2,3,5"→"1,2,3,5"→"Use clips 1,2,3,5 only"）但 filter 采样仍截断；随后 group_clips 也被截断。**未出现**伪装成功筛选、默认全量计划或旧 timeline 复用。
- **到达/终止**：Agent 走通 load_media→split_shots(skip)→understand_clips（12 clips 真实 VLM，02:04→02:08）→filter_clips（12 次，多次截断 is_error）→group_clips（1 次截断）；随后 `GraphRecursionError`（recursion limit 32）终止 rc=1，未到 plan/render → `assembly_export=error`（无 render artifact）、`verifier=not_run_no_submission`、`submission_status=not_verified`、reward=null。
- **闭合**：17 工具开始/17 完成（load 1、split 1、understand 1、read_history 1、filter 12、group 1）；40 逻辑请求全部闭合（agent 16 / mcp_sampling 22 / llm_validation 1 / vlm_validation 1；multimodal 12、text 28；finish_reason tool_calls 16 / stop 12 / length 10）；`unknown_requests=[]`；sum_total_tokens 284,888（<1M 软阈值）。
- **资源**：1184 样本（质量 complete）；CPU 45.43 core-s / 有效区间 720.96s / 均值 0.063 core；memory.current 峰 557,731,840 B、kernel peak 557,907,968 B；I/O read 0 / write 843,776 B；netns 逐接口（resource-samples 含 netns 原始）。attempt wall 722.56s（host-finalization）、agent 相位 718.76s（<1800s）、采样窗 720.96s。目录边界：input 14,451,838 B 不变、project 0、submission 0→510,945 B。容器删除回验 `removed`；raw manifest 42 项回读 0 错。
- **分析**：`reports/analysis/OPENSTORYLINE-ASSEMBLY-TASK1-EXECUTION-03/`（result.json/summary/curves/manifest 10 项回读 0 错）。
- **结论**：这是完整采集的失败观察，不是完成的组接负载。修复版行为验证成功，但真实供应商在 filter 节点 2048 上限下反复截断导致 Agent 无法完成；不放大预算、不改代码、不补跑。语义/官方未评估（not_integrated）。进一步的真实端到端完成仍待新授权（含对 filter 节点额度或提示的后续授权决策）。

## OPENSTORYLINE-ASSEMBLY-RELIABILITY-REPAIR-01（2026-10-31）：通用 assembly 可靠性修复 + 离线生产链验收（不启动真实 Agent）

**修复模型输出截断被掩盖、模式说明混淆、默认全量计划和旧时间线复用四类通用可靠性问题，形成可复用 assembly 执行版本。既有 task1 失败记录原样保留，不改成成功。**
- **① 截断/解析/预算贯通**：`sampling_handler` 按 finish_reason 区分 stopReason（endTurn/maxTokens/error），记账仍闭合；`sampling_requester` 新增 `LLMTruncationError`/`LLMProviderError`，assembly 作用域截断/供应商错误抛错（interview 默认不变）；`filter_clips` 移除宽泛 except（坏 JSON/错 schema/未知 clip ID 不再降级“全部素材+成功”），`max_tokens` 改由节点级 `[filter_clips]` 配置并受单请求上限约束；`group_clips` 截断传播 + strict 下默认 single-group fallback 拒绝；`understand_clips` strict 下 default 拒绝。
- **② 模式语义/引导**：`PlanTimelineInput.is_ai_transition` 明确要求已有 `generate_ai_transition.groups`，非普通拼接；assembly 引导完整链 load→split(skip)→understand→filter/group→plan→render→check，分组变化必须重 plan，render 不接受自然语言“ffmpeg 拼接”作真实计划。
- **③ 计划有效性/渲染门禁**：`render_video` 新增 `assembly_render_plan_consistency`，编码前比对 render 实际消费的 timeline 与当前 group_clips（空轨/不匹配/重复拒绝）；`register_tools` assembly 分支给 render 注入 `group_clips` 依赖，约束服务端重新装载后的真实 payload；旧产物保留。
- **④ 递归参数**：`recursion_limit` 由任务配置读取（默认 32，int 1..200 校验），进入冻结身份 `execution_params`/request/report；本轮不提高正式值。
- 部署：`_SOURCE_OVERLAYS` 新增 sampling_handler/sampling_requester/filter/group/understand/node_schema/config/config.toml 只读 overlay（不建镜像）；`assembly-offline-gate.json` assets 刷新至新代码身份；profile 登记 `docs/video_runtime_profiles.json/.md`。
- 测试：新增 unit 29（容器内，截断/解析/门禁/3-4-5段契约）、control_chain 8（宿主，真 freeze→临时批准→execute_once→导出→技术验收→报告→清理）、native 3（容器内 network=none 原生渲染消费新计划，4 段红绿蓝黄顺序/时长/完整解码）。回归 wiring 22、contract 10、identity_freeze 21、e2e 6、宿主 59、source/tests 30。既有条件：source/tests `test_formal_state_paths…` 因历史 formal 目录存在失败，非本轮引入。
- 边界：未创建正式身份/批准/attempt、未启动真实 assembly、未改其他三仓、未提交推送。真实语义选片、供应商表现及端到端完成仍待新授权运行。
- 证据：`env/video/openstoryline/OPENSTORYLINE-ASSEMBLY-RELIABILITY-REPAIR-01/`（diagnosis/pre-change-snapshots/tests/deployment/summary/manifest）。

## VIDEO-PROFILE-THREE-POINT-CLOSEOUT-01（2026-10-30）：三点离线收尾完成

**闭合上一轮登记遗漏：① VideoWeaver 字典 profile 帧率不被静默忽略；② video-use 时长/容差非有限值发送前拒绝；③ profile 登记区分执行程序来源与任务/故事来源。**
- **① host_runner.py**：`resolve_media_profile()` 允许字段白名单（video_codec/width/height/frame_rate/audio），
  未知/拼写字段拒绝，width/height 须 int，frame_rate 仅接受标称 `30/1`/`30000/1001`（文档注明二者不数学精确相等）；
  显式 60fps/25fps 等拒绝；`validate_task_config(mode="live")` 与 managed_launch/host_runner.main 在发送前消费。
- **② video_use_task_entry.py**：`_finite_num()` 校验（bool/NaN/±Infinity/非法类型拒绝）；enabled duration
  的 target_s 有限正数、tolerance_s 有限非负数；Bolt 166/视频流/±0.1s 契约不变，165.88s FAIL 不改。
- **③ docs/video_runtime_profiles.json/.md（v2）**：execution_source（程序 repo@commit）与 task_source
  （任务/故事 repo@commit）分列；依据 source-manifest/固定上游 HEAD 核对（video-use `43cfc566…`、
  FireRed `c9e94521…`、ViMax `fd4b72e7…`、VideoWeaver `c809392f…`）；`recursion_limit=32` 更正为本地入口配置值
  （非"上游默认"）；既有行为适配单独列。13 组合/7 输入计数不变。
- 测试：新增 `test_profile_frame_rate.py` 13 项 + `test_repurpose_duration_finite.py` 7 项；受影响回归
  VideoWeaver 10 模块 + video-use 9 模块全 PASS（合计 116）。既有条件（test_manifest_reread 历史 manifest
  mismatch、test_vimax_remote_closeout 读取已清理 raw）单列不称通过。
- 证据：`reports/analysis/VIDEO-PROFILE-THREE-POINT-CLOSEOUT-01/`（pre-change 快照、reproduction-evidence、
  test-log、summary、manifest 7 项回读 0 错）。

## VIDEO-RUNTIME-GENERALIZATION-AND-PROFILE-CONSOLIDATION-01（2026-10-30）：四仓契约化与 profile 登记完成（离线）

**把"同类型换任务只换配置"落到代码：单任务数字/规格移入显式契约/受限 profile，未改 Agent 行为。**
- video-use：`repurpose_technical_acceptance` 改为消费 `output_contract.technical_acceptance`（唯一来源）；
  Bolt 166s/1080x1920/h264/aac 立体声/视频流±0.1s 成为显式 profile（legacy list 归一化）；缺/非法契约发送前拒绝。
- OpenStoryline assembly：候选数=输入清单、目标段数=`output_contract.segments`（3/4/5 同一实现支持）；
  guidance/request_instruction/solution 验收同源；数字 `<N>.mp4` 文件名作为适配边界发送前验证。
- VideoWeaver：live 缺 judge_media 关键字段拒绝（不静默套 8/8/16/40）；`media_profile`（受限 silent_720p30_h264）
  显式登记并由 judge 消费；预算上限与最低完成量独立。
- ViMax：修复 `seconds_per_shot` 与提示文本矛盾——提示与总时长共同实际消费配置值，非法值拒绝。
- 未改 Agent 提示策略/工具集合/规划策略/递归上限；上游 filter_clips/group_clips/默认补依赖/timeline 复用
  保持不改；未启动真实任务、未创建正式身份/批准/attempt、未构建镜像/安装依赖、未改历史 manifest/正式配置。
- 版本/适配登记：`docs/video_runtime_profiles.json` + `.md`（区分上游 commit/模型适配/任务类型/工具集/生成
  能力/行为源码适配/正确性修复/代码身份/unknown/恢复；13 组合/7 输入计数不变）。
- 测试：四仓相关模块独立进程全 PASS（video-use 74、openstoryline 新增 10+21 等、videoweaver 9 新增等、
  vimax 6 新增等）；`test_manifest_reread`（历史 manifest 因后续代码演进回读报 mismatch，历史保留不改）与
  `test_vimax_remote_closeout`（读取已清理历史 raw）为既有条件非本轮引入。
- 证据：`reports/analysis/VIDEO-RUNTIME-GENERALIZATION-AND-PROFILE-CONSOLIDATION-01/`（pre-change 快照、
  summary、test-log、manifest）。

## OPENSTORYLINE-ASSEMBLY-TASK1-EXECUTION-02（2026-10-30）：首次真实 assembly 执行，Agent 至 render 后递归超限，无提交物

**真实验证运行，Agent 自主完成 4-clip 最终 timeline，但未提交 solution，官方未评分、reward=null。**
- **真实流程**：`check-task-config`→`preflight`（formal_ready=true，12 文件结构化输入，镜像 ID 匹配）→
  `freeze-identity`（26 文件绑定 + 12 文件身份 + manifest `62fca74e…`；身份 SHA `e07dfab9…`，身份文件
  SHA `781f3fbd…`）→ APPROVAL（绑定身份文件 SHA + task/run）→ `--launch-detached`（PID 3502235）。
- **真实消费**：12 clip bytes/SHA 与 instruction SHA（`f355d25d…`）均在磁盘核对并入冻结；容器输入门禁
  `container-input-verify passed`（12 文件、挂载源匹配、只读）、overlay 门禁 `passed`（5 个 overlay）。
- **真实视觉请求**：35 个逻辑请求全部闭合（agent 16 / mcp_sampling 17 / llm_validation 1 /
  vlm_validation 1）；mcp_model_response 17 个（12 multimodal/VLM 抽帧理解 + 5 text）；token 合计 322,721
  （<1M 软阈值；mcp 子集 55,423）。`unknown_requests=[]`。费用 unknown。
- **到达阶段/终止**：Agent 走通 load_media→split_shots→understand_clips→filter_clips→group_clips→
  plan_timeline_pro→render_video（多次），最终 timeline 为 **4 clip 单次整段**（10→2→5→8，输出 0–21.686s）；
  随后 `GraphRecursionError`（recursion limit 32）终止 rc=1，未提交 solution.mp4/solution.json →
  `assembly_export=error`、`verifier=not_run_no_submission`、`submission_status=not_verified`。
- **资源**：1463 样本（质量 complete）；CPU 279.01 core-s / 891.81s 有效区间 / 均值 0.313 core；
  memory.current 峰 3,797,151,744 B、kernel peak 3,797,676,032 B；cgroup I/O read 0 / write 983,040 B；
  netns 逐接口（lo/eth0 逐样本累计，network.csv 2927 行）；attempt wall 893.56s（<2700s）、agent 相位
  ~890.2s（<1800s）。容器删除回验 `removed`；raw manifest 61 项回读 0 错。
- **官方未评分**：reward=null；语义 not_evaluated；技术验收 not_run（无提交物）。不改门槛、不宿主重选片/
  改 timeline/修成片、不重渲染、不补跑。**失败观察如实登记，不标成功，不计入已完成覆盖。**
- 分析 `reports/analysis/OPENSTORYLINE-ASSEMBLY-TASK1-EXECUTION-02/`（manifest 10 项回读 0 错）。

## OPENSTORYLINE-ASSEMBLY-IDENTITY-FREEZE-REPAIR-01（2026-10-30）：assembly 身份冻结链离线修复完成

**修复了 assembly 多文件任务在生产身份冻结链的确定性缺口，用真实 freeze 产物跑通离线 execute_once。**
- 根因：原 `preparation_readiness()` 以 `INPUT.is_file()` 校验输入，而 assembly 的 `INPUT` 是 12 文件
  **目录** → `registered_input_missing` 阻断 freeze；`freeze_identity()` 亦未绑定 `openstoryline_assembly.py`。
- 修复：共享输入描述 `describe_task_input()`（assembly=目录+逐文件 bytes/SHA+确定性 manifest_sha256，
  绝不 digest 目录；interview=原单文件结构不变）；`preparation_readiness()` 按 task_kind 分派共同/专属门禁
  （interview 保留 ASR/verifier/render 门禁；assembly 消费 `assembly-offline-gate.json` 记录，不要求采访
  ASR/verifier）；`freeze_identity()` 绑定任务感知 source 集（含 helper/config/instruction/12 文件身份/
  overlay）+ `task_kind`/`output_contract`；`load_runtime_approval()` 执行前重校验（绑定文件重哈希、
  必需绑定完整子集、当前磁盘输入==冻结输入）；`--freeze-identity` CLI 分派；task-config 的 preflight 用任务
  唯一根。
- 测试：新 `test_assembly_identity_freeze_repair.py` **21 项全 PASS**（真实 readiness/freeze/
  load_runtime_approval/execute_once，未 mock 这些函数；仅 fake docker/git/凭据/运行时/Agent 边界）。
  直接受影响回归 PASS（assembly E2E 6、wiring 22、input-gate execute_once 6、env01_plan 5）；全量宿主可运行
  OpenStoryline pytest **128 passed + 9 subtests**。`check_project_state`（刷新本轮文件证据哈希后）PASS、
  `git diff --check` 干净。
- 边界：未创建正式身份/批准/attempt、未调用真实服务、未改其他三仓；上一任务阻断事实保留未标成功。
- 证据：`env/video/openstoryline/OPENSTORYLINE-ASSEMBLY-IDENTITY-FREEZE-REPAIR-01/`（含
  `execute-gate-evidence.json`、脱敏冻结身份样例、pre-change 快照、test-log、manifest）。
- 后续真实运行待新授权：使用修复后代码身份 + 新批准绑定，届时再明确运行命名。

## OPENSTORYLINE-ASSEMBLY-TASK1-EXECUTION-01（2026-10-30）：正式执行在身份冻结门禁处阻断，未发送真实请求

**生产 freeze 对 assembly 目录输入不适用 → 按授权边界停止，未创建身份/批准/attempt。**
- 新正式配置 `ASSEMBLY-task1-formal-execution-01.json`（task_id `OPENSTORYLINE-ASSEMBLY-TASK1-EXECUTION-01`、
  run_id `20261030T125005Z-openstoryline-assembly-task1-execution-01`）`--check-task-config` 通过：12 clip
  SHA 与 instruction SHA（`f355d25d…`）均与登记一致、输出目录空闲。
- 生产 `openstoryline_pilot_entry.freeze_identity()` 抛错 `formal identity cannot freeze before all gates
  pass: ['registered_input_missing']`：`preparation_readiness()` 检查 `INPUT.is_file()`，而 assembly 的
  `INPUT` 是**输入目录**（12 文件）→ 恒为 False；且 `freeze_identity()` 的 `source_paths` 未绑定
  `openstoryline_assembly.py`、未按 assembly 契约绑定 12 文件多文件身份。
  → 生产冻结机制未按 assembly 输入接线（assembly E2E 以 fixture 身份注入绕开冻结，未覆盖真实冻结）。
- 依授权边界“身份/输入/overlay 门禁失败→正常停止收尾”“不得手工跳过门禁”“执行中不修改生产代码”，
  本次未进行真实执行；模型/容器/ASR/TTS/render 发送均为 0。正式配置与阻断证据保留
  （`env/video/openstoryline/OPENSTORYLINE-ASSEMBLY-PRODUCTION-WIRING-01/revision-EXECUTION-01-BLOCKED-IDENTITY-GATE/`）。
  未来路径：先对生产冻结做 scoped 离线修复（assembly 目录输入 readiness + 绑定 assembly helper/12 文件身份）
  并验收，再另行授权正式 attempt。

## VIDEO-USE-REPURPOSE-BOLT-EXECUTION-01（2026-10-30）：一次真实 repurpose 正式 attempt，技术验收 5/6 通过

**Bolt 100m 决赛竖屏复剪，单次 attempt 完成并如实记录未完全达标。**
- **真实消费**：素材 `source.mp4`（SHA `1fe9e2e3…`，79,463,802 B）与原 instruction（SHA `d029e0dd…`）
  均从磁盘核对后进入冻结身份；镜像完整 ID `sha256:1a48c7b0…`（linux/arm64，codex-cli 0.163.0）。
- **流程**：新正式配置→`--check`→`--freeze`（21 文件绑定）→`--approve`（绑定 identity SHA
  `ae311034aa…`）→`--execute` 单次。宿主以 setsid 后台运行并按运行中状态核对（容器存活、资源流增长、
  日志落盘、deadline 有效），未给宿主入口加过短 timeout。
- **Agent**：`codex exec`（Bailian qwen3.7-plus responses，retries 0）rc=0、无超时，分配 1791.49s 实际
  1385.2s；ElevenLabs Scribe 转写 1 次 rc=0。71 工具调用/71 返回/0 协议错误；72 响应，token 合计
  3,708,713（input 3,692,254 含 cached 2,936,832、output 16,459、reasoning 6,085）；HTTP 次数 unknown。
- **提交物**：`workspace/output/repurpose.mp4`（102,930,795 B，SHA `970670b4…`），H.264 1080×1920 yuv420p、
  AAC 48k 立体声、完整解码 OK；轨迹显示实际发生 crop=405:720+scale=1080:1920 竖屏重构、drawtext 角标
  （WR 9.72→9.69 NEW WR，t=75s 切换）、subtitles 烧录 `captions.srt`（21 条英文）、`-t 166`。语义项
  （字幕正确性/比分时序/赛事选择/多机位）**not_evaluated**，仅引用 Agent 自检证据作有限描述。
- **技术验收 passed=False**：ffprobe/h264/1080x1920/aac_stereo/full_decode 全 true；**`duration_166s`
  false**（视频流 165.88s vs 目标 166.0±0.1s，差 0.12s）；容器/音频流均为 166.0s。不调整门槛、不改片、
  不补跑。
- **官方评估 not_run**（opus-vision/gemini-audio 未接入，非基础设施失败）；**reward=null**；
  `semantic_evaluation=not_evaluated`。
- **资源**：2062 样本（质量 complete，目标 0.5s 实测中位 0.6516s、最大 gap 1.052s）；attempt wall
  1397.42s，采样窗 1392.53s；CPU 1788.49 core-s、均值 1.284 core；memory.current 峰 2,402,893,824 B、
  kernel peak 2,404,245,504 B；cgroup I/O read 3.47 MB / write 6.36 MB；netns eth0 rx 7.58 MB /
  tx 147.08 MB（共享 netns 非 API 专属）。目录边界：materials 79,463,802 B 不变、workspace 0→
  155,909,278 B、output 0→102,930,795 B。容器删除回验 `removed`；raw manifest 142 项回读 0 错；
  分析 `reports/analysis/VIDEO-USE-REPURPOSE-BOLT-EXECUTION-01/`（manifest 10 项回读 0 错）。
- 一次性边界：单次 attempt、无补跑、无评审调片；未提交推送。
- **启动记录持久化**：宿主启动记录已持久保存到
  `reports/analysis/VIDEO-USE-REPURPOSE-BOLT-EXECUTION-01/revision-LAUNCH-RECORD-PERSIST-01/`
  （`launch-record.txt`/`execute.log` 源与副本 bytes/SHA 一致、无敏感信息未脱敏；修订 manifest 3 项回读 0 错；
  未改原 raw 与原分析 manifest）。

## 当前结论：video-use 新增 REPURPOSE，共13组有效覆盖记录（2026-10-30）

video-use覆盖E01/E02/E03/REPURPOSE，OpenStoryline覆盖E01/E02/E03，ViMax/VideoWeaver各覆盖G01/G02/G03，共7个输入、13个仓库×任务组合。有效研究记录不要求reward>0；不代表13次连续成功、同配置重复或已获Replay执行批准。当前统一入口是[成果索引](video_results.md)和[机器索引](video_results_index.json)。

下一步只需离线整理CPU工具回放材料（命令/参数/cwd、起止与返回、输入产物及资源窗口）；不为追分继续重跑。既有8组统一分析仍是历史子集，不能当作最新13组的完整聚合。

## VIDEOWEAVER-MUSICIANS-PRODUCTION-WIRING-01（2026-10-30）：单仓离线接线完成（不启动真实 Agent）

只补 VideoWeaver musicians 新 case 生产接线：`host_runner.validate_task_config`/`build_entry_script`/`judge`
实际消费 13 镜/65s/26 下载（draft 配置 `GX-musicians_band_rehearsal-draft.json`），14 项断言通过
（正反例 + 哈希/target 拒绝）。未改生产代码，未触发真实 Codex/供应商/凭据。`visual_only_adaptation` 声音
待用户确认。真实运行待授权。详见 `env/video/videoweaver/VIDEOWEAVER-MUSICIANS-PRODUCTION-WIRING-01/summary.md`。
其他三仓保持原未完成状态。

## VIMAX-MUSICIANS-PLANNING-WIRING-02（2026-10-30）：单仓规划离线接线完成（不启动真实规划）

**纠正上轮“接线完成”结论，把 ViMax musicians 规划接到已验证 v7 入口并做完整 13 镜头验收。**
- 生产入口 `env/video/vimax/planning/host_runner.py`（`preflight|run --out --approval --config`），
  基座 v7 镜像（非 v5）；统一上下文 `planning/task_context.py`＋config
  `GX-musicians_band_rehearsal_typeC-planning-context.json`；容器只读 overlay `planning_entry.py`/
  `plan_verifier.py`。所有消费者读同一上下文，显式值与源推导冲突 fail-closed。
- musicians 被实际消费：story SHA `4d52835e…`、registered-script 字节一致 `657acb1e…`、
  expected_shots=13（派生，不硬编码）；8192 输出 + enable_thinking=false；冻结 script session；
  plan-check.ok 为成功判定（RC0/COMPLETE 不代替）；运行中资源落盘；排他输出。
- 验收：容器内真实 verifier 对 13 镜头合成 workspace ok=true（13 storyboard/13 shot_desc/13 camera/3 角色），
  8/9/10 镜头契约及缺镜头/重复人物/错引用/环/剧本变更/双session/媒体ledger 反例全拒绝；24 项断言通过。
  模型/媒体零真实发送、零凭据读取、未创建身份/批准/attempt。真实规划与声音适配待用户授权。
  详见 `env/video/vimax/VIMAX-MUSICIANS-PLANNING-WIRING-02/summary.md`。其他三仓不变。

## VIMAX-MUSICIANS-PLANNING-FINAL-CLOSEOUT-01（2026-10-30）：规划链四项缺口收尾（离线验收完成）

**补齐完整控制链/身份绑定/采样就绪放行/容器退出判定，并修网络派生口径。保留 13 镜头验收，不转其他仓。**
- 完整控制链：真实 `run_attempt`/`validate_approval`/`final_outcome`/`summarize_run` 离线驱动
  （仅 fake Docker/凭据/cgroup/模型边界）；A–F 正反例通过（13 镜头通过、plan 失败但 RC0、entry 异常、
  身份篡改在凭据/模型前拒绝、已有 attempt 保护、收尾落盘）。
- 身份绑定：config bytes/SHA、task_context.py 及全部生产代码进入冻结身份/批准，改动即拒。
- 采样就绪放行：容器内 entry 等待 run/容器绑定 RELEASE；宿主证明归属+首资源样本+资源流可写+netns 就绪后放行；
  放行前模型 0 调用，陈旧握手忽略。
- 容器退出：`final_outcome` 五状态（Agent/plan-check/容器退出/清理/观测质量）分列并消费退出码；
  COMPLETE 后等自然退出，不再 SIGTERM 制造退出。
- 网络口径：RX/TX 独立、gap 断开、时间/身份断开、全缺测 unknown、合法零保留；原始/派生分开；
  报告 `report["netns"]` 实际消费。
- 测试 **50 项通过**（原 24 + 新增 26，PASS=50 FAIL/ERROR/SKIP=0）；`check_project_state` PASS、
  `git diff --check` 干净；模型/媒体零真实发送。详见
  `env/video/vimax/VIMAX-MUSICIANS-PLANNING-FINAL-CLOSEOUT-01/summary.md`。真实规划与声音适配仍待用户授权。

## OPENSTORYLINE-ASSEMBLY-PRODUCTION-WIRING-01（2026-10-30）：单仓 assembly 离线接线完成（不启动真实 Agent）

**把已下载素材的 agentic-vbench assembly task1 接入生产入口，并接通原生多素材节点/视觉采样/禁网 render。**
- 生产接线：`task_kind=assembly` 路由、12 文件逐项输入门禁、assembly 工作流引导、solution.mp4/solution.json
  从实际 render timeline 派生、结构技术验收（真实 ffprobe/ffmpeg）。
- 本轮接通：`understand_clips/filter_clips/group_clips` 经 `OPENSTORYLINE_TASK_KIND=assembly` + 只读 overlay
  `register_tools.py` **任务作用域注册**（默认 interview 不注册，采访行为不变）；视觉采样路径（视频抽帧→
  image_url→vlm 选择）与原生 `RenderVideoPipeline` 四段整段拼接（7.0s/red-green-blue-yellow/完整解码）均
  容器内 network=none 离线实测通过。
- E2E 收尾：真实 `execute_once()` 端到端离线验收通过（正常链技术通过/官方 not_run/reward=null/采访
  verifier·ASR·TTS·真实模型 0；缺产物/错 session/错 timeline 正确失败并保存报告清理；输入 SHA 错配 Agent 0；
  E02→assembly→E02 无残留）。此前三节点未注册是接线缺口（本轮已完成注册）；仅撤回“凭模型名否定视觉能力”结论。
- 仍待授权：真实供应商视觉兼容性与真实“12选4”选片 `needs_real_validation`；官方评估 `not_integrated`。
- 测试 52 项通过（+5 子测试：22 wiring + 4 原生 + 6 e2e + 14 回归 + 6 输入门禁）；模型/媒体/凭据零真实调用。
  详见 `env/video/openstoryline/OPENSTORYLINE-ASSEMBLY-PRODUCTION-WIRING-01/summary.md`（含
  `revision-E2E-CLOSEOUT-01`）。其他三仓不变。

## VIDEO-OPEN-SOURCE-EXPANSION-WIRING-01（2026-10-30）：开源素材获取与接线准备（不授权执行）

四项开源任务补齐素材与可完成接线：Bolt 与 assembly 素材经既有代理 `127.0.0.1:22111` 下载成功并登记 SHA
（上轮“无外网”是仅试直连的误判）；video-use `task_kind=repurpose` 路由（effects 属任务要求非仓库不支持，
官方裁判 not_integrated）；VideoWeaver musicians 13 镜头 case 确定性转换；ViMax 13 镜头 draft + `audio=
visual_only_adaptation`；OpenStoryline assembly 12 文件 draft 配置。7 项断言测试通过。**无仓可申请真实执行**
（均仍有 blocker/wiring_pending）。详见 `docs/video_open_source_expansion_preparation.md`、
`env/video/openstoryline/OPENSTORYLINE-EXPANSION-WIRING-01/summary.md`。

## VIDEO-OPEN-SOURCE-REPRESENTATIVE-EXPANSION-PREP-01（2026-10-30）：开源代表性扩展执行准备（不授权执行）

四仓各拟增一个开源来源任务，本轮只准备/登记/禁网评估。候选 1 video-use repurpose（Bolt 竖屏复剪）、
候选 2 OpenStoryline assembly task1（12 选 4 组接）、候选 3 ViMax musicians 13 镜头、候选 4 VideoWeaver
同源适配 case。素材：候选 1/2 公开 HF URL 本轮无外网出口不可达（`material_blocked`），候选 3/4 远端生成
无需下载（`materials_ready`）。候选 1 `requires_scope_decision`（效果与保源策略冲突+外部裁判依赖）；
候选 2 `existing_tools_expressible`（原生多素材链存在）。主方案
`docs/video_open_source_expansion_preparation.md`、登记 `docs/video_open_source_expansion_registry.json`。
未创建身份/批准/attempt、未下载素材、未调用模型。

## OPENSTORYLINE-E03-RUNTIME-CONFIRM-03（2026-10-30）：有效研究记录，原宿主导出失败＋独立恢复评分 reward=0

**使用已验收版本、`--launch-detached` 后台启动，唯一一次新正式 attempt。**
- **确定性执行修复实测生效**：① 资源运行中落盘（**1602行=1600周期点＋2边界点**，原容器窗口分析
  `complete`、CPU 809.91 core-s）；② **实际剪切与本次Agent选择一致、无额外默认清洗**，不等于语义选段正确；③ 帧率（render
  `avg_frame_rate=24000/1001`，导出 `exact_equal=True`、0 ppm；非 1199/50）。
- **原attempt与恢复分列**：原宿主正常归档采样并清理，但导出步骤因`NameError: PurePosixPath`失败；
  修复导入后，独立closeout在同一render/timeline完成导出及一次官方评分。不能称原attempt连续完成。
- **评分 complete、reward=0，官方任务未通过**：结束边界超容差，honesty/audio/duration通过。评分失败不使轨迹无效；不因分数补跑，不在通用任务文档传播golden精确边界。
- run_id `20261030T011456Z-openstoryline-e03-runtime-confirm-03`；identity `69cb7578…`；54 逻辑请求/306,597
  tokens；MCP 12/12、Agent工具10/10、模型请求54/54闭合。
- **实测时间分列**：原生Agent阶段966.097s；宿主execute 983.037s；原attempt 984.956s；采样边界窗口983.826s。
  采样目标0.5s，周期点实测中位0.601382s、均值0.614553s；恢复/评分不并入上述窗口或资源。
- [当前口径修订](../reports/analysis/OPENSTORYLINE-E03-RUNTIME-CONFIRM-03/revision-DOCUMENTATION-CLOSEOUT-01/summary.md)
  保留原摘要、run与manifest字节。本次文档整理不运行任务、不改代码或评分。

## 历史执行与修复记录

下列段落按当时阶段保存；“待执行/blocked/尚未形成”等历史状态不代表当前状态。当前覆盖和下一步以上方及成果索引为准。

## OPENSTORYLINE-FPS-SYNTHETIC-ACCEPTANCE-01（2026-10-29）合成媒体禁网验收：帧率修复实测通过（不运行 E03、不调用模型）

**用现有镜像+合成媒体+真实 MoviePy/FFmpeg 编码，验证「输入近似 fps + 输出精确 -r」是否真正保留帧率/帧数/时间轴。**
- **结论：通过**。四种帧率（24000/1001、60000/1001、25/1、30/1）输出 avg/r_frame_rate 精确、帧数无缺无重
  （直接 `FFMPEG_VideoWriter.write_frame` N 帧 seq_ok=True）、时长/PTS 0 ppm 漂移。基线（不追加输出 -r）在
  `24000/1001` 出现 **-165.81 ppm 累计漂移**（avg 落到 1199/50=23.98），与真实 E03 观察一致。
- MoviePy 2.1.2 输入侧仍构造 `-r 23.98`（`"%.02f"`），但输出侧 `-r 24000/1001` 覆盖、不丢帧不重复（实测）。
- 25/1、30/1 因 `%.02f` 无截断，有无 -r 都精确。
- **未修改生产代码**（当前实现已正确）。128×96 低分辨率合成、无音频；音画同步与真实素材仍留待真实 E03。
- 报告 `env/video/openstoryline/OPENSTORYLINE-FPS-SYNTHETIC-ACCEPTANCE-01/`。未创建身份/批准/attempt，
  未调用模型/API，容器 `--rm` 删除。帧率修复**已具备进入真实 E03 验证的条件**。

## OPENSTORYLINE-E03-THREE-POINT-CORRECTNESS-FINAL-01（2026-10-29）三处确定性修复＋断言式测试（不启动付费运行）

**补上一轮三个确定性错误并让测试能判失败。**
- ① **删除区间求补集**：`content_deletion_ranges` 改为"删除集合→合并重叠/相邻→对源区间求补集"，
  修正旧实现的三个错误（中间删除多删边界停顿、首句删除被首部扩展恢复、末句删除被尾部扩展恢复）。
- ② **CLI 查询/排他启动**：`apply_task_config` 增 `require_empty_output`，`--launch-status` 只读查询
  不再因输出目录已存在而拒绝；`launch_detached` 用 O_EXCL 在 Popen 前原子预留 record+log（并发至多
  一个子进程），Popen/starttime 失败有界回滚（回收子进程、关闭 fd、删除预留文件、原字节不变）。
- ③ **非法 fps 传播**：`build_write_ffmpeg_params` 让非法/非正/非有限帧率在 writer 启动前抛错
  （不再 try/except 吞掉置 None 继续 write_videofile）。fake Popen 捕获完整 argv：输入侧仍 MoviePy
  `"%.02f"`=23.98、输出侧追加 `-r 24000/1001`；最终编码精确保留留待真实验证。
- 测试改 `unittest`（失败非零退出）：`test_three_point_mirror`（15）+ `test_three_point_cli`（7）；
  受控错误预期实测退出码 1。E01/E02 与 edit_policy 回归通过。
- 修订目录 `env/video/openstoryline/OPENSTORYLINE-E03-THREE-POINT-CORRECTNESS-FINAL-01/`（manifest
  14 项独立回读 ok）。未创建身份/批准/attempt，未构建镜像，未提交推送。

## OPENSTORYLINE-E03-OBSERVATION-FPS-SEMANTICS-REPAIR-01（2026-10-29）三问题离线诊断＋最小修复（不重跑、不重渲染、不评分）

**根据 RUNTIME-CONFIRM-02 真实运行，限定处理三个问题，离线验证生产路径。**
- ① **资源样本未落盘**：宿主被外层工具超时杀掉（同进程组 SIGKILL），`Sampler` 只存内存、仅
  `finalize` 一次性落盘 → 0 样本/partial。修复：`Sampler` 增加 in-run JSONL 追加落盘（`sink_path`
  +`flush_every`，flush/close 均 fsync，写失败记 sink_state.error）；`execute_once` 传 sink、
  `finalize` 先 `close()`；新增托管分离启动 `launch_detached()`/`launcher_status()`（`start_new_session`
  脱离外层进程组、排他 launch record、可查询僵尸态）。历史缺失样本不可恢复，不补造。
- ② **帧率 24000/1001→1199/50**：首次真正丢失精度在 MoviePy `ffmpeg_writer.py` 的 `"%.02f" % fps`
  （2 位截断）。修复：`render_video.py` 新增 `exact_fps_for_ffmpeg()`（`Fraction(...).limit_denominator`
  精确复原），`write_videofile` 处追加 `-r <精确分数>`；`render_video.py` 加入 overlay 登记。最终编码
  是否精确保留留待下次真实运行确认。
- ③ **额外删除 ~5.92s**：重建区间证实额外删除=首部裁剪 [0,2850] + 句间停顿裁剪（830/450/980ms）+
  口吃清洗 [69520,70180] + 尾部裁剪 [89860,90007]，均非 Agent 指定区间，源于 speech_rough_cut 默认清洗。
  修复：`content_deletion` 启用时用 `content_deletion_ranges()`（合并保留句、保留停顿/首尾、只在显式
  删除句断开）+ task-scoped system prompt 覆盖；E01/E02 清洗路径不变。
- 离线验证：宿主测试（采样流 flush/close/写失败/追加/launcher 生命周期）＋镜像内测试（fps 复原与拒绝、
  content_deletion_ranges 反例）＋ E01/E02 与 edit_policy 回归。`check_project_state` PASS、`git diff
  --check` 干净、manifest 17 项独立回读 ok。修订目录
  `env/video/openstoryline/OPENSTORYLINE-E03-OBSERVATION-FPS-SEMANTICS-REPAIR-01/`。未创建身份/批准/
  attempt，未构建镜像，未提交推送。

## OPENSTORYLINE-E03-RUNTIME-CONFIRM-02（2026-10-29）一次真实 E03 运行：渲染完成、导出被帧率门拒绝

**一次正式 OpenStoryline E03（FINAL-WIRING-01 修复后生产入口），未补跑。**
- **Agent 完整走通原生链并成功渲染**：load_media→split_shots(skip)→local_asr→speech_rough_cut→
  plan_timeline_pro→render_video 全部成功；52 逻辑请求/273,067 tokens（<预算 60/1M）；6-clip 非空
  timeline、0 字幕、0 配音配乐。
- **修复生效**：`speech_rough_cut.user_request` 自主确定删除区间 [29190,38760]ms 并含
  “phone case … stand up reliably”删除目标；`forbid_added_subtitles` 生效（0 字幕）；输入/overlay
  门禁 passed（三覆盖文件实际只读挂载、容器内 SHA=冻结）。
- **导出失败（新缺陷，非本轮已修复项）**：`export_rendered_video` 帧率拒绝——源 24000/1001（23.976）
  vs 渲染 1199/50（23.98），相对偏差 **165.83 ppm > 2 ppm**。render_video 节点 ffmpeg 合成把时间基
  落到 1199/50，尽管 Agent 传入的 `load_media.metadata.fps` 与 plan_timeline 各 clip fps 均为 23.976。
  → 无有效提交物、官方 verifier `not_run_no_submission`、reward=null。
- **资源样本缺失**：宿主入口进程在 Agent 结束后被中断（工具超时），sampler 未落盘，分析 partial
  （0 样本/CPU None）；宿主收尾（导出尝试、verifier 跳过、容器回收、记录/manifest）由独立 closeout
  在同一 render/timeline 完成，非重跑/重渲染/重选段。
- run_id `20261029T152902Z-openstoryline-e03-runtime-confirm-02`；镜像 `sha256:9a1e876c…`；
  identity_sha256 `35a7aeee…`。分析 `reports/analysis/OPENSTORYLINE-E03-RUNTIME-CONFIRM-02/`。
  MCP 节点 10/10、模型请求 52/52 闭合；容器删除回验；未提交推送。
- **帧率保真缺陷属后续另行授权的修复范围**，本轮如实录、不重渲染、不调 cuts、不重评。

## OPENSTORYLINE-E03-REPAIR-FINAL-WIRING-01（2026-10-29）4 处收尾修复＋离线验证（不重跑、不渲染、不评分）

**补齐 WORKFLOW-REPAIR-01 的 4 处确定缺口，不扩大范围。**
- ① **覆盖源码未完整冻结＋无执行前核验**：抽取单一共享登记 `_SOURCE_OVERLAYS`/`overlay_sources()`
  （plan_timeline_pro、speech_rough_cut、task_policy 三文件），挂载与 `freeze_identity` 绑定同源；新增
  `frozen_overlay_mismatches()`（执行前重散列覆盖文件比冻结 files）与 `verify_overlay_sources()`（容器内
  docker inspect 证明 bind+readonly+源一致、容器内 SHA 等于冻结摘要），不符在 Agent 边界前拒绝（调用 0）。
- ② **旧修复 manifest 无法按登记路径回读**：保留旧清单原字节；新清单
  `OPENSTORYLINE-E03-REPAIR-FINAL-WIRING-01/manifest.json` 采用**仓库根相对路径**（根=含
  `project_state.json` 的目录），回读器从任意 cwd 独立解析；24 项 0 缺失 0 不匹配（含缺失/变更/错根反例）。
- ③ **粗剪校验是全局子串黑名单**：删除黑名单；任务约束改为从任务配置显式登记的
  `edit_policy.content_deletion`（`removal_target`+`keep_rest`）传入容器节点；启用时空请求/缺 removal_target
  明确失败，否则把权威删除目标注入逐句提示（来源记入 node_summary）；辅助“按停顿拆分”措辞不再触发拒绝；
  Agent 仍自主定区间，不用 golden/毫秒。
- ④ **所谓任务作用域实为全局变化**：字幕抑制改由 `edit_policy.forbid_added_subtitles` 控制，不再用
  `is_speech_rough_cut=true` 代替“禁止字幕”；无策略保留修改前默认（含 speech 路径照常出字幕），E03
  显式 `forbid_added_subtitles=true`；策略进入宿主导航→容器 env→节点消费，并随任务配置绑定下一次身份。
- 工作流表述纠正：上一轮只是 instruction 追加工作流**引导**，不是强制执行原生 skill；代码措辞已由
  “must be followed” 改为 “guidance only, not an enforced skill call”。
- 离线验证：宿主测试（身份冻结/篡改/未绑定/可写/SHA 拒绝、策略校验、spec 挂载/env）＋镜像内测试
  （删除目标注入、纯通用不冒充、完整+拆分合法、无策略默认、字幕策略任务化）＋ E01/E02 兼容回归＋
  plan_timeline 模式/空轨回归。`check_project_state` PASS、`git diff --check` 干净、manifest 独立回读 ok。
- 修订目录 `env/video/openstoryline/OPENSTORYLINE-E03-REPAIR-FINAL-WIRING-01/`。未创建身份/批准/attempt，
  未构建镜像，未提交推送。

## OPENSTORYLINE-E03-WORKFLOW-REPAIR-01（2026-10-29）确定性工作流/校验修复＋离线验证（不重跑、不渲染、不评分）

**只修确定性缺陷并离线验收，真实语义选段与端到端仍待新授权。**
- **根因（按真实失败轨迹）**：① `speech_rough_cut.user_request` 丢失删除目标（只传“split at natural speech
  pauses”通用回退）；② `plan_timeline_pro` 双模式/无 groups/无 clips 时静默返回空视频轨且 `isError=false`；
  ③ 空 timeline 反复送入 render 耗尽步数；④ speech 模式仍自动产生 45 条字幕（违反无字幕契约）。
  `GraphRecursionError` 只是终止机制，非根因。
- **修复（fail-closed，不改变用户 instruction / E01-E02 语义）**：
  - `speech_rough_cut.py`：空/通用 `user_request` → `ValueError`（工具错误），不再静默继续。
  - `plan_timeline_pro.py`：双模式冲突、无 `generate_ai_transition.groups`、无 `group_clips.groups`、无
    `speech_rough_cut.clips`、空视频轨，均 fail-closed；speech 模式抑制自动字幕（artifact 字段保持原样）。
  - `openstoryline_pilot_entry.py`：`build_container_spec` 新增 2 条只读源码覆盖挂载（镜像仍固化旧版）；
    `request["instruction"]` 追加 task-scoped 原生工作流引导（不修改官方 instruction）。
- **离线验证（镜像内 network=none，覆盖挂载修复模块，无凭据/模型/ASR/渲染）**：4 组测试全部通过——
  原失败参数（双模式/无 groups/空 user_request/空视频轨）→ 明确错误；合法 speech/普通/AI/E01-E02 路径→非空；
  E02 真实 filler 删除请求未被覆盖；宿主入口覆盖挂载 2 条 readonly、修复后 SHA≠修改前快照、引导块嵌入指令。
- **事实更正（独立修订，不覆盖原报告）**：① 调用闭合——原生 Agent 工具 16/16、MCP 节点 18/18、模型请求
  59/59 均有结束记录，`GraphRecursionError` 不构成右删失；② attempt wall 1770.55s / Agent wall 1768.77s，
  CPU 765.68 core-s 是累计，非墙钟/采样时长。
- 修订目录：`env/video/openstoryline/OPENSTORYLINE-E03-WORKFLOW-REPAIR-01/`（diagnosis/修复位置/对照/测试日志/
  事实更正/快照索引/deployment/manifest）。未创建身份/批准/attempt，未构建镜像，未提交推送。

## VIDEO-E03-TWO-REPO-EXECUTION-01（2026-10-29）E03 两仓各一次真实执行（video-use 完整评分；OpenStoryline 到 render 后递归超限）

**在 READINESS-01 准备基础上串行执行两仓各一次 E03 正式 attempt，未补跑。**
- **video-use E03**（run_id `20261029T110903Z-video-use-e03-c01`；镜像 `sha256:1a48c7b0…`）：E03 素材真实消费
  （SHA `c66f380a…`），Agent 自主切除手机壳立起陈述段 [29120,34480]ms；导出 output.mp4（84.7451s/854×480/
  24000-1001/H.264/yuv420p/AAC）＋cuts.json（1 cut）；官方 verifier **complete**：**range 门 1/1 通过**、
  honesty SSIM 0.7485<0.8 → **reward=0**（audio xcorr 0.9974、duration 通过）。评分完整、reward=0 合法。
  300 样本/CPU 55.2 core-s；容器删除回验；20 响应/463,436 tokens；ElevenLabs ASR 1 次（远端）。
- **OpenStoryline E03**（run_id `20261029T111519Z-openstoryline-e03-expansion-01`；镜像 `sha256:9a1e876c…`）：
  输入门禁 passed（实际 Source=E03、Destination=/workspace/input、RW=false、容器内 11,604,798/`c66f380a…`、
  90.006583s/24000-1001）；链推进到 render_video（3 次 render 尝试）后 Agent 因 LangGraph `GraphRecursionError`
  （recursion limit 32）终止 → **无提交物** → verifier `not_run_no_submission`、reward=null。59 逻辑请求/
  494,167 tokens（<1M soft）；本地 ASR（paraformer-en）；2897 样本/CPU 765.7 core-s；容器删除回验。
  **单次 attempt 不补跑**；失败原因（E03 内容级任务所需递归步数超限）如实记录，不作为成功。
- **该批次结束时尚未形成12组覆盖**；后续E03 RUNTIME-CONFIRM-03已通过独立恢复补齐有效研究记录，不能据此改写本批无提交的事实。
- 报告 `reports/analysis/VIDEO-E03-TWO-REPO-EXECUTION-01/`（summary、逐 run 分析、manifest 22 项递归回读 0 错）。
  未提交推送。

## VIDEO-E03-TWO-REPO-READINESS-01（2026-10-29）E03 两仓能力核对与离线准备（不调用付费服务）

**判断“现有工具能否表达 E03 任务”，避免直接运行后才发现接线/能力不匹配。本轮不追求 reward、不跑真实 E03。**
- **E03 契约**：单段、内容级（语义陈述）删除——移除“手机壳能让手机可靠立起来”的陈述段，保留其余全部；
  素材 90.006583s/854×480/有理数帧率 24000/1001≈23.976fps/AAC16k mono（SHA `c66f380a…`）；提交
  output.mp4（H.264/yuv420p/AAC/同分辨率/音画同步）＋cuts.json（1 cut）。不得改写成“删除所有停顿/填充词”，
  不得加配音/字幕/配乐/变速。golden 数值未泄漏进 instruction（12000/38500 为格式示例，非 golden）。
- **video-use**：生产入口 `video_use_task_entry.py --check/--freeze/--approve/--execute`；`build_context`
  对 E03 输入/指令/judge/golden/输出/泄漏检查全过（`--check` 仅因 capability_blocked 拒绝）；`apply_context`
  E02→E03→E02 无残留；Codex（exec_command＋view_image）＋ElevenLabs 转写可表达内容级删除。
  **existing_tools_expressible＋wiring_ready**。
- **OpenStoryline**：`speech_rough_cut.user_request` 可承载内容级删除要求；`plan_timeline_pro` 消费保留片段；
  render 导出＋`export_cuts_from_final_timeline` 从 timeline 派生 cuts；确认流程可预批该计划；实际挂载错配
  在 Agent 边界前拒绝；E02→E03→E02 切换无残留。合成删除区间沿真实 timeline→cuts 接口传播（测试通过）。
  **existing_tools_expressible＋wiring_ready**。
- **判定**：两仓均可将旧 capability-blocked 更正为“可申请一次真实验证”（≠真实成功，≠执行批准）；
  后续运行草案（配置/入口/镜像完整 ID/身份绑定项/预算/唯一 run_id/采集/停止清理）见
  `reports/analysis/VIDEO-E03-TWO-REPO-READINESS-01/summary.md`。
- 测试：`tests/test_video_e03_readiness.py` 7 项通过（真实入口/控制分支，仅 fake Docker/凭据/ASR/Agent）。
- 报告 manifest 13 项回读 0 错。未创建批准/attempt，未调用付费服务，未提交推送。

## VIMAX-G03-PLAN-RECOVERY-AND-MEDIA-01（2026-10-29）规划离线复验＋媒体阶段（复用规划，零重新规划）

**修正 9 镜头验收接线、对已有规划离线复验；通过后只跑媒体，不重新规划、不重跑 VideoWeaver。**
- **规划复验（零真实 API）**：原规划门 FAIL（登记 verifier 仍要求 indices 0..9/10 镜头）保持；
  验收器参数化（expected_shots 从显式契约或冻结剧本派生，不硬编码 9；缺失/非法/冲突拒绝）；
  对**已有规划**（`vimax-g03-expansion-planning-20261029T072745Z-b1a631cb`）在登记镜像内
  （network=none、只读）重新验收 **ok=True**：storyboard 9（0..8）、descriptions 9、camera 9/8 过渡、
  2 角色、is_last 正确、无环、首帧 i2v small、无媒体产物。11 项定向测试通过
  （8/9/10 各自正例；9 镜头按 10/8 拒绝；缺镜头/相机环/错引用拒绝；改 expected_shots 改变结果）。
- **媒体阶段（复用规划）**：run_id `20261029T081529Z-vimax-g03-expansion-media-01`；镜像完整 ID
  `sha256:a97ea6076fbc…`；staged-planning 语义文件 SHA 与源一致；媒体身份绑定规划哈希＋原规划身份＋
  修订验收；17 个远端视频任务全部受理且 closeout 观测 SUCCEEDED（9 主体＋8 过渡）；14 图片＋17 视频
  下载；原生 `vimax_render_video` concat（shot_count 9）→ final_video.mp4 = **45s/1280×720/30fps/H264/
  无音轨/1350 帧/完整解码**；9 主体 clip 各 5.0s、8 辅助过渡。资源 1383 样本、CPU 186 core-s、
  mem 峰 2.19GB；容器删除回验；媒体 total-token usage partial。
- 工具回放：`ffmpeg-processes.jsonl`（15 子进程）＋render concat 事件＋model-events（create/poll/download
  完整）；远程 17 任务终态 SUCCEEDED。无官方语义评分，不虚构 reward。
- 报告：`reports/analysis/VIDEO-G03-TWO-REPO-EXPANSION-01/`（summary、run-overview、plan-recovery.json、
  tool-replay-readiness、manifest 31 项递归回读 0 错）。原规划 FAIL/身份/批准未改。未提交推送。

## VIDEO-G03-TWO-REPO-EXPANSION-01（2026-10-29）VideoWeaver G03 成功；ViMax G03 规划单次 attempt 未过门（媒体未跑）

**本批只做下一批两组：VideoWeaver G03 → ViMax G03，不同时展开 E03。**
- **VideoWeaver G03（成功）**：run_id `20261029T065904Z-videoweaver-g03-c01`；技术验收 passed
  （image 9/9、video 9/9、downloads 18/18、final.mp4 45s/1280×720/30fps/H264/无音轨）；预算用量
  llm 36/total 1.39M（均远低于 80/3M 上限）、polls 59、downloads 18（=最低预期，cap 27 未被误用为最低）。
  CPU 侧工具轨迹完整（exec_command 49、write_stdin 7 后台轮询关联、merge_videos.py 1、ffprobe 1，
  命令含完整参数/cwd/exit code）。容器删除回验；分析 `reports/analysis/VIDEO-G03-TWO-REPO-EXPANSION-01/`。
- **ViMax G03 规划（单次 attempt，规划门未通过）**：run_id
  `vimax-g03-expansion-planning-20261029T072745Z-b1a631cb`；Agent 产出有效 9 镜头规划（storyboard 0..8、
  9 camera/8 过渡、2 角色），但登记 `plan_verifier.py`（G02 派生未充分适配）仍要求 indices 0..9（10 镜头）
  → plan_check 失败；**配置接线缺陷，非模型/任务结果**。按“每阶段正式 attempt 至多一次”不补跑；
  **媒体阶段未授权、未执行**。已修正 9 镜头 verifier 供未来另行授权的规划 attempt（新 run_id/身份/批准）。
- 本批重点为 CPU 侧工具执行轨迹，非 LLM 请求重放；未启动 Replay 实验；未虚构官方 reward。
- 报告：`reports/analysis/VIDEO-G03-TWO-REPO-EXPANSION-01/`（summary、run-overview、tool-replay-readiness、
  manifest 递归回读）；任务登记/成果索引已更新。未提交推送。

## VIDEO-EIGHT-ANALYSIS-THREE-POINT-CLOSEOUT-01（2026-10-29）3 处残留离线收尾（严格限定，不运行任务）

**只收尾已确认的 3 处残留，不再扩展修复范围。**
- **修复 1（非工具事件误分类）**：`tool_intervals()` 现仅对合法区间 op 建配对组；ViMax 的 usage/diagnostic
  （op=None）等非区间事件被排除并计数（原因/数量进入 machine-results 的 tool_interval_filtering，
  属正常过滤）；缺 request_id 标 unattributed；真实 ambiguous/right_censored/start_missing/invalid_time 保留。
  原 50 项 `tool:None` ambiguous 已归零，实际歧义按记录重新统计；更正“OSL 存在 50 项并发歧义”旧说法。
- **修复 2（网络 gap 真实接线）**：CLI 显式参数 `--netns-gap-s`（默认 5.0s，网络采样契约
  `contract_unknown`，参数/依据写入 machine-results 与 netns-parameter.json 并绑定 manifest）经
  compute_unit→netns_totals→netns_delta_series 真实链路传入；超阈值缺口断开不累计，存在超阈值缺口时
  状态为 partial；RX/TX 独立、缺测≠0、回退/身份隔离不退化。真实记录相邻采样间隔最大约 0.7–2.1s
  （<5.0s），数值不变，但生产入口已实际消费阈值。
- **修复 3（ViMax Agent 时长独立）**：不再令 agent_wall=attempt_wall；仅当 run-record
  `phase_boundaries.agent_work` 存在同一单调域独立起止才计算（G01 media 784.079s、G02 media 1238.732s）；
  无边界则 agent_wall=None、reason 明确（G01/G02 planning）。attempt wall 不受影响。
- 不变量保持：内存采样峰/内核峰、video-use attempt wall（209.188/419.852s）、ViMax 下载 34/33
  （图片/视频分列）、VideoWeaver 请求 32/42 与 entry_rc=0、entry_wall 643.916/754.35 与 attempt_wall
  unknown 均不退化。
- 交付：`reports/analysis/VIDEO-EIGHT-RESULTS-CHARACTERIZATION-01/revision-THREE-POINT-CLOSEOUT-01/`
  （summary/correction-notes/limitations/总表/覆盖/阶段工具/阶段时序/用量媒体/machine-results/netns-parameter/manifest）。
- 测试 92 项通过（55 链＋15 旧聚合＋22 最终入口，其中新增 A–D 直接覆盖本轮 3 点）；manifest 44 项递归
  回读 0 错；`check_project_state` PASS；`git diff --check` 干净。
- 版本说明：`scripts/video_eight_final_aggregate.py` 已演进（FINAL-WIRING-01 manifest 中该代码绑定 SHA
  7743c7e8…/56,493 字节为演进前版本；其输出文件原字节不变仍可回读；此为如实记录的代码演进，未改旧
  manifest 掩盖）。未调用 API、未运行任务、未创建身份/批准，未提交推送。

## VIDEO-EIGHT-ANALYSIS-FINAL-WIRING-01（2026-10-29）4 类残留离线收尾（可完整复现，不重跑任务）

**只收尾上一轮修订未贯通的残留，不运行任何真实任务。**
- 新聚合入口 `scripts/video_eight_final_aggregate.py`（CLI：`--index/--per-run-root/--out`），
  一条命令生成全部产物（summary/correction-notes/limitations/总表/覆盖/阶段工具/阶段时序/用量媒体/
  machine-results/manifest）；输出根排他创建（已存在即拒绝，失败留证据须换新目录）。
- 问题 1（时间口径/字段接线）：attempt/entry/agent/lifecycle/采样窗/CPU 有效区间分列并注明来源、
  clock、精度、范围；VideoWeaver entry 区间（643.916/754.350s）不再放入 attempt_wall（attempt_wall
  保持 unknown，lifecycle UTC 另列）；VideoWeaver llm_calls 32/42、entry_rc 0/0、run_id 进入总表；
  video-use Agent rc 从实际 agent 相位读取；合法 0 不被 or 回退吞掉。
- 问题 2（网络有效增量）：全缺测→None（非 0）、有效零保留；时间倒序/重复、计数回退、读取失败、大 gap
  断开不累计；RX/TX 独立；按 (identity,interface) 分组不跨身份求差；身份继承自 per-run scope 证据、
  无法证明标 unverified；首末累计另列不作流量。
- 问题 3（阶段/工具区间可追溯）：stage-timing.csv 保存起止、clock/单位、session/node/call/request、
  start/end artifact、源行号；OSL 同键并发标 ambiguous（不用 FIFO 伪装）；finish<start 不产出负时长；
  right_censored/start_missing 分列；不同时间域不对齐。
- 问题 4（复现/覆盖保护）：CLI 一次生成全部承诺产物；manifest 在所有输出后生成，递归回读绑定
  输入/聚合器/共享代码/输出/子 manifest。
- 措辞收尾：不写“占大部分（定性）”，改为“记录显示存在远端生成、轮询与下载过程；尚未量化其占完整
  wall 的比例”；video-use ASR=远端 ElevenLabs、OSL ASR=本地模型；Agent 阶段≠本地计算；恢复/修订结果
  不叫原 attempt 连续成功；8 组不是同配置重复。
- 输出：`reports/analysis/VIDEO-EIGHT-RESULTS-CHARACTERIZATION-01/revision-FINAL-WIRING-01/`。
- 验证：86 项测试通过（55 链＋15 旧聚合＋16 新最终入口）；manifest 43 项递归回读 0 错；
  `check_project_state` PASS；`git diff --check` 干净。原 CORRECTION-01 修订与其构建器/测试原字节保留。

## VIDEO-EIGHT-RESULTS-ANALYSIS-CORRECTION-01（2026-10-29）6 项已确认问题离线修订（不重跑任务）

**只修分析，不重跑任何任务。** 原 8 组分析目录与其构建器原字节保留；修复后的聚合逻辑移到
`scripts/video_eight_aggregate.py`，修订输出在
`reports/analysis/VIDEO-EIGHT-RESULTS-CHARACTERIZATION-01/revision-CORRECTION-01/`。
- **问题 1（内存字段）**：原汇总读错字段（`max_memory_current_bytes`），改为
  `max_sampled_memory_current_bytes`（采样 current 峰）与 `max_kernel_memory_peak_bytes`（内核峰）分列；
  10 个单元全部有实测（撤回“多数缺失”与 ASR/FFmpeg 进程归因）。
- **问题 2（wall）**：video-use E01/E02 attempt wall 由 run-record 单调时钟改为 209.188/419.852s
  （原 182/386s 是采样窗）；attempt wall/采样窗/Agent 阶段分列；OSL 用 host-finalization、ViMax 用
  run-record、VideoWeaver 用 stages_rel entry 区间；起止缺失标 unknown。
- **问题 3（下载）**：链 `vimax_media_stats` 补 `video_download`；G01 下载 34（图 19＋视 15）、
  G02 33（图 14＋视 19），字节分列。
- **问题 4（硬编码/阶段耗时）**：聚合逻辑全部动态读取；新增 stage-timing.csv（相位＋可配对工具协议
  区间，finished/right_censored 分列，含配对身份与来源）。
- **问题 5（因果归因）**：撤回“几乎全部/主导/本地 ASR/稳定可复现/某流量即某 API”等表述；video-use
  ASR 为远端 ElevenLabs；无进程证据不作精确归因。
- **问题 6（网络）**：netns 按接口有效区间增量（回退断开、RX/TX 独立），累计首末值另列不作流量。
- 定向测试 70 项通过（55 链＋15 新聚合，直接覆盖修复后逻辑）；manifest 54 项递归回读 0 错；
  `check_project_state` PASS；`git diff --check` 干净。未调用 API、未运行任务、未提交推送。

## VIDEO-EIGHT-RESULTS-CHARACTERIZATION-01（2026-10-29）四仓 8 组现有记录离线行为与本地资源分析（只读，未运行任务；已被 CORRECTION-01 修订）

**对 8 组“仓库×任务”记录做统一描述性分析（4 个已执行输入 E01/E02/G01/G02；ViMax 规划/媒体、OSL 原 attempt/独立恢复分阶段，不伪装成单次连续执行）。**
- 结论：8 组均到达各自最终阶段；时间形态差异＝远端生成等待主导（ViMax/VideoWeaver，轮询/下载）vs 本地 Agent/ASR 主导（video-use/OSL，CPU 高、网络小）；同仓 E02/G02 工作量普遍增大但非全部非线性（OSL E02 反而比 E01 短，不同输入不可比）。reward=0 且评分完整为合法结果。
- 覆盖：10 个分析单元（per-run）由 `scripts/video_analysis_chain.py` 全新目录重算（同口径）；聚合输出 run-overview.csv/json、coverage.csv、stage-tool-summary.csv、request-usage-media.csv、summary.md、limitations.md、manifest.json。
- 关键数字：video-use E01/E02 响应 21/20、tokens 551k/653k、墙钟 182/386s；OSL E01/E02 逻辑请求 38/21、tokens 245k/198k、Agent 1310/727s（均渲染完成、宿主导出失败后独立恢复评分 reward=0）；ViMax G01/G02 planning 66.6/97.1s、media 785/1240s、video_create 15/19、poll 74/119；VideoWeaver G01/G02 llm 32/42、tokens 1.08M/1.67M、墙钟 644/754s。
- 限制：远端推理时间/费用未知；逐工具耗时仅协议间隔；整容器采样无阶段级资源归因；ViMax media total-token 缺失（partial_output_only）、G02 图片来源 PARTIAL；生成任务无官方语义评分；netns≠API 流量；OSL 恢复成本不并入原 Agent。
- 报告：`reports/analysis/VIDEO-EIGHT-RESULTS-CHARACTERIZATION-01/`（summary.md、run-overview.csv/json、coverage.csv、stage-tool-summary.csv、request-usage-media.csv、limitations.md、per-run/、manifest.json）。
- 验证：分析链 54 项测试通过；manifest 47 项回读 0 错；`check_project_state` PASS；`git diff --check` 干净。
- 下一步建议：暂不新增执行；补重复/新增 G03/E03 属另行决策。本轮未调用 API、未运行 Agent、未创建身份/批准，未提交推送。

## 视频阶段结果

四仓已有 **12个仓库×任务组合、6个输入**：video-use/OpenStoryline各E01/E02/E03，ViMax/VideoWeaver各G01/G02/G03。原生轨迹、资源样本、提交物、评分、身份和必要恢复记录见 [视频结果索引](video_results.md) 与 [路径登记](video_results_index.json)。

- video-use E01/E02/E03连续剪辑并完整评分，reward=0；流程有效不等于官方任务通过。
- OpenStoryline E01/E02/E03真实至render后经独立恢复评分，reward=0；原导出失败不追溯改写，恢复成本单列。
- ViMax G01/G02/G03为8/10/9主体、40/50/45s成片；规划/媒体分阶段，G03复验原规划后运行媒体；来源和usage缺口保留PARTIAL。
- VideoWeaver G01/G02/G03连续生成到原生merge；G02原配置FAIL与修订PASS分列。媒体由百炼远端生成，本地不观测远端推理资源。

## 本轮直接清理

用户已明确授权：不用归档，直接删除失败/错素材运行、重复诊断/fake输出和无用视频专属旧快照。有效数据及其规划/恢复、生产源码配置、必要回归fixture保留。非视频数据、参考仓、原素材、模型缓存、venv、凭据和Docker镜像不动。
精确清单见 [删除回执](video_cleanup_20261029_receipt.json)；前后核对见 [保留结果哈希表](video_retained_integrity_20261029.json)。旧状态里的已删除路径只是历史标识，不再当作当前文件入口。

## 下一步

1. 离线整理12组的CPU工具回放材料：调用/命令完整参数、cwd、输入/产物依赖、起止/返回、异步session及资源窗口。
2. 将原attempt、独立恢复/评分、ViMax规划/媒体分层；已有8组聚合仅作历史子集。
3. 本阶段不再因reward=0、语义边界偏差或既有PARTIAL补跑；新增多素材/字幕等覆盖与同配置重复另行决策。
4. 本次仅整理文档，不执行Replay；CPU-02/Replay状态和其他项目保持不变。

本页无新执行授权。见 [扩展计划](video_task_expansion_plan.md)、[分析口径](video_analysis_guidelines.md)、[剪辑排障](video_editing_troubleshooting.md)、[ViMax](vimax_troubleshooting.md)、[VideoWeaver](videoweaver_troubleshooting.md)。

<a id="video-use-optional-coverage-backlog"></a>

## 暂缓可选覆盖

video-use批量转写、动画、字幕、下载、多素材音乐/调色等仅在后续任务明确要求时覆盖；不为增加工具数量强行调用，不加音频理解模型追分。

## 非视频成果和授权边界

公开trace见 [操作v3](../reports/analysis/PUBLIC-TRACE-OPERATIONS-v3/summary.md)、[软件工具v3](../reports/analysis/PUBLIC-TRACE-SOFTWARE-TOOLKITS-v3/summary.md)。
三类本地见 [合并复核v3](../reports/analysis/LOCAL-THREE-CLASS-REPEAT-01-combined-review-v3/summary.md)：9个固定任务各3点，错路由样本单列。本轮不动上述数据或其他对话工作。
G2/G3-R未通过，CPU-02/Replay暂停；未更新HTML、未提交推送。

## 已完成专项：AgentX DeepSeek客户端重复测量

[最终报告](../reports/analysis/AGENTX-DEEPSEEK-FIVE-REPEATS-v1/summary.md)：Full全量分析为393会话、98,827请求；所选5个会话各执行3次，共117个唯一源请求、351次正式客户端执行。只测客户端，未执行原始业务工具，原始长输出负载未完整复现。相关证据已做[同机独立备份](agentx_evidence_backup_20261023.md)。上述边界如实保留，不作为待补跑项。


## 旧锚点兼容

以下仅保持旧链接可定位；已删除中间数据不恢复，旧任务标题不代表当前状态。当前事实从上方结果索引进入。

<a id="current-task"></a>
<a id="历史入口2026-10-24本轮整理"></a>
<a id="video-use-edit-pilot-02"></a>
<a id="video-use-edit-pilot-01"></a>
<a id="video-use-codex-bailian-integration-01"></a>
<a id="bailian-vision-smoke-01"></a>
<a id="video-use-volcano-vision-01"></a>
<a id="video-use-volcano-capability-02"></a>
<a id="video-use-volcano-capability-01"></a>
<a id="video-use-api-review-01"></a>
<a id="video-use-env-01"></a>
<a id="video-four-repo-plan-01"></a>
<a id="当前任务与下一步"></a>
<a id="后续待办video-use-可选能力覆盖暂缓未授权执行"></a>
<a id="video-use-edit-pilot-02一次正式执行与验收已完成"></a>
<a id="pilot-02-验收修订历史原始评分保留"></a>
<a id="video-use-edit-pilot-03单次-attempt-与独立验收已完成"></a>
<a id="pilot-03-离线边界复核与报告修订"></a>
<a id="video-use-edit-pilot-04单次正式执行与验收已完成"></a>
<a id="当前任务video-use-edit-pilot-01一次授权-attempt-已停止未完成真实剪辑"></a>
<a id="当前任务video-use-codex-bailian-integration-01codex百炼工具看图兼容性已验证一次真实-cli-会话"></a>
<a id="素材获取agenticvbench-exp-disfluency-interview-3-task01已获取并核验用户手动上传"></a>
<a id="当前任务bailian-vision-smoke-01百炼-qwen37-plus-图片探针通过发送-11"></a>
<a id="当前任务video-use-volcano-vision-01一次图片探针完成判定-unknown发送-11"></a>
<a id="当前任务video-use-volcano-capability-02工具结果回传补验完成图片未执行发送-12"></a>
<a id="当前任务video-use-volcano-capability-01火山路由三次上限协议探针完成发送-23"></a>
<a id="当前任务video-use-api-review-01只读-api账号模型能力核查完成"></a>
<a id="外部服务清单"></a>
<a id="关键结论"></a>
<a id="需要用户决定提供只问服务模型与环境变量名不需要密钥"></a>
<a id="当前任务video-use-env-01视频环境第一闭环无模型验证完成"></a>
<a id="计划video-four-repo-plan-01可行性核查完成video-use-环境闭环已建真实执行仍未授权"></a>
<a id="四个仓库的可行性与缺口"></a>
<a id="统一记录什么"></a>
<a id="简单推进顺序"></a>
<a id="上一任务local-three-class-repeat-0112次补齐及v3合并复核完成"></a>
<a id="历史阶段v2续批后由complete-02补齐预定槽位"></a>
<a id="原批初次停止时记录保持原义"></a>
<a id="前次任务volcano-three-chain-limited-offline-characterization"></a>
<a id="已完成任务measurement-coverage-unified-01"></a>
<a id="当前任务measurement-coverage-unified-01"></a>
<a id="本轮停止点"></a>
<a id="保留事项与停止边界"></a>
<a id="video-use-edit-pilot-03"></a>
<a id="video-use-edit-pilot-04"></a>
<a id="保留事项与后续清理边界"></a>
