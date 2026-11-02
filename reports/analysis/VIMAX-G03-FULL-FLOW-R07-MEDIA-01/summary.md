# VIMAX-G03-FULL-FLOW-R07-MEDIA-01 — 媒体阶段完整正常流程成功，R07 标完整完成

## 结论

**一次真实付费媒体 attempt（run_id `g03-full-flow-r07-media-01-20261102T021018Z-bc2d3e00`）经托管启动器（stage=media）完整正常流程成功：8 逻辑图片（6 肖像＋2 候选）→ 17 视频（9 主体＋8 过渡）→ 25 正常下载 → 原生 concat → 45.000s H.264/1280×720/30/1fps/无音轨成片（SHA `d4150200f5dc1b7b…`）；COMPLETE v3 全维度有效、final_path_resolution owned/exists/accepted 全 true、required_work 在 deadline 内；宿主 termination=native_agent_done、容器退出 0、清理核验、cleanup_errors=[]；supervisor runner_exited rc=0；远端 closeout 17/17 SUCCEEDED audio=false 复下载独立记账；测量/资源边界齐全。** 结合 R07 规划（VIMAX-G03-FULL-FLOW-R07-PLANNING-01 通过），**R07 标完整正常流程完成**。

## 规划映射（零重新规划）
- 复用唯一允许的规划 VIMAX-G03-FULL-FLOW-R07-PLANNING-01（run `g03-full-flow-r07-planning-01-20261102T014721Z-1db09049`、session `g03-full-flow-r07-planning-01`、身份 `2fb476e6…`）。
- 媒体 session `g03-full-flow-r07-media-01` 由规划 session seed（session-source-map.json：13 个语义文件 SHA 一致，script `c8cced9c…`；new_session=true）。
- 未调用 vimax_narrative_planning；未复用历史 G03/G01/G02/musicians 媒体、任务ID、ledger、缓存。

## 预算与对账（批准 8/16/34/1564/25，实际）
- image_generations 8（6 肖像＋2 候选，候选数显式固定 2）；image_create_sends 实际 8（≤16）；video_creates 实际 17 任务（≤34 尝试 cap）；video_polls 137（≤1564 ledger cap）；media_downloads 25/25（8 图＋17 视频）；llm_calls 5（≤80）；observed_output_tokens_total 914（<500,000 软阈值）；unclosed_requests={}。
- 远端 17/17 SUCCEEDED（audio=false、SR 720、duration 5）；closeout 复下载 17 独立记账。

## 成片与验收
- final 45.000s / H.264 / 1280×720 / 30/1fps / 无音轨 / 11,300,557 bytes / 完整解码 / SHA `d4150200f5dc1b7b…`。
- 原生 concat 只消费主体 shots/0..8（各 5.000s）；8 个辅助过渡不入 final（final 45s ≠ 85s 远端量）。
- COMPLETE v3：schema_valid/session/run/ownership/render/final_path owned+exists+accepted/format/timing 全 true；required_work 在 deadline 内。
- 资源：3055 样本 / wall 1528.67s / CPU 190.80 core-s（counter_boundary）；mem current end 427.2MB / kernel peak 1552.3MB / sampled max 1551.8MB；I/O read 0 / write 90,112B；netns 767 行（eth0 rx≈78.8MB/tx≈8.9MB）；真实开始/结束边界完整；采样跨 120s 持续增长至结束。

## 保护与边界
- 未改生产代码/模型/预算/验收阈值；媒体启动/查询均经托管启动器（stage=media）＋同执行域证明（启动器 SHA `ff875bc4…`，proof `9b897b1e…`）。
- 未复用旧批准/旧证明；未追加第二次 attempt；未独立恢复或宿主补拼接。
- 历史 G03、R05/R06 及规划证据原字节保留；R08/R09 未启动；未增加组合/输入计数。
- 状态用规定更新器，不改 execution_authorization；check_project_state 与 git diff --check 通过。

## 证据位置
- 媒体 raw：`data/raw/generated/VIMAX-G03-FULL-FLOW-R07-MEDIA-01/g03-full-flow-r07-media-01/`（119 文件）
- 独立副本：`raw-persistent-copy/`（逐文件 bytes/SHA 一致；diff -rq 0）
- 启动控制目录：`control/`；配置/身份/批准/规划映射见本目录副本
- 分析：`analysis/`（result.json、summary.md）；报告根（本 summary、final-report、handover、launch-record、manifest）
