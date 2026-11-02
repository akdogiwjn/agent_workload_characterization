# VIMAX-G01-FULL-FLOW-R05-MEDIA-02 — 完整正常流程成功

## 性质声明

一次新授权真实媒体 attempt 执行完毕并走通**完整正常流程**（attempt 1 / retry 0）：门禁全过、19 逻辑图片生成、15 视频（8 主体 + 7 辅助）生成与下载、原生 concat 产出 **40.000s / H.264 High / 1280×720 / 30fps / 无音轨** 成片、COMPLETE v3 全维度验收通过（含修复后的 `final_path_resolution`）、宿主终态 **native_agent_done（rc=0）**、容器清理回验。MEDIA-01 失败观察与全部证据原样保留，未复用其任何媒体产物。

## 1. 预检、实际测试数量、生产修改

- 发送前核验全 PASS：planning source、19/15/34、budget→env→ledger（video_polls=1380 硬 cap）、audio=false 贯通、adapter 只读挂载+容器内 SHA=冻结、修复后 host_runner 绑定、COMPLETE v3、原生 concat、资源流/startup gate。
- **本轮 fresh 测试**：MEDIA-FINAL-PATH-REPAIR-01 修复链 42 PASS（final_artifact_path 12 + complete_schema_deadline 19 + host_lifecycle 4 + deadline_race 7）；媒体预算 helper 40 + 轮询上界 6 = 46 PASS；容器内视频创建策略 17/17 PASS；容器内图片创建策略 25/25 PASS；`resolve_final_artifact_path` 定向正反例（相对/绝对/cwd 无关/缺文件/穿越/symlink 逃逸/错 session/NUL/反斜杠/URL/workspace 根）全 PASS；verify_identity_approval、validate_planning_source、image identity PASS。旧日志不计。
- **生产修改：零**。仅新建正式配置、staged-planning 可追溯复制、新媒体身份/APPROVAL、launch 记录。MEDIA-FINAL-PATH-REPAIR-01 为既有已验收修复，本轮绑定其 host_runner SHA。

## 2. run/session、镜像、身份、实际命令

- run_id `g01-full-flow-r05-media-02-20261101T141641Z-6e4a9447`；session `g01-full-flow-r05-media-02`；source session `g01-full-flow-r05-planning-01`
- 镜像 `vimax-task-bailian:arm64-v7-capability-planning-01` = `sha256:a97ea6076fbcd456ada0d0e1267ebf50058daa52698e0996cffaf66da1f176f3`（linux/arm64）
- 身份文件 SHA `7b8d66340d719ea436e3358d2ecab0333b69102b2c4f6a711c0699155ae5e103`（= APPROVAL frozen_identity_sha256，非 synthetic；绑定源规划身份 `9085c610…`、修复后 host_runner `fe7d6b4d…` 及全部语义文件）
- 命令：`python3 -B env/video/vimax/VIMAX-MEDIA-ENTRY-REPAIR-01/host_runner.py run --out data/raw/generated/VIMAX-G01-FULL-FLOW-R05-MEDIA-02/g01-full-flow-r05-media-02 --config env/video/vimax/task-configs/G01-full-flow-r05-media-02-formal.json`（setsid nohup，PID 1535210）

## 3. 零重新规划、规划语义一致、新工作区无旧媒体

- 未调用 vimax_narrative_planning；staged-planning 与 R05 规划 raw 逐字节一致（diff 0）；registered script/storyboard/camera_tree/characters/8×shot_description SHA 等于规划登记值。
- 新命名空间 `env/video/vimax/VIMAX-G01-FULL-FLOW-R05-MEDIA-02/` 启动前无任何 PNG/MP4/首帧/缓存；正式工作区为全新目录。未复制 MEDIA-01 肖像/候选/视频/过渡/final/task_id/ledger。

## 4. 预算实际消费者及对账

- env：`VIMAX_BAILIAN_BUDGET_VIDEO_POLLS=1380`（ledger 硬 cap，覆盖默认 1800）等全部进入。
- ledger：image_generations **19/19**、video_creates **15/30**（尝试口径）、video_polls **148/1380**、media_downloads **34/34**、llm_calls **26/80**；observed_output_tokens_total **4475**（<500000 软阈值）；`unclosed_requests={}`。
- 图片：逻辑 19 = 3 肖像 + 16 候选；HTTP 发送 **19**（0 429/0 重试）；下载 19。
- 视频：创建尝试 15 = 受理 15；终态 **15/15 SUCCEEDED**（closeout 复核，usage.audio=false、output_video_duration=5、SR=720）；轮询 148；下载 15。
- 正常下载合计 **34**；closeout 复下载 15（独立于 34 cap，落盘 attempt/remote-closeout/）。

## 5. audio=false、主体/辅助映射、远端终态

- audio=false 端到端：配置 `video_generation.audio=false` → env `VIMAX_BAILIAN_VIDEO_AUDIO=false` → payload `parameters.audio=false` → 远端 usage.audio=false（15/15）→ 25 clip 与 final 均 0 音轨；expected.audio=none。
- 主体 8（shots/0..7/video.mp4，H.264/1280×720/30fps/5.000s/无音轨）；辅助 7（shots/1..7/transition_video_from_shot_0.mp4，同规格）；辅助不入最终 40s concat。

## 6. 原生concat、final规格/顺序/解码/SHA

- 原生 `script2video_pipeline.__call__` `concatenate_videoclips([shots/{0..7}/video.mp4])` → `write_videofile(libx264)`；容器日志 concat_start(shot_count=8)→concat_done→render_done。
- final_video.mp4：40.000s / H.264 High / 1280×720 / yuv420p / r_frame_rate=avg_frame_rate=30/1 / 0 音轨 / 完整解码 OK / bytes 13,986,232 / SHA `639e778b68eb101d…`；顺序主体 0→7，时长 8×5s 一致。

## 7. 相对路径如何被真实宿主接受（final_path_resolution 证据）

- 生产者 `vimax_adapters.vimax_render_video` 原生写入工作区相对路径 `final_video_path=.working_dir/g01-full-flow-r05-media-02/script2video/final_video.mp4`（未改 fixture 为绝对路径）。
- 修复后宿主 `resolve_final_artifact_path` 以 `/workspace` 为基准映射到**本次** mounted workspace（不依赖宿主 cwd），run-record `complete_marker_assessment.final_path_resolution` 记录：`owned=true, exists=true, workspace_relative=.working_dir/g01-full-flow-r05-media-02/script2video/final_video.mp4, host_path=<本次 raw>/workspace/.working_dir/…, reason=null`。
- COMPLETE v3：`final_path_owned=true`、`final_artifact_exists=true`、`final_artifact_accepted=true` → 宿主终态 **native_agent_done**（rc=0）。

## 8. COMPLETE v3、截止、宿主终态、退出与清理

- v3 各维度全 True；required_work_finished（2469935.151s）< work_deadline（2473771.318s），deadline_reached_at_observation=false（5400s 内完成）；容器 exit 0、removed 验证 True；cleanup_errors=[]；host total_wall 1564.65s。

## 9. trace/请求闭合、usage、unknown及远端closeout

- 工具 1 次 vimax_render_video ok=True；账本 unclosed_requests={}；llm 26 行 sum_total 112,385（prompt 107,910 / completion 4,475）；媒体 usage 19 图 + 15 视频（audio=false）；远端 closeout 15/15 SUCCEEDED 复核。
- unknown：费用金额无账单；语义一致性 not_evaluated。HTTP/usage 均有账本证据。

## 10. 各时间窗口、资源指标与质量

- 3124 样本；CPU 185.82 core-s / 有效 1563.33s / 均值 0.119 core；mem kernel peak 1,558,937,600 B / sampled max 1,551,814,656 B；I/O read 0 / write 200,704 B；netns 784 行、eth0 rx≈105.1MB / tx≈258.6MB（逐接口累计，非 API 专属）；host total_wall 1564.65s。
- 阶段分列：规划 77.99s、媒体 Agent/必需工作 1563.3s、remote closeout（短于收尾窗）、审批等待不计入媒体窗口。测量质量 complete。

## 11. raw/副本文件数、manifest及历史保护

- raw：133 文件（208M）；raw-persistent-copy 133 文件，diff -rq 0 差异（副本多 1 个 manifest.json，payload 与 raw 完全一致）。raw manifest 133 项、报告 manifest 全项，跨 cwd 独立回读 0 错（manifest 不自哈希）。
- MEDIA-01 失败观察、原始证据、两个 manifest（138/129）及全部历史证据原样保留；未提交推送、未改 execution_authorization；覆盖计数不变。

## 12. 判定

程序完成（Agent rc=0 正常 + COMPLETE v3 全维度 + 宿主 native_agent_done）+ 技术 PASS（媒体生成/下载/原生 concat/final 规格全达标）+ 语义 not_evaluated + 官方 not_integrated/not_run（reward=null）+ 测量质量 complete。**R05 标完整流程完成。**
