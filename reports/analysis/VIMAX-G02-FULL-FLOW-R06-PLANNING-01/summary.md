# VIMAX-G02-FULL-FLOW-R06-PLANNING-01 — 规划阶段完成（新规划通过，媒体待批准）

## 结论

**一次新授权真实 G02 规划 attempt（run_id `g02-full-flow-r06-planning-01-20261101T152744Z-cd860dee`）执行完毕并通过生产 plan_verifier：10 镜头 / 2 角色 / 10 相机 / 9 过渡边，0 媒体请求，15 LLM 逻辑请求（43,675 tokens），attempt 95.92s，容器自然退出与清理核验，测量质量 complete。** 规划产物（storyboard / shot descriptions / camera tree / characters）已冻结；为媒体阶段提供数量依据。**规划通过不等同成片完成；本记录是媒体阶段的前置，不增加完整生成任务覆盖数。** 新规划，未复用历史 G02/G01/G03/musicians storyboard/camera_tree/shot_description。

## 输入与范围
- 故事 pottery_workshop_studio_space_typeB（SHA `77096d93…`，metadata requested_shots=10，2 scenes × 5 shots）；registered script（SHA `481d1b97…`）。
- 10 镜头、5 秒/镜头、目标 50 秒、landscape 16:9；G02 登记的 720p/30fps/无声执行 profile 保持；单首帧 i2v、variation_type=small；无末帧控制图。
- 无声（no_audio），不继承 musicians 有声策略；不声称无声适配等于完整满足原故事所有可能声音语义。

## 运行
- run_id `g02-full-flow-r06-planning-01-20261101T152744Z-cd860dee`；镜像 `sha256:a97ea6076fbcd456ada0d0e1267ebf50058daa52698e0996cffaf66da1f176f3`；身份文件 SHA `93661346…`。
- 命令：`host_runner.py preflight --out <OUT> --config <formal-context>`；`host_runner.py run --out <同一OUT> --approval <APPROVAL-01> --config <同一context>`（nohup 后台，run-record 已持久化）。
- 预算消费：logical_request_cap 30（实际 15）、observed 43,675 < 250,000 软阈值、0 图/视频、SDK retries 0。

## plan_verifier 验收（真实生产）
- ok=True；storyboard 10、shot_description 10、camera 10、character 2、transition 9；16 项 checks 全 True：
  fresh single session、session_mode script、registered script 匹配、expected_shot_count 契约、
  native schema、camera tree 引用合法无环、capability、角色引用、native planning 成功、
  无源复制、请求记录、媒体缺席。
- 语义等价明确标 not machine-proven（index/order 与 frozen script 已证）。

## 发送前核验（本轮无生产代码修改）
- adapter-src 与镜像 divergence 恰好为已允许的 MEDIA_FIX_RELS 三项（video/image bailian api、script2video pipeline）；无新增差异，未扩大允许集。
- 定向测试：test_vimax_planning_final_boundary.py 40 passed、test_vimax_media_budget_helper.py 40 passed。
- load_context 离线验证消费 G02：story SHA、registered_script 重构 SHA=481d1b97…、expected_shots=10 与 story 派生一致、shot_ids 1-10、seconds_per_shot=5。
- 预检 self-check（容器内）返回正确 capability/budget caps，credential_values_read=False、0 模型请求。

## 资源与请求
- 190 样本（目标 0.5s）；CPU 4.31 core-s（counter_boundary）；mem current end 121.8MB / kernel peak 127.7MB / sampled max 127.4MB；I/O read 0 / write 98,304B；netns eth0 rx≈107KB/tx≈205KB、lo 0、48 样本、0 读失败；覆盖 94.75s；rows_lost 0。
- 请求：15 逻辑（outer agent 2 + inner planning 13）；usage 覆盖 15/15、sum_total_tokens 43,675（<250K 软阈值）；unclosed_request_ids=[]；http_exchange_count=unknown（如实标记）。
- 测量质量 complete（五指标 complete、ack host written + entry ok、stream 190/190、netns complete、scope released）。

## 媒体预算草案（只读，未授权）
见 `media-budget-draft.json/.md`。核心估算（media_budget_helper 真实生产分支）：
- 主体镜头 10、过渡 9、角色 2；候选首帧分支相机 3（camera_0/2/3），其余 7 相机父首帧派生；
- 图片创建估算 12（6 肖像 = 2 角色 × 3 视图 + 6 候选 = 3 相机 × 2）；
- 视频创建估算 19（10 主体 + 9 过渡）；下载 31（12 图 + 19 视频）、closeout 复下载 19；
- 图片 HTTP 上界 24、视频创建尝试上界 38、时间窗自然轮询上界 1748；显式 ledger video_polls cap 另列待确认；
- work/closeout 采用 5400/600 口径（media entry 默认 closeout=300 冲突列待确认）；
- 不沿用旧 G01"19图/15视频/34下载/1380轮询"，也不照搬旧 G02 配置"23图"等数字。
- 媒体阶段未启动、未创建媒体身份/批准，需另批批准。

## 保护与边界
- 未复用历史规划答案；未注入旧 G02/G01/G03/musicians storyboard/camera_tree。
- 未改模型/预算/规划策略/生产代码；未改历史运行；未提交推送；未启动 Replay。
- 覆盖计数不变；R05 保持完成、MEDIA-01 失败记录保持；R06 仅记"规划通过、媒体待批准"；R07–R09 不启动。

## 证据位置
- 规划 raw：`data/raw/generated/VIMAX-G02-FULL-FLOW-R06-PLANNING-01/g02-full-flow-r06-planning-01/`
- 独立副本：`raw-persistent-copy/`（磁盘 48 文件 / manifest 47 项；diff -rq 0 差异；跨 cwd 回读 0 错）
- 分析：`analysis/`（result.json、summary.md、manifest）；报告根（本 summary、final-report、identity、APPROVAL、handover、media-budget-draft、launch-record）
