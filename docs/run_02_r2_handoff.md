# RUN-02-R2：已验证启动路径的单次真实联合观测

日期：2026-09-14。状态：**任务书就绪；先实施 A 离线接线，B 单次真实执行另批。**

配套：[执行提示词](run_02_r2_execution_prompt.md)、[RUN-02 原任务书](run_02_handoff.md)、[G1 集中评审](g1_consolidated_review.md)。遵循任务书与提示词 → 实施模型交付 → 原评审核验 → 用户批准执行。

## 1. 当前事实与本批范围

原 RUN-02 因沙箱 socket 权限受限停止，R1 因执行环境未注入凭据停止，两次均未开始真实任务。READY-01 最新只读检查通过：

- [summary](../reports/preparation/READY-01/20260914T111017Z-7eb3c4/summary.json)，SHA-256 `cc234ad87b9c00189c20f9ec8c1836a3f762aca36a9ac420b83533b323ac2a65`。
- [manifest](../reports/preparation/READY-01/20260914T111017Z-7eb3c4/manifest.json)，SHA-256 `af76a6e481d56488f09031eb0702780dbc928174e2998151ef2f01725a4bf942`。
- 选定配置解析、凭据到短子进程的传递、无代理环境、固定 Docker endpoint/image 检查通过。task/catalog 为 registered_not_checked；没有认证请求，不证明网关认证有效。

本批仍为 SWE-bench Verified `django__django-16485` 的一次新尝试，服务 RQ2/RQ3：获取真实工具窗口、mini 宿主 CPU/RSS 与容器资源联合证据。不是新增 benchmark，不是性能 A/B，也不增加独立 task 数。

只做 R2 独立身份与启动接线，复用已验收 runner、hook、采集器、分析与清理。禁止重做 READY-01、环境安装、拉镜像、smoke、B1、PMU/perf、replay 或分类器。

## 2. A：最小离线接线与审批登记

完整阅读四份基础文档 methodology.md、docs/development_tasks.md、references/README.md、references/manifest.yaml，再读本任务书、原 RUN-02/R1/READY-01 交付、data_management.md 和 trace_contract.md。第三方只作参考。

### A1 独立身份和输出

保持 collection=`RUN-02`，新增固定 attempt_label=`RUN-02-R2`：

| 内容 | 固定位置 |
| --- | --- |
| R2 批准 | `reports/resource/RUN-02/retries/R2/APPROVAL.txt` |
| R2 一次性登记 | `reports/resource/RUN-02/retries/R2/ATTEMPT_STARTED.json` |
| R2 启动预检证据 | 同目录 `PREFLIGHT.json`，独占创建 |
| 新 raw | `data/raw/generated/RUN-02/<new_run_id>/` |
| 新派生报告 | `reports/resource/RUN-02/<new_run_id>/` |

允许薄 R2 入口或最小参数化现有启动代码，不复制 runner/cleanup。默认计划零副作用；不提供任意 namespace/任意输出路径来绕过守卫。批准绑定 attempt_label、完整代码/配置/task/image/预算/路径、凭据路线、执行权限、旧失败记录及 READY 成功证据哈希。

旧 RUN-02/R1 的批准、marker、预检与两批 READY 报告保持原字节；A 前后核验相关哈希。旧批准不适用于 R2。缺批准、身份漂移或 R2 marker 存在时拒绝，不删除或重新登记。

### A2 一次执行进程完成全部启动步骤

不能把 READY 检查进程中的变量视为持久状态，也不能只把 `VOLCANO_API_KEY` 传进去就运行旧入口。新入口必须实际完成以下链路：

1. 校验新批准与实际 task record/catalog/接线代码身份；固定值见下方身份表，不只复制登记值而跳过实际文件核验。
2. 原子创建 R2 marker，之后任何预检/凭据/模型/任务失败均消耗本次槽位，保留失败证据，不自动创建 R3。保持已验收一次性顺序，不悄悄改变原入口。
3. 仅清除本次进程及其子环境的大小写 HTTP_PROXY/HTTPS_PROXY/ALL_PROXY/NO_PROXY 与 SMOKE_APPROVED_PROXY；不修改用户配置或其他 shell。锁定 `unix:///var/run/docker.sock`，清除远端 context 影响。
4. 在同一获准进程内，按 READY-01 路线检查选定 provider/model 的字段精确为 `{env:VOLCANO_API_KEY}`，使用已验证 loader 内存解析；缺失/空值/未解析引用直接拒绝。
5. 明确传入现有 runner 接受的 credentials：最终 mini 子环境 `OPENAI_API_BASE/OPENAI_API_KEY`。若使用中间 launcher 子进程，则真实构造 `PILOT_API_BASE/PILOT_API_KEY` 并证明下游映射。不能只检查非空或只在文档画箭头。整个链路无密钥 argv/日志/临时 env 文件，不导出全量环境。
6. 在相同获准执行环境完成固定 Docker 只读预检，然后调用既有 runner 一次。原预检总额度沿用 ≤60 秒；凭据/静态检查实际耗时单列，不伪称全部均由 Docker 超时器限制。
7. 成功或失败均更新 R2 marker；调用前失败不得制造 run 样本。runner 返回后生成既有派生报告与完整性证据，返回真实状态。

上面第 1 步的唯一固定身份：

| 项目 | 值 |
| --- | --- |
| task | `django__django-16485` |
| record SHA-256 | `762de270d1ce06ab23104a35322098178624865c886d7b0ddadf9044d8fec46a` |
| catalog | `workload_catalog/run_02.yaml`，SHA-256 `fca2c6f094196d4e4a62c285ed6a3fc230c8e4deded11e0c5f5bab573ed13656` |
| image | `swebench/sweb.eval.arm64.django_1776_django-16485@sha256:19d403c243c2857e7cb9cf5af8ce3f1cb6d87be91c5254e1de00040e6db3b7d2` |
| model | 已登记 DeepSeek-V4-Flash，路由 `openai/deepseek-v4-flash`，不改大小写/endpoint/provider |
| harness / evaluator | mini 2.4.6 / evaluator 02e7a74，复用现有两个 venv |

生产配置 `/home/lcq/.config/opencode/opencode.json` 只在获批执行时按白名单读取选定条目。A 使用合成配置和假密钥；不读生产配置或真实秘密。不将历史 candidate/gold/test_patch 注入 Agent，不改变问题陈述或任务初态。

### A3 五组行为回归，一次集中完成

1. 默认计划零 Docker/网络/真实凭据读取；旧批准/漂移/重复 marker 拒绝，旧证据不变。
2. 真实 R2 入口＋临时新批准＋fake runtime/transport 跑通；假 VOLCANO 引用经实际启动映射到 mini 子环境，不靠 mock `_credentials()` 返回正确值掩盖接线。
3. 缺少/空引用及原代理污染场景：前两者 runner 调用为零；代理仅本次环境清除，子环境无代理，报告无秘密。清除后不得跳过显式用户批准。
4. 预检失败保留安全分类、失败 marker、runner=0；一次成功后重复调用拒绝；报告失败/清理失败保留非零语义。
5. 复用真实 mini 封网贯通，验证工具/宿主文件、原生 duration、清理与报告；扫描最终产物数 >0，假秘密不出现。只测试接线变化，不重写现有测量回归。

允许现有 venv 的离线/封网测试。A 禁止 Docker 查询、真实权限探测、API、安装、镜像操作、真实批准/marker 创建、git 提交推送。

交付 `docs/run_02_r2_delivery.md`：唯一真实命令、解释器/argv、完整实际哈希、预算、准确输出路径、所需权限与凭据注入责任、实际测试、旧文件核验。标 `user_approval=pending`、`tool_execution_permission=pending`。任务书不猜测尚未实现的命令。A 完成后停止，原评审集中验收。

## 3. B：新批准后单次执行，预算不变

用户批准最终清单后，执行工具对登记单次命令显式申请沙箱外权限；预检与 runner 在同一获准环境。权限拒绝即停，不改 socket 权限、sudo、远端 daemon 或全局沙箱策略。

由操作员通过安全方式将 VOLCANO_API_KEY 注入该执行环境，不打印值，不把密钥写进提示词或 shell argv。不得假定 IDE 的变量自动继承。

| 约束 | 保持不变 |
| --- | --- |
| 次数 | R2 一次；无自动 retry，无额外 smoke |
| 模型请求 / steps | 各 ≤30，格式错误计数，三层自动重试禁用 |
| 输出 tokens | 每请求 ≤4096 |
| wall | Agent ≤25 min，Verifier ≤5 min，总运行 ≤30 min；Docker 预检独立 ≤60 s |
| 容器 | 最多两个、顺序，各 ≤4 CPU / 8 GiB、network none、pull=never |
| 采样 | 容器 0.5 s、mini 宿主 0.2 s、产物监控 0.25 s |
| 产物 | run_dir 5 GiB 检测阈值，容器可写层无配额 |
| 费用 | 无新增费用上限；unknown 价格保留 usage，不宣称免费 |
| 网络 | 仅原获选宿主模型网关，无代理；若需代理停止等待新批准，不静默恢复 |

失败即保存停止，不修代码重跑、不创建 R3、不换模型或镜像。清理只按本次身份，失败/越时/未确认如实记录。I/O 正式 null、共享 CPU、退出后末端计数可能缺失继续作为已接受限制。

## 4. 交付与停止

交付启动检查、独立三状态、Agent 退出/提交状态、请求/工具数、usage、工具时间线和 coverage、宿主与容器原始证据、资源摘要、清理与哈希。预检失败不计真实任务；task 未解决不等于测量无效。单次真实运行不证明生产代表性、开销因果关系或独占 Tool CPU。

完成后交回原评审，G1 不自动通过。本批不再开展通用 readiness 开发；只对授权、安全、真实接线、停止和证据保真阻塞一次集中列项，其他限制记录即可。
