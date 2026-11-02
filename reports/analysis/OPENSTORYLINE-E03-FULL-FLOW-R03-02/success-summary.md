# OPENSTORYLINE-E03-FULL-FLOW-R03-02 — 完整正常流程成功（原生内容删除→render→宿主导出→技术检查→一次官方评分）

## 结论

**唯一正式 attempt（run_id `20261101T054433Z-openstoryline-e03-full-flow-r03-02`）真实执行完毕且为完整正常流程：输入/overlay 门禁真实通过（docker inspect 实际 Source=E03 输入目录、只读挂载、容器内 bytes=11604798/SHA=`c66f380a…`=冻结、ffprobe 90.006583s/854×480/24000-1001/AAC 匹配；27 项 overlay 只读挂载、容器内 SHA=冻结）；原生 interview 链真实走通 load_media→split_shots(skip)→local_asr→speech_rough_cut（41 句内部请求全部成功、0 降级）→plan_timeline_pro→render_video，Agent 正常返回 rc=0（无超时，agent wall 950.95s<1800s），完成判定真实写入 render_artifact_id 与 submission_export_pending → 宿主从最终 render 实际消费的 timeline 正常导出 output.mp4/cuts.json → 技术检查真实通过（帧率源/输出精确 24000/1001、exact_equal=true、0 ppm）→ 官方 verifier 完整执行一次（evaluation_complete=true、reward=0.0，合法）。** R03-01 失败观察原样保留，不改写。

## 预算整链（本轮核心验收）

- 配置 `request_budget.max_logical_requests=100` → 冻结身份 budget `{100, 1000000, 32768}` → 实际 request.budget 同值 → 容器 configure_budget 消费 → ledger 上限 100。
- token 软阈值固定 1,000,000、单请求输出固定 32,768（未随任务放宽）。
- 实际使用 52 次逻辑请求（<100），预算未触及；默认 60 的全局默认不变。

## 运行身份与预算（实际冻结值）

- task_id `OPENSTORYLINE-E03-FULL-FLOW-R03-02`；task_kind=interview；run_id `20261101T054433Z-openstoryline-e03-full-flow-r03-02`
- 镜像 `openstoryline-task:arm64-native-confirm-flow-03`，ID `sha256:9a1e876c08c10d56c7959111af1a2afc382245e6657032c5da3dd195df5e8bd0`，linux/arm64
- 身份内容 SHA `fe05a47074e63314279a51ba7e07288a16172fe45aab28f45cdf881c3d0e768a`；身份文件 SHA `bb72d61413df14b70584e37c6d66a34d6f30a5f4b53b7938648f6396ae71e46e`；绑定 66 文件（48 interview 冻结源 + 27 overlay 去重 + task config）
- APPROVAL `openstoryline-e03-full-flow-r03-02-approval-v1` 绑定身份文件 SHA；no_retry=true
- 预算：max_logical_requests=100（批准的单任务值）、soft 1,000,000、单请求输出 32768；recursion_limit=32；total 2700s（agent 1800/verifier 600/cleanup reserve 300）；容器 4 CPU/8GiB；retries=0
- 模型/路由：qwen3.7-plus / dashscope / DASHSCOPE_API_KEY / retries=0

## 门禁与冻结（真实生产机制）

- `--check-task-config` ok（无 golden 泄漏、edit_policy content_deletion+forbid_added_subtitles 规范化正确）
- `--preflight` formal_ready=true、镜像匹配、16 ASR cache
- `freeze_identity` FROZEN（budget 100/1M/32768、66 文件、27 overlay 全绑定）
- APPROVAL 绑定身份文件 SHA
- 容器输入核验 passed（实际挂载 E03、容器内 bytes/SHA/ffprobe 匹配）
- overlay 核验 passed（27 项）
- request.json：budget 100/1M/32768、frozen identity budget 一致、frozen sha 匹配、E03 目标、无 golden 泄漏、无 E02/assembly

## Agent 自主选段与内容删除

- Agent 自主选删除区间 `[29190ms,38760ms]`（与 R03-01 判断一致）
- speech_rough_cut 41 句内部请求**全部成功**（0 降级、0 解析失败），实际删除 `[29190,30810]ms`
- **仅一次粗剪即完成**，Agent 未发起第二轮（R03-01 因预算 60 耗尽被截断；本轮预算 100 下第一轮完整成功）
- rendered_source_intervals `[[0,29190],[30810,90007]]`；非目标内容保留（未额外清洗首尾/停顿）
- timeline：2 video 项、**0 text/subtitle 项**（forbid_added_subtitles 生效）

## 技术检查（真实执行）

- 帧率：source `24000/1001` vs output `24000/1001` **exact_equal=true**、0 ppm、tolerance_passed=true
- 视频：H.264/yuv420p/854×480/59.94fps（23.976）
- 音频：AAC/44100Hz/立体声/non_silent、音视频 start 0 对齐
- 容器时长 88.39s；output.mp4（10,671,049B、SHA `bada9078…`）与 render 源逐字节一致

## 一次官方评分

- verifier complete、evaluation_complete=true、wrapper/judge rc 0、judge SHA `cb5486bac…`==冻结
- **reward=0.0**（`passed 0/1 cuts; ssim=0.9817, audio_xcorr=0.9966`；n_gt=1、n_submitted=1；honesty/audio/duration pass）
- per_cut：golden `[29.143,34.328]s` vs submitted `[29.19,30.81]s`，start_offset 0.047s（通过）但 end_offset 3.518s（>0.2s 不通过）——Agent 删除 `[29190,30810]` 与 golden `[29143,34328]` 尾部相差约 3.5s
- 评分完整、reward=0 合法；Agent 自主选段如实提交，不修改 cuts/不重评

## 工具/请求/资源

- 工具 10/10 全闭合（load 1/split 1/local_asr 1/read 2/speech 1/plan 1/elementrec 2/render 1）；自动依赖 elementrec/render 共享 call_id `call_33b6f9a2…`
- 模型请求 52/52 闭合（agent 9/mcp 41/validation 2），usage 覆盖 52/52、sum_total_tokens 248,393（<1M）、0 右删失、0 blocked
- 资源 1570 行（boundary 2+sample 1568）；CPU 780.22 core-s/有效 967.10s/均值 0.807；mem 峰 5,479,772,160B、kernel peak 6,946,013,184B；I/O read 0/write 974,848B；netns eth0 rx≈4.30MB/tx≈1.36MB、lo≈1.03MB
- 采样窗 967.10s 覆盖 agent 950.95s；container removal=removed；cleanup_errors=[]；host total 1033.82s

## 判定（分别）

1. 程序完成：完整正常（Agent rc=0、宿主导出、技术检查、一次评分、清理正常）。
2. 技术验收：PASS（帧率精确 24000/1001、编码/音频/同步/解码）。
3. 语义评分：官方完整一次、reward=0.0（合法），Agent 自主删除区间与 golden 尾部不命中，如实报告。
4. 测量质量：complete（1570 行、netns 齐全、无缺测）。

## 保护与边界

- 未补跑、未追加 attempt；R03-01 失败观察原样保留。
- 未改生产代码；本次运行冻结后未边跑边改。
- 未改历史 raw/身份/批准/评分/manifest；未提交推送；未 reset/restore/clean。
- 覆盖计数不变；R01/R02 保持完成；R04–R09 不启动。
- live 无 offline fake-model（build_container_spec 默认 False；request 无该键）。

## 证据位置

- raw：`data/raw/generated/OPENSTORYLINE-E03-FULL-FLOW-R03-02/20261101T054433Z-openstoryline-e03-full-flow-r03-02/…`
- raw 独立副本：`raw-persistent-copy/`（磁盘实际 58 文件 / manifest 登记 55 项 + 3 排除控制文件；逐文件 bytes/SHA 一致、diff -rq 0 差异、跨 cwd 回读 0 错）
- 分析：`analysis/`（result.json、summary.md、curves/、manifest）
- 启动记录副本：`launch-record.json`；身份：`frozen-identity.json`；批准：`APPROVAL.json`；交接：`handover-run.md`
