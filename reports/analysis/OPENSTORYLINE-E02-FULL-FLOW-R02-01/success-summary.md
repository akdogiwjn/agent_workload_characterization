# OPENSTORYLINE-E02-FULL-FLOW-R02-01 — 完整正常流程成功（原生剪辑→render→宿主导出→技术检查→一次官方评分）

## 结论

**唯一正式 attempt（run_id `20261101T025952Z-openstoryline-e02-full-flow-r02-01`）真实执行完毕且为完整正常流程：输入/overlay 门禁真实通过（docker inspect 实际挂载源=E02 输入目录、容器内 bytes/SHA=冻结、25 项 overlay 只读挂载容器内 SHA=冻结），原生 interview 链 load_media→split_shots(mode=skip)→local_asr→speech_rough_cut→plan_timeline_pro→render_video 全部成功，Agent 正常返回（rc=0，agent wall 479.66s<1800s 截止），完成判定真实写入 render_artifact_id 与 submission_export_pending，宿主从最终 render 实际消费的 timeline 导出 output.mp4/cuts.json，技术检查真实通过（源/输出帧率精确 60000/1001，exact_equal=true、0 ppm），官方 verifier 完整执行一次（evaluation_complete=true、reward=0.0，合法）。** E02-EXPANSION-01/02 历史失败与独立恢复事实原样保留，不因本运行改写。

## 运行身份与预算（实际冻结值）

- task_id `OPENSTORYLINE-E02-FULL-FLOW-R02-01`；task_kind=interview；observation_id `OPENSTORYLINE-E02-FULL-FLOW-R02-01/openstoryline-e02`
- run_id `20261101T025952Z-openstoryline-e02-full-flow-r02-01`
- 镜像 `openstoryline-task:arm64-native-confirm-flow-03`，ID `sha256:9a1e876c08c10d56c7959111af1a2afc382245e6657032c5da3dd195df5e8bd0`，平台 linux/arm64
- 身份内容 SHA `251cda2368b923f9545c11e63e73122592fd46ace699f62fe86520c8a29798ad`；身份文件 SHA `f21db2534a427bc49f75fb0ce5bfa034413c8576725433fc505695ad225ff0fa`；绑定 65 文件（49 interview 冻结源 + 25 overlay 去重 + task config）
- APPROVAL `openstoryline-e02-full-flow-r02-01-approval-v1` 绑定身份文件 SHA；no_retry=true、retry=0
- 预算：max_logical_requests=60、soft 1,000,000 tokens、单请求输出 32768；recursion_limit=32；total 2700s（agent 1800 / verifier 600 / cleanup reserve 300）；容器 4 CPU / 8GiB；retries=0
- 模型/路由（冻结身份）：qwen3.7-plus / https://dashscope.aliyuncs.com/compatible-mode/v1 / DASHSCOPE_API_KEY / sdk_retries=0 / application_retries=0

## 门禁与冻结（真实生产机制）

- `--check-task-config`：ok，golden_timestamp_leak=[]，edit_policy valid（未继承 E03 content_deletion / assembly 策略，normalized={}）
- `--preflight`：formal_ready=true，image inspect 匹配完整 ID + linux/arm64，命名空间干净，16 项 ASR cache 可读
- `freeze_identity`：真实生产冻结（readiness→image/upstream/task commit→全部绑定），formal_gate_status=PASS
- APPROVAL 在生产冻结后绑定身份文件 SHA
- 容器输入核验 `container-input-verify passed`：**实际 Source=`…/exp-disfluency-interview-4-task01/input`**、bind、readonly、容器内 bytes=689288、SHA=`13d716c63a13fede09874c19fa0508eb68a6ed075b1e427eb27e1e372d5a51b8`、ffprobe 30.029317s/854×480/60000-1001/AAC == 冻结规格
- overlay 核验 `overlay-verify passed`：25 项 overlay 实际只读挂载、容器内 SHA=宿主冻结
- request.json：output_dir=/workspace/output、recursion_limit=32、frozen_identity 内容 SHA 匹配、instruction 含 E02 填充音目标（非 E01）、明确宿主自动提交职责（host adapter derives output.mp4/cuts.json）

## Agent 正常完成（rc=0，无超时）

- agent wall 479.66s（agent_finished−agent_initialized；容器入口 command rc=0、timed_out 无、termination 无）
- 原生工具：10 tool_call_started / 10 tool_call_finished 全成功（load_media 1、split_shots 1、local_asr 1、read_node_history 2、speech_rough_cut 1、plan_timeline_pro 1、elementrec_transition 1、elementrec_text 1、render_video 1）
- 自动依赖：elementrec_text/elementrec_transition/render_video 共享 tool_call_id `call_52059561405f424a9ba6042e`（start/end artifact 均本次 session；render_video start/finish artifact 完全配对）；不凭 call_id 合并
- 模型请求 16/16 全闭合：agent 9 / mcp_sampling 5 / llm_validation 1 / vlm_validation 1；usage 覆盖 16/16，sum_total_tokens 107,437（<1M 软阈值）；unknown_requests=[]、无右删失
- 完成判定真实生效：agent-result.json 含 `render_artifact_id=render_video_1793502527.8456743`、`submission_export_pending=true`；session-status.json 同值；agent-termination.json `status=agent_complete`；render-candidates.jsonl 1 行 `is_final=true`、`timeline_source=exact_payload_match`、`candidate_state=bound`、`timeline_artifact_id=plan_timeline_pro_1793502522.3580658`、`timeline_payload_sha256=24c72d13…`；candidate-finalize-status `finalized=1/1`

## Render→实际 timeline→output.mp4/cuts.json 来源链

- session `env01-cfe35253ebe344a1992efe782e4dd492`；render artifact `render_video_1793502527.8456743`（宿主导出选择依据=agent-result 与 session-status 联合记录、成功同 session MCP 调用消费）
- render 消费 timeline `plan_timeline_pro_1793502522.3580658`（payload SHA `24c72d13…`，3 个 video 项；rendered_source_intervals [[750,2970],[3810,5190],[6710,28910]]，source_duration 30029ms）
- `export_rendered_video`：output.mp4 = 834,081 B、SHA `6a62861170c82d7ee50538f3e11c48bf0d874d377b1c2e469f998485588286c1`，与 render 源逐字节一致
- `export_cuts_from_final_timeline`：cuts.json 从同一 final timeline 派生——4 cuts（[0,750]、[2970,3810]、[5190,6710]、[28910,30029]，reason `outside_final_rendered_source_intervals`），保留源区间总长 25.8s

## 技术检查（真实执行）

- 帧率：source_raw `60000/1001` vs output_raw `60000/1001`，**exact_equal=true**、relative_diff_ppm=0.0、tolerance_passed=true（策略 `openstoryline-frame-rate-bounded-tolerance-v1`）——真实 render 保持精确源帧率，不再出现历史 E02 的 2997/50 舍入
- 视频：H.264 / yuv420p / 854×480 / 60000-1001（59.94fps）
- 音频：AAC / 44100Hz / 立体声 / non_silent=true；video/audio start_time 均 0.000000，同步
- 完整解码（export 内校验通过）；容器时长 25.8s

## 一次官方评分

- `verifier.status=complete`、`evaluation_complete=true`、wrapper_returncode=0、official_judge_returncode=0
- judge SHA `cb5486bac…` == 冻结身份绑定 judge_sha256（E02 task judge 与 E01 同一文件，SHA 一致）
- reward=0.0（合法）；checks 全 evaluated（cut_ranges/duration/ssim/audio_xcorr）
- 详情：`passed 0/2 cuts; ssim=0.9914, audio_xcorr=0.9872888510656003`；n_gt=2、n_submitted=4；honesty_pass=true、audio_pass=true、duration_pass=true；per_cut golden [5.666,6.556]s vs submitted [5.19,6.71]s（start_offset 0.476s>0.3s）、golden [23.076,23.607]s vs submitted [28.91,30.029]s
- 评分完整、reward=0 合法；Agent 自主剪切 4 项 cuts 与 golden 两项位置不完全对齐，如实提交评分，不篡改来源

## 资源（容器 scope，含 MCP/ASR/FFmpeg 子进程）

- 808 行（boundary 2 + sample 806）；目标 0.5s
- CPU 341.88 core-s / 有效区间 497.06s / 均值 0.688 core
- memory.current 采样峰 5,967,896,576 B、kernel peak 6,940,819,456 B
- I/O read 0 / write 462,848 B
- netns 逐接口（容器 netns，非 API 专属）：eth0 rx≈2.15MB/tx≈0.62MB、lo rx/tx≈0.50MB
- 采样窗 497.06s 覆盖 agent 相位 479.66s；measurement_quality complete/continuous、无缺测
- 容器删除回验 `removed`、sampling_status `stopped_and_archived`、cleanup_errors=[]、无残留 openstoryline 容器
- host pre_archive_wall 521.52s；verifier 窗 03:09:19Z→03:09:42Z

## 判定（分别）

1. 程序完成：完整正常——Agent rc=0、无超时、完成判定写入、宿主导出+评分、清理正常。
2. 技术验收：PASS（帧率精确保持 60000/1001、编码/尺寸/音频/同步/解码）。
3. 语义评分：官方 verifier 完整一次，reward=0.0（0/2 cuts），合法失败，不因 score 补跑。
4. 测量质量：complete（808 行、netns 齐全、覆盖 agent 窗口、无缺测）。

## 保护与边界

- 未补跑、未追加第二次 attempt；E02-EXPANSION-01（错误输入观察）与 E02-EXPANSION-02（帧率门拒绝＋独立 FPS 恢复）历史事实原样保留。
- 未改生产代码；本次运行冻结后未边跑边改。
- 未改历史 raw/身份/批准/评分/manifest；未提交推送；未 reset/restore/clean。
- 覆盖计数不变（同一仓库×任务组合的新运行，不增加输入或组合数）。
- live 路径无 offline fake-model 开关（build_container_spec 默认 offline_fake_model=False；request.json 无该键）。

## 证据位置

- raw：`data/raw/generated/OPENSTORYLINE-E02-FULL-FLOW-R02-01/20261101T025952Z-openstoryline-e02-full-flow-r02-01/…`
- raw 独立持久副本：`raw-persistent-copy/`（逐文件 bytes/SHA 一致、`diff -rq` 0 差异；manifest 56 项跨 cwd 回读 0 错）
- 分析：`analysis/`（result.json、summary.md、manifest）
- 启动记录副本：`launch-record.json`；身份：`frozen-identity.json`；批准：`APPROVAL.json`
- 交接记录：`handover-run.md`
