# VIMAX-MUSICIANS-AUDIO-FULL-FLOW-R08-PLANNING-01 — 规划阶段完成（新规划通过，媒体待批准）

## 结论

**一次新授权真实 musicians 有声规划 attempt（run_id `musicians-audio-full-flow-r08-planning-01-20261102T025402Z-91e194be`）经规划阶段持久托管启动器执行完毕并通过生产 plan_verifier：13 镜头 / 3 角色 / 13 相机 / 12 过渡，0 媒体/音频请求，18 LLM 逻辑请求（54,941 tokens），attempt 102.36s，容器自然退出 0 与清理核验，测量质量 complete，supervisor runner_exited rc=0。** 规划产物（storyboard / shot descriptions / camera tree / characters）已冻结；为有声媒体阶段提供数量依据。**规划通过不等同成片完成；本记录是媒体阶段的前置，不增加完整生成任务覆盖数。** 新规划，未复用历史 musicians/G01/G02/G03 storyboard/camera_tree/shot_description。

## 输入与声音范围
- 故事 musicians_band_rehearsal_typeC（SHA `4d52835e…`，3 scenes / 13 shots）；registered script（SHA `657acb1e…`）。
- 13 镜头、5 秒/镜头、目标 65 秒（已登记执行适配，不冒称原故事规定总时长）、landscape 16:9。
- **有声路线**：native wan2.6-i2v-flash audio=true；保留环境声/room tone、吉他/键盘/cajón 演奏声、故事内笑声及自然动作声音；禁止新增无关对白/旁白/背景配乐；silent count 不被升级为整镜头绝对静音。本次仅规划，不生成音频。

## 托管与身份
- 沿用 R07 已真实验证的 planning 托管分支（未重建）；证明复用 R07 同一持久宿主执行域探针（`reports/analysis/VIMAX-G03-FULL-FLOW-R07-PLANNING-01/probe/host-confirmed-probe/verification.json`，启动器 SHA `ff875bc4…` 与执行域核对一致）。
- 新 context `MUSICIANS-AUDIO-full-flow-r08-planning-01-context.json`（SHA `bb154411…`）、唯一 run/session、身份 `32bba3be…`、APPROVAL-01.json（attempts_authorized=1）均按当前生产机制冻结；托管器/阶段适配/证明绑定进身份。
- 命令：`scripts/vimax_managed_launch.py launch --stage planning --config <ctx> --out <preflight-out> --approval <APPROVAL> --control <control> --persistence-proof <proof>`；`status --control <同一>`。

## plan_verifier 验收（真实生产）
- ok=True；storyboard 13、shot_description 13、camera 13、character 3、transition 12；16 项 checks：15 项布尔 True；`automatic_semantic_equivalence_to_all_13_supplied_actions` 明确标 not machine-proven（index/order 与 frozen script 已证）。

## 发送前核验
- 本地镜像 ID/平台核对一致；adapter divergence 恰好为已登记 MEDIA_FIX_RELS 三项；无新增差异。
- context→preflight→身份/批准→容器 env→plan_verifier 一致；story/script bytes/SHA 磁盘核对通过；13 镜头/5 秒经 load_context 派生验证。
- 媒体权限与预算为 0；预检 self-check 正确；credential_values_read=False、0 模型请求。

## 资源与请求
- 203 样本（目标 0.5s）；CPU 4.566 core-s（counter_boundary）；mem current end 122.3MB / kernel peak 125.1MB / sampled max 124.3MB；I/O read 0 / write 102,400B；netns eth0 rx≈133KB/tx≈256KB、lo 0、51 样本、0 读失败、覆盖 100s。
- 请求：18 逻辑（outer 2 + inner 16）；usage 覆盖 18/18、observed_total_tokens 54,941；unclosed_request_ids=[]；异常 0；http_exchange_count=unknown。
- 测量质量 complete（五指标 complete、ack host written + entry ok、stream 203/203、netns complete、scope released）。

## 有声媒体预算草案（只读，未授权）
见 `media-budget-draft.json/.md`。核心估算（media_budget_helper 真实生产分支）：
- 主体镜头 13、过渡 12、角色 3；候选首帧分支相机 2（camera_0/9），其余 11 相机父首帧派生；
- 图片创建估算 13（9 肖像 = 3 角色 × 3 视图 + 4 候选 = 2 相机 × 2）；
- 视频创建估算 25（13 主体 + 12 过渡）；下载 38（13 图 + 25 视频）、closeout 复下载 25；
- 图片 HTTP 上界 26、视频创建尝试上界 50、时间窗自然轮询上界 2300；显式 ledger video_polls cap 另列待确认；
- 候选数解析 env>config>default 2，后续建议显式固定 2。
- 有声契约：video_generation.audio=true、expected.audio=aac、原生拼接保留音轨、最终非静音检查沿用已验收规则；音轨存在/非静音 ≠ 乐器正确或动作同步；不对每镜头强制非静音。
- 不沿用旧 musicians"11图/25视频"或 G01/G02/G03 预算。
- 媒体阶段未启动、未创建媒体身份/批准，需另批批准。

## 保护与边界
- 未复用历史规划答案；未注入旧 musicians/G01/G02/G03 storyboard/camera_tree。
- 未改模型/预算/规划策略/规划工具/提示/验收/生成能力；未改历史运行；未提交推送；未启动 Replay。
- 覆盖计数不变；R01–R07 保持完成；R08 仅记"新规划通过，媒体待批准"；R09 不启动。

## 证据位置
- 规划 raw：`data/raw/generated/VIMAX-MUSICIANS-AUDIO-FULL-FLOW-R08-PLANNING-01/musicians-audio-full-flow-r08-planning-01/`
- 独立副本：`raw-persistent-copy/`（磁盘 51 文件；diff -rq 0；跨 cwd 回读）
- 启动控制目录：`control/`（launch.json/lifecycle.json/RELEASE.json/日志）
- 分析：`analysis/`（result.json、summary.md）；报告根（本 summary、final-report、identity、APPROVAL、handover、media-budget-draft、launch-record）
