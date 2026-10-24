# VIMAX-NETWORK-VALIDATION-02：审计修复集中记录与禁网验收

日期：2026-10-23。范围：修复 VIMAX-NETWORK-VALIDATION-01 审计问题 + 一次完整禁网验收。不读取真实密钥、不调用真实模型 API、不执行正式八镜头任务。参考仓库原件未改；旧镜像（`vimax-task-bailian:arm64-v1`）、旧验证目录（VIMAX-NETWORK-VALIDATION-01）与全部历史结果保留。

## 新镜像

| 项 | 值 |
| --- | --- |
| 新标签 | `vimax-task-bailian:arm64-v2` = `sha256:0f59cedefcc0cd96ec80c9458a7016ab84679c32c0c76c7f1c89ff782c68a902`，linux/arm64 |
| 派生方式 | `Dockerfile.v2` 从 v1（`sha256:045fe9cd…7be6`）只 COPY 变更代码层 + 导入自检；**无依赖重装、无基础镜像拉取** |
| 旧标签 | v1 保留不动 |

## 一、逐项审计修复

### 1. 资源采集与完整证据
- cgroup 采样目标 0.5 s（实测 93 点、平均间隔 ~0.500 s，`resource_sample_gaps_ns` 全量保存，无填零/插值；只有真实相邻计数参与差分）；
- netns 周期显式 2.0 s 并登记原因与实测开销（`docker exec` 实测均值 **0.082 s**/次，0.5 s 周期会污染被测容器；cgroup 与 netns 周期分列，均非 Agent 工作窗口）；
- **完成握手**：容器内验证写 `COMPLETE` 后 `signal.pause()` 保持存活（SIGTERM→优雅退出 rc0）；宿主在容器存活时先取**最终资源边界**再 stop/rm——CPU 边界不再缺失（本轮 `cpu_core_seconds=63.76 s / wall 46.40 s / avg 1.37 cores`，边界 read_status 全 ok）；
- 完整证据：逐点样本（`resource-samples.jsonl`，每点含 counters+per-file read_status+monotonic 时间）、起止边界、内核内存峰值（`memory.max_usage_in_bytes` 本轮可读：2.17 GB；采样下界 1.88 GB 分列）、I/O（`blkio.throttle.io_service_bytes_recursive` 可读：写 233,472 B、读 0 且有 `ok_no_records_real_zero` 依据；非 throttle 接口 not_found 已记录——本宿主 cgroup v1 的 blkio 计量即此形态，**写入证据在样本文件 read_status 中，非假设**）；
- 结论：CPU/内存/I/O 本轮均有效采到；正式测量要求（0.5 s 目标 + 完整边界 + 逐点证据）满足；唯一限制是 cgroup v1 blkio 只有 throttle 接口可用（已如实登记）。

### 2. 异常清理与最终成功判定
- 采样器/netns 线程/容器分别在独立 try 中回收；netns 线程显式 `set()+join(15s)`；清理错误全保留于 `problems`/`cleanup_errors` 并映射非零退出；
- **严格报告判定**（`evaluate_report` 纯函数）：报告缺失/JSON 损坏/非对象/无 checks/**任一必要检查缺失或失败**/failures 非空 → 整体失败；`REQUIRED_CHECKS` 42 项与驱动侧检查名静态同步（宿主回归防漂移）；容器 rc0、COMPLETE 握手、镜像完整 ID 比对均为必要条件；
- 容器**唯一名称**（`vimax-netval-<uuid8>`），删除只针对本次创建并**核验归属**（inspect name 匹配）的完整 container ID，删除后只读核验不存在，镜像保留；
- 所有 docker 命令带超时（默认 30 s，受共同 deadline 剩余时间约束）；
- **注入反例**（宿主离线回归 `runner/test_runner_offline.py`，10/10）：报告缺失、损坏、非对象、无 checks、必要项缺失、必要项失败、failures 非空、预检反例为关键项、有效报告唯一通过路径、检查名单同步。Docker 命令超时路径经 `sh()` 的 TimeoutExpired 包装为 rc124（未在本次验收中触发，接线存在）。

### 3. 请求账本、重试与预算
- **新共享账本** `agent_runtime/request_ledger.py`：open 事件**发送前落盘**，close/error 闭合（传输超时等结果不明的标 `right_censored`），闭合事件携带 op；写入失败计数+写入 sidecar（`*.writefailures`），`flush_state` 输出未闭合请求与计数——账本失败不静默；
- **外层 Agent**（`llm.py`）：OpenAI SDK **显式 `max_retries=0`**（此前为 SDK 默认 2——审计纠正项"默认假设 SDK 零重试"不成立，现已显式化）；项目级 3 次重试**每次尝试**都 open/close 入账并过门禁；形状补发（tools→无 tools）每次都是新逻辑请求，计数不绕过；usage（含 completion_tokens）入账；
- **内部 LangChain**：`_build_chat_model` 注入继承 `BaseCallbackHandler` 的账本回调（on_chat_model_start/end/error），逐次记录角色（inner_langchain）、阶段提示、usage；LangChain `max_retries=0` 已有；各 agent 的 tenacity 重试每次实际再调用都经回调计数；单请求输出 token 上限过 `guard_output_tokens`（observed 累计仅软阈值，不宣称硬上限）；
- 图片创建、视频创建、轮询、下载分别过 `guard`（`image_generations/video_creates/video_polls/media_downloads` + 共同 deadline）；
- 工具调用 ID / 逻辑请求 / HTTP 交换 / 远端 job 分列（request_id、op、task_id、provider_request_id 各自独立字段）；HTTP 实际交换次数无传输层证据时保持 unknown；
- **纠正错误说明**：撤销"同步图片生成重试不会重复计费"（V1 版注释）——生成请求超时/5xx 时服务端结果不明，**默认不自动补发**；仅明确 429（未受理）可重试且不重置单调用 deadline；视频创建保持零重试；下载为幂等免费操作，有界重试与付费生成策略分开；
- **门禁反例**（容器内实测）：`VIMAX_BAILIAN_BUDGET_IMAGE_GENERATIONS=2` 时第 3 次图片生成在发送前被 `BudgetExceeded` 拒绝（计数=2），账本留痕。

### 4. 付费生成前能力预检
- `preflight_render_capability` 在 `vimax_render_video` 的 script 分支**构造任何生成器之前**执行：shot 数/ID/顺序（idx 0..N-1 连续）、每 shot `variation_type` 对照首尾帧支持（默认不支持）、camera tree 合法性（无效引用/自父/环检测）、transition 额外视频调用对照 `VIMAX_BAILIAN_BUDGET_TRANSITIONS` 上限、缺失产物检查；
- 不兼容 → ToolResult False + 具体 shot 与原因 + `capability_preflight_failed` 状态，**图片与视频发送数为 0**；
- 不改写 medium→small、不丢尾帧、不换模型；保留原生 Agent 规划行为；
- **反例实测**：fake 注入 `plan_variation_medium` 规划出 medium shot 后，render 被预检拒绝，image/video 计数**零增量**（`preflight_medium_variation_rejected_with_zero_sends` PASS）；
- **修订旧结论**：V1 的"在 user_requirement 中要求 small 即可正式运行"**不成立**（decompose 节点不接收 user_requirement，LLM 规划不受其约束）——正式运行的保障是本预检（拒绝+人工修订规划），非提示词约定。

### 5. 下载跳转与时间上限
- 两个生成器的媒体下载器重写：**跳转独立计数，第 2 次跳转明确失败**（V1 的 `continue` 无上限 bug 已修）；相对 `Location` 经 `urljoin` 解析；仅允许 http/https（防降级/异协议）；授权头永不到媒体域；重试不重置单调用 deadline；大小上限保留（图片 20 MB/视频 200 MB）；
- **离线反例全过**：0 跳转（隐含基线）、1 跳转成功、2 跳转失败、循环（经 2 跳上限拦截）、相对地址成功、超大（21 MB）拒绝、媒体 401/404 拒绝（无真实网络，全部经 fake 注入）。

### 6. 严格验收与镜像身份
- `agent_narrative_planning_ok`/`agent_render_ok`：工具结果必须**显式 ok=true** 且在对应 turn 之后（等待每 turn 的 done 事件而非任意 tool_result）；
- `agent_process_rc0`：进程 returncode 必须为 0；错误退出/工具失败不再因产物存在而过关；
- 媒体断言显式化：h264、1280×720、**30fps**、~40 s、无音轨、完整解码；
- **8 段与 shot 严格映射**：shot i 的 `video.mp4` SHA-256 对照 fake 媒体库得到 shot→clip 映射，final_video 每段（5 s 中点抽帧识别编号）必须**按序等于**该映射（本轮 `segments=[1,3,0,2,6,5,7,4]` 与 `shot_clip` 逐位相等）——集合恰好含 0–7 不再足够；
- 镜像预检：完整 ID/OS/架构与 `--expect-image-id` 硬比对，不匹配拒绝启动（本轮实测以旧 ID 启动新标签会被拒）；
- 新 manifest（见下）登记实际代码/Dockerfile/requirements/配置的 bytes+SHA-256。

## 二、禁网验收结果（新 session，`--network none`，fake 仅在 127.0.0.1）

**42/42 必要检查全过，runner ok=true（problems=[]），总 wall 47.0 s；验证链 wall 40.7 s；容器 rc=0（SIGTERM 优雅退出）；清理核验通过、镜像保留。**

关键证据位置：
- 验收报告：`workspace/validation/validation-report.json`（42 检查 + 反例明细）
- 原生事件：`workspace/validation/agent-events.jsonl`；预检反例：`preflight-negative-events.jsonl`
- 请求账本：`workspace/validation/bailian-events.jsonl`（LLM 尝试/生成/轮询/下载全量 open/close/error）+ `.state`（未闭合=空、写入失败=0）
- **资源逐点样本：`resource-samples.jsonl`（93 点）；边界/摘要/gap 在 `run-record.json`**；netns 23 点（exec 开销实测 0.082 s）
- 最终视频：`workspace/validation/agent-session/.working_dir/*/script2video/final_video.mp4`（40.0 s、8 段严格映射）

## 三、状态分列（非整体 READY）

| 维度 | 状态 | 依据 |
| --- | --- | --- |
| 正常执行路径 | **READY** | 全新 session 冷启动→规划→渲染→拼接→导出全链 PASS（严格断言） |
| 资源完整性 | **READY（含登记限制）** | CPU/内存/IO 边界+逐点+gap 完整；限制：cgroup v1 仅 throttle blkio 接口、netns 2.0 s 周期（开销实测登记） |
| 任务媒体有效性 | **READY（禁网口径）** | 8 段严格映射、40.0s、720p/30fps/无音轨、完整解码；真实模型输出质量未测 |
| 异常收尾 | **READY** | 严格判定+注入反例 10/10（宿主）+容器内反例（预检/门禁/下载） |
| 归档完整性 | **READY** | 逐点样本+账本+边界+manifest（内容哈希）；旧目录/镜像未动 |

**能否进入正式执行审批**：可以。能力边界（首尾帧拒绝、transition 预算、真实输出质量、费用规模）在预检与预算门禁下显式化；尚缺的只是正式授权与运行时密钥注入（`DASHSCOPE_API_KEY`/`BAILIAN_WORKSPACE_ID`）。

## 四、修订的旧结论（历史保留，此处更正）

1. ~~"同步图片生成重试不会重复计费"~~ → 撤销：结果不明时不自动补发，仅 429 重试；
2. ~~"user_requirement 要求 small 即可正式运行"~~ → 撤销：decompose 不接收 user_requirement；保障是付费前能力预检；
3. ~~"只保存资源 summary"~~ → 撤销：逐点样本+边界+read_status 全量落盘；
4. ~~"默认 SDK 和所有节点零重试"~~ → 撤销：OpenAI SDK 此前为默认 2 次重试（现已显式 0），tenacity 各节点保留项目重试且逐次入账。
