# OPENSTORYLINE-E01-FULL-FLOW-R01-02 — 完整正常流程成功（原生剪辑→render→宿主导出→技术检查→一次官方评分）

## 结论

**唯一正式 attempt（run_id `20261031T183007Z-openstoryline-e01-full-flow-r01-02`）真实执行完毕且为完整正常流程：输入/overlay 门禁真实通过，原生 interview 链 load_media→split_shots→local_asr→speech_rough_cut→plan_timeline_pro→render_video 全部成功，Agent 正常返回（rc=0，无超时，agent wall 1076.69s<1800s 截止），完成判定真实写入 render_artifact_id 与 submission_export_pending，宿主从最终 render 实际消费的 timeline 导出 output.mp4/cuts.json，技术检查真实通过，官方 verifier 完整执行一次（evaluation_complete=true、reward=0.0，合法）。** 上一轮 R01-01 的失败观察原样保留，不因本运行改写。

## 运行身份与预算（实际冻结值）

- task_id `OPENSTORYLINE-E01-FULL-FLOW-R01-02`；task_kind=interview；observation_id `OPENSTORYLINE-E01-FULL-FLOW-R01-02/openstoryline-e01`
- run_id `20261031T183007Z-openstoryline-e01-full-flow-r01-02`
- 镜像 `openstoryline-task:arm64-native-confirm-flow-03`，ID `sha256:9a1e876c08c10d56c7959111af1a2afc382245e6657032c5da3dd195df5e8bd0`，平台 linux/arm64
- 身份内容 SHA `9cc0e3630c125baa242c2365e05dc5431317b249bf3d6565c23b435171c23b5d`；身份文件 SHA `7e9cbbb8356d7db868c6c3065df1288f1a812166487f384f7f5f63383381261c`；绑定 65 文件（49 interview 冻结源 + 25 overlay 去重 + task config）；required_frozen_sources 无缺失
- APPROVAL `openstoryline-e01-full-flow-r01-02-approval-v1` 绑定身份文件 SHA；no_retry=true、retry=0
- 预算：max_logical_requests=60、soft 1,000,000 tokens、单请求输出 32768；recursion_limit=32；total 2700s（agent 1800 / verifier 600 / cleanup reserve 300）；容器 4 CPU / 8GiB；retries=0
- 模型/路由（冻结身份）：qwen3.7-plus / https://dashscope.aliyuncs.com/compatible-mode/v1 / DASHSCOPE_API_KEY / sdk_retries=0 / application_retries=0

## 门禁与冻结（真实生产机制）

- `--check-task-config`：ok，golden_timestamp_leak=[]，edit_policy valid
- `--preflight`：formal_ready=true，image inspect 匹配完整 ID + linux/arm64，命名空间干净，16 项 ASR cache 可读
- `freeze_identity`：真实生产冻结（readiness→image/upstream/task commit→全部绑定），formal_gate_status=PASS
- APPROVAL 在生产冻结后绑定身份文件 SHA
- `load_runtime_approval` 执行前重校验通过（全部绑定文件重哈希一致、必需绑定无缺失、磁盘输入==冻结输入、命名空间干净）
- 容器输入核验 `container-input-verify passed`：实际 Source=E01 输入目录、只读挂载、容器内 bytes/SHA=`a9bce74a…`/2017306
- overlay 核验 `overlay-verify passed`：25 项 overlay 实际只读挂载、容器内 SHA=宿主冻结

## Agent 正常完成（rc=0，无超时）

- agent wall 1076.69s（容器入口 command rc=0、timed_out 无、termination 无）；agent_finished−agent_initialized ≈1061.5s
- 原生工具：11 tool_call_started / 11 tool_call_finished 全成功（load 1、split 1、local_asr 1、speech_rough_cut 1、plan_timeline_pro 1、render_video 1、elementrec_text 1、elementrec_transition 1、read_node_history 3）
- 自动依赖与历史 E01 一致：elementrec_text/elementrec_transition 与 render_video 共享 tool_call_id `call_44f36897…`（start/end artifact 均本次 session）；render_video start/finish artifact 完全配对（`render_video_1793472486.4214995`）；不凭 call_id 合并
- 模型请求 36/36 全闭合：agent 10 / mcp_sampling 24 / llm_validation 1 / vlm_validation 1；usage 覆盖 36/36，sum_total_tokens 205,470（<1M 软阈值）；unknown_requests=[]、无右删失
- 完成判定真实生效：agent-result.json 含 `render_artifact_id=render_video_1793472486.4214995`、`submission_export_pending=true`；session-status.json 同值；agent-termination.json `status=agent_complete`；render-candidates.jsonl 1 行 `is_final=true`、`timeline_source=exact_payload_match`、`candidate_state=bound`、`timeline_artifact_id=plan_timeline_pro_1793472429.4117346`、`timeline_payload_sha256=9ae7447c…`；candidate-finalize-status `finalized=1/1`

## Render→实际 timeline→output.mp4/cuts.json 来源链

- session `env01-924924885a1e49138c7b9437b6d0e59d`；render artifact `render_video_1793472486.4214995`（宿主导出选择依据=agent-result 与 session-status 联合记录、成功同 session MCP 调用消费）
- render 消费 timeline `plan_timeline_pro_1793472429.4117346`（payload SHA `9ae7447c…`，11 个 video 项，rendered_source_intervals [[490,21990],[22940,36980]]，source_duration 37000ms）
- `export_rendered_video`：output.mp4 = 2,009,938 B、SHA `ccfd7d6292dda14a13af3e8b0c47c5f21ea52fe9910587dae6c21055f65b14c6`，与 render 源逐字节一致
- `export_cuts_from_final_timeline`：cuts.json 从同一 final timeline 派生——3 cuts（[0,490]、[21990,22940]、[36980,37000]，reason `outside_final_rendered_source_intervals`），保留源区间总长 35.54s

## 技术检查（真实执行）

- 帧率：source_raw `25/1` vs output_raw `25/1`，exact_equal=true、relative_diff_ppm=0、tolerance_passed=true（策略 `openstoryline-frame-rate-bounded-tolerance-v1`）
- 视频：H.264 / yuv420p / 854×480 / 25fps / 时长 35.52s（容器 format 35.54s）
- 音频：AAC / 44100Hz / 立体声 / non_silent=true
- 完整解码（export 内解码校验通过）

## 一次官方评分

- `verifier.status=complete`、`evaluation_complete=true`、wrapper_returncode=0、official_judge_returncode=0
- judge SHA `cb5486bac…` == 冻结身份绑定 judge_sha256
- reward=0.0（合法）；checks 全 evaluated（cut_ranges/duration/ssim/audio_xcorr）
- 详情：`passed 0/1 cuts; ssim=0.9849, audio_xcorr=0.9809944506962859`；n_gt=1、n_submitted=3；honesty_pass=true、audio_pass=true、duration_pass=true；per_cut：golden [25.32,26.205]s vs matched submitted idx1 [21.99,22.94]s

## 资源（容器 scope，含 MCP/ASR/FFmpeg 子进程）

- 1757 行（boundary_start 1 + sample 1755 + boundary_end 1）；目标 0.5s，周期点中位 0.6015s、最大 gap 0.7068s
- CPU 471.43 core-s / 有效区间 1078.44s / 均值 0.437 core
- memory.current 采样峰 5,525,487,616 B、kernel peak 6,944,653,312 B
- I/O read 0 / write 774,144 B
- netns 逐接口（lo/eth0 首末累计：eth0 rx≈5.53MB/tx≈1.36MB、lo rx/tx≈0.78MB；容器 netns，非 API 专属流量；本地资源不含远端模型/ASR 计算）
- 采样窗 1078.44s 覆盖 agent 相位 1076.69s；measurement_quality complete/continuous、coverage_ratio 1.0、identity_verified=true
- 容器删除回验 `removed`、sampling_status `stopped_and_archived`、cleanup_errors=[]
- host pre_archive_wall 1105.44s；verifier 窗 18:49:05Z→18:49:30Z

## 判定（分别）

1. 程序完成：完整正常——Agent rc=0、无超时、完成判定写入、宿主导出+评分、清理正常。
2. 技术验收：PASS（帧率/编码/尺寸/音频/解码）。
3. 语义评分：官方 verifier 完整一次，reward=0.0（0/1 cuts），合法失败，不因 score 补跑。
4. 测量质量：complete（1757 行、netns 齐全、覆盖 agent 窗口、无缺测）。

## 保护与边界

- 未补跑、未追加第二次 attempt；R01-01 失败观察（OPENSTORYLINE-E01-FULL-FLOW-R01-01）原样保留。
- 未改生产代码；本次运行冻结后未边跑边改。
- 未改历史 raw/身份/批准/评分/manifest；未提交推送；未 reset/restore/clean。
- 覆盖计数不变（同一仓库×任务组合的新运行，不增加输入或组合数）。

## 证据位置

- raw：`data/raw/generated/OPENSTORYLINE-E01-FULL-FLOW-R01-02/20261031T183007Z-openstoryline-e01-full-flow-r01-02/…`
- raw 独立持久副本：`raw-persistent-copy/`（逐文件 bytes/SHA 一致、`diff -rq` 0 差异）
- 分析：`analysis/`（result.json、summary.md、curves/、manifest）
- 启动记录副本：`launch-record.json`；身份：`frozen-identity.json`；批准：`APPROVAL.json`
- 交接记录：`handover-run.md`
