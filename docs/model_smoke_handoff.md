# SMOKE-01：单次真实工具协议连通性检查

日期：2026-09-11。状态：**执行文档已准备；真实请求尚未授权、尚未执行**。

前置：PREP-01、ENV-01 已通过集中验收。当前基线为默认测试 231 项、显式 SDK 集成 23 项；两个硬超时测试已证明请求进入 fake transport 后被父进程 SIGKILL，所有测试子进程退出。此处不重开安装和离线适配验收。

## 1. 给用户的审批摘要

本批需要用户明确批准 **SMOKE-01 单请求范围**，否则只准备/展示计划，不读取真实密钥、不发送请求。转发本文要求阅读，不等于批准执行。

| 项 | 固定范围 |
| --- | --- |
| 模型/provider | 用户指定的 DeepSeek-V4-Flash / 火山AI网关；配置来源 `/home/lcq/.config/opencode/opencode.json` |
| 调用链 | 已安装 mini-SWE-agent 2.4.6 → litellm 1.100.1 → openai SDK 2.54.0 → 用户网关 |
| 候选路由 | `openai/deepseek-v4-flash`，请求 body 的 model 为 `deepseek-v4-flash`；离线构造已验证，网关接受性待本次检查 |
| 请求数 | 最多一次应用层模型 HTTP 请求；0 自动重试，不换模型/端点补试 |
| 输入 | 一条不含真实任务、代码或私有资料的消息，请求 bash 工具返回 `echo smoke-ok` |
| 工具 | mini 自带 bash schema；只解析返回值，**任何返回命令均不执行**，包括 echo |
| 输出 | 请求参数 `max_tokens=100`；记录实际 usage，若网关未遵守上限如实记录，不追加请求 |
| 时限 | 子进程启动后查询预算 30 秒，超时父进程 kill 并回收；父进程准备/报告与最多 5 秒回收时间单列，不声称整个 CLI 恰好 30 秒结束 |
| 费用 | 无金额上限；价格未知，不能承诺免费或极小额。调用取消不保证服务端停止处理或不计费 |
| 凭据 | 只读本地指定配置，密钥只在内存/进程环境中传递，不打印、hash、存文件或置于 argv |
| 网络 | 仅向指定 HTTPS 网关请求；保持本地价格表开关，不访问其他模型服务、远端价格表或包源 |
| 停止 | 无论成功、纯文本、认证失败、超时还是本地失败，本批均停止；不拉镜像、不运行 benchmark、不重试 |

申请确认用语：**是否批准 SMOKE-01：从指定配置在内存读取凭据，仅向该网关发送上述一次工具协议请求，30 秒查询预算、输出上限 100 token、零重试，不执行工具？**

## 2. 先读与本批范围

遵守项目四份必读文档及数据/trace 契约，再读：

- `docs/environment_adaptation_delivery.md` 最新返修记录；
- `docs/first_run_approval.md`、`data/catalog/env01_environment.json`；
- `src/agent_workload_characterization/runners/smoke.py`、`model_adapter.py`；
- `tests/integration_env01.py`、`reports/preparation/ENV-01/manifest.json`。

不用重新阅读全部第三方源码或重跑全套历史数据检查。不得修改 references、旧工程、原始任务记录、用户配置、已有 ENV/PREP 报告或第三方安装包；不安装/下载依赖，不 commit/push。

允许本批做的最小准备修改：生成独立、无凭据 smoke 配置；必要的安全凭据启动器及其假配置测试；新增本批报告/交付说明。不得借此构建完整 Runner/collector。遇到已验收执行路径回归或需要重大改造，先报告，不用真实请求诊断代码缺陷。

## 3. 请求前准备（不计为真实请求，但不可借此探测网关）

1. 核对独立解释器 `.venvs/mini-swe-agent-2.4.6-env01/bin/python` 和关键安装版本，检查 ENV-01 报告哈希及工作树变更；不重新安装。
2. 当前 `data/catalog/pilot_run_config.yaml` 仍含 `UNVERIFIED_PREFIX/deepseek-v4-flash`，**不能直接拿默认配置发送**。从该无凭据模板生成 `data/catalog/smoke_01_config.yaml`，保留必要结构，设置：
   - `model.model_name: openai/deepseek-v4-flash`；
   - `model.cost_tracking: ignore_errors`；
   - `model.litellm_routing: unverified`（当前准备层对该值的判断较粗，真实网关尚未验证，不提前标 true）；
   - `environment.api_base_env: PILOT_API_BASE`、`auth_env: PILOT_API_KEY`；
   - `run.env_startup_command: null`；不含真实 baseURL/apiKey。
3. 此配置的路由依据记录为 ENV-01 的**离线请求构造证据**，不要把它与“网关已验证”混成一个状态。smoke 程序实际覆盖 max_tokens=100、num_retries=0 和 mini 重试环境；无需把 max_tokens 加进 PREP-01 限制更严的配置白名单。
4. 准备新输出目录 `reports/smoke/SMOKE-01-<UTC批次>/`，验证路径守卫、写权限和独占新批次，不能复用/覆盖历史运行。准备本批 code/config hash；不 hash 用户凭据配置。
5. 用无真实凭据环境运行 offline plan，检查语义、model、消息、100 token、零重试和输出路径。`--help` 或 offline plan 失败时先停止处理本地问题，不发送请求。

当前默认配置为占位值这一修正仅在新 smoke 配置进行，不回写历史 pilot 输入或宣称正式 benchmark 配置冻结。

## 4. 安全读取凭据与启动

现有 smoke 入口只消费环境变量，不负责解析 OpenCode 配置。若没有可复用的安全启动器，本批实现一个很小的自有启动器，并先用合成 JSON/JSONC、假密钥测试。

启动器要求：

- 真实读取必须发生在批准后；从指定文件解析 `provider`，唯一选择火山AI网关与 `deepseek-v4-flash` 项，读取该 provider 的 baseURL/apiKey。使用严格 JSON；确有 JSONC 语法时复用已有正确解析器，不能用粗糙正则剥注释造成值变化。
- 验证 endpoint 是 HTTPS、无 userinfo，model/provider 唯一且与审批一致；缺失、歧义、引用型凭据或不支持格式时输出固定安全错误并停止。禁止 dump 原始配置或解析异常原文。
- 不 cat/rg 用户配置，不打印环境变量全集，不要求用户把 key 粘贴到聊天或终端命令。不使用 `set -x`、`env KEY=<真实值> ...`、含密钥的 shell export、.env 文件或凭据哈希。
- 在启动器内构造受限进程环境：必要 PATH/PYTHONPATH/locale/证书配置 + 本次 PILOT_API_BASE/KEY；不复制所有云/模型服务凭据。`PYTHONPATH` 使用本项目绝对 `src` 路径。
- 强制 `LITELLM_LOCAL_MODEL_COST_MAP=True`、`MSWEA_MODEL_RETRY_STOP_AFTER_ATTEMPT=1`。真实 smoke 不传 `_transport` 或任何 fake/captured 模式。
- 默认直接访问网关，清除 HTTP_PROXY/HTTPS_PROXY/ALL_PROXY 及小写变体；**不自动沿用下载包时的代理授权**。若本机只能经代理访问，应在发送前把具体代理方式补入审批，不能失败后切代理再发。
- 子进程 stdout/stderr 在内存捕获；只输出白名单结果字段或固定错误摘要，不把 raw traceback、原始 HTTP 响应、auth、完整 URL、`_captured_requests` 发布到终端/日志。文件和终端使用同一安全投影。
- 假密钥回归覆盖缺字段/JSON 错误、启动异常、返回错误与最终文件/终端。测试不调用真实配置读取、不联网。

启动器具体文件/命令在本批交付列出。下节给出它应构造的确切 smoke 子命令，不要求用户手工注入密钥。

## 5. 唯一一次实际调用（批准后）

工作目录固定 `/home/lcq/agent_workload_characterization`，由上述启动器在内存设置环境后启动：

```bash
/home/lcq/agent_workload_characterization/.venvs/mini-swe-agent-2.4.6-env01/bin/python -B \
  -m agent_workload_characterization.runners.smoke \
  --config /home/lcq/agent_workload_characterization/data/catalog/smoke_01_config.yaml \
  --result-dir /home/lcq/agent_workload_characterization/reports/smoke/SMOKE-01-<UTC批次> \
  --execute --i-approve-the-smoke
```

`<UTC批次>` 替换为实际新批次标识；PYTHONPATH 和凭据由启动器设置，以上命令本身不包含秘密。启动器不循环、不自动重试；确认标志只是程序保护，不代替真实用户授权。

执行前向用户简要复述任务/请求数/时限/费用未知及“不执行工具”。已有明确同范围批准则不重复索要批准。查询运行中不改配置、不并行发送第二个请求。

**不执行**返回的 bash 命令；不创建 Agent task loop、不启动 Docker、不导入 evaluator、不发送 django 任务题面。若返回多个 tool calls，只按观测数量记录，不逐个执行。

请求结果不明（连接断开、子进程被杀、启动器意外退出）时，必须按“可能已发送/可能计费”处理；不要因缺报告就重试。真实生产路径没有 fake transport 的请求计数证据，禁止把 retries=0 配置写成网关侧已观测 exactly-one；报告写一次启动及观测依据。

## 6. 结果判定与记录

不能只依据退出码或 `ok` 宣布所有能力通过，分别记录：

| 观测 | 本批结论 |
| --- | --- |
| 已解析 tool call 且 usage 合法可用 | 本次路由/auth/工具协议可用，usage 可记录；非 benchmark 成功 |
| 已解析 tool call 但 usage 缺失 | 工具协议检查可用，usage coverage 不完整；不能声称费用核算完成 |
| plain text + usage | 连通性有证据，工具协议未按期望返回；保留 unexpected_plain_text，不再请求 |
| FormatError/截断 | 响应已收到但协议未完成；保留可用 usage，注明输出上限可能影响完成 |
| 认证/模型名/限流/连接错误 | 按安全错误类型分类；未知原因不推断，失败后停止 |
| watchdog 超时 | 本地查询终止；服务端是否完成、token/费用可能未知，不能填零 |

检查 usage 是合法计数（非 bool、非负整数），不把任意响应字符串当计数发布。原生 cost=0 若来自 ignore_errors，仅列 `source_cost`；本批未核实真实价格时，结论层 `amount=null/cost_status=unknown`。usage 不等于价格。

新增交付物：

- 本批独立配置与必要安全启动器/假配置测试；
- `reports/smoke/SMOKE-01-<UTC批次>/` 的脱敏结果、判定摘要与 manifest（涵盖结果/config/code 证据；不含密钥/用户配置哈希）；
- `docs/model_smoke_delivery.md`：批准范围、实际唯一启动命令（无秘密）、时限、退出码、usage、协议/认证状态、错误与限制；
- 小范围更新 `first_run_approval.md` 与当前进度。历史包保留不改写。

本批不重跑 23 项 SDK 集成或完整历史 trace 分析来充数；仅对新增启动器做离线测试。若更改共享代码则运行相关回归并说明原因。

## 7. 停止与后续

**不管结果成功与否，SMOKE-01 执行一次即结束。** 不自动二次 smoke、不换 endpoint/provider/model、不添加联网权限、不安装依赖或拉镜像。

成功后下一候选是本地单任务 wrapper + 基础资源观测与镜像准备的合并批次；另行生成任务书与审批。失败则交付一次性诊断和建议，重试仍需新的明确授权。

SMOKE-01 不能证明：benchmark 可跑、验证器正确、CPU/Tool 归因有效、性能/成本代表性、长期模型稳定性。P0-07/G0/M1/G1 状态由对应范围的证据评审，不因一次连通性成功自动全通过。
