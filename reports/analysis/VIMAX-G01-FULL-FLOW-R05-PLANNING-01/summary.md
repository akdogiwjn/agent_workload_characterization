# VIMAX-G01-FULL-FLOW-R05-PLANNING-01 — 规划阶段完成（新规划通过，媒体待预算批准）

## 结论

**一次新授权真实 G01 规划 attempt（run_id `g01-full-flow-r05-planning-01-20261101T070459Z-3f4e2dab`）执行完毕并通过生产 plan_verifier：8 镜头 / 1 角色 / 8 相机 / 7 过渡边，0 媒体请求，13 LLM 逻辑请求（37,873 tokens），attempt 77.99s，容器自然退出与清理核验。** 规划产物（storyboard / shot descriptions / camera tree / characters）已冻结；为媒体阶段提供数量依据。**规划通过不等同成片完成；本记录是媒体阶段的前置，不增加完整生成任务覆盖数。** 新规划，未复用历史 G01/G02/G03/musicians storyboard/camera_tree。

## 输入与范围
- 故事 photographer_urban_timelapses_typeA（SHA `aaf6545c…`，metadata requested_shots=8，2 scenes × 4 shots）；registered script（SHA `447e4d88…`）。
- 8 镜头、5 秒/镜头、目标 40 秒、landscape 16:9；720p/30fps/无音轨范围保持；单首帧 i2v、variation_type=small；无末帧控制图。
- 无音轨（no_audio），不继承 musicians 有声策略。

## 运行
- run_id `g01-full-flow-r05-planning-01-20261101T070459Z-3f4e2dab`；镜像 `sha256:a97ea6076fbcd456ada0d0e1267ebf50058daa52698e0996cffaf66da1f176f3`；身份 SHA `9085c610…`。
- 命令：`host_runner.py preflight --out <OUT> --config <formal-context>`；`host_runner.py run --out <OUT> --approval <APPROVAL-01> --config <formal-context>`（nohup 后台，run-record 已持久化）。
- 预算消费：logical_request_cap 30（实际 13）、observed 37,873 < 250,000 软阈值、0 图/视频、SDK retries 0。

## plan_verifier 验收（真实生产）
- ok=True；storyboard 8、shot_description 8、camera 8、character 1、transition 7；14 项 checks 全 True：
  fresh single session、session_mode script、registered script 匹配、expected_shot_count 契约、
  native schema、camera tree 引用合法无环、capability、角色引用、native planning 成功、
  无源复制、请求记录、媒体缺席。
- 语义等价明确标 not machine-proven（index/order 与 frozen script 已证）。

## 发送前确定性修复（留快照）
- preflight 首次因 adapter-src 与镜像 divergence（`script2video_pipeline.py`、`image_generator_bailian_api.py`）失败——
  这两个是已验收的宿主生产 adapter 修复（musicians concat、image throttling/policy），媒体阶段用宿主版。
  将 MEDIA_FIX_RELS 允许集从单文件扩展为三个已修复文件。pre-change 快照：
  `pre-change/host_runner.py.pre`（旧 sha `0b54899e…` → 新 `d7a4b17a…`）。

## 资源与请求
- 155 样本（目标 0.5s）；mem 采样峰 122 MB；CPU null（counter_boundary，end 缺失如实记录）；
  netns eth0 rx≈92KB/tx≈181KB、lo 0；覆盖 75.97s；rows_lost 0。
- 请求：13 逻辑（outer agent 2 + inner planning 11）；usage 覆盖 13、sum_total_tokens 37,873；
  http_exchange_count=unknown（如实标记）。

## 媒体预算草案（只读，未授权）
见 `media-budget-draft.json/.md`。核心估算：
- 主体镜头 8、过渡 7、角色 1；
- 图片创建估算 5（3 肖像 = 1 角色 × 3 视图 + 2 候选 = 1 candidate_shot × 2）；
- 视频创建估算 15（8 主体 + 7 过渡）；
- 下载估算 20（5 图 + 15 视频）；轮询上界 900；
- work/closeout 采用 5400/600（当前正式媒体配置口径；media entry 默认 closeout=300 冲突列待确认）；
- 不沿用旧 G01"19图/15视频"、musicians"11图/25视频"；8 镜头 ≠ 8 次视频创建。
- 媒体阶段未启动、未创建媒体身份/批准，需另批批准。

## 保护与边界
- 未复用历史规划答案；未注入旧 G01/G02/G03/musicians storyboard/camera_tree。
- 未改模型/预算/规划策略；未改历史运行；未提交推送；未启动 Replay。
- 覆盖计数不变；R01–R04 保持完成；R05 仅规划阶段完成，媒体待批准。

## 证据位置
- 规划 raw：`data/raw/generated/VIMAX-G01-FULL-FLOW-R05-PLANNING-01/g01-full-flow-r05-planning-01/`
- 独立副本：`raw-persistent-copy/`（磁盘 44 文件 / manifest 43 项；diff 0；跨 cwd 回读 0 错）
- 分析：`analysis/`（result.json、summary.md、manifest）；报告根（本 summary、final-report、identity、APPROVAL、handover、media-budget-draft）
