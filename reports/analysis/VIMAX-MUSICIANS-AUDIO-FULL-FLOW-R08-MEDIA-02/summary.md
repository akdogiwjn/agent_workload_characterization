# VIMAX-MUSICIANS-AUDIO-FULL-FLOW-R08-MEDIA-02 — 有声媒体完整正常流程成功，R08 标完整完成

## 结论

**唯一真实付费有声媒体 attempt（run_id `musicians-audio-full-flow-r08-media-02-20261102T070109Z-e37817d9`）在修复版生产链上完整正常流程成功：13 逻辑图片（9 肖像＋4 候选，候选数固定 2）→ 25 视频（13 主体＋12 过渡，audio=true/AAC）→ 38 正常下载 → 原生 AAC 拼接（仅主体 shots/0..12）→ 65.10s（video_stream，主判定 65±0.5 PASS）H.264/1280×720/30/1fps/AAC 成片（SHA `ce54ee583a85586e…`）；正式技术验收 applied+ok（12 项 checks 全 True、契约 digest `b15d5f66…` 与冻结一致）；COMPLETE v3 全维度有效、required_work 在 deadline 内；宿主 native_agent_done、容器退出 0、清理核验；supervisor runner_exited rc=0；远端 closeout 25/25 SUCCEEDED（usage.audio=true）；trace/资源/后处理计时齐全。** 结合 R08 规划（通过），**R08 标完整正常流程完成**；R08-MEDIA-01 MP3 技术失败观察原样保留。

## 修复链真实生效
- `pipeline_fix_mount`：pipeline `9a69b0ea…` 只读挂到 `/opt/vimax/src/pipelines/script2video_pipeline.py`，
  容器内 SHA==冻结、import 解析到挂载路径；concat 审计 `-acodec aac`（修复版生效，非 libmp3lame）。
- `media_technical.py`（`ca96d007…`）必需绑定；identity 携带 technical_contract（schema+digest）；
  门禁重算比对通过；技术验收共享 close_deadline（每步 remaining、min(timeout,remaining)）。

## 预算与对账
- image 13/13、image HTTP 发送 13（≤26）、video 任务 25/25、video 创建尝试 25（≤50）、video 轮询 136
  （≤2300）、正常下载 38（=13 图＋25 视频，恰等于 cap）、llm_calls 8；unclosed={}。
- 远端 25/25 SUCCEEDED（usage.audio=true）；closeout 复下载 25 独立记账。

## 成片与正式技术验收
- final 65.10s(video)/65.13s(audio/container)，H.264 1280×720 30/1fps，**AAC**（非 MP3），44100Hz/2ch，
  非静音（mean −17.1 dB），A/V start diff 0.0 / duration diff 0.03s；SHA `ce54ee583a85586e…`。
- technical_acceptance ok=True：media/video/resolution/fps/duration(video_stream 65±0.5)/
  audio_track=1/audio_codec_aac/non_silent/av_start/av_duration/decode 全 True；timing wall_s 0.93、
  remaining 4424s。

## 资源与计时
- 3113 样本 / wall 1557.8s / CPU 255.68 core-s；mem cur 502.3MB/kernel peak 2.09GB/sample max 2.09GB；
  I/O write 114,688B；netns 781 行；采样跨 120s 持续至结束。
- attempt_wall_s 1560.71（Agent 窗口）、total_wall_s 1576.92（含技术验收 0.93s）、
  technical_acceptance 阶段单独记录。

## 证据位置
- 媒体 raw：`data/raw/generated/VIMAX-MUSICIANS-AUDIO-FULL-FLOW-R08-MEDIA-02/musicians-audio-full-flow-r08-media-02/`
  （152 文件）；独立副本 `raw-persistent-copy/`（逐文件 bytes/SHA 一致，diff -rq 0）。
- 报告：`reports/analysis/VIMAX-MUSICIANS-AUDIO-FULL-FLOW-R08-MEDIA-02/`
  （control、配置/身份/批准、有效契约/digest、规划映射、部署/import 证据、COMPLETE/ENTRY-PHASES、
  run-record、成片 SHA、正式技术报告、trace/资源/netns、远端 closeout、manifest 绑定实际运行代码）。
- 状态：R08 标完整完成；R08-MEDIA-01 失败观察保留；R09 未启动；未增加组合/输入计数；
  check_project_state PASS、git diff --check 通过；未提交推送。
