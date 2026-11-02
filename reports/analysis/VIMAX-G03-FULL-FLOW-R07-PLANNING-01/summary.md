# VIMAX-G03-FULL-FLOW-R07-PLANNING-01 — 规划阶段完成（新规划通过，媒体待批准）

## 结论

**一次新授权真实 G03 规划 attempt（run_id `g03-full-flow-r07-planning-01-20261102T014721Z-1db09049`）经规划阶段持久托管启动器执行完毕并通过生产 plan_verifier：9 镜头 / 2 角色 / 9 相机 / 8 过渡，0 媒体请求，14 LLM 逻辑请求（40,666 tokens），attempt 87.42s，容器自然退出 0 与清理核验，测量质量 complete，supervisor runner_exited rc=0。** 规划产物（storyboard / shot descriptions / camera tree / characters）已冻结；为媒体阶段提供数量依据。**规划通过不等同成片完成；本记录是媒体阶段的前置，不增加完整生成任务覆盖数。** 新规划，未复用历史 G03/G01/G02/musicians storyboard/camera_tree/shot_description。

## 输入与范围
- 故事 athletes_gym_training_duo_typeC（SHA `b93891f85b…`，9 shots / 2 scenes）；registered script（SHA `c8cced9cbef5faf7…`）。
- 9 镜头、5 秒/镜头、目标 45 秒、landscape 16:9；G03 登记的 720p/30fps/无声执行 profile 保持；单首帧 i2v、variation_type=small；无末帧控制图。
- 无声（no_audio），不继承 musicians 有声策略；不声称无声适配等于完整满足原故事所有可能声音语义。

## 规划托管支持
- `scripts/vimax_managed_launch.py` 新增显式 `planning` 阶段（默认仍 `media`，原门禁与防覆盖不退化）：`--stage planning --approval`；planning 门禁用真实规划 `load_context` + `validate_approval` + preflight 归属/attempt 保护；同一 OUT 首次 run 放行、已有 attempt 拒绝；media 仍要求全新 OUT。
- 托管器/阶段适配/持久性证明进入本次冻结身份 `files` 绑定；旧 media 批准因启动器字节变更被拒（保持零发送语义）。
- 修改启动器后旧证明保留，在同一持久宿主执行域用最终启动器重新做 130.00s 离线真实采样探针（2595 样本、start/end 边界、rc=0），`verification.json` 绑定最终 SHA 与实际 boot/PID ns/cgroup/UID。

## 运行
- run_id `g03-full-flow-r07-planning-01-20261102T014721Z-1db09049`；镜像 `sha256:a97ea6076fbcd456ada0d0e1267ebf50058daa52698e0996cffaf66da1f176f3`；身份文件 SHA `2fb476e6…`；supervisor PID 2108006 / runner PID 2108020。
- 命令：`scripts/vimax_managed_launch.py launch --stage planning --config <ctx> --out <preflight-out> --control <control> --approval <APPROVAL> --persistence-proof <verification.json>`；`status --control <同一>`。
- 预算消费：logical_request_cap 30（实际 14）、observed 40,666 < 250,000 软阈值、0 图/视频、SDK retries 0。

## plan_verifier 验收（真实生产）
- ok=True；storyboard 9、shot_description 9、camera 9、character 2、transition 8；16 项 checks：15 项布尔 True；`automatic_semantic_equivalence_to_all_9_supplied_actions` 明确标 not machine-proven（index/order 与 frozen script 已证）。

## 发送前核验
- 本地镜像 ID/平台核对一致；adapter-src 与镜像 divergence 恰好为已允许的 MEDIA_FIX_RELS 三项；无新增差异、未扩大允许集。
- context→preflight→身份/批准→容器 env→plan_verifier 一致；story/script bytes/SHA 磁盘核对通过；9 镜头/5 秒经 load_context 派生验证。
- 媒体权限与预算为 0；预检 self-check 返回正确 capability/budget caps、credential_values_read=False、0 模型请求。

## 资源与请求
- 172 样本（目标 0.5s）；CPU 4.444 core-s（counter_boundary）；mem current end 121.3MB / kernel peak 123.1MB / sampled max 122.1MB；I/O read 0 / write 98,304B；netns eth0 rx≈101KB/tx≈189KB、lo 0、44 样本、0 读失败；覆盖 85.99s；rows_lost 0。
- 请求：14 逻辑（outer agent 2 + inner planning 12）；usage 覆盖 14/14、observed_total_tokens 40,666；unclosed_request_ids=[]；http_exchange_count=unknown（如实标记）。
- 测量质量 complete（五指标 complete、ack host written + entry ok、stream 172/172、netns complete、scope released）。

## 媒体预算草案（只读，未授权）
见 `media-budget-draft.json/.md`。核心估算（media_budget_helper 真实生产分支）：
- 主体镜头 9、过渡 8、角色 2；候选首帧分支相机 1（camera_0），其余 8 相机父首帧派生；
- 图片创建估算 8（6 肖像 = 2 角色 × 3 视图 + 2 候选 = 1 相机 × 2）；
- 视频创建估算 17（9 主体 + 8 过渡）；下载 25（8 图 + 17 视频）、closeout 复下载 17；
- 图片 HTTP 上界 16、视频创建尝试上界 34、时间窗自然轮询上界 1564；显式 ledger video_polls cap 另列待确认；
- work/closeout 采用 5400/600 口径（media entry 默认 closeout=300 冲突列待确认）；
- 候选数解析 env>config>default 2，后续建议显式固定 2。
- 不沿用旧 G01"19图/15视频/34下载/1380轮询"，也不照搬旧 G02"12/19/31/1748"。
- 媒体阶段未启动、未创建媒体身份/批准，需另批批准。

## 保护与边界
- 未复用历史规划答案；未注入旧 G03/G01/G02/musicians storyboard/camera_tree。
- 未改模型/预算/规划策略/规划工具/提示/验收/生成能力；未改历史运行；未提交推送；未启动 Replay。
- 覆盖计数不变；R05 保持完成、R06 保持完成（MEDIA-01 失败观察保留）；R07 仅记"规划通过、媒体待批准"；R08/R09 不启动。

## 证据位置
- 规划 raw：`data/raw/generated/VIMAX-G03-FULL-FLOW-R07-PLANNING-01/g03-full-flow-r07-planning-01/`
- 独立副本：`raw-persistent-copy/`（磁盘 47 文件，与源逐文件 bytes/SHA 一致；diff -rq 0 差异；跨 cwd 回读）
- 启动控制目录：`control/`（launch.json/lifecycle.json/RELEASE.json/日志）
- 探针：`probe/host-confirmed-probe/verification.json`
- 报告 manifest：`manifest.json`（报告物理 86 文件；列出数据文件 83、manifest 控制文件 1、offline-verification 控制文件 1、raw 副本自身 manifest 1）
- 分析：`analysis/`（result.json、summary.md）；报告根（本 summary、final-report、identity、APPROVAL、handover、media-budget-draft、launch-record）
