# RUN-02：真实 Coding Agent 联合观测试点

2026-09-14 后续状态：A 已验收，原 B 因沙箱 Docker socket 权限限制在预检阶段停止；只读诊断确认沙箱外固定镜像存在。原批准不复用。重试依据 [RUN-02-R1 任务书](run_02_r1_handoff.md)，本页保留原目标与预算，不直接重跑旧命令。

日期：2026-09-14。状态：**任务书就绪；仅可先做 A 离线准备。B 真实执行未授权。**

配套：[集中评审](g1_consolidated_review.md)、[交给实施模型的提示词](run_02_execution_prompt.md)。保持“任务书＋提示词 → 实施模型交付 → 原评审核验”三步。

## 1. 目的与非目标

属于 SWE-bench Verified 的 `django__django-16485`，不是新增 benchmark。再次运行同一任务，是为验证新增采集链，不是修复 RUN-01 的结果，也不是增加独立 task 数。

服务 RQ2（时间花在哪里）与 RQ3（哪些已观测 scope 消耗资源）。新增一次真实 attempt，取得：原生工具窗口＋mini 宿主进程 CPU/RSS＋容器 CPU/memory＋请求边界与 verifier。允许任务失败；不得为 resolved=true 重试。

不做：per-tool 专属 cgroup、完整后代进程树、常驻服务框架、工具分类器、PMU/perf/eBPF、Hotspot、replay、scale、新 benchmark、全量 ingest、安装或下载。不能把 RUN-01/02 的差异归因于 instrumentation 开销：Agent 行为随机、代码已有变化。

## 2. 必读与复用

完整阅读 methodology.md、docs/development_tasks.md、references/README.md、references/manifest.yaml，再读 data_management.md、trace_contract.md、本任务书及集中评审。

按需核对自有代码：`runners/c_entry.py`、`coding_pilot.py`、`mini_agent_adapter.py`、`tool_event_env.py`、`container_runtime.py`、`collectors/host_process.py`、`resource_sampler.py`、`analyzers/resource_summary.py`；沿用真实 mini 封网集成与 swebench 解析测试。不遍历或修改全部第三方项目。

现有接线：mini adapter 输出 `mini_tool_events.jsonl`、`host_process.jsonl`。后者当前为单个结构化 JSON 文档，不能因扩展名而按逐行记录解析。工具文件包含真实 hook 数据，禁止用 runner 收到 status 的时间替代执行边界。

现有 `c_entry.py` 固定 `COLLECTION=RUN-01-C`，计划文案还含历史 host 未采集状态。**不能直接把旧 C 命令当 RUN-02 命令运行，也不能只改字符串绕过 catalog pin。**

## 3. A：一次离线集成准备，完成后停止

允许的改动仅限本次必要的新入口/配置、分析接线、测试及文档。复用现有组件，不复制第二套 runner、hook、budget 或 cleanup 状态机。优先新增薄 RUN-02 入口和独立配置；若需要公共参数化，只做最小改动并保留旧入口行为。

### A1 身份与实际入口

- 新 collection 建议 `RUN-02`；raw 为 `data/raw/generated/RUN-02/<run_id>/`，派生报告为 `reports/resource/RUN-02/<run_id>/`，均独占创建。旧 RUN-01/B1 批次只读。
- 使用已有固定 task record，SHA-256：`762de270d1ce06ab23104a35322098178624865c886d7b0ddadf9044d8fec46a`。核对实际 locator 与内容，不在文档/终端输出 gold patch。
- 镜像固定为 `swebench/sweb.eval.arm64.django_1776_django-16485@sha256:19d403c243c2857e7cb9cf5af8ce3f1cb6d87be91c5254e1de00040e6db3b7d2`。
- 沿用 mini 2.4.6、evaluator 02e7a74 的两个现有 venv；模型 DeepSeek-V4-Flash。模型请求 ID 的大小写、路由前缀按成功 smoke/实际配置核对并登记，不能凭名称静默切换。
- 默认计划模式无 Docker/网络/凭据读取；执行需新批准记录，绑定 task/image/config/code/预算/输出集合。旧 C/B 批准不复用；双旗标不代表用户身份。
- 交付实际解释器、模块、argv、完整哈希和授权状态。命令必须真实存在并经离线组装验证；本任务书不猜测新命令。

### A2 观测与分析接线

- 以实际 mini hook 的工具 ID、open/closed/error、monotonic 时间和返回状态构建逐调用时间表；与 trajectory 对照，重复/孤立/未闭合分别报告。Submitted 可保留其真实中断语义，不能伪造正常 closed。
- 宿主数据必须来自本次 mini 子进程 PID+starttime，保留 units、原始快照、首末可读区间、退出缺失与采集读耗时；不是 B1 的 sleep 子进程，不冒充所有后代或进程全生命周期 CPU。
- 容器 CPU 只用同 scope 有效边界差；memory current/kernel peak/sampled max 分开；I/O 正式 null＋原因。docker_stop 后末值消失仍合法保留 null。
- 工具窗口与容器采样仅 shared_scope 时间关联。覆盖不足时不插值，不按持续时间分摊 CPU，不复制容器总 CPU 给每个调用。输出可观测窗口/采样覆盖与未知量。
- 请求计数包括格式错误、最后一次请求；begin/end 不双计。模型 latency 不当本地 CPU；不把 E2E 减累计请求时长称为宿主 CPU/纯 Agent 开销。
- 分开 execution/evaluation/archive 与 agent_exit/submitted/candidate_source；LimitsExceeded 不因工作树修复成功而改成干净提交。
- raw 封存前等日志写入完成，递归列全文件；派生摘要另写，身份、哈希、大小、遗漏/缺失能对账。不回填旧运行新增字段。

### A3 最小离线验收（集中完成）

| 验收组 | 最低行为证据 |
| --- | --- |
| 新入口隔离 | 默认零副作用；缺批准/单旗标/身份漂移拒绝；输出不指向历史集合 |
| 真实 mini 接线 | 已安装 mini＋fake transport 封网＋fake 环境，证明工具执行实际发生、新工具文件与宿主文件进入最终包；不只是类名存在 |
| 失败与停止 | 复用格式错误、wall kill、Submitted 回归；新增文件在失败路径存在或有明确失败记录，不能因缺文件而 PASS |
| 保真与安全 | 原始时间来源、缺失/实测零、未知 I/O；凭据/答案 canary 在最终自有产物/Agent 输入边界检查有效，扫描产物数必须大于零 |
| 报告 | 全文件哈希回读；真实工具/宿主来源与假数据明确；派生报告不覆盖 raw |

默认测试应隔离旧数据、Docker、网络和 SDK；显式 mini/evaluator 集成只用现有环境与合成输入，不发 API。无需复制 494 项测试逐条重写；报告本轮实际测试数量、命令和结果。每套测试设置合理超时，可分组，不因全量超时重跑真实实验。

A 阶段禁止 Docker 查询/启动、模型 smoke、读取密钥值、网络、镜像操作。记录所需路径存在性和脱敏静态配置即可；真实环境检查留到 B 批批准内。

## 4. B 运行审批提案（不是本次授权）

| 项目 | 提案 |
| --- | --- |
| 次数 | 1 task、1 新 attempt，失败即停，不自动重试 |
| 模型请求／step | 各 ≤30；格式错误请求仍计入；三层重试禁用的实际配置登记 |
| 输出 token | 单请求 ≤4096（传 SDK 上限并计数），不是全 run 4096 |
| 时间 | Agent ≤25 min，Verifier ≤5 min，总运行 ≤30 min；分段不得叠加超总限 |
| 预检 | 单独 ≤60 s，只允许本地端点/已存在镜像检查；无 build/setup/install；与运行 wall 分开报告 |
| 容器 | 最多 Agent/Verifier 两个、顺序，每个 ≤4 CPU/8 GiB，network none，pull=never |
| 采样 | 沿用 runner 0.5 s、mini 父轮询 0.2 s、产物监控 0.25 s；A 核对实际值，变化需列入新审批 |
| 存储 | run_dir 5 GiB 检测阈值，不是容器磁盘硬上限；无可写层配额，清理删除本次容器回收 |
| 网络／费用 | 仅宿主 mini 到既有获选模型网关；代理若需要须明确列入批准。无费用上限，价格未知保留 unknown＋usage，不宣称免费 |
| 清理 | 仅本次 container/run 身份与自建子进程；正常清理纳入预算，强制兜底若越时如实记录，不静默扩额 |

既有成功认证不保证长期有效。仅在批准执行时使用环境变量凭据，支持环境引用解析但禁止原文输出/持久化；不先跑一次“免费 smoke”。第一次失败即保存并停止。Agent 仅拿 problem_statement 与必要环境身份，不注入历史 candidate/gold/test_patch；禁用整条 instance 渲染的启动命令。

A 交付 `docs/run_02_delivery.md`，唯一审批段须填：真实命令、全哈希、task/镜像/model/venv、预算、准确输出路径、环境变量名称及代理需求、限制、`user_approval=pending`。用户对该最终清单明确批准后才能写批准记录并执行；若已有同一批准对应的 attempt，只读交付它，不再新跑。

## 5. B 后的报告与停止点

输出三状态、Agent 退出/提交状态、实际请求/工具计数、token/费用状态、独立 wall；工具时间线及 coverage；mini 宿主原始证据；Agent/Verifier 容器 CPU/memory 与缺失；collector 读耗时；全部源/产物血缘与清理证据。

可以描述本 run 哪些工具窗口最长、哪些 scope CPU/memory 较高；不能把它们称为独占 Tool CPU 热点，不能对一个任务报告生产 P99 或架构需求。

RUN-01 仅作为旧观测能力参照，不合并成独立任务样本、不用新运行回填旧 null。结果无论成功失败均交回原评审；只更新 G1 六条的新增证据，不自行通过 G1。不自动进入第二个任务、PMU、优化或第三次运行。

## 6. 防止继续琐碎返修

范围固定为“新 attempt 身份＋既有观测接线＋最小报告”。已接受的缺失（共享 CPU、I/O 降级、退出末边界缺失、采样遗漏）记录即可。审查一次集中列出影响授权、安全、停止、原始证据和研究语义的阻塞；其余记后续待办。若发现必须扩大范围才能完成，先报告原因，不自行扩建框架。
