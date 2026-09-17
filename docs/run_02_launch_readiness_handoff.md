# RUN-02 启动前集中检查（READY-01）

日期：2026-09-14。当前为任务文档；实施时先完成 A 离线准备，停止交回评审。**不创建 R2，不消耗新的任务 attempt，不执行 Agent/模型。**

配套：[提示词](run_02_launch_readiness_prompt.md)、[原任务](run_02_handoff.md)、[R1 交付](run_02_r1_delivery.md)。研究目标、任务、模型、镜像和预算均不改变。

## 1. 为什么做这一步

原 RUN-02 因沙箱 socket 权限受限停止；R1 在获准的沙箱外环境中通过 Docker 预检，却没有 PILOT_API_BASE/PILOT_API_KEY，任务仍未开始。两次都是启动前失败，不是 benchmark 失败，也没有新增资源测量样本。

本批把权限、身份、输出路径、凭据解析及子进程传递放在一起核对。不能用另一次模型调用来测试配置；变量非空只证明传递就绪，不证明网关会接受凭据。

## 2. A：最小离线准备

阅读 methodology.md、docs/development_tasks.md、references/README.md、references/manifest.yaml，随后阅读本任务书、原 RUN-02/R1 交付与 data_management.md/trace_contract.md。

只改必要的自有启动辅助代码、测试和新文档；复用现有 credentials loader、受限环境构造和输出守卫。不新建配置框架或重做 runner/collector，不运行旧 smoke 入口。

### A1 确定唯一凭据注入路径

优先核对 `runners/smoke_launcher.py` 的 `load_credentials()`、`build_restricted_env()`，复用合适的解析逻辑而不是调用 `launch_smoke()`。

- 生产配置来源候选为 `/home/lcq/.config/opencode/opencode.json`，选定 DeepSeek-V4-Flash 条目；本阶段只用合成配置测试，不读生产配置值或真实凭据。
- 若引用 `{env:VAR}`，必须在最终获准执行进程内解析；缺失、空值、仍是未解析引用均拒绝。引用只解一层，不能作为字面 API key 发送。
- 若最终采用 PILOT_API_BASE/PILOT_API_KEY 直接注入，明确由谁在什么环境中设置。不能假定 IDE、用户 shell、沙箱外工具进程自动继承相同环境。
- 只选一条明确的注入路线并登记；不在失败后静默切换 provider/endpoint/认证方案。
- 密钥仅存在于调用期内存及指定子进程环境；不得进入 argv、shell 历史、临时 env 文件、批准记录、日志、完整异常链、配置快照或报告。不要求用户把密钥粘贴到对话。
- 不读取无关 provider、全量 environ 或秘密值进行终端展示。结果只输出固定白名单布尔值/安全类别；不输出密钥长度、前后缀、摘要哈希或 URL 查询参数。

### A2 默认离线计划与检查模式

准备薄 readiness 入口：默认计划零副作用；显式只检查模式与真实任务入口分离，代码中不得调用 runner.run、smoke、模型 SDK 网络接口或容器启动。

检查分层输出：

| 项目 | A 可以证明 | 后续受限只读检查才可证明 |
| --- | --- | --- |
| task/image/预算/解释器/代码 | 本地静态身份与路径；使用现有固定配置 | 当时最终环境中解释器与固定镜像实际可用 |
| 凭据 | 合成 inline/reference/缺失/空值解析及环境传递 | 真实引用在最终环境可解析，变量存在且非空 |
| 权限 | 需要的本地 socket 与工具权限已登记 | 获准环境访问固定 Docker socket 成功 |
| 输出 | 守卫与独占策略的临时目录回归 | 计划输出路径无明显冲突；不保证未来写入永不失败 |

合成环境传递测试必须启动无网络的短子进程，只回传白名单检查结果，验证父进程→受限子环境的映射。不要用“计划里写了 True”证明实际传递。

不要创建 R2 批准/marker/原始数据集合。readiness 检查用独立 `reports/preparation/READY-01/<check_id>/`，按已有守卫独占写入，不能触碰 RUN-02 或 R1 的批准/marker。检查报告不是运行批准。

### A3 五组最低回归

1. 默认零 Docker/网络/密钥读取；检查模式没有 runner/model/container 启动路径。
2. 合成 `{env:VAR}` 成功、变量缺失、空值、未解析引用拒绝；明确 inline 路线支持与否。
3. fake secret 经真实短子进程环境传递，最终报告/错误无 canary，实际扫描产物数量大于零。
4. 拒绝继承未批准代理、远端 Docker context/host；只允许预登记本地端点与凭据变量。任何需要代理的情况停止等待新增明确范围。
5. 临时目录软链接/覆盖拒绝；旧失败文件前后哈希一致；超时和错误只输出安全类别。

A 完成交付 `docs/run_02_launch_readiness_delivery.md`：实际命令、代码身份、所选凭据来源与注入责任、测试、尚不能证明的内容，以及下一节检查的最终审批清单。标 `read_only_check_approval=pending`，停止交回评审。

## 3. B：需另批的最终环境只读检查（不是运行重试）

A 验收后向用户申请：允许单次 readiness 命令在工具明确批准的沙箱外环境中访问固定本地 Docker socket，并仅在内存读取选定凭据以做存在性、解析和传递检查。**没有该批准，不能读取真实凭据或执行 Docker 查询。**

检查总 wall ≤60 秒；自建检查子进程最多一个、≤5 秒，无 busy loop；报告阈值 1 MiB。Docker 仅查本地 context/daemon/已登记 digest，不能 pull/build/run。固定镜像沿用原 RUN-02 task 镜像，不查询远端。

不发 API、不调用模型、不执行 verifier/benchmark、不修改环境配置、socket 权限或用户配置；不使用 sudo/替代 socket/远端 Docker。对该单次命令申请工具权限，不请求宽泛永久 python/bash 权限。

结果为 READY_FOR_APPROVAL / NOT_READY，逐项记录 observed/unknown/failed。失败即停，不自动修配置后再检查。只证明该进程环境在当时可用，**不证明认证有效、后续工具进程会继承变量、benchmark 能跑或 G1 通过**。

## 4. 后续真正运行的前置设计（本批不实施执行）

readiness 成功后才准备新的独立尝试批准，不删除旧 marker。新运行入口应复用同一启动/凭据解析路径，在实际获准进程内重新检查变量，不能依赖上次检查进程的内存环境。

后续批准必须同时包含执行环境、凭据注入方式、任务/模型/image/预算、代码身份、输出 namespace。新 attempt 的消耗点由届时任务书明确，不能本批偷偷移动旧入口的 marker 顺序或绕过一次性限制。

完成本批后保持原失败证据和研究状态不变。权限/凭据检查的失败不增加真实 task/run 样本；已接受的 I/O、共享 CPU 和末端计数缺失不返修。
