# 项目阶段研究报告：AI Agent Workload Characterization synthesis v1

生成日期：2026-10-07；同日修订（v1.1）：修正三项总判断的过度表述——资源缺口改为分层描述、CPU-02 表述按权限检查记录收紧、撤回"唯一最优下一步"的过强推荐，并收紧若干发现的适用范围。本轮为离线汇总与文档修正，不联网、不执行、不改变任何 Gate 状态。研究问题以 methodology §25（RQ1–RQ6）为准；状态以 project_state.json（2026-10-07 真源）为准。

## 当前阶段：行为侧证据初步成形，资源侧证据初步但覆盖与粒度有限

项目已得到的：三个行为证据面（公开 Coding corpus、桌面任务语义与保存动作、宏观请求流）加一组自运行 Coding 资源数据，均完成限定范围的离线分析与登记，manifest 哈希回读一致。资源侧**已有**：修复后 CODING-REPEAT-01 的 3 task × 3 repeat 真实容器级资源数据——Agent/verifier 双 scope 的 cgroup CPU、内核内存峰值与时间观测，以及限定范围的活动与资源共现观察（characterization-v3）。资源侧**尚缺**：更广的任务与 workload 类别覆盖（Office/Assistant/Video 等尚无任何测量）、单工具或进程级资源归因（现为共享容器 scope）、正式 I/O 观测（至今 null）、函数热点与架构层解释（RQ4/RQ5 无证据）。公开 trace 不含资源字段，当前已分析的公开语料不足以填补上述缺口，需要新增受控测量或具有相应资源观测的可信数据源。G2/G3-R 未通过，CPU-02 与 Replay 执行暂停。

## 核心观察（每条注明来源、单位与边界）

**1. Coding 公开语料的工具形态以通用 shell 为主，但语义可分类比例有限。** SWE-rebench v2（85 shard / 9,435 trajectory / 598,148 原生 tool_call）中 bash_terminal 占 511,104（85.4%）；保守活动分类后 Unknown 为 476,590（79.7%）。**前者是原生接口维度（记录形态），后者是活动语义维度（保守命令证据分类），二者不是同一口径，不能互相换算或混用。**按 participant 的 Unknown 比例从 14.9%（cursor）到 >99%（gpt-5.6-luna 等）——该分布反映各来源记录格式差异，不支持任何活动密度排名。允许的解释：Coding agent 的公开记录大量以复合 shell 命令形态存在，逐命令语义恢复依赖 participant 格式。不允许的外推：把 Unknown 当"未执行"、跨 participant 比较勤奋度。

**2. 桌面工作集是多应用混合，不是单一浏览器或单一文档场景。** OSWorld v3 的 108 个任务定义静态标签（可重叠）为：文件管理相关 74、浏览器信息处理 55、文档/PDF 25、演示文稿 17、媒体/游戏 16、开发/终端 15、邮件 12、表格 10、日历 7、Unknown 5。三个 Claude 来源的保存原生动作中 click 与 text_or_key 合计占 76.15%–80.36%（分母含 unknown）。734/755 条轨迹为 partial——**partial 是分析覆盖状态，不是任务失败**；216 个逐任务 native 零值字段（MiniMax/Qwen 模型级 n=1、median=0 旧口径）**不得引用**；GPT-5.6 来源 run 混合且缺 048，不能当统一批次。

**3. 该来源样本内的宏观请求流呈"多轮大上下文 + subagent 普遍"形态。** AgentX（单一来源 request-flow corpus，393 traces / 68,266 model requests）中 subagent 内部请求 39,822（58.3%），显式 subagent groups 1,697；pooled input tokens median 88,768、output median 376。MiniMax-M3 桌面侧 35,272 条 usage calls 的逐请求中位数：input 2,797、cache_read 86,508.5、output 73 token——大量缓存读而非每次全量输入。允许的解释：**在该来源样本内**，RQ1 意义上 Agent workload 相对单次 LLM 呈 multi-turn、上下文累积（以缓存读形态）与请求扇出的描述性差异。不允许：把该来源的形态推广为所有 Agent workload 的普遍规律、token 当账单、模板派生 token 当真实 API 累计（Applied Compute 是 production-derived template，非真实执行）、记录区间重叠当 CPU/GPU 并发。

**4. 同任务重复变异在受控自运行中明确存在；在本批已核对的具体范围内，Interpreter/Execute 调用数与 CPU 高低不一致。** CODING-REPEAT-01（9 个显式 run）：astropy-13398 的 attempt wall IQR 41.28 s（93.95/162.69/176.51）、Agent CPU IQR 37.89 core-s（14.78/34.50/90.56）、内核峰值内存 IQR 136.1 MiB；该任务最高与最低 CPU run 的 Interpreter/Execute 调用数相同（2 个），django-16485 的高 CPU run 调用数（4）反而少于低 CPU run（7）。**该观察只覆盖本批三个任务、FORM 分类的 Interpreter/Execute 类别与 9 个 run，不否定其他调用特征（如命令内容、时长、类别组合）对资源差异的解释价值——后者的检验尚未进行。**允许：固定任务、固定条件下运行间变异的描述。不允许：因果归因、把 3×3 试点推广为 Coding 类别规律、旧 P1-12 缺陷批次与修复后数据直接比较（模型/API/配置不一致）。

**5. 自运行 Coding 是当前唯一的系统级资源数据来源，为公开 trace 补充了资源信息。** Per-task median：Agent CPU 25.10 / 34.50 / 39.42 core-s（astropy-13236 / astropy-13398 / django-16485），内核峰值内存 113.3 / 140.8 / 1341.0 MiB；verifier 为独立 scope（median 3.55–7.59 core-s）；观测窗内请求与工具区间近串行（overlap≈0，是记录区间顺序的描述，不证明单线程）。Django 高内存与活动类别只是 co-occurrence。共享容器、无 per-tool 独占归因、wall−CPU 不作等待时间；覆盖限于 3 个 Coding task。

**6. 任务结果、Agent 终止机制与基础设施失败是三个需分列的维度，两套语料均已按此口径登记。** Coding 9 run：astropy-13398 三次均 LimitsExceeded 而 resolved 为 1 true / 2 false；django 三次 Submitted 全 resolved。**LimitsExceeded 在该来源协议（mini-Swe-agent 预算限制）下是预算边界的正常终止信号，不是实验失败或工具故障；是否计入"实验失败"按各来源协议分别判断，不跨来源合并。**SWE-rebench：agent_exit submit 7,212 / submitted 2,220 / agent_proxy/inference_server/prompt_too_long 类失败 3（基础设施/失败类单独计数），evaluation resolved 4,751 / failed 4,683 / skipped 1——resolved 不等于正常 termination，usage 不等于账单。

**7. 距离 CPU/OS 层面正式 characterization 的差距是具体的。** 缺：真实 Agent 容器热点（**CPU-02 状态：普通用户 perf 执行的权限检查记录为访问被拒 exit 255；特权方案（监督器）为实验性源码，未安装、未批准，其执行安全闭环未完成；路线为主动暂停；未取得有效热点样本。这不构成"特权 perf 已被证明不可用"的结论**）、正式 I/O 观测（至今 null）、受控变量下的架构敏感性对照（RQ4/RQ5 无证据）。行为侧数据（本报告 1–3 条）可以为资源测量的任务选择与假设提供输入，但不能替代测量本身；当前已分析的公开语料不足以填补资源缺口，需要新增受控测量或具有相应资源观测的可信数据源。

**8. 部分"差异"只是来源格式或采样口径差异。** SWE-rebench participant 间 Unknown 差异是格式差异；OSWorld pooled 静态调用 97.62% 为 text_or_key 主要由 MiniMax 一个来源的文本结构贡献（3,225,612/3,272,413），不能宣布"所有模型 97.62% 操作是按键"；AgentX 与 Applied Compute 不形成共同总体；对象数（如 SWE-bench 16,229）不等于轨迹数。

## 完成 / 未完成清单

- **已下载且已完成限定分析**：SWE-rebench v2；AgentX + Applied Compute macro v1；OSWorld task-behavior v3；OSWorld 第三方小样 3 条；Coding 自运行 9 run（review + characterization v3）。
- **已下载尚未分析**：SWE-bench Verified 35 组完整 / 16,229 对象、Lite 5 组 / 1,500、Test sonar 2,147/2,294（对象数≠轨迹数，格式抽样确认，未做行为分析）。
- **尚无可用公开 trace**：Office 真实执行、Assistant、Video 类别。
- **需要自行生成或另行获取资源证据**：单工具/进程级归因、正式 I/O、函数热点、架构敏感性（RQ4/RQ5 及 RQ3 的归因部分；RQ3 的 scope 级描述已由 3×3 Coding 数据初步覆盖）。
- **暂停、非近期关键路径**：CPU-02 特权路线、Replay 执行、G2/G3-R。

## 下一阶段决策顺序（建议，未执行）

| 方向 | 已有 | 尚缺 | 该方向能新增什么 |
| --- | --- | --- | --- |
| **A. 样本覆盖缺口** | Coding 3 task×3 repeat 的容器级资源数据；行为侧 111 task（SWE-rebench）/108 任务（OSWorld）/2,206 task（SWE-bench 已下载未分析） | Office/Assistant/Video 类别的任何测量；Coding 更广 task 与 workload 类别 | 更广任务/类别下的描述性资源分布与重复波动，增强 RQ3 描述的外延 |
| **B. 测量能力缺口** | Agent/verifier 双 scope cgroup CPU、内核内存峰值、wall、请求/工具计数与区间 | 单工具或进程级归因、正式 I/O、函数热点、架构层指标 | 测量粒度与指标维度——**仅扩样（更多同类 cgroup 样本）不会自动产生这些能力** |
| **C. 下一步建议（仅建议，不执行、不自动启动）** | 先做一次有限离线检查：现有 CODING-REPEAT-01 的事件记录与资源采样能否支持尚未完成的行为—资源关联问题（如活动类别与内存采样点的细化关联、区间内资源轨迹）。characterization-v3 已回答的内容（时间结构、FORM 分类、共现观察）直接引用，不重复开发。 | — | 若该检查无新增信息：转向代表性 SWE-bench 子集的行为分析，或公开 Computer/Office 测量的准备设计；不制造长期前置任务 |

前一版曾将"扩展 task 的资源测量设计（CODING-RESOURCE-EXPAND-01）"表述为唯一最优下一步，**该过强推荐现予撤回**：扩 task 主要增加样本、任务和类别覆盖（方向 A），增强采集主要增加测量粒度与指标（方向 B），二者解决不同缺口，孰先孰后应经上表比较后由用户裁定。本报告不自动启动任何一条路线。

## 边界重申

本轮未重跑分析器、未执行任何轨迹/benchmark/模型/网络操作；引用数字均可回溯到各来源报告（evidence_matrix.json 有逐条定位）；对未独立验证的事项均标注"来源报告"。G2/G3-R、CPU-02、Replay 状态不变；下载完成不等于分析完成；本报告不构成任何执行授权。

## 可追溯入口

- [evidence_matrix.json](evidence_matrix.json) · [manifest.json](manifest.json)
- SWE-rebench v2 / OSWorld v3（含 acceptance_summary.md）/ AgentX+Applied v1 / CODING-REPEAT review-v1 + characterization-v3（见各自 manifest）
- SWE-bench 获取登记：BULK-NONVIDEO-20260929 / SWEBENCH-CONTINUATION-20260930 / SWEBENCH-SUPPLEMENT-20261006
