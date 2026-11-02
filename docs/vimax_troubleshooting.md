# ViMax 排障与快速复现

更新：2026-10-29。结果见 [视频索引](video_results.md)，任务见 [扩展计划](video_task_expansion_plan.md)。G01/G02已有真实成片，不需要再跑旧失败轮次。

## 固定成功路径

- 原生Agent `main_agent.py` JSONL，规划和媒体分阶段记录。
- 媒体宿主入口：`env/video/vimax/VIMAX-MEDIA-ENTRY-REPAIR-01/host_runner.py run --out <新目录> --config <新配置>`。
- 规划宿主入口（当前维护）：`env/video/vimax/planning/host_runner.py preflight|run --out <唯一新目录> --approval <APPROVAL> --config <planning-context>`。
- v7镜像 `vimax-task-bailian:arm64-v7-capability-planning-01`，完整ID `sha256:a97ea6076fbcd456ada0d0e1267ebf50058daa52698e0996cffaf66da1f176f3`。
- 当前video adapter修复按正式配置只读挂载；发送前核容器import路径和SHA，不能只核镜像标签。
- 模型qwen3.7-plus/qwen-image-3.0/wan2.6-i2v-flash。单首帧、720P30、无音轨、variation small。

## 问题与修法

| 问题 | 修法与约束 |
| --- | --- |
| script被保存成idea，后续错规划源 | script session保持字节与来源，源SHA门禁，不让工具调用替换冻结文本 |
| JSON截断被宽松解析吞掉，thinking耗尽输出 | 严格JSON；仅允许限定恢复；enable_thinking=false、明确输出上限；记录finish/usage/request关联 |
| LangChain callback吞预算异常、关联拿最近请求 | inline/raise_error按锁版本验证；发送前原子预留与持久化；响应携带对应request ID，不猜配 |
| 规划medium/large触发双帧但adapter只支持首帧 | 能力约束进入各规划节点；实际render preflight；不事后改计划/删镜头绕过 |
| seed_session先读空目录、runner参数错误、日志丢失 | 复用REPAIR-01真实生命周期路径；空工作区初始化；stdout/stderr实时保存，删除前补取 |
| MoviePy线程膨胀导致reader失败 | 本机cpuset 0-7对齐CPU配额；pids约束与已有配置一起核对，不视为通用主机值 |
| 429/部分受理被误写全失败 | create并发1、远端在途1、最小间隔1s；仅明确未受理429有限重试，每次记账；unknown不重建 |
| 已取得task_id后兄弟失败丢清单 | remote_closeout在有界收尾内查原任务并下载成功产物，未终态保持pending/unknown |
| 镜头数/过渡数默认8/7 | 新任务由真实规划和camera tree核定expected；0过渡合法；缺失不静默回退G01 |
| 图片14次请求却有33PNG，被误称批量 | n=1；肖像、候选、复制/抽帧首帧分开；文件数不是HTTP请求数；未保存逐文件关联则PARTIAL |
| 验收写死ACTUAL=14/8 | 预期来自冻结契约/规划，观测来自账本，不把observed写成expected；保留独立修订 |
| 每段5s被当作已证明拼接顺序 | 需要拼接输入/绑定代码/事件等来源；总时长不能单独证明顺序，不要求重编码视频字节相等 |

## 结果和统计边界

G01：8主体＋7辅助过渡、40s；当前代表媒体阶段复用已通过规划，另保留早期完整成功PILOT-04及规划依赖。
G02：10主体＋9过渡、50s；核心契约/预算通过，图片来源PARTIAL，媒体账本total缺失。最新验收从 [G02修订](../reports/analysis/VIMAX-G02-EXPANSION-01/revision-ACCEPTANCE-01/summary.md) 进入。

轮询按操作关联统计，119 open＋119 close是119次操作，不是238次HTTP；独立收尾查询单列。
图片创建、下载、复制/抽帧分开；远端任务受理/完成/下载分开。
无真实429的成功run不证明重试分支已实测；实际账单和未采到字段保持unknown。

下一任务G03需新规划、新expected、预算、身份和批准；不把本页当执行授权。已删除无用失败/诊断输出，代码/配方/必要fixture和有效结果保留，见 [清理说明](video_results.md#2026-10-29-直接清理)。

## 2026-10-29：G03 规划离线复验＋媒体阶段（VIMAX-G03-PLAN-RECOVERY-AND-MEDIA-01）

- **规划复验（零真实 API）**：原 G03 规划门 FAIL 因登记 verifier 仍要求 10 镜头（indices 0..9）；本轮将验收器
  参数化（expected_shots 从显式契约/冻结剧本派生，不硬编码 9），对**已有规划**离线重新验收
  （image 内 network=none 只读）：ok=True（storyboard 9、descriptions 9、camera 9、8 过渡、2 角色、
  is_last 正确、无环、首帧 i2v small）。11 项定向测试通过（8/9/10 各自正例；9 镜头按 10/8 契约拒绝；
  缺镜头/相机环/错角色引用拒绝）。不重新规划、不改原 FAIL/身份/批准。
- **媒体阶段（复用规划）**：run_id `20261029T081529Z-vimax-g03-expansion-media-01`；镜像
  `sha256:a97ea607…`；17 个远端视频任务全部受理并 closeout 观测 SUCCEEDED（9 主体＋8 过渡）；
  原生 `vimax_render_video` concat（shot_count 9）→ final_video.mp4=45s/1280×720/30fps/H264/无音轨/
  1350 帧/完整解码；9 主体 clip 各 5.0s、8 辅助过渡。14 图片＋17 视频下载。CPU 186 core-s、mem 峰 2.19GB。
- 工具回放：`ffmpeg-processes.jsonl`（15 子进程）＋render concat 事件＋model-events 完整 create/poll/
  download；远程 17 任务终态 SUCCEEDED。媒体 total-token usage partial_output_only。容器删除回验。
