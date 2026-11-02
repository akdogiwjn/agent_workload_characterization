# OPENSTORYLINE-ASSEMBLY-FULL-FLOW-R04-01 — 完整正常流程成功（12素材→视觉理解→自主选4→排序→timeline→render→宿主导出solution）

## 结论

**唯一正式 attempt（run_id `20261101T062526Z-openstoryline-assembly-full-flow-r04-01`）真实执行完毕且为完整正常流程：输入/overlay 门禁真实通过（docker inspect 实际 Source=12素材目录、只读挂载、27 项 overlay 只读挂载容器内 SHA=冻结）；原生 assembly 链真实走通 load_media→split_shots(skip)→understand_clips（12 素材视觉理解）→filter_clips（自主选恰好 K=4 个不同 clip：clip_0001/0002/0003/0005）→group_clips（按 storyboard slot 排序：clip_0002→clip_0001→clip_0005→clip_0003）→plan_timeline_pro（4 video 项 10.mp4→4.mp4→5.mp4→3.mp4 全片）→render_video；Agent 正常返回 rc=0（无超时，agent wall 475.00s<1800s），**assembly 完成判定真实生效（不再误用 interview 必需节点）**，写入 render_artifact_id 与 submission_export_pending → 宿主从最终 render 实际消费的 timeline 导出 solution.mp4/solution.json → 技术验收通过（结构 10 项 check 全 PASS、媒体完整解码）→ 归档清理正常。**official_evaluation=not_integrated、reward=null、semantic_evaluation=not_evaluated**（官方裁判未接入，结构/技术验收不等于故事板五字段语义正确）。历史 EXECUTION-02/03/04 原样保留。**

## 运行身份与预算（实际冻结值）

- task_id `OPENSTORYLINE-ASSEMBLY-FULL-FLOW-R04-01`；task_kind=assembly；run_id `20261101T062526Z-openstoryline-assembly-full-flow-r04-01`
- 镜像 `openstoryline-task:arm64-native-confirm-flow-03`，ID `sha256:9a1e876c08c10d56c7959111af1a2afc382245e6657032c5da3dd195df5e8bd0`，linux/arm64
- 身份内容 SHA `c8017dc9cfbbf29b05463ebe95f1cc69c78fa661b5a1ceae7a4fde13a46cc539`；身份文件 SHA `a53d682ffbf234eae0cd6a8a97c1ff742e253141f38ff8331c457193896f89a8`；绑定 42 文件（assembly 冻结源 + 27 overlay + task config + 8 storyboard 模板）
- APPROVAL `openstoryline-assembly-full-flow-r04-01-approval-v1` 绑定身份文件 SHA；no_retry=true
- 预算：**max_logical_requests=60（assembly，未继承 E03 的 100）**、soft 1,000,000、单请求输出 32768；recursion_limit=32；total 2700s（agent 1800 / verifier 600 为墙钟记账槽位 / cleanup reserve 300）；容器 4 CPU/8GiB；retries=0
- filter_clips 节点额度：base_max_tokens=8192、max_tokens_cap=8192、max_parse_retries=0（effective 8192）；group_clips：4096/16384/retries0（未提高）
- 模型/路由：qwen3.7-plus / dashscope / DASHSCOPE_API_KEY / retries=0

## 门禁与冻结（真实生产机制）

- `--check-task-config` ok（task_kind=assembly、12 输入 SHA 全匹配、contract segments=4、无 golden 泄漏）
- `--preflight`：首次因 `assembly_offline_gate_invalid:assets_valid` 拒绝——`assembly-offline-gate.json` 的 assets 登记 `openstoryline_pilot_entry.py` SHA `9f280e94…` 过期（READINESS-01/FINAL-CLOSEOUT 改动后为 `fc0e4052…`）。**确定性部署资产过期缺陷**，按授权最小修复：留 pre-change 快照、重算 gate assets 为当前磁盘 SHA、保留修复前 preflight 记录到 evidence。修复后 preflight formal_ready=true。
- `freeze_identity` FROZEN（budget 60/1M/32768、42 文件、27 overlay、output_contract segments=4）
- APPROVAL 绑定身份文件 SHA
- 容器输入核验 passed（实际挂载 12 素材目录、只读）；overlay 核验 passed（27 项）
- request.json：budget 60/1M/32768、frozen identity 一致、assembly 引导、无 golden、4 storyboard slots、12 clips

## Agent 自主选段与装配链

- understand_clips 12 素材视觉理解（12 个 clip_caption）
- filter_clips 自主选恰好 K=4 个不同 clip：`clip_0001/0002/0003/0005`
- group_clips 按 storyboard slot 排序：Slot1→clip_0002(10.mp4)、Slot2→clip_0001(4.mp4)、Slot3→clip_0005(5.mp4)、Slot4→clip_0003(3.mp4)；无增删重
- plan_timeline_pro 4 video 项（10.mp4→4.mp4→5.mp4→3.mp4，全片 window 0→duration）
- render_video 生成 21.049s 视频；**未注入历史选片/timeline/render**

## 完成链路与来源链

- render-candidates.jsonl 1 行 `timeline_source=exact_payload_match`、`candidate_state=bound`、`is_final=true`、timeline `plan_timeline_pro_1793514860.702099`、payload SHA `d9dd3ca1…`
- agent-termination `agent_complete`；agent-result/session-status 含 `render_artifact_id=render_video_1793514865.485898`
- **assembly 完成判定正常**：task-kind-aware（不再误用 interview 的 local_asr/speech_rough_cut）；submission_status `assembly_verified`；assembly_export `exported`
- solution.mp4（2,549,661 B、SHA `4e1bc351…`、1080×608/30fps/AAC）与 render 源**逐字节一致**
- solution.json 4 段连续 half-open：source 10→4→5→3，全 source_range 从 0，output [0,4.566]→[4.566,9.732]→[9.732,15.024]→[15.024,21.049]

## 技术验收（真实执行）

- verification ok=true；structural 10 项 check 全 PASS（schema_object/segment_count/contiguous/start_zero/source_format/source_range_full/no_duplicate_source/total_matches_media/half_open_intervals/frame-quantization 策略 `openstoryline-assembly-final-media-frame-quantization-v1`，tolerance 0.0353s）
- media：H.264/yuv420p/1080×608/30fps、AAC 44100 立体声、duration 21.049s、full_decode_ok=true

## 官方/语义

- official_evaluation `not_integrated_official_evaluation`、reward=null、evaluation_complete=false（官方裁判未接入）
- semantic_evaluation `not_evaluated`（故事板五字段匹配未机器证明）；结构验收通过不等于选片语义正确

## 工具/请求/资源

- 工具 13/13 全闭合（load 1/split 1/understand 1/read 4/filter 1/group 1/plan 1/elementrec 2/render 1）；自动依赖 elementrec/render 共享 call_id `call_f8ce9815…`
- 模型请求 29/29 闭合（agent 12/mcp 15/validation 2），usage 覆盖 29/29、sum_total_tokens 207,703（<1M）、0 右删失、0 blocked
- 资源 812 行（boundary 2+sample 810）；CPU 81.41 core-s/有效 492.71s/均值 0.165；mem 峰 1,552,654,336B、kernel peak 1,553,055,744B；I/O read0/write765,952B；netns eth0 rx≈1.40MB/tx≈4.38MB、lo≈0.70MB
- 采样窗 492.71s 覆盖 agent 475.00s；container removal=removed；cleanup_errors=[]；host total 494.38s

## 判定（分别）

1. 程序完成：完整正常（Agent rc=0、assembly 完成判定、宿主导出、技术验收、清理正常）。
2. 技术验收：PASS（结构 10 项 + 媒体解码）。
3. 语义/官方：not_evaluated / not_integrated（reward=null），如实记录。
4. 测量质量：complete（812 行、netns 齐全、无缺测）。

## 保护与边界

- 未补跑、未追加 attempt；EXECUTION-02/03/04 历史失败与独立恢复原样保留。
- 发送前唯一代码改动：刷新 assembly-offline-gate.json 资产 SHA（部署资产过期修复），留 pre-change 快照与修复前 preflight 记录；未改语义/预算/模型/工具。
- 未改历史 raw/身份/批准/评分/manifest；未提交推送；未 reset/restore/clean。
- 覆盖计数不变；R01/R02/R03 保持完成；R05–R09 不启动。
- live 无 offline fake-model（真实 Agent/模型模式）。

## 证据位置

- raw：`data/raw/generated/OPENSTORYLINE-ASSEMBLY-FULL-FLOW-R04-01/20261101T062526Z-openstoryline-assembly-full-flow-r04-01/…`
- raw 独立副本：`raw-persistent-copy/`（磁盘实际 56 文件 / manifest 登记 53 项 + 3 排除控制文件；逐文件 bytes/SHA 一致、diff -rq 0 差异、跨 cwd 回读 0 错）
- 分析：`analysis/`（result.json、summary.md、curves/、manifest）
- 启动记录副本：`launch-record.json`；身份：`frozen-identity.json`；批准：`APPROVAL.json`；交接：`handover-run.md`
- 发送前修复：`pre-change/`（gate 快照）、`evidence/preflight-before-gate-refresh.json`
