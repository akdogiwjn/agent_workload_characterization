# ENV-01：独立环境安装与运行前适配

日期：2026-09-11。状态：**任务书已准备；安装/下载/第三方执行待用户明确批准，尚未开始**。

前置：[PREP-01 准备包](first_run_preparation_handoff.md)已通过集中验收，231 项离线测试通过。此批不重开 PREP-01 审计，不代表 G0/G1 自动通过。

## 1. 一批完成什么

在独立环境安装固定 mini-SWE-agent 2.4.6 及依赖，完成**真实已安装 SDK 调用链的离线适配验证**，产出可供下一次单请求 smoke 使用的程序、配置和明确命令。重点解决 provider 路由、环境变量映射、真实序列化泄漏风险和多层重试。

本批不拉镜像、不运行容器、不调用模型、不运行 benchmark/verifier。镜像准备与真实单任务留到后续审批，不因安装成功自动开始。

## 2. 一次性授权请求

执行模型先确认用户是否已明确批准 **ENV-01 下表范围**；单独转发任务书或“阅读文档”不视为安装批准。未批准时只展示此摘要并停止，不重复要求用户选择已定模型、harness、pip 或路径。

| 项 | 本批拟执行范围 |
| --- | --- |
| 软件 | 本地已校验 mini-swe-agent 2.4.6 wheel + 必要运行依赖，不安装额外 benchmark/开发工具全集 |
| 环境 | `/home/lcq/agent_workload_characterization/.venvs/mini-swe-agent-2.4.6-env01`，独立 Python venv，无 system-site-packages |
| 下载区 | 项目 `data/raw/software/env01/wheelhouse/`，pip 临时目录也放该批次目录；禁共享缓存写入 |
| 软件源 | 公共 PyPI（pypi.org/files.pythonhosted.org），无认证；不沿用未知私有 index 或自动换镜像源 |
| 网络用途 | 仅包索引/必要 wheel 下载；离线适配阶段禁止任何外连（含遥测、价格表和模型请求） |
| 下载与磁盘预算 | 下载上限提案 1 GiB、该批新增磁盘总量 3 GiB；这是安全边界，不是已测量大小。超限停止，不自动扩预算 |
| 时间 | 下载/安装合计 15 分钟；离线测试每命令有界、整批测试建议 10 分钟；到限保留记录后停止 |
| 第三方执行 | 批准后允许在独立环境导入 mini/litellm、执行必要 help/version、使用假凭据和拦截 transport 做离线调用/序列化测试 |
| 凭据 | 不读取真实 opencode.json、不提取真实 key；仅假 endpoint/key、已有脱敏 provider/model 信息 |
| 产物 | 自有适配代码/测试、锁定包清单与哈希、ENV-01 报告、下一次 smoke 审批命令 |

上限须实际实施：下载前解析计划/检查已知包大小，未知大小通过有界下载处理；限时、隔离缓存和磁盘监测/配额至少采取可验证的措施。不要仅在文档写上限而执行无限下载。预计超限可提前报告所需调整，不强行凑预算。

## 3. 先读与复用

完整阅读项目四份必读文档与 trace/data 契约，再读：

- `docs/first_run_preparation_delivery.md`、`docs/first_run_approval.md`；
- `docs/mini_2_4_6_static_delivery.md`、`data/catalog/mini_2_4_6_artifact.yaml`；
- `src/agent_workload_characterization/runners/preparation.py`、`runners/report_writer.py`、相关 tests；
- 固定 wheel 的 METADATA 及所需调用链成员；安装后以**实际安装版本源码**核实 litellm/底层 SDK 行为。

不修改 references、旧工程、原始任务记录、已有 wheel、历史报告；不升级项目原环境依赖，不整库复制第三方代码。存在脏工作树时保留所有既有改动，不提交/推送 Git。

## 4. 环境安装：批准后才执行

1. 检查批准范围、空闲磁盘、解释器版本及目标路径真实边界。路径已存在时核实来源，不能覆盖或自动删除；未知既有环境报告冲突。
2. 校验 mini wheel 大小 115037、SHA-256 `a35463c553ac825c7773b03cfa69cd44958e3af20155dcc5711fdf9e4c67cd54`。
3. 使用现有 Python `venv` + pip；不安装 uv、不升级系统 pip、不使用 sudo。venv/ensurepip 不可用时报告缺口，不转而改系统环境。
4. 固定 mini=2.4.6。先尝试从已有 SWE-bench 锁文件复用兼容约束；不执行参考仓库项目，不要求照搬其全部依赖。必要时在本批范围解析依赖并记录所选版本。
5. 包只接受兼容 wheels（含 mini 的直接/传递依赖）；不执行未知 sdist 构建。缺 wheel 时列明包和原因，等待是否扩大授权，不静默编译。
6. 配置 pip 使用明确的公共源、禁版本联网检查、禁共享缓存；下载到本批 wheelhouse，记录每个文件名、大小、SHA、包版本和来源。具体 pip 参数依据本机已有 pip help 核实，不为升级 pip 新开依赖链。
7. 从已归档 wheelhouse 离线安装（no-index）到独立环境，执行依赖一致性检查；记录实际依赖快照。安装不执行含真实密钥的 shell 初始化或用户项目 startup 脚本。
8. `.venvs/` 和下载区不进 Git；对现有 ignore 规则做最小补充。将环境路径、解释器、已安装分发版本、wheel hashes、安装结果写新批次 manifest。

依赖解析时的探测与实际下载都计入本批预算。禁止自动重建环境、自动重试整个安装流程或换源；失败保留日志摘要与已下载文件。下一次是否继续由用户确认，不自动清理。

## 5. 适配层：连接 PREP-01 与实际 SDK

实现最小自有模块，建议 `runners/model_adapter.py` 与独立 smoke 入口；可按已有布局调整。不开完整 Coding Runner、不接资源采集器。

### 5.1 模型路由与配置

- 模型选择固定 DeepSeek-V4-Flash，不再询问用户模型/provider。区分 OpenCode 配置键、litellm provider 前缀和最终请求 model 字段；用安装版本证据核实映射。
- 本批以假 HTTPS 端点验证 URL 构造（含 `/v1` 是否重复）、auth 映射与 tools 格式；不向实际网关探测。若真实网关模型 alias 尚不能由现有脱敏信息确定，明确留待 smoke 审批，不批量试名字。
- `PILOT_API_BASE/PILOT_API_KEY` 是本项目变量，不假定 SDK 原生识别。适配代码应明确转换到实际 SDK 支持的位置，测试生效；任何可能被 mini 序列化的 model_kwargs/config 都不得带密钥。
- 认证只注入需要的 Agent/model 进程，不传播到工具容器/环境。未来读取真实凭据的入口本批仅用假配置测试；不运行该入口读取真实用户文件。
- 保留准备计划与有效运行配置差异，不将 PREP-01 的“允许字段名列表”当作有效参数值。验证真正传给 SDK 的参数。

### 5.2 离线调用与防泄漏

在第三方导入前准备离线防护与假凭据。网络禁止必须覆盖 import/init/query 的潜在价格表、遥测及 HTTP 路径；仅 mock 顶层 completion 不能证明实际路由正确。可用拦截底层 HTTP transport 的 fake response + 出站网络拒绝，分层测试。

最低场景：正常响应、tool call 响应但不执行、认证/超时错误、缺 usage、价格未知、响应/异常回显 canary。调用真实模型适配/序列化代码，但不执行 Agent 生成的命令，不加载真实任务题面。

检查所有本批输出：stdout/stderr、异常、mini 序列化轨迹/config、自有 call record、报告文件。错误类型固定白名单、usage 各层白名单复用 PREP-01。不要为了采原生日志先把秘密落盘再删除；原始敏感 response 先在内存安全处理，注明脱敏，不声称字节级原始副本。

如果第三方默认日志/轨迹仍泄漏，优先用自有 adapter/明确 hook 限制字段；不修改 site-packages 或 references 来隐藏差异。确需第三方补丁时报告范围与替代方案，不扩大本批授权。

### 5.3 请求、重试与费用

- 每次请求有非空 ID；保留调用成功/失败、usage 与可用客户端起止时间；monotonic/UTC 按现有契约，不伪称服务端耗时。
- 明确区分任务 attempt、mini tenacity、litellm/底层 SDK 重试。以计数 fake transport 实证：一次失败只产生一次底层请求；仅检查环境变量字符串不算禁重试证据。
- 固定下一次 smoke 为最多一次请求、0 自动重试、30 秒总 wall deadline；底层 timeout 不一定是总 deadline，不能混为一谈。
- 沿用已选策略：未知价格 `amount=null/cost_status=unknown`，原生返回 0 单列来源值，不改成已核算费用。使用真实 mini 成本路径制造未知价格情形，确保不丢已经收到的 usage。
- 用户无金额上限，不把 bundled 3 USD 当用户限制；核实 mini 实际如何关闭金额停止条件。不能凭猜测设 0/-1；若不支持，记录最小适配方法。步数和超时限制独立保留。

## 6. 交付下一次 smoke 的可执行入口

本批只实现并用 fake transport 验证入口，**不实际发送请求**。默认应是离线检查/显示计划；真实模式必须显式选择并在另次用户批准后才调用。

更新 `docs/first_run_approval.md` 的 smoke 部分：给出确切独立环境解释器、入口、参数、输出路径；不含密钥或完整私有 endpoint。列明：

- 单条非任务消息；最多 1 请求、输出上限 100 token、总 30 秒、0 自动重试；
- 若要验证结构化工具兼容，可附一个无害工具 schema 并只记录响应，绝不执行 tool call；提前写明请求形态；
- 模型费用未知，不承诺“极小额”或免费；记录实际 usage；
- 真实凭据只从用户指定配置安全提取并在内存注入，不打印、hash 或保存密钥；
- 失败停止，不更换端点/模型自动再试；成功也不启动 benchmark。

不要求本批实现本地任务 wrapper、镜像拉取、verifier、cgroup collector。这些列入真实任务前下一批，而非此次安装验收前置。

## 7. 测试与产物

默认项目 unittest 仍不依赖 mini/litellm 安装、旧数据、Docker 或网络；真实安装版本离线集成测试使用单独显式入口，注明环境/版本。不要把缺 mini 的默认测试悄悄 skip 后称实际 SDK 测试通过。

最低验收证据：

1. wheel/安装版本对应，依赖一致性检查通过；未改原环境。
2. 离线 transport 验证 model/URL/auth/tools 的实际出站构造，没有真实联网。
3. 正常和错误路径 canary 不进最终文件/stdout/stderr，真实 mini 序列化路径已覆盖。
4. 失败底层请求计数=1；usage/费用未知语义正确；退出与 timeout 有测试。
5. 已验收项目测试（基线 231）与新增自有测试通过；显式集成测试单列。
6. 输出路径保护、历史产物保留，`git diff --check` 通过。

建议交付：

- 自有最小模型适配模块、smoke 入口及测试；
- `data/catalog/env01_environment.json`：解释器/锁定依赖/软件产物定位，无秘密；
- `reports/preparation/ENV-01-<batch>/`：环境快照、离线集成结果、缺口、manifest（绑定代码状态与依赖 hashes）；
- `docs/environment_adaptation_delivery.md`：实际操作、结果、预算用量、局限；
- 更新 smoke 审批清单和当前进度入口；不全库改历史措辞。

若离线策略无法避免第三方主动外连，或依赖/预算阻塞，交付已完成部分与精确阻塞，不调用真实 API 来绕过。

## 8. 验收与停止

集中验收：越权联网、秘密泄漏、输入/历史产物损坏、假测试冒充实际 SDK 验证是阻塞项；真实网关是否接受请求、镜像/benchmark 未运行是预期下一批事项，不阻塞 ENV-01。

完成后停止，向用户提交下一次 smoke 的具体审批请求。不得自动拉镜像、运行模型/benchmark、扩大场景、提权或提交 Git。ENV-01 验收不自动通过 G0/M1/G1；后续 Gate 按对应测量证据评审。
