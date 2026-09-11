# 试点 Harness/模型配置兼容性（P0-07 静态核实，未执行）

状态：**静态核实文档**。未安装任何软件、未导入第三方包、未执行 CLI、未发任何网络/API 请求、
未运行容器或 benchmark。证据索引：[pilot_harness_model_evidence.json](../reports/quality/pilot_harness_model_evidence.json)。

## 1. 用户已定决策（本轮不再询问）

- harness 按 benchmark 选择；SWE-bench 试点核实 **mini-SWE-agent**（不切 OpenHands/OpenClaw）
- 模型已选 **DeepSeek-V4-Flash**（经 `~/.config/opencode/opencode.json` 的 `火山AI网关` provider）
- 每次运行前须说明具体任务并取得明确确认；无金额上限 ≠ 不限资源/自动重试/自动运行

## 2. 模型配置核实（脱敏投影，EV-HM-OPENCODE-001）

配置经内存 JSONC 解析器读取，输出严格白名单；原文件未计算全文哈希（有意为之，非快照）。

| 项 | 值（脱敏后） |
| --- | --- |
| provider 配置键 | `火山AI网关`（唯一 provider；无禁用项） |
| 模型配置键 / 显示名 | `deepseek-v4-flash` / `DeepSeek-V4-Flash`（**唯一匹配，无歧义**） |
| 协议类别 | OpenAI-compatible（依据 npm SDK `@ai-sdk/openai-compatible`；**不保证所有参数兼容**） |
| baseURL | 存在，https，路径含 `/v1`（具体端点不发布） |
| 认证方式 | `provider.options.apiKey` 字段（类型 str；**密钥值未提取、未输出、未持久化**——解析仅在内存中提取白名单键，密钥字段不进入任何输出路径） |
| 声明限制 | maxInputTokens=256000；maxOutputTokens=8192 |
| 能力声明 | 配置内无显式能力字段（declared_capabilities=null） |

**注意**：配置键与显示名词干一致（`deepseek-v4-flash`），但**线上请求的 model ID 是否等于该键、
或需网关路由前缀，未经任何请求验证**——这是 GAP-MODEL-ADAPTER-001，不是已确认映射。
"OpenCode 能用该模型"不构成本 harness 能用该模型的证据。

## 3. Harness 版本核实（EV-HM-MINI-NOTINSTALLED-001 / EV-HM-LOCK-001 / EV-HM-HISTTRAJ-001）

| 事实 | 证据 |
| --- | --- |
| mini-SWE-agent **未安装**于任何已检查环境（系统/用户 site-packages、两个旧工程 venv、项目目录） | 定向查找，无命中 |
| 无本地源码 checkout | 同上 |
| swebench 02e7a74 的 `uv.lock` 锁定 **mini-swe-agent 2.4.6**（PyPI sdist/wheel 哈希在锁文件内，2026-07-23 发布） | EV-HM-LOCK-001 |
| 历史轨迹由 **1.17.3** 产生（版本漂移！） | EV-HM-HISTTRAJ-001 |
| 依赖：litellm + openai（模型经 litellm 路由）、jinja2/pydantic/typer 等 14 项 | uv.lock |
| swebench `requires-python >= 3.10`；本机 3.11 满足 | pyproject/uv.lock |

**入口链（静态，EV-HM-ARGVBUILDER-001）**：
`python -m minisweagent.run.benchmarks.swebench --subset <dataset> --split <split> -w 1 -o <out>
-c <bundled:…/benchmarks/swebench.yaml> -c <custom.yaml> -m <model>`。
bundled config 位于 mini 包内 `builtin_config_dir/benchmarks/swebench.yaml`——**该文件的字段结构
在本地无源码情况下不可核实**（GAP-MINI-SRC-001）。

**版本建议（proposed，不因 latest/锁定字样直接冻结）**：
- **推荐固定 2.4.6**：与 swebench 02e7a74 锁文件一致，argv builder 即针对该生态；理由是工具链一致性
- 备选 1.17.3：与本地历史轨迹行为连续（trajectory_format=mini-swe-agent-1），但与 swebench 锁不一致，
  需说明取舍
- 决定条件：获取源码后核对两版配置 schema 差异，再由用户确认

## 4. 静态兼容性矩阵

状态取值：confirmed_static（源码/配置证据充分）/ proposed（有依据待验证）/ unknown / incompatible。

| 项 | 状态 | 证据与理由 | 后续验证方法 |
| --- | --- | --- | --- |
| 请求协议 | **confirmed_static（mini 侧）/ unknown（litellm 下游）** | mini 2.4.6 默认 LitellmModel：`litellm.completion(model=..., tools=[BASH_TOOL], **model_kwargs)`（F-MODEL-ROUTING-001）；OpenCode 侧 OpenAI-compatible（EV-HM-OPENCODE-001）。下游 litellm 对火山网关的参数兼容仍未知 | litellm 源码/文档或授权连通性测试（OI-LITELLM-DEEPSEEK-001） |
| model ID | **proposed** | 配置键 `deepseek-v4-flash` 唯一无歧义；但线上请求 ID 可能需网关前缀/与显示名不同，未验证 | 一次授权连通性测试观察请求体 model 字段 |
| base URL / auth | **confirmed_static（mini 传递机制）/ unknown（litellm 行为）** | mini 侧：model_kwargs **逐字直通** litellm.completion（F-MODEL-ROUTING-001）——api_base/api_key 若放 model_kwargs 会随轨迹落盘（F-TRAJECTORY-PRIVACY-001，阻塞项）；推荐 env-var 认证（mini-extra config .env → litellm 标准变量）。OpenCode baseURL 已含 `/v1`（EV-HM-OPENCODE-001）；litellm 是否追加路径未知 | OI-LITELLM-DEEPSEEK-001；首次运行前验证 env-var 路线不含密钥落盘 |
| 工具动作格式 | **confirmed_static（2.4.6）** | 2.4.6 用**结构化 tool call**：单一 `bash` function tool，`{"command":...}` 参数（F-ACTION-PROTOCOL-001, actions_toolcall.py）；与 1.17.3 纯文本协议**不同**——历史轨迹不构成 2.4.6 证据。FormatError 模板区分 finish_reason=length 截断 | 无（静态已定）；运行时观察响应格式一致性 |
| 输出与错误 | **confirmed_static（结构）** | 每条消息 extra 含完整 litellm response dump（usage/finish_reason/tool_calls，F-TRAJECTORY-PRIVACY-001）；FormatError 路径也持久化 response；连续 3 次格式错误→RepeatedFormatError 退出 | 拒绝响应/网关错误形态需运行观察 |
| 参数与限制 | **confirmed_static** | bundled swebench.yaml：step_limit=250、cost_limit=3.0 USD、wall_time 无限、连续格式错误 3 次（F-BUNDLED-CONFIG-001）；per-command 60s；重试 tenacity 10 次/4-60s 退避，认证类错误不重试（F-RETRY-001）；模型侧声明 256k in/8192 out（EV-HM-OPENCODE-001） | 速率限制为网关侧行为，运行观察 |
| 成本处理 | **confirmed_static（双侧）** | mini 2.4.6：`litellm.completion_cost`；cost<=0 或异常→默认 **RuntimeError 崩溃**（critical 日志仅在此非忽略分支输出）。**`ignore_errors` 分支静默返回 0.0，无 critical 日志、无任何标记**——不能依赖该日志发现计费缺失；且此时 agent cost_limit 与全局限额对未计价调用**永不触发**（累计恒 0.0），限额保护失效（F-COST-001）。正规路径 `litellm_model_registry` JSON 注册真实价格（限额随之有效）。历史 0.0 原因仍不可断定。swebench run_api 侧 KeyError 另行记录（EV-HM-RUNAPI-COST-001） | **OI-PRICE-001 运行前必须二选一**：registry 注册真实价格（限额有效） 或 ignore_errors+**独立"成本未知"标记**（不能依赖 mini 日志；可用轨迹内逐调用 usage 独立核算） |
| 轨迹产物 | **confirmed_static（2.4.6）** | `<instance>.traj.json`：messages（每条 extra 含完整 response dump + timestamp）+ info（model_stats{instance_cost, api_calls}、config{agent+model 含 model_kwargs}、mini_version、exit_status、submission）；trajectory_format=**mini-swe-agent-1.1**；另有 preds.json（model_patch）+ minisweagent.log（F-TRAJECTORY-PRIVACY-001）。**无 per-tool 进程/CPU 信息** | **首次运行前阻塞**：确认认证走 env-var（model_kwargs 不含密钥）；P1 进程级观测需 proxy/wrapper 评估 |

> **归档读取脱敏规程（本轮确立）**：历史轨迹成员的 `info.config` 含 `api_base`/`api_key`。
> 首次读取时输出截断恰好挡住了密钥显示，但**截断不是可靠脱敏机制**——不能据此证明此前输出从未
> 泄露。今后所有归档/含密钥配置读取必须在输出前做**白名单键过滤**（仅提取 role/content/timestamp/
> exit_status/model_stats 键名等白名单字段），禁止依赖截断或事后检查。本文件登记的轨迹信息
> 均来自白名单字段。 |
| 执行环境 | **confirmed_static（字段适配 + digest 要求登记）** | **镜像字段适配**：mini 读 `instance.image_name / docker_image`，两者皆无则按 instance_id **推导** `swebench/sweb.eval.x86_64.<id>:latest`；**不读 evaluator 所用的 `image` 字段**（make_test_spec 用 `instance["image"]`）——两个工具消费**不同数据集列**。试点记录是否含 image_name/docker_image、其值是否等于 evaluator image 值**未核实**；不能概括为"自动使用 evaluator 同一镜像"（F-ENVIRONMENT-001）。即便名字相同，双方均为 `:latest`——**digest 一致性须在首次运行前逐字段核实/固定**。docker 机制已确认：`--rm`、cwd=/testbed、BASH_ENV | 核实数据集行的 image_name/docker_image 列；digest 固定属运行授权（OI-DATASET-NS-001 扩展） |

## 5. 未来 Agent 输入白名单（设计，未运行；配置条件性隔离）

**默认路径**：`agent.run(task)` 仅传 `instance["problem_statement"]`（渲染进 instance_template）
——patch/test_patch/F2P/P2P 不经默认链进入 Agent。

**配置条件性例外**：可选 `run.env_startup_command` 若启用，会以 `Template(...).render(**instance)`
用**整个 instance dict**（含参考答案字段，若在数据集行中）渲染——隔离是**配置条件性**的，
不是全链路无条件的。bundled swebench.yaml **未设置**该项；试点配置必须保持不设。

允许进入 Agent 输入的字段（投影，本轮未创建）：`instance_id`、`problem_statement`、
repo/`base_commit`（checkout 用）、必要工作目录约定。

必须排除：`patch`（gold）、`test_patch`、FAIL_TO_PASS/PASS_TO_PASS、hints、任何测试答案字段；
record.json 整体不可作为命令输入；不得设置 env_startup_command。

## 6. telemetry proxy 复用评估（设计项，未开发）

VW 试点中 proxy 记录逐请求 usage/TTFT/latency。mini 场景下：若模型请求可经本地 proxy 转发到
`火山AI网关`，可复用同一记账/观测链；**前提**是 mini/litellm 允许自定义 api_base（轨迹 config 中
存在 api_base 字段，1.17.3 佐证字段存在；2.4.6 待核对）。若需 proxy 适配补丁，列为 P1 实现项，
本任务不启动。不做强行复用：先判断 mini 原生 model_stats 能否满足试点最小记账需求
（api_calls + instance_cost 形态已见；token 级 usage 待源码确认）。

## 7. 未验证项汇总与最小后续工作（2.4.6 静态阅读后更新）

| 未验证项 | 归属 |
| --- | --- |
| litellm 对火山网关的路由（前缀/base_url 键/auth 变量名、/v1 行为） | OI-LITELLM-DEEPSEEK-001：需 litellm 源码/文档或授权连通性测试 |
| deepseek-v4-flash 价格：registry JSON 或 ignore_errors + 独立记账 | OI-PRICE-001：**运行前必须二选一**（否则首查 RuntimeError） |
| model_kwargs 含密钥必落轨迹（F-TRAJECTORY-PRIVACY-001） | 首次运行前阻塞项：走 env-var 认证并验证 |
| princeton-nlp vs SWE-bench 数据集 id 等价性 + revision 固定 | OI-DATASET-NS-001 |
| evaluator 镜像 digest、本机 Docker/架构 | 沿袭，P1-00 预检 |
| Agent 输入投影生成器（仅需 problem_statement） | P1 实现项 |

**需要的授权（明确、有限）**：
1. （可选）litellm 源码/文档查阅——解决 OI-LITELLM-DEEPSEEK-001 的路由字段；或
2. （可选，另行确认）一次模型连通性测试——验证前缀/base_url/auth，极小额费用
3. 沿袭：P1-00 预检、首次真实运行（逐次确认）

## 8. 非目标

本文件不是运行授权；`execution_authorized=false` 不变。不安装、不下载、不调用模型、不运行
benchmark/容器/验证器；不修改 references、旧工程、用户配置、原始任务记录；不重跑 macro 掩盖缺口。
